"""
Dot Cloud API client.
Wraps all Dot developer platform APIs using the new authV2 endpoints.
"""

import logging
from typing import Any, Optional

import httpx

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

# Dot Cloud API base path (new V2 endpoints)
_BASE = "/api/authV2/open"


class DotClientError(Exception):
    """Raised when a Dot API call fails."""

    def __init__(self, status_code: int, message: str, detail: Any = None):
        self.status_code = status_code
        self.message = message
        self.detail = detail
        super().__init__(f"[{status_code}] {message}")


class DotClient:
    """
    Async HTTP client for the Dot. cloud API (authV2).

    Usage:
        async with DotClient(api_key="dot_app_xxx") as client:
            devices = await client.list_devices()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        s = settings or get_settings()
        self._api_key = api_key or s.dot_api_key
        self._base_url = (base_url or s.dot_api_base_url).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    # ── lifecycle ────────────────────────────────────────────────

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # ── helpers ──────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
    ) -> Any:
        client = await self._ensure_client()
        resp = await client.request(method, path, json=json)
        logger.debug("Dot API %s %s -> %s", method, path, resp.status_code)

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise DotClientError(resp.status_code, str(body), body)

        # Some endpoints return a plain list (e.g. /devices, /list)
        return resp.json()

    # ── Device management ────────────────────────────────────────

    async def list_devices(self) -> list[dict]:
        """GET /api/authV2/open/devices — list all devices."""
        return await self._request("GET", f"{_BASE}/devices")

    async def get_device_status(self, device_id: str) -> dict:
        """GET /api/authV2/open/device/:id/status"""
        return await self._request("GET", f"{_BASE}/device/{device_id}/status")

    async def switch_next_content(self, device_id: str) -> dict:
        """POST /api/authV2/open/device/:id/next"""
        return await self._request("POST", f"{_BASE}/device/{device_id}/next")

    async def list_device_tasks(
        self, device_id: str, task_type: str = "loop"
    ) -> list[dict]:
        """GET /api/authV2/open/device/:deviceId/:taskType/list"""
        return await self._request(
            "GET", f"{_BASE}/device/{device_id}/{task_type}/list"
        )

    # ── Text API ─────────────────────────────────────────────────

    async def send_text(
        self,
        device_id: str,
        *,
        refresh_now: bool = True,
        title: Optional[str] = None,
        message: Optional[str] = None,
        signature: Optional[str] = None,
        icon: Optional[str] = None,
        link: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> dict:
        """POST /api/authV2/open/device/:deviceId/text"""
        payload: dict[str, Any] = {"refreshNow": refresh_now}
        if title is not None:
            payload["title"] = title
        if message is not None:
            payload["message"] = message
        if signature is not None:
            payload["signature"] = signature
        if icon is not None:
            payload["icon"] = icon
        if link is not None:
            payload["link"] = link
        if task_key is not None:
            payload["taskKey"] = task_key

        return await self._request(
            "POST", f"{_BASE}/device/{device_id}/text", json=payload
        )

    # ── Image API ────────────────────────────────────────────────

    async def send_image(
        self,
        device_id: str,
        image_base64: str,
        *,
        refresh_now: bool = True,
        link: Optional[str] = None,
        border: int = 0,
        dither_type: str = "DIFFUSION",
        dither_kernel: str = "FLOYD_STEINBERG",
        task_key: Optional[str] = None,
    ) -> dict:
        """POST /api/authV2/open/device/:deviceId/image"""
        payload: dict[str, Any] = {
            "refreshNow": refresh_now,
            "image": image_base64,
            "border": border,
            "ditherType": dither_type,
            "ditherKernel": dither_kernel,
        }
        if link is not None:
            payload["link"] = link
        if task_key is not None:
            payload["taskKey"] = task_key

        return await self._request(
            "POST", f"{_BASE}/device/{device_id}/image", json=payload
        )
