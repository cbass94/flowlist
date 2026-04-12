from datetime import datetime

from pydantic import BaseModel


class InviteCreate(BaseModel):
    email: str


class InviteRead(BaseModel):
    id: int
    email: str
    token: str
    created_at: datetime
    accepted_at: datetime | None
    expires_at: datetime | None
    status: str  # "pending" | "accepted" | "expired"
