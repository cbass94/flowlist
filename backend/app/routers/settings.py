"""
Settings router — user profile and scheduling preferences.

GET   /api/settings/              → current user's settings
PATCH /api/settings/              → update settings
GET   /api/settings/calendars     → list calendars from Google (for calendar ID picker)
POST  /api/settings/reschedule    → trigger a full reschedule immediately
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.scheduling_run_log import ScheduleTrigger
from app.models.user import User
from app.repositories import user_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.settings import CalendarItem, UpdateSettings, UserSettings
from app.services import calendar_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _user_to_settings(user: User) -> UserSettings:
    return UserSettings(
        timezone=user.timezone,
        display_name=user.display_name,
        personal_account_connected=user.personal_account_connected,
        work_start_hour=user.work_start_hour,
        work_end_hour=user.work_end_hour,
        hard_start_hour=user.hard_start_hour,
        hard_end_hour=user.hard_end_hour,
        buffer_minutes=user.buffer_minutes,
        work_calendar_id=user.work_calendar_id,
        personal_calendar_id=user.personal_calendar_id,
    )


@router.get("/", response_model=ApiResponse[UserSettings], summary="Get user settings")
async def get_settings(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[UserSettings]:
    return ok(_user_to_settings(current_user))


@router.patch("/", response_model=ApiResponse[UserSettings], summary="Update user settings")
async def update_settings(
    body: UpdateSettings,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserSettings]:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return ok(_user_to_settings(current_user))

    user = await user_repo.update_settings(db, current_user.id, **updates)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return ok(_user_to_settings(user))


@router.get(
    "/calendars",
    response_model=ApiResponse[list[CalendarItem]],
    summary="List Google Calendars",
)
async def list_calendars(
    account: str = "work",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CalendarItem]]:
    """Return calendars accessible by the work or personal Google account."""
    if account not in ("work", "personal"):
        raise HTTPException(status_code=400, detail="account must be 'work' or 'personal'")
    if account == "personal" and not current_user.personal_account_connected:
        raise HTTPException(status_code=400, detail="Personal account not connected")

    try:
        raw = await calendar_service.list_user_calendars(current_user, db, account=account)  # type: ignore[arg-type]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Calendar error: {exc}") from exc

    items = [CalendarItem(**c) for c in raw]
    return ok(items)


@router.post(
    "/reschedule",
    response_model=ApiResponse[None],
    summary="Trigger full reschedule",
)
async def trigger_reschedule(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    """Immediately enqueue a full reschedule of all future blocks."""
    from app.routers.tasks import _enqueue_reschedule
    await _enqueue_reschedule(current_user.id, ScheduleTrigger.manual)
    return ok(None)
