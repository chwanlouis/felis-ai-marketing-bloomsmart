from enum import StrEnum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserRole(StrEnum):
    ROOT = "root"
    ADMIN = "admin"
    EMPLOYEE = "employee"
    CUSTOMER = "customer"


class UserModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
    )

    user_id: str
    username: str = Field(min_length=1)
    email: Optional[str] = None
    phone_number: str = ""
    password_hash: Optional[str] = None
    google_sub: Optional[str] = Field(default=None, min_length=1)
    is_email_verified: bool = False
    role: UserRole = UserRole.CUSTOMER
    is_active: bool = True
    created_at: int = 0
    last_login: int = 0

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_password(cls, value: Any) -> Any:
        if isinstance(value, dict):
            payload = dict(value)
            if not payload.get("password_hash") and payload.get("hashed_password"):
                payload["password_hash"] = payload["hashed_password"]
            payload.pop("hashed_password", None)
            return payload
        return value

    @model_validator(mode="after")
    def require_credential(self) -> "UserModel":
        if (
            self.password_hash is None
            and self.google_sub is None
            and not self.phone_number
        ):
            raise ValueError(
                "at least one of password_hash, google_sub, or phone_number is required"
            )
        return self
