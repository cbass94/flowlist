# FlowList — Pydantic schemas for User
from pydantic import BaseModel, computed_field

_ADMIN_USER_ID = 1


class UserRead(BaseModel):
    id: int
    email: str
    display_name: str | None
    personal_account_connected: bool

    @computed_field
    @property
    def is_admin(self) -> bool:
        return self.id == _ADMIN_USER_ID

    model_config = {"from_attributes": True}
