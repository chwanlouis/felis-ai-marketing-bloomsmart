from pathlib import Path
from string import Template
from html import escape
from jinja2 import Environment, FileSystemLoader, select_autoescape
from models.user import UserModel
from tools.permissions import Permission, has_permission


_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "templates"
_STATIC_PATH = _TEMPLATES_PATH.parent / "static"
_CSS_PATH = _STATIC_PATH / "style.css"
CRITICAL_CSS = _CSS_PATH.read_text(encoding="utf-8")
_JINJA_ENVIRONMENT = Environment(
    loader=FileSystemLoader(_TEMPLATES_PATH),
    autoescape=select_autoescape(("html", "xml")),
)


APP_ICON_URL = "https://aws-felis-ai-marketing-bloomsmart.s3.ap-southeast-2.amazonaws.com/static/felis_icon.jpeg"


def get_login_html(error_msg: str = "") -> str:
    error_block = f'<div class="error-msg">{error_msg}</div>' if error_msg else ""
    return _render_template(
        "login.html",
        error_block=error_block,
    )


def get_registration_html(error_msg: str = "") -> str:
    return _render_template(
        "registration.html",
        error_block=f'<div class="error-msg">{escape(error_msg)}</div>' if error_msg else "",
    )


def render_page(
    title: str,
    active_tab: str,
    content_html: str,
    current_user: UserModel,
    active_subtab: str = "",
) -> str:
    active_prod = "active" if active_tab == "products" else ""
    active_wa = "active" if active_tab == "whatsapp" else ""
    return _render_template(
        "page.html",
        title=title,
        content_html=content_html,
        active_prod=active_prod,
        active_wa=active_wa,
        active_quotation="active" if active_subtab == "quotation" else "",
        active_promotion="active" if active_subtab == "promotion" else "",
        sidebar_html=_render_sidebar(current_user, active_tab, active_subtab),
    )


def render_content_template(template_name: str, **context: object) -> str:
    """Render a page-content template for use inside the shared layout."""
    return _JINJA_ENVIRONMENT.get_template(template_name).render(**context)


def _render_template(template_name: str, **values: str) -> str:
    template_path = _TEMPLATES_PATH / template_name
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.substitute(
        critical_css=CRITICAL_CSS,
        app_icon_url=APP_ICON_URL,
        **values,
    )


def _render_sidebar(
    current_user: UserModel,
    active_tab: str,
    active_subtab: str,
) -> str:
    def allowed(permission: Permission) -> bool:
        return has_permission(current_user, permission)

    links = []
    if allowed(Permission.SHOP_READ):
        links.append('<li><a href="/shop/all">網上商店</a></li>')
    if allowed(Permission.ORDER_READ_OWN):
        links.append('<li><a href="/shop/orders">我的訂單</a></li>')
    if allowed(Permission.PRODUCT_READ):
        links.append(
            f'<li><a href="/products" class="{"active" if active_tab == "products" else ""}">'
            "產品目錄管理</a></li>"
        )
        links.append(
            f'<li><a href="/product/export" class="{"active" if active_tab == "product_export" else ""}">'
            "產品目錄 PDF</a></li>"
        )
    if allowed(Permission.ORDER_READ_ANY):
        links.append('<li><a href="/orders">訂單管理</a></li>')
    if allowed(Permission.CUSTOMER_READ):
        links.append(
            f'<li><a href="/customers" class="{"active" if active_tab == "customers" else ""}">'
            "客戶管理</a></li>"
        )
    if allowed(Permission.WHATSAPP_READ):
        links.append(
            f'<li><a href="/whatsapp" class="{"active" if active_tab == "whatsapp" else ""}">'
            "WhatsApp AI自動化</a><ul class=\"nav-submenu\">"
            f'<li><a href="/whatsapp/quotation" class="{"active" if active_subtab == "quotation" else ""}">'
            "產品報價</a></li>"
            f'<li><a href="/whatsapp/promotion" class="{"active" if active_subtab == "promotion" else ""}">'
            "產品推廣</a></li></ul></li>"
        )
    return "".join(links)
