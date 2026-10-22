"""Events radar routes. Owner: Taleb."""
from fastapi import APIRouter, HTTPException

from backend.app.schemas import EventMatch, EventsRefreshResult
from backend.events.radar import refresh_events, user_event_matches

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/users/{user_id}/events", response_model=list[EventMatch])
def list_events(user_id: int):
    return user_event_matches(user_id)


@router.post("/users/{user_id}/events/refresh", response_model=EventsRefreshResult)
async def refresh(user_id: int):
    try:
        return await refresh_events(user_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
