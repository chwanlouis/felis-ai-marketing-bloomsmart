from typing import Any
from pydantic import BaseModel, Field


class SessionModel(BaseModel):
    session_id: str
    user_id: str
    username: str
    role: str
    created_at: int
    expires_at: int
    cart: list[dict[str, Any]] = Field(default_factory=list)
