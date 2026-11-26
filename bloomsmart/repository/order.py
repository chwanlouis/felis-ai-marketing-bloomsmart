from decimal import Decimal
from typing import List, Optional
from botocore.exceptions import ClientError
from .base_repository import DynamoDBBaseRepository
from models.order import OrderModel


class OrderRepository(DynamoDBBaseRepository[OrderModel]):
    def __init__(self) -> None:
        super().__init__(
            table_name_env_key="DYNAMODB_TABLE_ORDER",
            default_table_name="felis_orders",
            partition_key="order_id",
            model_type=OrderModel,
        )

    def create_order(self, order: OrderModel) -> Optional[OrderModel]:
        return order if self.save(order) else None

    def update_items_and_total(
        self,
        order_id: str,
        items: List[dict],
        total: Decimal,
    ) -> bool:
        try:
            self.table.update_item(
                Key={self.partition_key: order_id},
                UpdateExpression="SET #items = :items, #total = :total",
                ExpressionAttributeNames={
                    "#items": "items",
                    "#total": "total",
                },
                ExpressionAttributeValues={
                    ":items": self._to_decimal(items),
                    ":total": self._to_decimal(total),
                },
            )
            return True
        except ClientError:
            return False

    def list_orders(self) -> List[OrderModel]:
        return sorted(self.scan_all(), key=lambda order: order.created_at, reverse=True)

    def update_status(self, order_id: str, status: str) -> bool:
        return self.update_field(order_id, "status", status)


order_repository = OrderRepository()
