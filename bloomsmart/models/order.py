from decimal import Decimal
from typing import Any
from pydantic import BaseModel, Field


class OrderModel(BaseModel):
    order_id: str
    user_id: str
    username: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: Decimal = Decimal("0")
    status: str = "pending"
    created_at: int

