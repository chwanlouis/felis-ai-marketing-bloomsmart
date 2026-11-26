import os
import sys
import uuid
from typing import Optional


PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bloomsmart"))
sys.path.insert(0, PACKAGE_ROOT)

from models.user import UserModel  # noqa: E402
from repository.user import Role, hash_password, UserRepository  # noqa: E402


user_repository = UserRepository(table_name_env_key="BLOOMSMART_DYNAMODB_TABLE_USER")


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _find_existing_user(
    username: str,
    email: Optional[str],
    phone_number: Optional[str],
) -> Optional[UserModel]:
    return (
        user_repository.get_by_username(username)
        or (user_repository.get_by_email(email) if email else None)
        or (user_repository.get_by_phone_number(phone_number) if phone_number else None)
    )


def main() -> None:
    username = _required_environment("BLOOMSMART_ADMIN_USERNAME").lower()
    email = os.getenv("BLOOMSMART_ADMIN_EMAIL", "").strip().lower() or None
    password = _required_environment("BLOOMSMART_ADMIN_PASSWORD")
    phone_number = os.getenv("BLOOMSMART_ADMIN_PHONE_NUMBER", "").strip() or None

    existing = _find_existing_user(username, email, phone_number)
    user_id = existing.user_id if existing else str(uuid.uuid5(uuid.NAMESPACE_URL, f"felis-admin:{username}"))
    user = UserModel(
        user_id=user_id,
        username=username,
        email=email or (existing.email if existing else None),
        phone_number=phone_number or (existing.phone_number if existing else ""),
        password_hash=hash_password(password),
        google_sub=existing.google_sub if existing else None,
        is_email_verified=existing.is_email_verified if existing else False,
        role=Role.ADMIN.value,
        is_active=True,
        phone_verified=False,
        sms_2fa_enabled=existing.sms_2fa_enabled if existing else False,
        sms_code_hash=existing.sms_code_hash if existing else "",
        sms_code_purpose=existing.sms_code_purpose if existing else "",
        sms_code_expires_at=existing.sms_code_expires_at if existing else 0,
        sms_code_attempts=existing.sms_code_attempts if existing else 0,
        created_at=existing.created_at if existing else 0,
        last_login=existing.last_login if existing else 0,
    )
    user_repository.upsert(user)
    print(f"Admin user initialized: {username}")


if __name__ == "__main__":
    main()
