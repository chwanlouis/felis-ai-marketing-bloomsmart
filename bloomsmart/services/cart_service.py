from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from models.product import ProductUnit
from repository.product import product_repository
from repository.session import session_repository


@dataclass(frozen=True)
class CartLine:
    product_id: str
    name: str
    unit: str
    unit_price: Decimal
    quantity: Decimal
    subtotal: Decimal
    is_suspended: bool


def cart_map(session: Any) -> dict[str, Decimal]:
    cart: dict[str, Decimal] = {}
    for item in session.cart:
        product_id = str(item.get("product_id", "")).strip()
        try:
            quantity = Decimal(str(item.get("quantity", 0)))
        except (InvalidOperation, TypeError, ValueError):
            quantity = Decimal("0")
        if product_id and quantity > 0:
            cart[product_id] = min(
                cart.get(product_id, Decimal("0")) + quantity,
                Decimal("99"),
            )
    return cart


def save_cart(session: Any, cart: dict[str, Decimal]) -> bool:
    return session_repository.update_cart(
        session.session_id,
        [
            {"product_id": product_id, "quantity": quantity}
            for product_id, quantity in cart.items()
        ],
    )


def format_quantity(quantity: Decimal) -> str:
    return format(quantity, "f").rstrip("0").rstrip(".") or "0"


def quantity_step(unit: str) -> str:
    return (
        "0.001"
        if unit in {ProductUnit.POUND.value, ProductUnit.KILOGRAM.value}
        else "1"
    )


def validate_quantity(quantity: Decimal, unit: str) -> Decimal:
    if quantity <= 0 or quantity > 99:
        raise ValueError("Quantity must be between 0 and 99")
    if unit not in {ProductUnit.POUND.value, ProductUnit.KILOGRAM.value}:
        if quantity != quantity.to_integral_value():
            raise ValueError("This product only accepts whole-number quantities")
        return quantity.to_integral_value()
    quantized = quantity.quantize(Decimal("0.001"))
    if quantity != quantized:
        raise ValueError("Weight-based quantities support at most 3 decimal places")
    return quantized


def get_cart_lines(session: Any) -> tuple[list[CartLine], Decimal]:
    lines: list[CartLine] = []
    total = Decimal("0")
    for product_id, quantity in cart_map(session).items():
        product = product_repository.get_product(product_id)
        if not product:
            continue
        unit_price = Decimal(str(product.get("price", 0))).quantize(Decimal("0.01"))
        subtotal = (unit_price * quantity).quantize(Decimal("0.01"))
        lines.append(
            CartLine(
                product_id=product_id,
                name=str(product.get("cn_name") or product.get("en_name")),
                unit=str(product.get("unit", "")),
                unit_price=unit_price,
                quantity=quantity,
                subtotal=subtotal,
                is_suspended=bool(product.get("is_suspend", False)),
            )
        )
        total += subtotal
    return lines, total.quantize(Decimal("0.01"))


def build_order_items(session: Any) -> tuple[list[dict[str, Any]], Decimal]:
    lines, total = get_cart_lines(session)
    return (
        [
            {
                "product_id": line.product_id,
                "name": line.name,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "line_total": line.subtotal,
            }
            for line in lines
        ],
        total,
    )
