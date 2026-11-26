from decimal import Decimal
from typing import Any, Callable

from models.order import OrderModel


def has_final_weights(order: OrderModel) -> bool:
    if not order.items:
        return False
    for item in order.items:
        try:
            if Decimal(str(item.get("actual_weight", ""))) <= 0:
                return False
        except (TypeError, ValueError, ArithmeticError):
            return False
        if not str(item.get("weight_unit", "")).strip():
            return False
    return True


def update_final_weights(
    order: OrderModel,
    raw_weights: list[str],
    get_product: Callable[[str], dict[str, Any] | None],
) -> tuple[list[dict[str, Any]], Decimal]:
    if order.status != "pending":
        raise ValueError("Final weight can only be updated for pending orders")
    if len(raw_weights) != len(order.items):
        raise ValueError("A final weight is required for every product")

    updated_items: list[dict[str, Any]] = []
    for item, raw_weight in zip(order.items, raw_weights):
        try:
            weight = Decimal(raw_weight.strip())
        except (ArithmeticError, AttributeError):
            raise ValueError("Final weight must be a valid number") from None
        product = get_product(str(item.get("product_id", "")))
        unit = str(product.get("unit", "") if product else "").strip()
        if not unit:
            raise ValueError("Product unit is unavailable")
        if weight <= 0:
            raise ValueError("Final weight and unit are required")

        updated_item = dict(item)
        updated_item["actual_weight"] = weight
        updated_item["weight_unit"] = unit
        unit_price = Decimal(str(updated_item.get("unit_price", 0)))
        updated_item["line_total"] = (unit_price * weight).quantize(Decimal("0.01"))
        updated_items.append(updated_item)

    total = sum(
        (Decimal(str(item["line_total"])) for item in updated_items),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    return updated_items, total


def validate_status_transition(order: OrderModel, status_value: str) -> None:
    if status_value == "confirmed":
        if order.status != "pending" or not has_final_weights(order):
            raise ValueError("Final weights are required before confirmation")
    elif status_value == "delivered" and order.status != "confirmed":
        raise ValueError("Only confirmed orders can be marked delivered")
