"""
Invites router — admin-only invite management.

POST   /api/invites          — create invite for an email (admin only)
GET    /api/invites          — list all invites (admin only)
DELETE /api/invites/{id}     — revoke an invite (admin only)
GET    /api/invites/verify   — validate a token (public, used by /invite page)

Admin is defined as user_id = 1 (the original owner account).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.repositories import invite_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.invite import InviteCreate, InviteRead
from app.services.auth_service import get_current_user
from app.services.rate_limit import check_rate_limit, get_client_ip

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invites", tags=["invites"])

_ADMIN_USER_ID = 1


def _require_admin(user: User) -> None:
    if user.id != _ADMIN_USER_ID:
        raise HTTPException(status_code=403, detail="Admin access required")


def _to_read(invite) -> InviteRead:
    return InviteRead(
        id=invite.id,
        email=invite.email,
        token=invite.token,
        created_at=invite.created_at,
        accepted_at=invite.accepted_at,
        expires_at=invite.expires_at,
        status=invite_repo.invite_status(invite),
    )


# ── Public ────────────────────────────────────────────────────────────────────
# NOTE: this must be declared before /{invite_id} to avoid route shadowing.

@router.get("/verify", response_model=ApiResponse[dict], summary="Verify invite token")
async def verify_invite(
    token: str = Query(..., description="Invite token from the invite link"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Validate an invite token. Used by the /invite landing page."""
    invite = await invite_repo.get_by_token(db, token)
    if invite is None or not invite_repo.is_valid(invite):
        raise HTTPException(status_code=404, detail="Invite not found or expired")
    return ok({"email": invite.email, "valid": True})


# ── Admin ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=ApiResponse[InviteRead], summary="Create invite")
async def create_invite(
    body: InviteCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[InviteRead]:
    _require_admin(current_user)
    ip = get_client_ip(request)
    await check_rate_limit(
        f"ratelimit:invites:create:{ip}",
        limit=5,
        window_secs=60,
        error_msg="Too many invite requests. Try again in a minute.",
    )
    email = body.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    invite = await invite_repo.create_invite(
        db, email=email, created_by_user_id=current_user.id
    )
    log.info("Invite created for %s by user %d", email, current_user.id)
    return ok(_to_read(invite))


@router.get("", response_model=ApiResponse[list[InviteRead]], summary="List invites")
async def list_invites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[InviteRead]]:
    _require_admin(current_user)
    invites = await invite_repo.get_all(db)
    return ok([_to_read(i) for i in invites])


@router.delete("/{invite_id}", response_model=ApiResponse[None], summary="Revoke invite")
async def revoke_invite(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    _require_admin(current_user)
    deleted = await invite_repo.delete_invite(db, invite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Invite not found")
    log.info("Invite %d revoked by user %d", invite_id, current_user.id)
    return ok(None)
