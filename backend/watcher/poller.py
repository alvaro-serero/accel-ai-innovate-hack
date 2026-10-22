"""Polls every company's ATS board and records changes. Owner: Leo.

Per company, in one DB transaction (a failing board changes nothing and never stops the others):
  - open in DB but gone from the board -> closed_at + event 'closed'
  - new posting -> insert into jobs + event 'opened'
      (same company and normalised title as a posting closed in the last 60 days -> 'reposted')
  - known posting closed earlier and back on the board -> reopen + 'opened' {"reopened": true}
  - content_hash (title + location + description) changed -> update + 'edited' {"changed": [...]}
  - always: last_seen_at, source_updated_at, ghost score; companies.last_polled_at
The first successful poll of a company is its baseline: its 'opened' events carry
{"baseline": true} so the feed and the "new" stats only count real openings.

Run once from the CLI (or every N minutes):
    python -m backend.watcher.poller
    python -m backend.watcher.poller --every 10
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from backend.app.db import fetch_all, pool
from backend.app.schemas import PollResult
from backend.watcher.ats import fetch_board, make_client
from backend.watcher.classify import classify_posting, content_hash, normalise_title
from backend.watcher.ghost import ghost_score

log = logging.getLogger("watcher.poller")

HTTP_CONCURRENCY = 20
DB_CONCURRENCY = 4  # the shared pool has 10 connections; leave room for API requests
REPOST_WINDOW = timedelta(days=60)
EDIT_FIELDS = (
    "title", "location", "city", "remote", "employment_type", "url",
    "description", "source_updated_at", "is_internship",
)

_running = False

_SELECT_JOBS = """
select id, ats_job_id, title, location, city, remote, employment_type, url, description,
       is_internship, published_at, source_updated_at, first_seen_at, closed_at,
       content_hash, repost_count
from jobs where company_id = %s
"""

_INSERT_JOB = """
insert into jobs (company_id, ats_job_id, title, location, city, remote, employment_type,
                  is_internship, url, description, published_at, source_updated_at,
                  first_seen_at, last_seen_at, content_hash, repost_count, ghost_score, ghost_reasons)
values (%(company_id)s, %(ats_job_id)s, %(title)s, %(location)s, %(city)s, %(remote)s,
        %(employment_type)s, %(is_internship)s, %(url)s, %(description)s, %(published_at)s,
        %(source_updated_at)s, %(now)s, %(now)s, %(content_hash)s, %(repost_count)s,
        %(ghost_score)s, %(ghost_reasons)s)
on conflict (company_id, ats_job_id) do nothing
returning id
"""

# Used for edits and reopens: rewrite the content columns.
_UPDATE_CONTENT = """
update jobs set title = %(title)s, location = %(location)s, city = %(city)s, remote = %(remote)s,
       employment_type = %(employment_type)s, is_internship = %(is_internship)s, url = %(url)s,
       description = %(description)s, source_updated_at = %(source_updated_at)s,
       published_at = coalesce(published_at, %(published_at)s),
       content_hash = %(content_hash)s, last_seen_at = %(now)s, closed_at = null,
       ghost_score = %(ghost_score)s, ghost_reasons = %(ghost_reasons)s
where id = %(id)s
"""

# Unchanged postings: no event, but keep freshness and the ghost score current.
_TOUCH = """
update jobs set last_seen_at = %(now)s,
       source_updated_at = coalesce(%(source_updated_at)s, source_updated_at),
       published_at = coalesce(published_at, %(published_at)s),
       ghost_score = %(ghost_score)s, ghost_reasons = %(ghost_reasons)s
where id = %(id)s
"""

_INSERT_EVENT = "insert into job_events (job_id, kind, at, detail) values (%s, %s, %s, %s)"


def _find_repost(rows: list[dict], title: str, now: datetime) -> dict | None:
    """Most recently closed posting of the same company with the same normalised title."""
    key = normalise_title(title)
    if not key:
        return None
    candidates = [
        r for r in rows
        if r["closed_at"] is not None and r["closed_at"] >= now - REPOST_WINDOW
        and normalise_title(r["title"]) == key
    ]
    return max(candidates, key=lambda r: (r["closed_at"], r["id"]), default=None)


def process_board(company: dict, postings: list[dict], now: datetime) -> dict:
    """Apply one board snapshot to the DB in a single transaction. Returns event counts."""
    counts = {"opened": 0, "reposted": 0, "edited": 0, "closed": 0}
    baseline = company.get("last_polled_at") is None

    seen: dict[str, dict] = {}
    for p in postings:
        if p.get("ats_job_id") and p.get("title"):
            seen.setdefault(p["ats_job_id"], p)

    events: list[tuple] = []
    touches: list[dict] = []

    with pool().connection() as conn:  # commits on success, rolls back on any exception
        rows = conn.execute(_SELECT_JOBS, (company["id"],)).fetchall()
        by_ats_id = {r["ats_job_id"]: r for r in rows}

        # 1. Closes first, so a posting closed and re-created in the same poll counts as a repost.
        open_missing = [r for r in rows if r["closed_at"] is None and r["ats_job_id"] not in seen]
        if open_missing and not seen:
            log.warning(
                "%s (%s/%s) returned 0 postings but has %d open: not closing anything",
                company["name"], company["ats"], company["slug"], len(open_missing),
            )
        elif open_missing:
            for r in open_missing:
                conn.execute("update jobs set closed_at = %s where id = %s", (now, r["id"]))
                r["closed_at"] = now
                open_days = int((now - r["first_seen_at"]).total_seconds() // 86400) if r["first_seen_at"] else None
                events.append((r["id"], "closed", Jsonb({"open_days": open_days})))
                counts["closed"] += 1

        # 2. Every posting on the board.
        for ats_job_id, p in seen.items():
            fields = {
                **p,
                **classify_posting(p),
                "content_hash": content_hash(p["title"], p["location"], p["description"]),
                "now": now,
            }
            row = by_ats_id.get(ats_job_id)

            if row is None:
                prev = None if baseline else _find_repost(rows, p["title"], now)
                repost_count = (prev["repost_count"] or 0) + 1 if prev else 0
                score, reasons = ghost_score(
                    title=p["title"], published_at=p["published_at"], first_seen_at=now,
                    source_updated_at=p["source_updated_at"], repost_count=repost_count, now=now,
                )
                inserted = conn.execute(
                    _INSERT_JOB,
                    {**fields, "company_id": company["id"], "repost_count": repost_count,
                     "ghost_score": score, "ghost_reasons": reasons},
                ).fetchone()
                if inserted is None:  # another poller inserted it a moment ago
                    continue
                if prev:
                    events.append((inserted["id"], "reposted",
                                   Jsonb({"previous_job_id": prev["id"], "repost_count": repost_count})))
                    counts["reposted"] += 1
                else:
                    events.append((inserted["id"], "opened", Jsonb({"baseline": True} if baseline else {})))
                    counts["opened"] += 1
                continue

            score, reasons = ghost_score(
                title=p["title"], published_at=row["published_at"] or p["published_at"],
                first_seen_at=row["first_seen_at"],
                source_updated_at=p["source_updated_at"] or row["source_updated_at"],
                repost_count=row["repost_count"], now=now,
            )
            params = {**fields, "id": row["id"], "ghost_score": score, "ghost_reasons": reasons}

            if row["closed_at"] is not None:
                conn.execute(_UPDATE_CONTENT, params)
                events.append((row["id"], "opened", Jsonb({"reopened": True})))
                counts["opened"] += 1
            elif row["content_hash"] != fields["content_hash"]:
                changed = [f for f in EDIT_FIELDS if row[f] != fields[f]]
                conn.execute(_UPDATE_CONTENT, params)
                events.append((row["id"], "edited", Jsonb({"changed": changed})))
                counts["edited"] += 1
            else:
                touches.append(params)

        with conn.cursor() as cur:
            if touches:
                cur.executemany(_TOUCH, touches)
            if events:
                cur.executemany(_INSERT_EVENT, [(job_id, kind, now, detail) for job_id, kind, detail in events])
        conn.execute("update companies set last_polled_at = %s where id = %s", (now, company["id"]))

    return counts


async def _poll(company_ids: list[int] | None = None) -> PollResult:
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    sql = "select id, name, ats, slug, last_polled_at from companies"
    params = None
    if company_ids:
        sql += " where id = any(%s)"
        params = (company_ids,)
    companies = await asyncio.to_thread(fetch_all, sql + " order by id", params)
    if not companies:
        log.info("no companies to poll")
        return PollResult()

    http_sem = asyncio.Semaphore(HTTP_CONCURRENCY)
    db_sem = asyncio.Semaphore(DB_CONCURRENCY)

    async with make_client(HTTP_CONCURRENCY) as client:

        async def one(company: dict) -> dict | None:
            try:
                async with http_sem:
                    postings = await fetch_board(client, company["ats"], company["slug"])
                async with db_sem:
                    return await asyncio.to_thread(process_board, company, postings, now)
            except Exception as exc:  # noqa: BLE001 - one broken board must not stop the poll
                log.warning("poll failed for %s (%s/%s): %s", company["name"], company["ats"], company["slug"], exc)
                return None

        outcomes = await asyncio.gather(*(one(c) for c in companies))

    ok = [o for o in outcomes if o is not None]
    result = PollResult(
        polled=len(ok),
        opened=sum(o["opened"] + o["reposted"] for o in ok),
        edited=sum(o["edited"] for o in ok),
        closed=sum(o["closed"] for o in ok),
    )
    log.info(
        "poll done in %.1fs: %d/%d boards ok, opened %d (reposted %d), edited %d, closed %d",
        time.monotonic() - started, result.polled, len(companies), result.opened,
        sum(o["reposted"] for o in ok), result.edited, result.closed,
    )
    return result


async def poll_all(company_ids: list[int] | None = None) -> PollResult:
    """Poll every board once. A call while another poll is running returns all zeros."""
    global _running
    if _running:
        log.info("poll already running, skipping")
        return PollResult()
    _running = True
    try:
        return await _poll(company_ids)
    finally:
        _running = False


async def _main(every: float | None) -> None:
    while True:
        result = await poll_all()
        print(result.model_dump_json())
        if not every:
            return
        await asyncio.sleep(every * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poll every company board once (or in a loop).")
    parser.add_argument("--every", type=float, help="repeat every N minutes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_main(args.every))
