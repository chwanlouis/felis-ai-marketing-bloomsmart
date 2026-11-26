import uuid
from typing import Any, Dict, List, Optional
from .base_repository import DynamoDBBaseRepository
from models.product import ProductModel


class ProductRepository(DynamoDBBaseRepository[Dict[str, Any]]):
    def __init__(self):
        super().__init__(
            table_name_env_key="DYNAMODB_TABLE_PRODUCT",
            default_table_name="felis_products",
            partition_key="product_id"
        )

    def _normalize_product(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize schema attributes including the new marketing_strategy field."""
        product_id = str(
            item.get("product_id", item.get("id", ""))
        ).strip() or str(uuid.uuid4())[:8]
        raw_price = item.get("price", 0.0)
        try:
            price_val = float(raw_price) if raw_price is not None else 0.0
        except (ValueError, TypeError):
            price_val = 0.0
        try:
            display_order = int(item.get("display_order", 0) or 0)
        except (ValueError, TypeError):
            display_order = 0

        model = ProductModel.model_validate({
            "product_id": product_id,
            "is_suspend": item.get("is_suspend", False),
            "en_name": str(item.get("en_name", "")).strip(),
            "cn_name": str(item.get("cn_name", "")).strip(),
            "product_type": item.get("product_type", ""),
            "display_order": display_order,
            "unit": str(item.get("unit", "")).strip(),
            "price": price_val,
            "photo_url": str(item.get("photo_url", "")).strip(),
            "product_description": str(item.get("product_description", "")).strip(),
            "marketing_strategy": str(item.get("marketing_strategy", "")).strip(),
        })
        normalized = model.model_dump(mode="json")
        normalized["id"] = product_id
        normalized["product_type"] = "|".join(
            product_type.value for product_type in model.product_type
        )

        if not normalized["en_name"] and normalized["cn_name"]:
            normalized["en_name"] = normalized["cn_name"]
        elif not normalized["cn_name"] and normalized["en_name"]:
            normalized["cn_name"] = normalized["en_name"]

        return normalized

    def save_product(self, product: Dict[str, Any]) -> bool:
        normalized = self._normalize_product(product)
        return self.save(normalized)

    def list_products(self) -> List[Dict[str, Any]]:
        products = [self._normalize_product(item) for item in self.scan_all()]
        return sorted(
            products,
            key=lambda product: (
                product.get("display_order", 0),
                product.get("cn_name", ""),
                product.get("en_name", ""),
            ),
        )

    def save_products(self, products: List[Dict[str, Any]]) -> bool:
        normalized_products = [self._normalize_product(product) for product in products]
        return self.save_batch(normalized_products)

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        item = self.get_by_id(product_id)
        return self._normalize_product(item) if item else None

    def delete_product(self, product_id: str) -> bool:
        return self.delete(partition_value=product_id)

    def update_marketing_strategy(self, product_id: str, strategy: str) -> bool:
        return self.update_field(
            partition_value=product_id,
            field_name="marketing_strategy",
            field_value=strategy
        )


product_repository = ProductRepository()
