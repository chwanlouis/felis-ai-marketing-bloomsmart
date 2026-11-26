import asyncio
import os
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from mangum import Mangum
from routes.auth import router as auth_router
from tools.webpage import APP_ICON_URL
from routes.products import router as products_router
from routes.whatsapp import router as whatsapp_router
from routes.shop import router as shop_router
from routes.customers import router as customers_router
from tools.logger import get_logger


logger = get_logger(__name__)
app = FastAPI(title="Felis AI Marketing - Workspace")
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
    name="static",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> PlainTextResponse:
    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
    )
    return PlainTextResponse(
        f"{type(exc).__name__}: {exc}",
        status_code=500,
    )


# Web App Manifest for Android & PWA
@app.get("/manifest.json", response_class=JSONResponse)
def get_manifest():
    return {
        "name": "Felis AI 工作區",
        "short_name": "Felis AI",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0b0f19",
        "theme_color": "#111827",
        "icons": [
            {
                "src": APP_ICON_URL,
                "sizes": "192x192",
                "type": "image/jpeg",
                "purpose": "any maskable"
            },
            {
                "src": APP_ICON_URL,
                "sizes": "512x512",
                "type": "image/jpeg",
                "purpose": "any maskable"
            }
        ]
    }

# Include Routers
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(whatsapp_router)
app.include_router(shop_router)
app.include_router(customers_router)

# Initialize Mangum handler
handler = Mangum(app)


def lambda_handler(event, context):
    """Event loop wrapper for Python 3.14+ compatibility"""
    logger.info("Lambda request received")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return handler(event, context)
