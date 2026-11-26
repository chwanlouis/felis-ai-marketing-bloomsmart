import json
import uuid
from io import BytesIO
from typing import Annotated, List
from urllib.parse import quote
from fastapi import APIRouter, Depends, Form, UploadFile, File, Query, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from tools.s3_client import upload_photo_to_s3
from tools.logger import get_logger
from repository.product import product_repository
from models.product import ProductType, ProductUnit
from tools.webpage import render_content_template, render_page
from models.user import UserModel
from tools.permissions import Permission, PermissionChecker
from services.product_pdf import build_product_catalog_pdf


router = APIRouter()
logger = get_logger(__name__)

PRODUCT_TYPES = [product_type.value for product_type in ProductType]

UNITS = [product_unit.value for product_unit in ProductUnit]
ProductCatalogUser = Annotated[
    UserModel,
    Depends(PermissionChecker(Permission.PRODUCT_READ)),
]
ProductManager = Annotated[
    UserModel,
    Depends(PermissionChecker(Permission.PRODUCT_UPDATE)),
]


@router.get("/products", response_class=HTMLResponse)
def products_page(
    current_user: ProductCatalogUser,
    edit_id: str = Query(default=None),
):
    products = product_repository.list_products()
    product_views = []
    for product in products:
        raw_types = str(product.get("product_type", ""))
        types = [value.strip() for value in raw_types.split("|") if value.strip()]
        description = str(product.get("product_description", "") or "")
        cn_name = str(product.get("cn_name", "") or "")
        en_name = str(product.get("en_name", "") or "")
        unit = str(product.get("unit", "") or "").strip()
        price = product.get("price", "")
        price_display = (
            f"{price:.2f}" if isinstance(price, (int, float)) else str(price)
        )
        view_product = json.loads(json.dumps(dict(product), default=str))
        view_product.update({
            "types": types,
            "photo_urls": [
                url.strip()
                for url in str(product.get("photo_url", "") or "").split("|")
                if url.strip()
            ],
            "description": description,
            "cn_name": cn_name,
            "en_name": en_name,
            "unit": unit,
            "price_display": price_display,
            "display_name": cn_name or en_name,
            "search_terms": (
                f"{cn_name} {en_name} {description} {' '.join(types)} "
                f"{unit} {price_display} {product.get('id', '')}"
            ).lower(),
        })
        product_views.append(view_product)
    content = render_content_template(
        "product.html",
        products=product_views,
        product_types=PRODUCT_TYPES,
        units=UNITS,
    )
    return HTMLResponse(
        render_page("產品目錄管理", "products", content, current_user=current_user)
    )


@router.get("/product/export", response_class=HTMLResponse)
def product_export_page(current_user: ProductCatalogUser):
    content = render_content_template(
        "product_export.html",
        product_types=PRODUCT_TYPES,
    )
    return HTMLResponse(
        render_page(
            "產品目錄 PDF",
            "product_export",
            content,
            current_user=current_user,
        )
    )


@router.get("/product/exportPdf/{product_type:path}")
def export_product_pdf(
        current_user: ProductCatalogUser,
        product_type: str,
):
    selected_type = product_type.strip() or "all"
    if selected_type != "all" and selected_type not in PRODUCT_TYPES:
        raise HTTPException(status_code=404, detail="Product type not found")

    products = [
        product
        for product in product_repository.list_products()
        if product.get("is_suspend") is not True
        and (
            selected_type == "all"
            or selected_type in {
                value.strip()
                for value in str(product.get("product_type", "")).split("|")
                if value.strip()
            }
        )
    ]
    pdf_content = build_product_catalog_pdf(products, selected_type)
    filename = f"product-catalog-{selected_type.replace(' ', '-')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                'attachment; filename="product-catalog.pdf"; '
                f"filename*=UTF-8''{quote(filename)}"
            ),
        },
    )


@router.post("/products/add")
async def add_product(
        current_user: ProductCatalogUser,
        en_name: str = Form(...),
        cn_name: str = Form(...),
        product_description: str = Form(default=""),
        marketing_strategy: str = Form(default=""),
        display_order: int = Form(default=0, ge=0),
        product_type: List[str] = Form(default=[]),
        unit: str = Form(...),
        price: float = Form(...),
        photos: List[UploadFile] = File([]),
):
    valid_types = [ProductType(t).value for t in product_type if t in PRODUCT_TYPES]
    combined_type = "|".join(valid_types) if valid_types else PRODUCT_TYPES[0]

    unit_clean = unit.strip()
    if unit_clean not in UNITS:
        unit_clean = UNITS[0]

    photo_urls = []
    for photo in photos:
        if photo and photo.filename:
            url = upload_photo_to_s3(photo)
            if url:
                photo_urls.append(url)
    combined_photo_url = "|".join(photo_urls)

    new_product = {
        "id": str(uuid.uuid4())[:8],
        "en_name": en_name,
        "cn_name": cn_name,
        "product_description": product_description.strip(),
        "marketing_strategy": marketing_strategy.strip(),
        "display_order": display_order,
        "product_type": combined_type,
        "unit": unit_clean,
        "price": price,
        "photo_url": combined_photo_url,
    }
    if not product_repository.save_product(new_product):
        logger.error("Product creation failed")
        raise RuntimeError("Failed to save product to DynamoDB.")

    logger.info("Product created: product_id=%s", new_product["id"])
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/products/edit/{product_id}", response_class=HTMLResponse)
def edit_product_redirect(
    current_user: ProductCatalogUser,
    product_id: str,
):
    return RedirectResponse(url=f"/products?edit_id={product_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/products/edit/{product_id}")
async def edit_product(
        current_user: ProductCatalogUser,
        product_id: str,
        en_name: str = Form(...),
        cn_name: str = Form(...),
        product_description: str = Form(default=""),
        marketing_strategy: str = Form(default=""),
        display_order: int = Form(default=0, ge=0),
        product_type: List[str] = Form(default=[]),
        unit: str = Form(...),
        price: float = Form(...),
        existing_photos: str = Form(default=""),
        photos: List[UploadFile] = File([]),
):
    valid_types = [ProductType(t).value for t in product_type if t in PRODUCT_TYPES]
    combined_type = "|".join(valid_types) if valid_types else PRODUCT_TYPES[0]

    unit_clean = unit.strip()
    if unit_clean not in UNITS:
        unit_clean = UNITS[0]

    kept_photo_urls = [u.strip() for u in existing_photos.split("|") if u.strip()]

    for photo in photos:
        if photo and photo.filename:
            url = upload_photo_to_s3(photo)
            if url:
                kept_photo_urls.append(url)

    combined_photo_url = "|".join(kept_photo_urls)

    product = product_repository.get_product(product_id)
    if product is None:
        raise ValueError(f"Product '{product_id}' was not found.")

    product.update({
        "en_name": en_name,
        "cn_name": cn_name,
        "product_description": product_description.strip(),
        "marketing_strategy": marketing_strategy.strip(),
        "display_order": display_order,
        "product_type": combined_type,
        "unit": unit_clean,
        "price": price,
        "photo_url": combined_photo_url,
    })
    if not product_repository.save_product(product):
        logger.error("Product update failed: product_id=%s", product_id)
        raise RuntimeError("Failed to update product in DynamoDB.")
    logger.info("Product updated: product_id=%s", product_id)
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/products/delete/{product_id}")
async def delete_product(
        current_user: ProductCatalogUser,
        product_id: str,
):
    if not product_repository.delete_product(product_id):
        logger.error("Product deletion failed: product_id=%s", product_id)
        raise RuntimeError("Failed to delete product from DynamoDB.")

    logger.info("Product deleted: product_id=%s", product_id)
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/products/suspend/{product_id}")
def suspend_product(
        current_user: ProductManager,
        product_id: str,
        request: Request,
):
    product = product_repository.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    product["is_suspend"] = not bool(product.get("is_suspend", False))
    if not product_repository.save_product(product):
        logger.error("Product suspension update failed: product_id=%s", product_id)
        raise RuntimeError("Failed to update product suspension in DynamoDB.")

    logger.info(
        "Product suspension updated: product_id=%s is_suspend=%s",
        product_id,
        product["is_suspend"],
    )
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"is_suspend": product["is_suspend"]})
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/products/delete")
async def delete_product_form(
        current_user: ProductCatalogUser,
        product_id: str = Form(...),
):
    return await delete_product(product_id=product_id, current_user=current_user)