"""
Session management and FastAPI auth dependency.

Sessions are stateless signed cookies (itsdangerous URLSafeTimedSerializer).
The cookie contains only the user_id; the signature proves it hasn't been tampered.
No server-side session state is needed — one less moving part.

Cookie attributes:
  HttpOnly: true   — not accessible to JavaScript
  Secure: true     — HTTPS only (set only in production)
  SameSite: Lax    — CSRF protection for top-level navigations
"""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import Cookie, Depends, HTTPException, Response

from app.config import settings
from app.database import AsyncSession, get_db
from app.models.user import User

COOKIE_NAME = "flowlist_session"

_signer = URLSafeTimedSerializer(settings.secret_key, salt="flowlist-session-v1")


# ── Cookie helpers ────────────────────────────────────────────────────────────


def create_session_cookie(response: Response, user_id: int) -> None:
    """Sign user_id and set it as a session cookie on the response."""
    token = _signer.dumps({"uid": user_id})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_expire_hours * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Delete the session cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")


def decode_session_cookie(token: str) -> int | None:
    """
    Verify and decode a session cookie token.
    Returns user_id on success, None if invalid or expired.
    """
    try:
        data = _signer.loads(
            token, max_age=settings.session_expire_hours * 3600
        )
        uid = data.get("uid")
        return int(uid) if uid is not None else None
    except (BadSignature, SignatureExpired, (ValueError, TypeError)):
        return None


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_optional_user(
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Like get_current_user but returns None instead of raising 401.
    Used by endpoints that behave differently for authenticated vs anonymous requests.
    """
    if not session_cookie:
        return None
    user_id = decode_session_cookie(session_cookie)
    if user_id is None:
        return None
    from app.repositories import user_repo
    return await user_repo.get_by_id(db, user_id)


async def get_current_user(
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency. Resolves the current authenticated user from the
    session cookie. Raises 401 if unauthenticated or session is invalid.

    Usage:
        @router.get("/something")
        async def handler(user: User = Depends(get_current_user)):
            ...
    """
    if not session_cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_session_cookie(session_cookie)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session invalid or expired")

    from app.repositories import user_repo
    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")

    return user
