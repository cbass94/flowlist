"""
Auth router — Google OAuth 2.0 endpoints.

Flow summary:
  PRIMARY (work account login):
    1. GET /api/auth/login/work          → redirect to Google consent
    2. GET /api/auth/callback/work       → exchange code, upsert user, set cookie, redirect to /
                                           New users must have a valid invite (or be the first user).

  SECONDARY (personal account connection, requires existing session):
    3. GET /api/auth/connect/personal    → redirect to Google consent (personal OAuth app)
    4. GET /api/auth/callback/personal   → attach tokens to user, redirect to /settings

  Other:
    GET  /api/auth/status   → { authenticated, user } — never raises 401
    GET  /api/auth/me       → current user info (or 401)
    GET  /api/auth/logout   → clear session cookie, redirect to /
    POST /api/auth/logout   → clear session cookie (for API callers)

Rate limits (per IP):
  /api/auth/login/work      — 10 req/min
  /api/auth/connect/personal — 10 req/min
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories import user_repo
from app.repositories import invite_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.user import UserRead
from app.services import crypto, oauth as oauth_service
from app.services.auth_service import (
    clear_session_cookie,
    create_session_cookie,
    get_current_user,
    get_optional_user,
)
from app.services.rate_limit import check_rate_limit, get_client_ip
from app.models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_POST_LOGIN_REDIRECT = "/"
_POST_CONNECT_REDIRECT = "/settings"
_AUTH_RATE_LIMIT = 10
_AUTH_RATE_WINDOW = 60


def _no_invite_html(email: str) -> str:
    safe_email = email.replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FlowList — Invitation Required</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f8fafc;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    margin: 0;
  }}
  .card {{
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 40px;
    max-width: 420px;
    width: 90%;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  .icon {{ font-size: 3rem; margin-bottom: 16px; }}
  h1 {{ font-size: 1.4rem; color: #1e293b; margin: 0 0 12px; }}
  p {{ color: #64748b; font-size: 0.9rem; line-height: 1.6; margin: 0 0 12px; }}
  .email {{ font-weight: 600; color: #1e293b; word-break: break-all; }}
  .back {{
    display: inline-block;
    margin-top: 8px;
    color: #3b82f6;
    text-decoration: none;
    font-size: 0.875rem;
  }}
  .back:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">🔒</div>
  <h1>Invitation Required</h1>
  <p>The Google account <span class="email">{safe_email}</span> doesn't have an
  active invitation to access FlowList.</p>
  <p>Contact the FlowList admin to request an invite link, then try signing in again.</p>
  <a class="back" href="/api/auth/login/work">← Try a different account</a>
</div>
</body>
</html>"""


# ── Primary: work account login ───────────────────────────────────────────────


@router.get("/login/work", summary="Redirect to Google OAuth (work account)")
async def login_work(request: Request) -> RedirectResponse:
    ip = get_client_ip(request)
    await check_rate_limit(
        f"ratelimit:auth:login:{ip}",
        limit=_AUTH_RATE_LIMIT,
        window_secs=_AUTH_RATE_WINDOW,
    )
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

    # ── Invite gate: new users need a valid invite (except the very first user) ──
    existing = await user_repo.get_by_work_google_id(db, token_data.google_id)
    pending_invite = None
    if existing is None:
        all_users = await user_repo.get_all(db)
        if len(all_users) > 0:
            # Not the first user — require a valid invite
            pending_invite = await invite_repo.get_valid_by_email(db, token_data.email)
            if pending_invite is None:
                log.warning(
                    "Blocked uninvited registration attempt for email=%s", token_data.email
                )
                return HTMLResponse(_no_invite_html(token_data.email), status_code=403)

    user = await user_repo.upsert_work_account(
        db,
        google_id=token_data.google_id,
        email=token_data.email,
        display_name=token_data.display_name or token_data.email,
        access_token=crypto.encrypt(token_data.access_token),
        refresh_token=crypto.encrypt(token_data.refresh_token) if token_data.refresh_token else "",
        token_expiry=token_data.expires_at,
    )

    if pending_invite is not None:
        await invite_repo.accept(db, pending_invite)
        log.info("Invite accepted: email=%s user_id=%d", token_data.email, user.id)

    redirect = RedirectResponse(_POST_LOGIN_REDIRECT, status_code=302)
    create_session_cookie(redirect, user.id)
    return redirect


# ── Secondary: personal account connection ────────────────────────────────────


@router.get("/connect/personal", summary="Connect personal Google account")
async def connect_personal(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> RedirectResponse:
    ip = get_client_ip(request)
    await check_rate_limit(
        f"ratelimit:auth:connect:{ip}",
        limit=_AUTH_RATE_LIMIT,
        window_secs=_AUTH_RATE_WINDOW,
    )
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


@router.get("/logout", summary="Log out (GET — for navigation links)")
async def logout_get() -> RedirectResponse:
    """Clear session cookie and redirect to /. Used by the Settings page sign-out link."""
    resp = RedirectResponse("/", status_code=302)
    clear_session_cookie(resp)
    return resp


@router.post("/logout", response_model=ApiResponse[None], summary="Log out (POST — for API callers)")
async def logout_post(response: Response) -> ApiResponse[None]:
    clear_session_cookie(response)
    return ok(None)
