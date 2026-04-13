# FlowList — Calendar router
# Exposes read-only calendar data to the frontend.
# The app never exposes raw Google tokens to the client.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.envelope import ApiResponse, ok
from app.services import calendar_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get(
    "/event/{event_id}",
    response_model=ApiResponse[dict],
    summary="Fetch a Google Calendar event by ID",
)
async def get_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    Look up a Google Calendar event by its ID.
    Searches the user's work and personal calendars via the work account.
    Returns event details (id, summary, start, end) or 404 if not found.
    """
    if not current_user.work_access_token:
        raise HTTPException(status_code=400, detail="Work Google account not connected")

    try:
        event = await calendar_service.get_event_by_id(current_user, db, event_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Calendar error: {exc}") from exc

    if event is None:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    return ok(event)


@router.get("/events")
async def get_events(start: str, end: str):
    """Return calendar events in a date range (both work + personal calendars)."""
    raise NotImplementedError


@router.get("/free-slots")
async def get_free_slots(date: str):
    """Return free slots for a given date respecting scheduling rules."""
    raise NotImplementedError
