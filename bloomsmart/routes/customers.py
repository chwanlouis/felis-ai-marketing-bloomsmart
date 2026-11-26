from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from models.user import UserModel
from repository.user import user_repository
from services.customer_service import search_customers
from tools.permissions import Permission, PermissionChecker
from tools.webpage import render_content_template, render_page


router = APIRouter()
AdminUser = Annotated[
    UserModel,
    Depends(PermissionChecker(Permission.CUSTOMER_READ)),
]


@router.get("/customers", response_class=HTMLResponse)
def customers_page(
    current_user: AdminUser,
    query: str = Query(default="", alias="q", max_length=100),
) -> HTMLResponse:
    customers = search_customers(user_repository.list_users(), query)
    customer_views = [
        {
            "user_id": customer.user_id,
            "username": customer.username,
            "email": customer.email or "",
            "phone_number": customer.phone_number,
            "is_active": customer.is_active,
        }
        for customer in customers
    ]
    content = render_content_template(
        "customers.html",
        query=query,
        customers=customer_views,
    )
    return HTMLResponse(
        render_page(
            "客戶管理",
            "customers",
            content,
            current_user=current_user,
        )
    )
