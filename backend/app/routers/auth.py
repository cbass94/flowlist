"""
Auth router — Google OAuth 2.0 endpoints.

Flow summary:
  PRIMARY (work account login):
    1. GET /api/auth/login/work          → redirect to Google consent
    2. GET /api/auth/callback/work       → exchange code, upsert user, set cookie, redirect to /

  SECONDARY (personal account connection, requires existing session):
    3. GET /api/auth/connect/personal    → redirect to Google consent (personal OAuth app)
    4. GET /api/auth/callback/personal   → attach tokens to user, redirect to /settings

  Other:
    GET  /api/auth/status   → { authenticated, user } — never raises 401
    GET  /api/auth/me       → current user info (or 401)
    POST /api/auth/logout   → clear session cookie
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories import user_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.user import UserRead
from app.services import crypto, oauth as oauth_service
from app.services.auth_service import (
    clear_session_cookie,
    create_session_cookie,
    get_current_user,
    get_optional_user,
)
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_POST_LOGIN_REDIRECT = "/"
_POST_CONNECT_REDIRECT = "/settings"


# ── Primary: work account login ───────────────────────────────────────────────


@router.get("/login/work", summary="Redirect to Google OAuth (work account)")
async def login_work() -> RedirectResponse:
    url, _state = await oauth_service.get_authorization_url("work")
    return RedirectResponse(url, status_code=302)


@router.get("/callback/work", summary="Handle Google OAuth callback (work account)")
async def callback_work(
    code: str,
    state: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        stored = await oauth_service.verify_and_consume_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if stored != "work":
        raise HTTPException(status_code=400, detail="Unexpected OAuth state value")

    try:
        token_data = await oauth_service.exchange_code("work", code)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Google token exchange failed: {exc}")

    if not token_data.google_id:
        raise HTTPException(status_code=502, detail="Google did not return a user ID")

    user = await user_repo.upsert_work_account(
        db,
        google_id=token_data.google_id,
        email=token_data.email,
        display_name=token_data.display_name or token_data.email,
        access_token=crypto.encrypt(token_data.access_token),
        refresh_token=crypto.encrypt(token_data.refresh_token) if token_data.refresh_token else "",
        token_expiry=token_data.expires_at,
    )

    redirect = RedirectResponse(_POST_LOGIN_REDIRECT, status_code=302)
    create_session_cookie(redirect, user.id)
    return redirect


# ── Secondary: personal account connection ────────────────────────────────────


@router.get("/connect/personal", summary="Connect personal Google account")
async def connect_personal(
    current_user: User = Depends(get_current_user),
) -> RedirectResponse:
    url, _state = await oauth_service.get_authorization_url(
        "personal", user_id=current_user.id
    )
    return RedirectResponse(url, status_code=302)


@router.get("/callback/personal", summary="Handle Google OAuth callback (personal account)")
async def callback_personal(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        stored = await oauth_service.verify_and_consume_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not stored.startswith("personal:"):
        raise HTTPException(status_code=400, detail="Unexpected OAuth state value")

    try:
        user_id = int(stored.split(":")[1])
    except (IndexError, ValueError):
        raise HTTPException(status_code=400, detail="Malformed OAuth state payload")

    try:
        token_data = await oauth_service.exchange_code("personal", code)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Google token exchange failed: {exc}")

    if not token_data.google_id:
        raise HTTPException(status_code=502, detail="Google did not return a user ID")

    user = await user_repo.connect_personal_account(
        db,
        user_id=user_id,
        google_id=token_data.google_id,
        access_token=crypto.encrypt(token_data.access_token),
        refresh_token=crypto.encrypt(token_data.refresh_token) if token_data.refresh_token else "",
        token_expiry=token_data.expires_at,
    )

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return RedirectResponse(_POST_CONNECT_REDIRECT, status_code=302)


# ── Session ───────────────────────────────────────────────────────────────────


@router.get("/status", response_model=ApiResponse[dict], summary="Auth status")
async def auth_status(
    current_user: User | None = Depends(get_optional_user),
) -> ApiResponse[dict]:
    """Return auth state without raising 401. Used on initial page load."""
    if current_user is None:
        return ok({"authenticated": False, "user": None})
    return ok({
        "authenticated": True,
        "user": UserRead.model_validate(current_user).model_dump(),
    })


@router.get("/me", response_model=ApiResponse[UserRead], summary="Get current user")
async def get_me(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[UserRead]:
    return ok(UserRead.model_validate(current_user))


@router.post("/logout", response_model=ApiResponse[None], summary="Log out")
async def logout(response: Response) -> ApiResponse[None]:
    clear_session_cookie(response)
    return ok(None)
