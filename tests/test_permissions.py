import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "bloomsmart"))

from models.user import UserModel
from fastapi import HTTPException

from tools.permissions import (
    Permission,
    PermissionChecker,
    has_permission,
    permissions_for_role,
)


def _user(role: str) -> UserModel:
    return UserModel(
        user_id=f"{role}-1",
        username=role,
        password_hash="test-hash",
        role=role,
    )


def test_admin_permissions():
    admin = _user("admin")

    assert has_permission(admin, Permission.SHOP_READ)
    assert has_permission(admin, Permission.ORDER_CREATE_ANY)
    assert has_permission(admin, Permission.ORDER_UPDATE_STATUS)
    assert has_permission(admin, Permission.PRODUCT_READ)
    assert has_permission(admin, Permission.WHATSAPP_READ)
    assert not has_permission(admin, Permission.ORDER_READ_OWN)


def test_customer_permissions():
    customer = _user("customer")

    assert has_permission(customer, Permission.SHOP_READ)
    assert has_permission(customer, Permission.ORDER_READ_OWN)
    assert not has_permission(customer, Permission.ORDER_UPDATE_STATUS)
    assert not has_permission(customer, Permission.ORDER_CREATE_ANY)


def test_unknown_roles_have_no_permissions():
    assert permissions_for_role("employee") == frozenset()
    assert not has_permission(_user("employee"), Permission.SHOP_READ)


def test_root_has_all_permissions():
    assert permissions_for_role("root") == frozenset(Permission)


def test_permission_checker_rejects_missing_permission():
    checker = PermissionChecker(Permission.ORDER_UPDATE_STATUS)

    try:
        checker(_user("customer"))
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "orders:update_status" in str(exc.detail)
    else:
        raise AssertionError("PermissionChecker should reject customer access")
