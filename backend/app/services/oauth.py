"""
Google OAuth 2.0 service.

Responsibilities:
  - Build authorization URLs for work and personal accounts
  - Exchange auth codes for access + refresh tokens
  - Store anti-CSRF state nonces in Redis (5-minute TTL)
  - Parse Google's id_token to extract sub/email/name without a full JWT library
    (safe because we receive the token directly from Google's token endpoint over TLS)

Two separate OAuth apps are registered — one per Google Cloud project/account.
See README.md for how to set them up.
"""

import base64
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx

from app.config import settings
from app.services.redis_client import get_redis

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

AccountType = Literal["work", "personal"]

# Scopes for each account type.
# Both need openid so we get an id_token with the Google user ID (sub).
_WORK_SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar",
])
_PERSONAL_SCOPES = " ".join([
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar",
])

# Redis key template for OAuth state nonces
_STATE_KEY = "oauth:state:{state}"
_STATE_TTL = 300  # 5 minutes


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str


@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    expires_at: datetime
    google_id: str   # Google user sub (stable across token refreshes)
    email: str
    display_name: str | None


def _get_config(account: AccountType) -> OAuthConfig:
    if account == "work":
        return OAuthConfig(
            client_id=settings.google_work_client_id,
            client_secret=settings.google_work_client_secret,
            redirect_uri=settings.google_work_redirect_uri,
            scopes=_WORK_SCOPES,
        )
    return OAuthConfig(
        client_id=settings.google_personal_client_id,
        client_secret=settings.google_personal_client_secret,
        redirect_uri=settings.google_personal_redirect_uri,
        scopes=_PERSONAL_SCOPES,
    )


def _decode_id_token(id_token: str) -> dict:
    """
    Extract the payload from a Google id_token without signature verification.
    Safe here because the token arrived directly from Google's token endpoint
    over TLS — we are not relying on the signature for security.
    """
    parts = id_token.split(".")
    if len(parts) < 2:
        raise ValueError("Malformed id_token")
    payload = parts[1]
    # JWT base64 is URL-safe and unpadded
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


async def get_authorization_url(
    account: AccountType,
    user_id: int | None = None,
) -> tuple[str, str]:
    """
    Build the Google OAuth authorization URL and store the state nonce in Redis.

    For the personal account connection, pass `user_id` so the callback knows
    which user to attach the tokens to. The user_id is embedded in the Redis
    value (not in the URL — no user data in query params).

    Returns (authorization_url, state_nonce).
    """
    cfg = _get_config(account)
    state = secrets.token_urlsafe(32)

    redis_value = account if user_id is None else f"{account}:{user_id}"
    redis = get_redis()
    await redis.set(_STATE_KEY.format(state=state), redis_value, ex=_STATE_TTL)

    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": cfg.scopes,
        "state": state,
        "access_type": "offline",   # request refresh token
        "prompt": "consent",        # always show consent screen to get refresh_token
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}", state


async def verify_and_consume_state(state: str) -> str:
    """
    Verify state nonce exists in Redis, delete it (one-time use), and return
    the stored value (e.g. "work" or "personal:42").
    Raises ValueError on missing/expired state.
    """
    redis = get_redis()
    key = _STATE_KEY.format(state=state)
    value = await redis.get(key)
    if value is None:
        raise ValueError("OAuth state is invalid or expired. Please try logging in again.")
    await redis.delete(key)
    return value


async def exchange_code(account: AccountType, code: str) -> TokenData:
    """
    Exchange an authorization code for tokens. Calls Google's token endpoint.
    Returns a TokenData with decrypted (plaintext) token strings — the caller
    is responsible for encrypting before storing in the DB.
    """
    cfg = _get_config(account)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "redirect_uri": cfg.redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
    if resp.status_code != 200:
        raise ValueError(f"Token exchange failed: {resp.status_code} {resp.text}")

    data = resp.json()

    # Decode the id_token to get the user's Google ID and profile
    id_token = data.get("id_token", "")
    claims: dict = {}
    if id_token:
        claims = _decode_id_token(id_token)

    # Google returns expires_in seconds from now
    expires_in = data.get("expires_in", 3600)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)

    return TokenData(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        expires_at=expires_at,
        google_id=claims.get("sub", ""),
        email=claims.get("email", ""),
        display_name=claims.get("name"),
    )


async def refresh_access_token(
    account: AccountType, refresh_token_plaintext: str
) -> tuple[str, datetime]:
    """
    Use a stored refresh token to get a new access token.
    Returns (new_access_token, new_expires_at).
    Does NOT update the DB — callers must persist the new token.
    """
    cfg = _get_config(account)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token_plaintext,
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "grant_type": "refresh_token",
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
    if resp.status_code != 200:
        raise ValueError(f"Token refresh failed: {resp.status_code} {resp.text}")

    data = resp.json()
    expires_in = data.get("expires_in", 3600)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)
    return data["access_token"], expires_at
