import time
import uuid
from decimal import Decimal

from fastapi import APIRouter, Cookie, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse

from models.order import OrderModel
from repository.order import order_repository
from repository.product import product_repository
from repository.session import session_repository
from repository.user import Role, user_repository
from models.product import ProductType
from models.user import UserModel
from tools.logger import get_logger
from tools.permissions import Permission, has_permission
from tools.webpage import render_content_template, render_page
from services.cart_service import (
    build_order_items as _build_order_items,
    cart_map as _cart_map,
    format_quantity as _format_quantity,
    get_cart_lines,
    quantity_step as _quantity_step,
    save_cart as _save_cart,
    validate_quantity as _validate_quantity,
)
from services.order_service import (
    update_final_weights,
    validate_status_transition,
)
router = APIRouter()
logger = get_logger(__name__)
ORDER_STATUSES = ("pending", "confirmed", "delivered", "completed", "cancelled")
STATUS_LABELS = {
    "pending": "待處理",
    "confirmed": "已確認",
    "delivered": "已送達",
    "completed": "已完成",
    "cancelled": "已取消",
}
PRODUCT_TYPES = tuple(product_type.value for product_type in ProductType)


def _get_active_session(session_id: str | None):
    session = session_repository.get_valid_session(session_id or "")
    if not session:
        return None, None
    user = user_repository.get_user_by_id(session.user_id)
    if not user or not user.is_active:
        session_repository.delete_session(session.session_id)
        return None, None
    return session, user


def _require_session(session_id: str | None):
    session, user = _get_active_session(session_id)
    if not session or not user:
        return None, RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return (session, user), None


def _require_admin(session_id: str | None):
    result, response = _require_session(session_id)
    if response:
        return None, response
    session, user = result
    if user.role not in {Role.ROOT.value, Role.ADMIN.value}:
        return None, RedirectResponse(url="/shop/all", status_code=status.HTTP_303_SEE_OTHER)
    return (session, user), None


def _render_shop_page(
    title: str,
    page_kind: str,
    current_user: UserModel,
    **context: object,
) -> HTMLResponse:
    content = render_content_template(
        "shop.html",
        page_kind=page_kind,
        **context,
    )
    return HTMLResponse(
        render_page(title, "shop", content, current_user=current_user)
    )


def _product_view(product: dict) -> dict[str, object]:
    price = Decimal(str(product.get("price", 0))).quantize(Decimal("0.01"))
    return {
        "id": str(product.get("id", "")),
        "name": str(product.get("cn_name") or product.get("en_name") or "未命名產品"),
        "en_name": str(product.get("en_name", "")),
        "description": str(product.get("product_description", "") or ""),
        "unit": str(product.get("unit", "") or "件"),
        "price": price,
        "photo_url": str(product.get("photo_url", "") or "").split("|")[0].strip(),
        "quantity_step": _quantity_step(str(product.get("unit", ""))),
    }


@router.get("/shop", response_class=HTMLResponse)
def shop_root():
    return RedirectResponse(url="/shop/all", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/shop/cart/add")
def add_to_cart(
    product_id: str = Form(...),
    quantity: Decimal = Form(default=Decimal("1"), gt=0, le=99),
    session: str = Cookie(default=None),
):
    result, response = _require_session(session)
    if response:
        return response
    active_session, _ = result
    product = product_repository.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.get("is_suspend") is True:
        raise HTTPException(status_code=400, detail="Product is suspended")
    try:
        quantity = _validate_quantity(quantity, str(product.get("unit", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cart = _cart_map(active_session)
    cart[product_id] = min(cart.get(product_id, Decimal("0")) + quantity, Decimal("99"))
    if not _save_cart(active_session, cart):
        raise HTTPException(status_code=500, detail="Unable to update shopping cart")
    return RedirectResponse(url="/shop/cart", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/shop/cart", response_class=HTMLResponse)
def cart_page(session: str = Cookie(default=None)):
    result, response = _require_session(session)
    if response:
        return response
    active_session, user = result
    lines, total = get_cart_lines(active_session)
    customer_options = []
    if has_permission(user, Permission.ORDER_CREATE_ANY):
        customer_options = [
            customer
            for customer in user_repository.list_users()
            if customer.is_active and customer.role == Role.CUSTOMER.value
        ]
    line_views = [
        {
            "name": line.name,
            "unit_price": line.unit_price,
            "product_id": line.product_id,
            "quantity": _format_quantity(line.quantity),
            "quantity_step": _quantity_step(line.unit),
            "subtotal": line.subtotal,
            "is_suspended": line.is_suspended,
        }
        for line in lines
    ]
    return _render_shop_page(
        "購物車",
        "cart",
        user,
        lines=line_views,
        total=total,
        has_suspended=any(line.is_suspended for line in lines),
        customer_options=customer_options,
    )


@router.post("/shop/cart/update")
def update_cart(
    product_id: str = Form(...),
    quantity: Decimal = Form(..., ge=0, le=99),
    session: str = Cookie(default=None),
):
    result, response = _require_session(session)
    if response:
        return response
    active_session, _ = result
    cart = _cart_map(active_session)
    if quantity:
        product = product_repository.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        try:
            cart[product_id] = _validate_quantity(quantity, str(product.get("unit", "")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        cart.pop(product_id, None)
    if not _save_cart(active_session, cart):
        raise HTTPException(status_code=500, detail="Unable to update shopping cart")
    return RedirectResponse(url="/shop/cart", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/shop/cart/delete")
def delete_cart_item(
    product_id: str = Form(...),
    session: str = Cookie(default=None),
):
    result, response = _require_session(session)
    if response:
        return response
    active_session, _ = result
    cart = _cart_map(active_session)
    cart.pop(product_id, None)
    if not _save_cart(active_session, cart):
        raise HTTPException(status_code=500, detail="Unable to delete cart item")
    return RedirectResponse(url="/shop/cart", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/shop/checkout")
def checkout(
    target_user_id: str = Form(default=""),
    session: str = Cookie(default=None),
):
    result, response = _require_session(session)
    if response:
        return response
    active_session, user = result
    lines, _ = get_cart_lines(active_session)
    if any(line.is_suspended for line in lines):
        raise HTTPException(
            status_code=400,
            detail="Suspended products cannot be checked out",
        )
    order_user = user
    if has_permission(user, Permission.ORDER_CREATE_ANY):
        target_user = user_repository.get_user_by_id(target_user_id.strip())
        if (
            not target_user
            or not target_user.is_active
            or target_user.role != Role.CUSTOMER.value
        ):
            raise HTTPException(status_code=400, detail="A valid customer is required")
        order_user = target_user
    items, total = _build_order_items(active_session)
    if not items:
        return RedirectResponse(url="/shop/cart", status_code=status.HTTP_303_SEE_OTHER)
    order = OrderModel(
        order_id=str(uuid.uuid4()),
        user_id=order_user.user_id,
        username=order_user.username,
        items=items,
        total=total,
        created_at=int(time.time()),
    )
    if not order_repository.create_order(order) or not _save_cart(active_session, {}):
        raise HTTPException(status_code=500, detail="Unable to create order")
    logger.info("Order created: order_id=%s user_id=%s", order.order_id, order_user.user_id)
    if has_permission(user, Permission.ORDER_CREATE_ANY):
        return RedirectResponse(url="/orders", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=f"/shop/orders/{order.order_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/shop/orders", response_class=HTMLResponse)
def customer_orders(session: str = Cookie(default=None)):
    result, response = _require_session(session)
    if response:
        return response
    _, user = result
    order_views = []
    for order in order_repository.list_orders():
        if order.user_id != user.user_id:
            continue
        order_views.append({
            "order_id": order.order_id,
            "short_id": order.order_id[:8],
            "created_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(order.created_at)),
            "total": order.total,
            "status_label": STATUS_LABELS.get(order.status, order.status),
            "items": [
                {
                    "name": str(item.get("name", "未命名產品")),
                    "quantity": item.get("quantity"),
                    "actual_weight": item.get("actual_weight"),
                    "weight_unit": str(item.get("weight_unit", "")),
                }
                for item in order.items
            ],
        })
    return _render_shop_page(
        "我的訂單",
        "customer_orders",
        user,
        orders=order_views,
    )


@router.get("/shop/orders/{order_id}", response_class=HTMLResponse)
def order_confirmation(order_id: str, session: str = Cookie(default=None)):
    result, response = _require_session(session)
    if response:
        return response
    _, user = result
    order = order_repository.get_by_id(order_id)
    if not order or order.user_id != user.user_id:
        raise HTTPException(status_code=404, detail="Order not found")
    item_views = []
    for item in order.items:
        product = product_repository.get_product(str(item.get("product_id", "")))
        photo_url = str(product.get("photo_url", "") if product else "").split("|")[0].strip()
        item_views.append({
            "name": str(item.get("name", "未命名產品")),
            "photo_url": photo_url,
            "quantity": item.get("quantity", 0),
            "actual_weight": item.get("actual_weight"),
            "weight_unit": str(item.get("weight_unit", "")),
            "line_total": Decimal(str(item.get("line_total", 0))).quantize(Decimal("0.01")),
        })
    order_view = {
        "order_id": order.order_id,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "total": order.total,
        "items": item_views,
    }
    return _render_shop_page(
        "訂單已提交",
        "order_confirmation",
        user,
        order=order_view,
    )


@router.get("/orders", response_class=HTMLResponse)
def admin_orders(session: str = Cookie(default=None)):
    result, response = _require_admin(session)
    if response:
        return response
    _, user = result
    order_views = []
    for order in order_repository.list_orders():
        order_views.append({
            "order_id": order.order_id,
            "short_id": order.order_id[:8],
            "username": order.username,
            "total": order.total,
            "status": order.status,
            "items": [
                {
                    "name": str(item.get("name", "未命名產品")),
                    "actual_weight": item.get("actual_weight"),
                    "weight_unit": str(item.get("weight_unit", "")),
                    "unit": str(
                        (product_repository.get_product(str(item.get("product_id", ""))) or {})
                        .get("unit", "")
                    ),
                }
                for item in order.items
            ],
        })
    return _render_shop_page(
        "訂單管理",
        "admin_orders",
        user,
        orders=order_views,
        statuses=tuple(STATUS_LABELS.items()),
    )


@router.post("/orders/{order_id}/weight")
def update_order_weight(
    order_id: str,
    actual_weight: list[str] = Form(default=[]),
    session: str = Cookie(default=None),
):
    _, response = _require_admin(session)
    if response:
        return response
    order = order_repository.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        updated_items, total = update_final_weights(
            order,
            actual_weight,
            product_repository.get_product,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not order_repository.update_items_and_total(order_id, updated_items, total):
        raise HTTPException(status_code=500, detail="Unable to update final weight and total")
    return RedirectResponse(url="/orders", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/orders/{order_id}/status")
def update_order_status(
    order_id: str,
    status_value: str = Form(..., alias="status"),
    session: str = Cookie(default=None),
):
    _, response = _require_admin(session)
    if response:
        return response
    order = order_repository.get_by_id(order_id)
    if status_value not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid order status")
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        validate_status_transition(order, status_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not order_repository.update_status(order_id, status_value):
        raise HTTPException(status_code=500, detail="Unable to update order")
    return RedirectResponse(url="/orders", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/shop/{product_type:path}", response_class=HTMLResponse)
def shop_page(
    product_type: str = "all",
    session: str = Cookie(default=None),
):
    result, response = _require_session(session)
    if response:
        return response
    _, user = result
    products = [
        product
        for product in product_repository.list_products()
        if product.get("is_suspend") is not True
    ]
    selected_type = product_type if product_type in PRODUCT_TYPES else "all"
    product_views = [
        _product_view(product)
        for product in products
        if selected_type == "all" or selected_type in {
            value.strip()
            for value in str(product.get("product_type", "")).split("|")
            if value.strip()
        }
    ]
    available_types = [
        product_type
        for product_type in PRODUCT_TYPES
        if any(
            product_type in {
                value.strip()
                for value in str(product.get("product_type", "")).split("|")
                if value.strip()
            }
            for product in products
        )
    ]
    return _render_shop_page(
        "網上商店",
        "shop",
        user,
        products=product_views,
        selected_type=selected_type,
        product_types=available_types,
    )
