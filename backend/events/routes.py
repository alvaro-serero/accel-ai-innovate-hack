"""Events radar routes. Owner: Taleb.
STUBS: replace fixtures with event_matches joined to events.
"""
from fastapi import APIRouter

from backend.app import fixtures
from backend.app.schemas import EventMatch, EventsRefreshResult
from backend.events.radar import refresh_events

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/users/{user_id}/events", response_model=list[EventMatch])
def list_events(user_id: int):
    return fixtures.EVENTS


@router.post("/users/{user_id}/events/refresh", response_model=EventsRefreshResult)
async def refresh(user_id: int):
    return await refresh_events(user_id)
