"""
Image processing utilities for the Dot Quote/0 e-ink display.
Screen resolution: 296 x 152 pixels, black & white.
"""

import base64
import io
import logging
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .config import get_settings

logger = logging.getLogger(__name__)

SCREEN_W = 296
SCREEN_H = 152


def resize_image_to_screen(
    img: Image.Image,
    width: int = SCREEN_W,
    height: int = SCREEN_H,
) -> Image.Image:
    """
    Resize an image to fit the Quote/0 screen (296x152).
    Uses LANCZOS for high-quality downscaling.
    """
    return img.resize((width, height), Image.LANCZOS)


def image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """Convert a PIL Image to a base64-encoded string."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def base64_to_image(data: str) -> Image.Image:
    """Convert a base64 string to a PIL Image."""
    raw = base64.b64decode(data)
    return Image.open(io.BytesIO(raw))


def bytes_to_image(data: bytes) -> Image.Image:
    """Convert raw bytes to a PIL Image."""
    return Image.open(io.BytesIO(data))


def render_text_to_image(
    title: Optional[str] = None,
    message: Optional[str] = None,
    signature: Optional[str] = None,
    *,
    width: int = SCREEN_W,
    height: int = SCREEN_H,
    bg_color: str = "white",
    text_color: str = "black",
    font_path: Optional[str] = None,
    title_size: int = 18,
    message_size: int = 14,
    signature_size: int = 10,
    padding: int = 8,
) -> Image.Image:
    """
    Render text fields into a 296x152 black-and-white image suitable
    for the Quote/0 Image API.  This allows fully custom layouts that
    go beyond the built-in Text API formatting.
    """
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if font_path:
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                logger.warning("Font %s not found, falling back to default", font_path)
        return ImageFont.load_default(size=size)

    y = padding

    if title:
        fnt = _font(title_size)
        draw.text((padding, y), title, fill=text_color, font=fnt)
        bbox = draw.textbbox((padding, y), title, font=fnt)
        y = bbox[3] + 6

    if message:
        fnt = _font(message_size)
        # Simple word-wrap within the screen width
        max_w = width - 2 * padding
        lines = _wrap_text(draw, message, fnt, max_w)
        for line in lines:
            if y > height - padding - message_size:
                break
            draw.text((padding, y), line, fill=text_color, font=fnt)
            bbox = draw.textbbox((padding, y), line, font=fnt)
            y = bbox[3] + 2

    if signature:
        fnt = _font(signature_size)
        bbox = draw.textbbox((0, 0), signature, font=fnt)
        sw = bbox[2] - bbox[0]
        draw.text(
            (width - padding - sw, height - padding - (bbox[3] - bbox[1])),
            signature,
            fill=text_color,
            font=fnt,
        )

    return img


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Very simple line wrapper that respects \\n and pixel widths."""
    result: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            result.append("")
            continue
        current = ""
        for ch in paragraph:
            test = current + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) > max_width and current:
                result.append(current)
                current = ch
            else:
                current = test
        if current:
            result.append(current)
    return result
