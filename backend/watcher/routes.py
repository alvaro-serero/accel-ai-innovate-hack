"""Watcher routes and scheduler hook. Owner: Leo.

GET  /api/data/stats    live numbers for the data layer page
GET  /api/data/feed     latest opened / edited / closed / reposted postings
POST /api/watcher/poll  run one poll now (demo button); waits and returns the counts
"""
import logging

from fastapi import APIRouter, HTTPException, Query

from backend.app.db import fetch_all, fetch_one
from backend.app.schemas import DataStats, FeedItem, PollResult
from backend.watcher.ghost import GHOST_THRESHOLD
from backend.watcher.poller import poll_all

log = logging.getLogger("watcher.routes")

router = APIRouter(prefix="/api", tags=["watcher"])


def register_jobs(scheduler) -> None:
    """Called by main.py when ENABLE_SCHEDULER=true. Only one running instance should do this."""
    scheduler.add_job(
        poll_all, "interval", minutes=10, id="poll_all",
        max_instances=1, coalesce=True, replace_existing=True,
    )


# Baseline 'opened' events come from a company's very first poll: they are not new postings.
_NOT_BASELINE = "coalesce((e.detail->>'baseline')::boolean, false) = false"

_STATS_SQL = f"""
select
  (select count(*) from companies) as companies,
  (select count(*) from jobs where closed_at is null) as jobs_open,
  (select count(*) from jobs where closed_at is null and is_internship) as internships_open,
  (select count(*) from jobs where closed_at is null and is_internship
                                and ghost_score >= %(threshold)s) as ghosts_open,
  (select count(*) from job_events e where e.kind in ('opened', 'reposted')
                                       and e.at >= now() - interval '24 hours'
                                       and {_NOT_BASELINE}) as new_last_24h,
  (select max(last_polled_at) from companies) as last_poll_at
"""

_FEED_SQL = f"""
select e.at, e.kind, c.name as company, j.title, j.url
from job_events e
join jobs j on j.id = e.job_id
join companies c on c.id = j.company_id
where (%(include_baseline)s or {_NOT_BASELINE})
  and (not %(internships_only)s or j.is_internship)
order by e.at desc, e.id desc
limit %(limit)s
"""


def _db_unavailable(exc: Exception) -> HTTPException:
    log.exception("database query failed: %s", exc)
    return HTTPException(status_code=503, detail="database unavailable")


@router.get("/data/stats", response_model=DataStats)
def data_stats():
    try:
        row = fetch_one(_STATS_SQL, {"threshold": GHOST_THRESHOLD})
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc
    internships = row["internships_open"]
    return DataStats(
        companies=row["companies"],
        jobs_open=row["jobs_open"],
        internships_open=internships,
        ghost_pct=round(100 * row["ghosts_open"] / internships, 1) if internships else 0,
        new_last_24h=row["new_last_24h"],
        last_poll_at=row["last_poll_at"],
    )


@router.get("/data/feed", response_model=list[FeedItem])
def data_feed(
    limit: int = Query(50, ge=1, le=500),
    internships_only: bool = False,
    include_baseline: bool = Query(False, description="also show postings found by a company's first poll"),
):
    try:
        rows = fetch_all(
            _FEED_SQL,
            {"limit": limit, "internships_only": internships_only, "include_baseline": include_baseline},
        )
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable(exc) from exc
    return [FeedItem(**r) for r in rows]


@router.post("/watcher/poll", response_model=PollResult)
async def trigger_poll():
    try:
        return await poll_all()
    except Exception as exc:  # noqa: BLE001
        log.exception("poll failed: %s", exc)
        raise HTTPException(status_code=503, detail="poll failed (database unavailable?)") from exc
