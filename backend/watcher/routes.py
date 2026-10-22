"""Watcher routes and scheduler hook. Owner: Leo.
STUBS: replace fixtures with real queries on jobs / job_events / companies.
"""
from fastapi import APIRouter

from backend.app import fixtures
from backend.app.schemas import DataStats, FeedItem, PollResult
from backend.watcher.poller import poll_all

router = APIRouter(prefix="/api", tags=["watcher"])


def register_jobs(scheduler) -> None:
    """Called by main.py when ENABLE_SCHEDULER=true. Only one running instance should do this."""
    scheduler.add_job(poll_all, "interval", minutes=10, id="poll_all", max_instances=1, coalesce=True)


@router.get("/data/stats", response_model=DataStats)
def data_stats():
    return fixtures.DATA_STATS


@router.get("/data/feed", response_model=list[FeedItem])
def data_feed(limit: int = 50):
    return fixtures.FEED[:limit]


@router.post("/watcher/poll", response_model=PollResult)
async def trigger_poll():
    return await poll_all()
