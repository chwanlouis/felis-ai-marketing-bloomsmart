import os
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union
from botocore.exceptions import ClientError
import boto3
from pydantic import BaseModel
from tools.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class DynamoDBBaseRepository(Generic[T]):
    """
    Generic Base Repository for AWS DynamoDB operations.
    Handles dynamic table initialization, float/Decimal casting, full CRUD, and partial updates.
    """

    def __init__(
        self,
        table_name_env_key: str,
        default_table_name: str,
        partition_key: str = "id",
        sort_key: Optional[str] = None,
        dynamodb_resource: Optional[Any] = None,
        aws_region: Optional[str] = None,
        model_type: Optional[Type[BaseModel]] = None,
    ):
        self.table_name_env_key = table_name_env_key
        self.default_table_name = default_table_name
        self.partition_key = partition_key
        self.sort_key = sort_key
        self.model_type = model_type

        if dynamodb_resource:
            self._resource = dynamodb_resource
        else:
            region = aws_region or os.getenv("AWS_REGION", "us-east-1")
            self._resource = boto3.resource("dynamodb", region_name=region)

    @property
    def table_name(self) -> str:
        """Dynamically resolve table name from environment or default fallback."""
        return os.getenv(self.table_name_env_key, self.default_table_name)

    @property
    def table(self):
        """Get the boto3 Table resource for the resolved table name."""
        return self._resource.Table(self.table_name)

    # -------------------------------------------------------------------------
    # Type Conversion Helpers (Decimal <-> Float)
    # -------------------------------------------------------------------------

    @classmethod
    def _to_decimal(cls, obj: Any) -> Any:
        """Recursively convert Python float to boto3-compatible Decimal."""
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: cls._to_decimal(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [cls._to_decimal(v) for v in obj]
        return obj

    @classmethod
    def _from_decimal(cls, obj: Any) -> Any:
        """Recursively convert boto3 Decimal back to Python float/int."""
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 != 0 else int(obj)
        if isinstance(obj, dict):
            return {k: cls._from_decimal(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [cls._from_decimal(v) for v in obj]
        return obj

    # -------------------------------------------------------------------------
    # Core CRUD Operations
    # -------------------------------------------------------------------------

    def get_by_id(
        self,
        partition_value: str,
        sort_value: Optional[str] = None
    ) -> Optional[T]:
        """Fetch a single item by primary key."""
        key = {self.partition_key: partition_value}
        if self.sort_key and sort_value:
            key[self.sort_key] = sort_value

        try:
            response = self.table.get_item(Key=key)
            item = response.get("Item")
            return self._deserialize(item) if item else None
        except ClientError as e:
            logger.error("DynamoDB get failed: table=%s error=%s", self.table_name, e)
            return None

    def _deserialize(self, item: Dict[str, Any]) -> Any:
        normalized = self._from_decimal(item)
        return self.model_type.model_validate(normalized) if self.model_type else normalized

    def _serialize(self, item: Union[T, BaseModel, Dict[str, Any]]) -> Dict[str, Any]:
        if self.model_type:
            model = item if isinstance(item, self.model_type) else self.model_type.model_validate(item)
            return self._to_decimal(model.model_dump(mode="json", exclude_none=False))
        if isinstance(item, BaseModel):
            return self._to_decimal(item.model_dump(mode="json", exclude_none=False))
        return self._to_decimal(item)

    def save(self, item: T) -> bool:
        """Create or replace a single item."""
        try:
            item_to_save = self._serialize(item)
            self.table.put_item(Item=item_to_save)
            return True
        except Exception as e:
            logger.exception("DynamoDB save failed: table=%s", self.table_name)
            raise RuntimeError(
                f"Failed to save item to DynamoDB table '{self.table_name}': {e}"
            ) from e

    def update_field(
        self,
        partition_value: str,
        field_name: str,
        field_value: Any,
        sort_value: Optional[str] = None
    ) -> bool:
        """Update a single attribute/column of an existing item."""
        key = {self.partition_key: partition_value}
        if self.sort_key and sort_value:
            key[self.sort_key] = sort_value

        val_to_save = self._to_decimal(field_value)

        try:
            self.table.update_item(
                Key=key,
                UpdateExpression="SET #attr = :val",
                ExpressionAttributeNames={"#attr": field_name},
                ExpressionAttributeValues={":val": val_to_save},
            )
            return True
        except ClientError as e:
            logger.error(
                "DynamoDB field update failed: table=%s field=%s error=%s",
                self.table_name,
                field_name,
                e,
            )
            return False

    def save_batch(self, items: List[T]) -> bool:
        """Bulk write items into DynamoDB."""
        if not items:
            return True

        try:
            with self.table.batch_writer() as batch:
                for item in items:
                    item_to_save = self._serialize(item)
                    batch.put_item(Item=item_to_save)
            return True
        except ClientError as e:
            logger.error("DynamoDB batch write failed: table=%s error=%s", self.table_name, e)
            return False

    def delete(
        self,
        partition_value: str,
        sort_value: Optional[str] = None
    ) -> bool:
        """Delete an item by primary key."""
        key = {self.partition_key: partition_value}
        if self.sort_key and sort_value:
            key[self.sort_key] = sort_value

        try:
            self.table.delete_item(Key=key)
            return True
        except ClientError as e:
            logger.error("DynamoDB delete failed: table=%s error=%s", self.table_name, e)
            return False

    def scan_all(self) -> List[T]:
        """Scan and retrieve all items in the table (handles pagination)."""
        items: List[Any] = []
        try:
            response = self.table.scan()
            items.extend(response.get("Items", []))

            while "LastEvaluatedKey" in response:
                response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
                items.extend(response.get("Items", []))

            return [self._deserialize(item) for item in items]
        except ClientError as e:
            logger.error("DynamoDB scan failed: table=%s error=%s", self.table_name, e)
            return []