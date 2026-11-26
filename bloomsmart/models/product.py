from decimal import Decimal
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


class ProductType(str, Enum):
    CP_SERIES = "CP 系列"
    SNACKS = "各式小食"
    SEAFOOD = "海產類"
    SAUSAGE_DUMPLINGS = "香腸/餃子"
    BALLS = "丸類"
    HOTPOT_SLICES = "火鍋片類"
    HOTPOT_INGREDIENTS = "火鍋配料"
    SOUP_BASE = "湯底"
    BBQ_MARINATED_MEAT = "燒烤醃肉"
    BBQ_MEAT = "燒烤肉類"
    BBQ_ACCESSORIES = "燒烤食品配料類"
    BBQ_TOOLS = "燒烤工具"
    POULTRY = "家禽類"
    BEEF = "牛肉類"
    PORK = "豬肉類"
    MUTTON = "羊肉類"
    HORMONE_FREE = "無激素食品"
    HALAL = "清真食品"
    PET_FOOD = "寵物食品"
    HOT_SELLING = "🔥熱賣產品"
    LIMITED_TIME = "⚡期間限定"


class ProductUnit(str, Enum):
    POUND = "磅"
    KILOGRAM = "公斤"
    BOX = "盒"
    PACK = "包"
    PIECE = "支"
    SHEET = "張"
    ITEM = "隻"


_LEGACY_PRODUCT_TYPE_VALUES = {
    "熱賣產品": ProductType.HOT_SELLING.value,
    "期間限定": ProductType.LIMITED_TIME.value,
}


class ProductModel(BaseModel):
    product_id: str
    is_suspend: bool = False
    en_name: str = ""
    cn_name: str = ""
    product_type: list[ProductType] = Field(default_factory=list)
    display_order: int = 0
    unit: ProductUnit = ProductUnit.PACK
    price: Decimal = Decimal("0")
    photo_url: str = ""
    product_description: str = ""
    marketing_strategy: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_product_types(cls, value: Any) -> Any:
        if isinstance(value, dict):
            payload = dict(value)
            raw_types = payload.get("product_type", [])
            if isinstance(raw_types, str):
                raw_types = raw_types.split("|")
            if isinstance(raw_types, list):
                payload["product_type"] = [
                    _LEGACY_PRODUCT_TYPE_VALUES.get(item.strip(), item.strip())
                    for item in raw_types
                    if item.strip()
                ]
            raw_unit = str(payload.get("unit", "")).strip()
            payload["unit"] = raw_unit or ProductUnit.PACK.value
            return payload
        return value
