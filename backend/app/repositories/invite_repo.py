"""Invite repository — CRUD for the invites table."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import Invite


async def create_invite(
    session: AsyncSession,
    email: str,
    created_by_user_id: int,
    expires_days: int = 7,
) -> Invite:
    invite = Invite(
        email=email.lower().strip(),
        token=str(uuid.uuid4()),
        created_by_user_id=created_by_user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
    )
    session.add(invite)
    await session.flush()
    return invite


async def get_by_token(session: AsyncSession, token: str) -> Invite | None:
    result = await session.execute(select(Invite).where(Invite.token == token))
    return result.scalar_one_or_none()


async def get_valid_by_email(session: AsyncSession, email: str) -> Invite | None:
    """Return the most recent pending, non-expired invite for this email."""
    result = await session.execute(
        select(Invite)
        .where(Invite.email == email.lower().strip())
        .where(Invite.accepted_at.is_(None))
        .order_by(Invite.created_at.desc())
    )
    for invite in result.scalars().all():
        if is_valid(invite):
            return invite
    return None


async def get_all(session: AsyncSession) -> list[Invite]:
    result = await session.execute(select(Invite).order_by(Invite.created_at.desc()))
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, invite_id: int) -> Invite | None:
    result = await session.execute(select(Invite).where(Invite.id == invite_id))
    return result.scalar_one_or_none()


async def accept(session: AsyncSession, invite: Invite) -> None:
    invite.accepted_at = datetime.now(timezone.utc)
    await session.flush()


async def delete_invite(session: AsyncSession, invite_id: int) -> bool:
    invite = await get_by_id(session, invite_id)
    if invite is None:
        return False
    await session.delete(invite)
    await session.flush()
    return True


def is_valid(invite: Invite) -> bool:
    """Return True if invite is pending and not expired."""
    if invite.accepted_at is not None:
        return False
    if invite.expires_at is not None:
        now = datetime.now(timezone.utc)
        expires = (
            invite.expires_at
            if invite.expires_at.tzinfo is not None
            else invite.expires_at.replace(tzinfo=timezone.utc)
        )
        if now > expires:
            return False
    return True


def invite_status(invite: Invite) -> str:
    if invite.accepted_at is not None:
        return "accepted"
    if not is_valid(invite):
        return "expired"
    return "pending"
