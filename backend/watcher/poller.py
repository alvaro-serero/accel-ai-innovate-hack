"""Polls every company's ATS board and records changes. Owner: Leo.

Per company: new posting -> insert jobs + job_events 'opened'; content_hash changed -> 'edited';
open in DB but gone from board -> closed_at + 'closed'; same title as a recently closed one -> 'reposted'.
"""
from backend.app.schemas import PollResult


async def poll_all() -> PollResult:
    # TODO(leo): load companies, fetch with ats.py (httpx.AsyncClient, 20 concurrent), upsert, classify, ghost score
    return PollResult(polled=0, opened=0, edited=0, closed=0)
