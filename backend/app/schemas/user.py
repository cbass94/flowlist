# FlowList — Pydantic schemas for User
from pydantic import BaseModel


class UserRead(BaseModel):
    id: int
    email: str
    display_name: str | None
    personal_account_connected: bool

    model_config = {"from_attributes": True}
