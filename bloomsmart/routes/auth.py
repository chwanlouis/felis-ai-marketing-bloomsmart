from urllib.parse import urlencode
from enum import StrEnum
from botocore.exceptions import BotoCoreError, ClientError
from typing import Annotated
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from repository.session import DEFAULT_SESSION_EXPIRE_SECONDS, session_repository
from repository.user import user_repository
from tools.webpage import (
    get_login_html,
    get_registration_html,
)
from models.auth import EmailLoginRequest, SetPasswordRequest
from models.user import UserModel, UserRole
from tools.logger import get_logger
from tools.permissions import get_current_user


router = APIRouter()
logger = get_logger(__name__)


def _landing_url(role: str | UserRole) -> str:
    return (
        "/products"
        if role in {
            UserRole.ROOT,
            UserRole.ADMIN,
            UserRole.ROOT.value,
            UserRole.ADMIN.value,
        }
        else "/shop/all"
    )


def _session_response(user: UserModel) -> RedirectResponse:
    session = session_repository.create_session(user=user)
    if not session:
        logger.error("Login session creation failed: user_id=%s", user.user_id)
        return RedirectResponse(url="/?error=session", status_code=status.HTTP_303_SEE_OTHER)

    landing_url = _landing_url(user.role)
    response = RedirectResponse(url=landing_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="session",
        value=session.session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=DEFAULT_SESSION_EXPIRE_SECONDS,
    )
    logger.info("Login session cookie issued: user_id=%s", user.user_id)
    return response


@router.get("/", response_class=HTMLResponse)
def login_page(error: str = Query(default=""), session: str = Cookie(default=None)):
    if session:
        active_session = session_repository.get_valid_session(session)
        if active_session:
            return RedirectResponse(
                url=_landing_url(active_session.role),
                status_code=status.HTTP_303_SEE_OTHER,
            )
    messages = {
        "1": "帳號、電郵地址、手機號碼或密碼錯誤，請重新再試。",
        "session": "無法建立登入工作階段，請稍後再試。",
    }
    return get_login_html(error_msg=messages.get(error, ""))


@router.post("/login")
def handle_login(identifier: str = Form(...), password: str = Form(...)):
    user = user_repository.verify_identifier_password(identifier, password)
    if not user:
        logger.warning("Password login failed")
        return RedirectResponse(url="/?error=1", status_code=status.HTTP_303_SEE_OTHER)

    logger.info("Password login succeeded: user_id=%s", user.user_id)
    return _session_response(user)


@router.post("/login/email")
def handle_email_login(payload: EmailLoginRequest):
    user = user_repository.get_by_email(payload.email)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    stored_hash = user.password_hash
    if not stored_hash or not user_repository.verify_credentials(user.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _session_response(user)


@router.post("/set-password")
def handle_set_password(
    payload: SetPasswordRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
):
    if current_user.user_id != payload.user_id:
        raise HTTPException(status_code=401, detail="Authenticated session required")
    if not user_repository.update_password(payload.user_id, payload.password):
        raise HTTPException(status_code=500, detail="Unable to set password")
    return {"ok": True}


class RegisterError(StrEnum):
    INVALID_OR_DUPLICATE = "1"
    SYSTEM_ERROR = "2"


ERROR_MESSAGES: dict[RegisterError, str] = {
    RegisterError.INVALID_OR_DUPLICATE: "手機號碼格式不正確，或此手機號碼已經註冊。",
    RegisterError.SYSTEM_ERROR: "系統暫時無法完成註冊，請稍後再試。",
}


def _redirect(path: str, **params: str) -> RedirectResponse:
    clean_params = {k: v for k, v in params.items() if v}
    url = f"{path}?{urlencode(clean_params)}" if clean_params else path
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/register", response_class=HTMLResponse)
def registration_page(
    error: str = Query(default=""),
    detail: str = Query(default=""),
):
    try:
        err_enum = RegisterError(error)
        message = ERROR_MESSAGES[err_enum]
        if detail:
            message = f"{message} 詳細：{detail}"
    except ValueError:
        message = ""

    return get_registration_html(error_msg=message)


@router.post("/register")
def register_user(
    username: str = Form(...),
    email: str = Form(default=""),
    password: str = Form(...),
    phone_number: str = Form(...),
):
    try:
        user = user_repository.create_user(
            username=username,
            email=email,
            phone_number=phone_number,
            password=password,
        )
    except ValidationError as exc:
        logger.exception("Registration validation failed for username=%s", username)
        exception_detail = f"{type(exc).__name__}: {exc}"[:500]
        return _redirect(
            "/register",
            error=RegisterError.INVALID_OR_DUPLICATE,
            detail=exception_detail
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Registration persistence failed for username=%s", username)
        exception_detail = f"{type(exc).__name__}: {exc}"[:500]
        return _redirect(
            "/register",
            error=RegisterError.SYSTEM_ERROR,
            detail=exception_detail,
        )

    if not user:
        logger.warning("Registration rejected: duplicate or invalid username=%s", username)
        return _redirect(
            "/register",
            error=RegisterError.INVALID_OR_DUPLICATE,
            detail="Username, email, or WhatsApp number already registered or invalid.",
        )

    return _redirect("/")


@router.get("/logout")
def logout(session: str = Cookie(default=None)):
    if session:
        session_repository.delete_session(session)
        logger.info("Logout completed")
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session")
    return response
