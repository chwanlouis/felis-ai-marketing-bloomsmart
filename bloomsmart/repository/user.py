import re
import time
import uuid
from typing import Any, List, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
from botocore.exceptions import ClientError
from .base_repository import DynamoDBBaseRepository
from models.user import UserModel, UserRole
from tools.logger import get_logger


password_hasher = PasswordHasher()
logger = get_logger(__name__)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHash, VerificationError, VerifyMismatchError):
        return False


Role = UserRole


class UserRepository(DynamoDBBaseRepository[UserModel]):
    def __init__(self, dynamodb_resource: object | None = None, table_name_env_key: str = "DYNAMODB_TABLE_USER") -> None:
        super().__init__(
            table_name_env_key=table_name_env_key,
            default_table_name="felis_users",
            partition_key="user_id",
            model_type=UserModel,
            dynamodb_resource=dynamodb_resource,
        )

    def save(self, item: UserModel | dict | None = None, **fields: object) -> bool:
        payload = item if item is not None else fields
        validated = UserModel.model_validate(payload)
        return super().save(validated)

    def upsert(self, item: UserModel | dict | None = None, **fields: object) -> UserModel:
        payload = item if item is not None else fields
        validated = UserModel.model_validate(payload)
        if not super().save(validated):
            raise RuntimeError("Unable to persist user")
        return validated

    @staticmethod
    def _normalize_user(item: UserModel | dict) -> UserModel:
        if isinstance(item, UserModel):
            return item
        payload = dict(item)
        payload["user_id"] = str(payload.get("user_id", payload.get("id", ""))).strip() or str(uuid.uuid4())
        payload["username"] = str(payload.get("username", "")).strip().lower()
        payload["email"] = str(payload.get("email", "")).strip().lower() or None
        payload["phone_number"] = str(payload.get("phone_number", "")).strip()
        payload["role"] = str(payload.get("role", Role.EMPLOYEE.value)).strip().lower()
        payload["created_at"] = int(payload.get("created_at", time.time()))
        return UserModel.model_validate(payload)

    def _update_user(self, user_id: str, **changes: object) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        merged = user.model_dump(mode="python")
        merged.update(changes)
        validated = UserModel.model_validate(merged)
        serialized = validated.model_dump(mode="json", exclude_none=False)
        key = {self.partition_key: user_id}
        update_values = {
            field: self._to_decimal(serialized[field])
            for field in changes
        }
        try:
            self.table.update_item(
                Key=key,
                UpdateExpression="SET " + ", ".join(f"#{field} = :{field}" for field in update_values),
                ExpressionAttributeNames={f"#{field}": field for field in update_values},
                ExpressionAttributeValues={f":{field}": value for field, value in update_values.items()},
            )
            return True
        except ClientError as exc:
            logger.error("Error updating user '%s': %s", user_id, exc)
            return False

    @staticmethod
    def normalize_phone_number(phone_number: str) -> str:
        normalized = phone_number.strip()
        if re.fullmatch(r"\d{8}", normalized):
            return f"+852{normalized}"
        return ""

    def create_user(
        self,
        username: str,
        phone_number: str,
        password: str,
        email: str = "",
        role: Role = Role.CUSTOMER,
    ) -> Optional[UserModel]:
        username = username.strip().lower()
        email = email.strip().lower()
        phone_number = self.normalize_phone_number(phone_number)
        if (
            not username
            or len(password) < 8
            or not phone_number
            or self.get_by_username(username)
            or (email and self.get_by_email(email))
            or self.get_by_phone_number(phone_number)
        ):
            return None

        role_enum = role if isinstance(role, Role) else Role(role)
        user = UserModel.model_validate(
            {
                "user_id": str(uuid.uuid4()),
                "username": username,
                "email": email or None,
                "phone_number": phone_number,
                "password_hash": hash_password(password),
                "role": role_enum.value,
                "is_active": True,
                "created_at": int(time.time()),
            }
        )
        return user if self.save(user) else None

    def get_user_by_id(self, user_id: str) -> Optional[UserModel]:
        return self.get_by_id(user_id)

    def get_by_username(self, username: str) -> Optional[UserModel]:
        normalized_username = username.strip().lower()
        for user in self.scan_all():
            if user.username == normalized_username:
                return user
        return None

    def get_by_email(self, email: str) -> Optional[UserModel]:
        normalized_email = email.strip().lower()
        return next(
            (user for user in self.scan_all() if user.email == normalized_email),
            None,
        )

    def get_by_google_sub(self, google_sub: str) -> Optional[UserModel]:
        return next(
            (user for user in self.scan_all() if user.google_sub == google_sub),
            None,
        )

    def get_by_phone_number(self, phone_number: str) -> Optional[UserModel]:
        normalized_phone = self.normalize_phone_number(phone_number)
        if not normalized_phone:
            return None
        for user in self.scan_all():
            if user.phone_number == normalized_phone:
                return user
        return None

    def verify_credentials(self, username: str, password: str) -> Optional[UserModel]:
        user = self.get_by_username(username)
        if not user or not user.is_active:
            return None
        if verify_password(password, user.password_hash or ""):
            self.update_login_timestamp(user.user_id)
            return user
        return None

    def verify_identifier_password(self, identifier: str, password: str) -> Optional[UserModel]:
        normalized_identifier = identifier.strip()
        if not normalized_identifier:
            logger.warning("Login rejected: reason=empty_identifier")
            return None

        user = self.get_by_username(normalized_identifier)
        identifier_type = "username"
        if not user:
            user = self.get_by_email(normalized_identifier)
            identifier_type = "email"
        if not user:
            user = self.get_by_phone_number(normalized_identifier)
            identifier_type = "phone"

        if not user:
            logger.warning(
                "Login failed: reason=identifier_not_found identifier_type=%s",
                identifier_type,
            )
            return None

        if not user.is_active:
            logger.warning(
                "Login failed: reason=user_inactive identifier_type=%s user_id=%s",
                identifier_type,
                user.user_id,
            )
            return None

        if not user.password_hash:
            logger.warning(
                "Login failed: reason=password_hash_missing identifier_type=%s user_id=%s",
                identifier_type,
                user.user_id,
            )
            return None

        if not verify_password(password, user.password_hash):
            logger.warning(
                "Login failed: reason=password_mismatch identifier_type=%s user_id=%s",
                identifier_type,
                user.user_id,
            )
            return None

        self.update_login_timestamp(user.user_id)
        logger.info(
            "Login authenticated: identifier_type=%s user_id=%s",
            identifier_type,
            user.user_id,
        )
        return user

    def update_login_timestamp(self, user_id: str) -> bool:
        return self._update_user(user_id, last_login=int(time.time()))

    def list_users(self) -> List[UserModel]:
        return list(self.scan_all())

    def update_role(self, user_id: str, new_role: Role) -> bool:
        role_enum = new_role if isinstance(new_role, Role) else Role(new_role)
        return self._update_user(user_id, role=role_enum.value)

    def update_password(self, user_id: str, new_password: str) -> bool:
        return self._update_user(
            user_id, password_hash=hash_password(new_password)
        )

    def set_password(self, user_id: str, new_password: str) -> bool:
        return self.update_password(user_id, new_password)

    def update_google_credentials(self, user_id: str, google_sub: str, clear_password: bool = False) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        changes: dict[str, object] = {
            "google_sub": google_sub,
            "is_email_verified": True,
        }
        if clear_password:
            changes["password_hash"] = None
        return self._update_user(user_id, **changes)

    def link_google_account(self, user_id: str, google_sub: str, clear_password: bool = False) -> bool:
        return self.update_google_credentials(user_id, google_sub, clear_password)

    def delete_user(self, user_id: str) -> bool:
        return self.delete(partition_value=user_id)


user_repository = UserRepository()
