import secrets
import time
from typing import Optional
from .base_repository import DynamoDBBaseRepository
from models.session import SessionModel
from models.user import UserModel
from tools.logger import get_logger

# Default Session Expiration: 24 hours (in seconds)
DEFAULT_SESSION_EXPIRE_SECONDS = 86400
logger = get_logger(__name__)


class SessionRepository(DynamoDBBaseRepository[SessionModel]):
    """
    Repository for managing user session state in DynamoDB.
    Supports session creation, expiration checks, and manual revocation.
    """

    def __init__(self):
        super().__init__(
            table_name_env_key="DYNAMODB_TABLE_SESSION",
            default_table_name="felis_sessions",
            partition_key="session_id",
            model_type=SessionModel,
        )

    def _normalize_session(self, item: SessionModel | dict) -> SessionModel:
        """Sanitize session attributes and ensure proper integer/string types."""
        now = int(time.time())
        payload = item.model_dump(mode="python") if isinstance(item, SessionModel) else item
        return SessionModel.model_validate({
            "session_id": str(payload.get("session_id", "")).strip(),
            "user_id": str(payload.get("user_id", "")).strip(),
            "username": str(payload.get("username", "")).strip().lower(),
            "role": str(payload.get("role", "customer")).strip(),
            "created_at": int(payload.get("created_at", now)),
            "expires_at": int(payload.get("expires_at", now + DEFAULT_SESSION_EXPIRE_SECONDS)),
            "cart": payload.get("cart", []),
        })

    def create_session(
            self,
            user: UserModel,
            expire_seconds: int = DEFAULT_SESSION_EXPIRE_SECONDS,
    ) -> Optional[SessionModel]:
        """
        Generate a cryptographically secure session token and persist the user session.

        :param user: Dict containing user_id, username, and role
        :param expire_seconds: Session duration in seconds
        :return: Normalized session dictionary or None if save failed
        """
        now = int(time.time())
        session_id = secrets.token_urlsafe(32)

        raw_session = {
            "session_id": session_id,
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "created_at": now,
            "expires_at": now + expire_seconds,
        }

        normalized = self._normalize_session(raw_session)
        if self.save(normalized):
            logger.info("Session created: user_id=%s", user.user_id)
            return normalized
        logger.error("Session creation failed: user_id=%s", user.user_id)
        return None

    def update_cart(self, session_id: str, cart: list[dict[str, object]]) -> bool:
        return self.update_field(session_id, "cart", cart)

    def get_valid_session(self, session_id: str) -> Optional[SessionModel]:
        """
        Fetch session by ID and verify that it has not expired.
        If expired, automatically removes the session from DynamoDB.
        """
        if not session_id or not session_id.strip():
            return None

        session = self.get_by_id(session_id.strip())
        if not session:
            logger.warning("Session not found")
            return None

        normalized = self._normalize_session(session)
        current_time = int(time.time())

        # Check if the session has passed its expiration time
        if normalized.expires_at < current_time:
            self.delete_session(session_id)
            logger.info("Session expired: user_id=%s", normalized.user_id)
            return None

        logger.debug("Session validated: user_id=%s", normalized.user_id)
        return normalized

    def delete_session(self, session_id: str) -> bool:
        """Revoke/delete an active session by session_id."""
        if not session_id:
            return False
        deleted = self.delete(partition_value=session_id.strip())
        logger.info("Session deleted: success=%s", deleted)
        return deleted


session_repository = SessionRepository()