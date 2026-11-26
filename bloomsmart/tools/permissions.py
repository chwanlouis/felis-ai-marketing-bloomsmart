from enum import StrEnum
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from models.session import SessionModel
from models.user import UserModel, UserRole
from repository.session import session_repository
from repository.user import user_repository


class Permission(StrEnum):
    SHOP_READ = "shop:read"
    CART_ADD = "cart:add"
    CART_UPDATE_OWN = "cart:update:own"
    CART_DELETE_OWN = "cart:delete:own"
    ORDER_CREATE_OWN = "orders:create:own"
    ORDER_CREATE_ANY = "orders:create:any"
    ORDER_READ_OWN = "orders:read:own"
    ORDER_READ_ANY = "orders:read:any"
    ORDER_UPDATE_WEIGHT = "orders:update_weight"
    ORDER_UPDATE_STATUS = "orders:update_status"
    PRODUCT_READ = "products:read"
    PRODUCT_CREATE = "products:create"
    PRODUCT_UPDATE = "products:update"
    PRODUCT_DELETE = "products:delete"
    CUSTOMER_READ = "customers:read"
    WHATSAPP_READ = "whatsapp:read"


ADMIN_PERMISSIONS = frozenset({
    Permission.SHOP_READ,
    Permission.CART_ADD,
    Permission.CART_UPDATE_OWN,
    Permission.CART_DELETE_OWN,
    Permission.ORDER_CREATE_ANY,
    Permission.ORDER_READ_ANY,
    Permission.ORDER_UPDATE_WEIGHT,
    Permission.ORDER_UPDATE_STATUS,
    Permission.PRODUCT_READ,
    Permission.PRODUCT_CREATE,
    Permission.PRODUCT_UPDATE,
    Permission.PRODUCT_DELETE,
    Permission.CUSTOMER_READ,
    Permission.WHATSAPP_READ,
})

CUSTOMER_PERMISSIONS = frozenset({
    Permission.SHOP_READ,
    Permission.CART_ADD,
    Permission.CART_UPDATE_OWN,
    Permission.CART_DELETE_OWN,
    Permission.ORDER_CREATE_OWN,
    Permission.ORDER_READ_OWN,
})

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ROOT: frozenset(Permission),
    UserRole.ADMIN: ADMIN_PERMISSIONS,
    UserRole.CUSTOMER: CUSTOMER_PERMISSIONS,
}

def has_permission(user: UserModel, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def permissions_for_role(role: str | UserRole) -> frozenset[Permission]:
    try:
        role_enum = role if isinstance(role, UserRole) else UserRole(role)
    except ValueError:
        return frozenset()
    return ROLE_PERMISSIONS.get(role_enum, frozenset())


def get_current_session(
    session_id: Annotated[str | None, Cookie(alias="session")] = None,
) -> SessionModel:
    active_session = session_repository.get_valid_session(session_id or "")
    if not active_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return active_session


def get_current_user(
    current_session: Annotated[SessionModel, Depends(get_current_session)],
) -> UserModel:
    user = user_repository.get_user_by_id(current_session.user_id)
    if not user or not user.is_active:
        session_repository.delete_session(current_session.session_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session is invalid",
        )

    return user


class PermissionChecker:

    def __init__(self, permission: Permission):
        self.permission = permission

    def __call__(
        self,
        current_user: Annotated[UserModel, Depends(get_current_user)],
    ) -> UserModel:
        if not has_permission(current_user, self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {self.permission.value}",
            )
        return current_user
