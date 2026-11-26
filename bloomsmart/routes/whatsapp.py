import urllib.parse
from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from repository.product import product_repository
from tools.webpage import render_content_template, render_page
from tools.logger import get_logger
from models.user import UserModel
from tools.permissions import Permission, PermissionChecker

router = APIRouter()
logger = get_logger(__name__)
WhatsAppUser = Annotated[
    UserModel,
    Depends(PermissionChecker(Permission.WHATSAPP_READ)),
]


@router.get("/whatsapp", response_class=HTMLResponse)
def whatsapp_page(current_user: WhatsAppUser):
    return RedirectResponse(url="/whatsapp/quotation", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/whatsapp/quotation", response_class=HTMLResponse)
def quotation_page(
    current_user: WhatsAppUser,
    filter_type: str = Query("all"),
):

    products = product_repository.list_products()

    types = sorted({str(p.get("product_type", "一般")) for p in products})

    filtered = (
        products
        if filter_type == "all"
        else [p for p in products if p.get("product_type") == filter_type]
    )

    msg_lines = ["📋 *成俊凍肉 — 每日報價單* 📋\n"]
    for idx, p in enumerate(filtered, 1):
        cn = p.get('cn_name', '')
        en = p.get('en_name', '')
        display_name = f"{cn} ({en})" if cn and en else (cn or en)
        price_val = p.get('price', '')
        price_display = f"{price_val:.2f}" if isinstance(price_val, (int, float)) else str(price_val)
        msg_lines.append(
            f"{idx}. *{display_name}*\n   💰 ${price_display} / {p.get('unit')}"
        )

    msg_lines.append("\n_請回覆所需數量以確認訂單！_")
    quotation_text = "\n".join(msg_lines)

    encoded_wa_text = urllib.parse.quote(quotation_text)
    whatsapp_link = f"https://wa.me/?text={encoded_wa_text}"
    content = render_content_template(
        "whatsapp_quotation.html",
        filter_type=filter_type,
        product_types=types,
        quotation_text=quotation_text,
        whatsapp_link=whatsapp_link,
    )
    return render_page(
        "產品報價",
        "whatsapp",
        content,
        active_subtab="quotation",
        current_user=current_user,
    )


@router.get("/whatsapp/promotion", response_class=HTMLResponse)
def promotion_page(
    current_user: WhatsAppUser,
    filter_type: str = Query("all"),
):

    products = product_repository.list_products()
    types = sorted({str(p.get("product_type", "一般")) for p in products})
    filtered = (
        products
        if filter_type == "all"
        else [p for p in products if p.get("product_type") == filter_type]
    )

    msg_lines = ["📣 *成俊凍肉 — 產品推廣* 📣\n"]
    for product in filtered:
        strategy = str(product.get("marketing_strategy", "") or "").strip()
        if not strategy:
            continue
        cn = str(product.get("cn_name", "") or "").strip()
        en = str(product.get("en_name", "") or "").strip()
        display_name = f"{cn} ({en})" if cn and en else (cn or en)
        msg_lines.append(f"*{display_name}*\n{strategy}\n")

    if len(msg_lines) == 1:
        msg_lines.append("目前沒有符合條件且已設定營銷策略的產品。")
    else:
        msg_lines.append("_歡迎查詢產品詳情及訂購！_")

    promotion_text = "\n".join(msg_lines)
    encoded_wa_text = urllib.parse.quote(promotion_text)
    whatsapp_link = f"https://wa.me/?text={encoded_wa_text}"
    content = render_content_template(
        "whatsapp_promotion.html",
        filter_type=filter_type,
        product_types=types,
        promotion_text=promotion_text,
        whatsapp_link=whatsapp_link,
    )
    return render_page(
        "產品推廣",
        "whatsapp",
        content,
        active_subtab="promotion",
        current_user=current_user,
    )