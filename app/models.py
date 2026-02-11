"""
Pydantic models for Dot Service API requests and responses.
"""

from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────────────


class DitherType(str, Enum):
    DIFFUSION = "DIFFUSION"
    ORDERED = "ORDERED"
    NONE = "NONE"


class DitherKernel(str, Enum):
    THRESHOLD = "THRESHOLD"
    ATKINSON = "ATKINSON"
    BURKES = "BURKES"
    FLOYD_STEINBERG = "FLOYD_STEINBERG"
    SIERRA2 = "SIERRA2"
    STUCKI = "STUCKI"
    JARVIS_JUDICE_NINKE = "JARVIS_JUDICE_NINKE"
    DIFFUSION_ROW = "DIFFUSION_ROW"
    DIFFUSION_COLUMN = "DIFFUSION_COLUMN"
    DIFFUSION_2D = "DIFFUSION_2D"


# ─── Text API ───────────────────────────────────────────────────────


class SendTextRequest(BaseModel):
    """Request body for sending text to the Quote e-ink screen."""

    device_id: Optional[str] = Field(
        None, description="Device serial number (uses default if omitted)"
    )
    refresh_now: bool = Field(
        True, description="Whether to display the content immediately"
    )
    title: Optional[str] = Field(None, description="Text title shown on screen")
    message: Optional[str] = Field(None, description="Text content shown on screen")
    signature: Optional[str] = Field(None, description="Text signature shown on screen")
    icon: Optional[str] = Field(None, description="Base64-encoded PNG icon (40x40 px)")
    link: Optional[str] = Field(None, description="NFC tap redirect URL")
    task_key: Optional[str] = Field(
        None, description="Task key for targeting specific Text API content"
    )


# ─── Image API ──────────────────────────────────────────────────────


class SendImageRequest(BaseModel):
    """Request body for sending an image to the Quote e-ink screen."""

    device_id: Optional[str] = Field(
        None, description="Device serial number (uses default if omitted)"
    )
    refresh_now: bool = Field(
        True, description="Whether to display the content immediately"
    )
    image: str = Field(..., description="Base64-encoded PNG image data (296x152 px)")
    link: Optional[str] = Field(None, description="NFC tap redirect URL")
    border: int = Field(0, description="0 = white border, 1 = black border")
    dither_type: DitherType = Field(DitherType.DIFFUSION, description="Dither type")
    dither_kernel: DitherKernel = Field(
        DitherKernel.FLOYD_STEINBERG, description="Dither algorithm"
    )
    task_key: Optional[str] = Field(
        None, description="Task key for targeting specific Image API content"
    )


class SendImageFileRequest(BaseModel):
    """Request for sending an image file (will be processed server-side)."""

    device_id: Optional[str] = Field(
        None, description="Device serial number (uses default if omitted)"
    )
    refresh_now: bool = Field(
        True, description="Whether to display the content immediately"
    )
    link: Optional[str] = Field(None, description="NFC tap redirect URL")
    border: int = Field(0, description="0 = white border, 1 = black border")
    dither_type: DitherType = Field(DitherType.DIFFUSION, description="Dither type")
    dither_kernel: DitherKernel = Field(
        DitherKernel.FLOYD_STEINBERG, description="Dither algorithm"
    )
    task_key: Optional[str] = Field(
        None, description="Task key for targeting specific Image API content"
    )


# ─── Device API ─────────────────────────────────────────────────────


class DeviceInfo(BaseModel):
    """Device information returned from the API."""

    id: str
    series: str
    model: str
    edition: int


class DeviceStatusInfo(BaseModel):
    """Device status details."""

    version: Optional[str] = None
    current: Optional[str] = None
    description: Optional[str] = None
    battery: Optional[str] = None
    wifi: Optional[str] = None


class RenderCurrent(BaseModel):
    rotated: Optional[bool] = None
    border: Optional[int] = None
    image: Optional[list[str]] = None


class RenderNext(BaseModel):
    battery: Optional[str] = None
    power: Optional[str] = None


class RenderInfo(BaseModel):
    last: Optional[str] = None
    current: Optional[RenderCurrent] = None
    next: Optional[RenderNext] = None


class DeviceStatus(BaseModel):
    """Full device status response."""

    deviceId: str
    alias: Optional[str] = None
    location: Optional[str] = None
    status: Optional[DeviceStatusInfo] = None
    renderInfo: Optional[RenderInfo] = None


class DeviceTask(BaseModel):
    """A device task entry."""

    type: str
    key: Optional[str] = None
    refreshNow: Optional[bool] = None
    title: Optional[str] = None
    message: Optional[str] = None
    signature: Optional[str] = None
    icon: Optional[str] = None
    link: Optional[str] = None
    image: Optional[str] = None
    border: Optional[int] = None
    ditherType: Optional[str] = None
    ditherKernel: Optional[str] = None


# ─── Common Response ────────────────────────────────────────────────


class DotApiResponse(BaseModel):
    """Standard response from the Dot cloud API."""

    code: int
    message: str
    result: Optional[dict] = None


class ServiceResponse(BaseModel):
    """Standard response from our service."""

    success: bool
    message: str
    data: Optional[dict | list] = None
