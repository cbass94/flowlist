# FlowList — Calendar router
# Exposes read-only calendar data to the frontend (busy slots, upcoming events).
# The app never exposes raw Google tokens to the client.
# TODO: implement endpoints
from fastapi import APIRouter

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/events")
async def get_events(start: str, end: str):
    """Return calendar events in a date range (both work + personal calendars)."""
    raise NotImplementedError


@router.get("/free-slots")
async def get_free_slots(date: str):
    """Return free slots for a given date respecting scheduling rules."""
    raise NotImplementedError
