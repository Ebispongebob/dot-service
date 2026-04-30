"""
Dot Service — FastAPI web service for controlling the Quote/0 e-ink display.

Provides REST endpoints that proxy and enhance the Dot. cloud API,
allowing you to deploy this service on any machine and control
the Quote e-ink screen over HTTP.

Also serves a visual web UI (Jinja2 templates) so non-technical users
can manage the device from a browser.
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .dot_client import DotClient, DotClientError
from .image_utils import (
    bytes_to_image,
    image_to_base64,
    render_text_to_image,
    resize_image_to_screen,
)
from .lark_bridge import LarkNotifyBridge
from .models import (
    DitherKernel,
    DitherType,
    SendImageRequest,
    SendTextRequest,
    ServiceResponse,
)

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────

_APP_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _APP_DIR / "templates"
_STATIC_DIR = _APP_DIR / "static"
_SETTINGS_FILE = _APP_DIR.parent / "ui_settings.json"

# ── Shared client instance ──────────────────────────────────────────

_dot_client: Optional[DotClient] = None
_lark_bridge: Optional[LarkNotifyBridge] = None


def _get_client() -> DotClient:
    global _dot_client
    if _dot_client is None:
        _dot_client = DotClient()
    return _dot_client


def _resolve_device(device_id: Optional[str]) -> str:
    """Return the given device_id or fall back to ui_settings → .env → error."""
    if device_id:
        return device_id
    # Fallback 1: UI-saved settings (ui_settings.json)
    ui_device = _load_ui_settings().get("device_id")
    if ui_device:
        return ui_device
    # Fallback 2: .env configuration
    default = get_settings().dot_default_device_id
    if default:
        return default
    raise HTTPException(
        status_code=400,
        detail="device_id is required (no default configured)",
    )


def _get_lark_bridge() -> LarkNotifyBridge:
    """Return the singleton Lark notification bridge."""
    global _lark_bridge
    if _lark_bridge is None:
        settings = _build_lark_settings()
        _lark_bridge = LarkNotifyBridge(
            settings, _get_client, lambda: _resolve_device(None)
        )
    return _lark_bridge


def _build_lark_settings() -> "Settings":
    """Build a Settings instance that merges .env + ui_settings.json."""
    from .config import Settings
    base = Settings().model_dump()
    ui = _load_ui_settings()
    for key, value in ui.items():
        if key not in base:
            continue
        default = base[key]
        if isinstance(default, bool):
            if isinstance(value, bool):
                base[key] = value
            elif isinstance(value, str):
                base[key] = value.lower() in ("true", "1", "yes")
        elif isinstance(default, int):
            if isinstance(value, (int, float)):
                base[key] = int(value)
            elif isinstance(value, str) and value.strip():
                try:
                    base[key] = int(value)
                except ValueError:
                    pass
        elif isinstance(default, str):
            if value is not None:
                base[key] = str(value)
    return Settings(**base)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Dot Service starting up ...")
    bridge = _get_lark_bridge()
    await bridge.start()
    try:
        yield
    finally:
        await bridge.stop()
        if _dot_client:
            await _dot_client.close()
        logger.info("Dot Service shut down.")


# ── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Dot Service",
    description=(
        "HTTP service for controlling the MindReset Dot. Quote/0 e-ink display. "
        "Deploy on any machine and push text or images to the screen via REST API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Error handler ───────────────────────────────────────────────────


def _handle_dot_error(e: DotClientError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


# ── UI settings persistence ─────────────────────────────────────────


def _load_ui_settings() -> dict:
    """Load UI-saved settings from ui_settings.json (if exists)."""
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save_ui_settings(data: dict) -> None:
    # Merge with existing settings so we don't erase other sections.
    existing = _load_ui_settings()
    existing.update(data)
    _SETTINGS_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), "utf-8"
    )


# ═══════════════════════════════════════════════════════════════════
#  Web UI pages (Jinja2 templates)
# ═══════════════════════════════════════════════════════════════════


@app.get("/", tags=["ui"], include_in_schema=False)
async def page_dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"request": request, "active": "dashboard"},
    )


@app.get("/ui/text", tags=["ui"], include_in_schema=False)
async def page_text(request: Request):
    return templates.TemplateResponse(
        request,
        "text.html",
        {"request": request, "active": "text"},
    )


@app.get("/ui/image", tags=["ui"], include_in_schema=False)
async def page_image(request: Request):
    return templates.TemplateResponse(
        request,
        "image.html",
        {"request": request, "active": "image"},
    )


@app.get("/ui/settings", tags=["ui"], include_in_schema=False)
async def page_settings(request: Request):
    s = get_settings()
    saved = _load_ui_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "active": "settings",
            "api_key": saved.get("api_key", s.dot_api_key),
            "device_id": saved.get("device_id", s.dot_default_device_id),
            "base_url": saved.get("base_url", s.dot_api_base_url),
        },
    )


@app.get("/ui/lark", tags=["ui"], include_in_schema=False)
async def page_lark_notify(request: Request):
    return templates.TemplateResponse(
        request,
        "lark_notify.html",
        {"request": request, "active": "lark"},
    )


@app.post("/ui/api/settings", tags=["ui"], include_in_schema=False)
async def save_settings(request: Request):
    """Save UI settings to ui_settings.json and hot-reload the client."""
    body = await request.json()
    data = {
        "api_key": body.get("api_key", ""),
        "device_id": body.get("device_id", ""),
        "base_url": body.get("base_url", "https://dot.mindreset.tech"),
    }
    _save_ui_settings(data)

    # Hot-reload the DotClient with new credentials
    global _dot_client
    if _dot_client:
        await _dot_client.close()
    _dot_client = DotClient(
        api_key=data["api_key"] or None,
        base_url=data["base_url"] or None,
    )

    return {"success": True, "message": "Settings saved"}


# ═══════════════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════════════


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
#  Lark / Feishu notification bridge
# ═══════════════════════════════════════════════════════════════════


@app.get("/lark/notify/status", tags=["lark"], response_model=ServiceResponse)
async def lark_notify_status():
    """Inspect the Lark polling notification bridge status."""
    return ServiceResponse(success=True, message="ok", data=_get_lark_bridge().status())


@app.post("/lark/notify/poll", tags=["lark"], response_model=ServiceResponse)
async def lark_notify_poll(
    notify: bool = Query(True, description="Whether matched messages should be sent to Dot"),
):
    """Poll configured Lark message sources once."""
    bridge = _get_lark_bridge()
    if not bridge.sources:
        return ServiceResponse(
            success=False,
            message="No Lark sources configured",
            data=bridge.status(),
        )
    data = await bridge.poll_once(notify=notify)
    return ServiceResponse(success=True, message="Lark poll finished", data=data)


@app.post("/lark/notify/test", tags=["lark"], response_model=ServiceResponse)
async def lark_notify_test(
    title: str = Query("飞书通知"),
    message: str = Query("这是一条 Dot Service 飞书通知测试"),
    signature: str = Query("Lark Bridge"),
):
    """Send a test notification through the same Dot path used by Lark polling."""
    try:
        data = await _get_lark_bridge().send_test_notification(
            title=title, message=message, signature=signature
        )
        return ServiceResponse(success=True, message="Test notification sent", data=data)
    except DotClientError as e:
        raise _handle_dot_error(e)


@app.post("/ui/api/lark_settings", tags=["ui"], include_in_schema=False)
async def save_lark_settings(request: Request):
    """Save Lark notification settings and hot-reload the bridge."""
    body = await request.json()
    data = {
        "lark_notify_enabled": body.get("enabled", False),
        "lark_notify_identity": body.get("identity", "user"),
        "lark_notify_profile": body.get("profile", ""),
        "lark_notify_chat_ids": body.get("chat_ids", ""),
        "lark_notify_user_ids": body.get("user_ids", ""),
        "lark_notify_keywords": body.get("keywords", ""),
        "lark_notify_mention_ids": body.get("mention_ids", ""),
        "lark_notify_monitor_all": body.get("monitor_all", False),
        "lark_notify_poll_interval_seconds": body.get("poll_interval_seconds", 60),
        "lark_notify_lookback_minutes": body.get("lookback_minutes", 10),
        "lark_notify_max_messages_per_push": body.get("max_messages_per_push", 3),
        "lark_notify_max_message_chars": body.get("max_message_chars", 48),
        "lark_notify_skip_existing_on_start": body.get("skip_existing_on_start", True),
        "lark_notify_dot_title": body.get("dot_title", "飞书通知"),
        "lark_notify_dot_signature": body.get("dot_signature", "Lark Bridge"),
    }
    _save_ui_settings(data)

    # Rebuild settings from env + ui_settings and reconfigure bridge
    new_settings = _build_lark_settings()
    global _lark_bridge
    if _lark_bridge and _lark_bridge.running:
        await _lark_bridge.stop()
    _lark_bridge = LarkNotifyBridge(
        new_settings, _get_client, lambda: _resolve_device(None)
    )
    has_sources = (
        new_settings.lark_notify_monitor_all
        or new_settings.lark_notify_chat_ids
        or new_settings.lark_notify_user_ids
    )
    if new_settings.lark_notify_enabled and has_sources:
        await _lark_bridge.start()

    return {"success": True, "message": "Lark settings saved and bridge reloaded"}


# ═══════════════════════════════════════════════════════════════════
#  Device management
# ═══════════════════════════════════════════════════════════════════


@app.get("/devices", tags=["devices"], response_model=ServiceResponse)
async def list_devices():
    """List all devices bound to this API key."""
    try:
        data = await _get_client().list_devices()
        return ServiceResponse(success=True, message="ok", data=data)
    except DotClientError as e:
        raise _handle_dot_error(e)


@app.get(
    "/devices/{device_id}/status", tags=["devices"], response_model=ServiceResponse
)
async def get_device_status(device_id: str):
    """Get the status of a specific device (battery, wifi, firmware, render info)."""
    try:
        data = await _get_client().get_device_status(device_id)
        return ServiceResponse(success=True, message="ok", data=data)
    except DotClientError as e:
        raise _handle_dot_error(e)


@app.post("/devices/{device_id}/next", tags=["devices"], response_model=ServiceResponse)
async def switch_next_content(device_id: str):
    """Switch the device to display the next content in its loop."""
    try:
        data = await _get_client().switch_next_content(device_id)
        return ServiceResponse(success=True, message="ok", data=data)
    except DotClientError as e:
        raise _handle_dot_error(e)


@app.get("/devices/{device_id}/tasks", tags=["devices"], response_model=ServiceResponse)
async def list_device_tasks(
    device_id: str,
    task_type: str = Query("loop", description="Task type (currently only 'loop')"),
):
    """List all tasks on the device."""
    try:
        data = await _get_client().list_device_tasks(device_id, task_type)
        return ServiceResponse(success=True, message="ok", data=data)
    except DotClientError as e:
        raise _handle_dot_error(e)


# ═══════════════════════════════════════════════════════════════════
#  Text API
# ═══════════════════════════════════════════════════════════════════


@app.post("/text", tags=["content"], response_model=ServiceResponse)
async def send_text(req: SendTextRequest):
    """
    Send text content to the Quote e-ink screen.

    Fields: title, message, signature, icon (base64 40x40 PNG), link.
    Set refresh_now=false to only update data without immediately rendering.
    """
    device_id = _resolve_device(req.device_id)
    try:
        data = await _get_client().send_text(
            device_id,
            refresh_now=req.refresh_now,
            title=req.title,
            message=req.message,
            signature=req.signature,
            icon=req.icon,
            link=req.link,
            task_key=req.task_key,
        )
        return ServiceResponse(success=True, message="Text sent", data=data)
    except DotClientError as e:
        raise _handle_dot_error(e)


# ═══════════════════════════════════════════════════════════════════
#  Image API
# ═══════════════════════════════════════════════════════════════════


@app.post("/image", tags=["content"], response_model=ServiceResponse)
async def send_image(req: SendImageRequest):
    """
    Send a base64-encoded PNG image (296x152) to the Quote e-ink screen.

    Supports dither control: DIFFUSION / ORDERED / NONE.
    """
    device_id = _resolve_device(req.device_id)
    try:
        data = await _get_client().send_image(
            device_id,
            req.image,
            refresh_now=req.refresh_now,
            link=req.link,
            border=req.border,
            dither_type=req.dither_type.value,
            dither_kernel=req.dither_kernel.value,
            task_key=req.task_key,
        )
        return ServiceResponse(success=True, message="Image sent", data=data)
    except DotClientError as e:
        raise _handle_dot_error(e)


@app.post("/image/upload", tags=["content"], response_model=ServiceResponse)
async def send_image_upload(
    file: UploadFile = File(..., description="Image file (PNG/JPG/BMP/GIF)"),
    device_id: Optional[str] = Form(None),
    refresh_now: bool = Form(True),
    link: Optional[str] = Form(None),
    border: int = Form(0),
    dither_type: DitherType = Form(DitherType.DIFFUSION),
    dither_kernel: DitherKernel = Form(DitherKernel.FLOYD_STEINBERG),
    task_key: Optional[str] = Form(None),
):
    """
    Upload an image file, automatically resize it to 296x152,
    and send it to the Quote e-ink screen.
    """
    device_id = _resolve_device(device_id)
    raw = await file.read()
    try:
        img = bytes_to_image(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    img = resize_image_to_screen(img)
    b64 = image_to_base64(img)

    try:
        data = await _get_client().send_image(
            device_id,
            b64,
            refresh_now=refresh_now,
            link=link,
            border=border,
            dither_type=dither_type.value,
            dither_kernel=dither_kernel.value,
            task_key=task_key,
        )
        return ServiceResponse(
            success=True, message="Image uploaded and sent", data=data
        )
    except DotClientError as e:
        raise _handle_dot_error(e)


# ═══════════════════════════════════════════════════════════════════
#  Text-to-Image (render text as a custom-layout image)
# ═══════════════════════════════════════════════════════════════════


@app.post("/text-to-image", tags=["content"], response_model=ServiceResponse)
async def send_text_as_image(
    device_id: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
    signature: Optional[str] = Query(None),
    refresh_now: bool = Query(True),
    border: int = Query(0),
    dither_type: DitherType = Query(DitherType.NONE),
    font_path: Optional[str] = Query(None, description="Path to a .ttf font file"),
    title_size: int = Query(18),
    message_size: int = Query(14),
    signature_size: int = Query(10),
    task_key: Optional[str] = Query(None),
):
    """
    Render text fields into a 296x152 image on the server, then push
    it to the Quote e-ink screen via the Image API.

    This bypasses the built-in Text API layout and gives you full
    control over font size and positioning.  Use dither_type=NONE
    for crisp text.
    """
    device_id = _resolve_device(device_id)

    img = render_text_to_image(
        title=title,
        message=message,
        signature=signature,
        font_path=font_path,
        title_size=title_size,
        message_size=message_size,
        signature_size=signature_size,
    )
    b64 = image_to_base64(img)

    try:
        data = await _get_client().send_image(
            device_id,
            b64,
            refresh_now=refresh_now,
            border=border,
            dither_type=dither_type.value,
        )
        return ServiceResponse(
            success=True, message="Text rendered and sent as image", data=data
        )
    except DotClientError as e:
        raise _handle_dot_error(e)
