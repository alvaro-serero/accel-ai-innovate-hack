"""Events radar pipeline. Owner: Taleb.

refresh_events(user_id): search.py (Keenable queries per target company x city)
-> extract.py (fetch page, trafilatura, Haiku -> event JSON)
-> verify.py (future date, same city/region, company named in page text, dedupe)
-> rank -> upsert events + event_matches.
Alvaro's run.py calls this, so keep the signature.
"""
from backend.app.schemas import EventsRefreshResult


async def refresh_events(user_id: int) -> EventsRefreshResult:
    # TODO(taleb)
    return EventsRefreshResult(found=0, verified=0, kept=0)
