"""
thumbnail.py — Generates a "Now Playing" card image.

Uses Pillow to draw track info over a blurred album art background.
Returns the path to the generated PNG.
"""

import os
import textwrap
from io import BytesIO
from typing import Optional

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from bot.config import config
from bot.utils.logger import get_logger

log = get_logger(__name__)

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_OUTPUT_DIR = os.path.join(config.CACHE_DIR, "thumbs")
os.makedirs(_OUTPUT_DIR, exist_ok=True)

_CARD_W, _CARD_H = 1280, 720


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try to load a bundled font, fall back to default."""
    font_name = "bold.ttf" if bold else "regular.ttf"
    path = os.path.join(_FONT_DIR, font_name)
    try:
        return ImageFont.truetype(path, size)
    except (IOError, OSError):
        return ImageFont.load_default()


async def _fetch_image(url: str) -> Optional[Image.Image]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        log.warning(f"Thumbnail fetch failed: {e}")
        return None


def _gradient_bg(width: int, height: int) -> Image.Image:
    """Create a simple dark gradient background."""
    img = Image.new("RGBA", (width, height), (15, 15, 25, 255))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        alpha = int(40 * (1 - y / height))
        draw.line([(0, y), (width, y)], fill=(100, 100, 200, alpha))
    return img


async def generate_thumbnail(
    title: str,
    artist: str,
    duration: str,
    requested_by: str,
    thumbnail_url: Optional[str] = None,
    output_filename: str = "now_playing.png",
) -> str:
    """
    Generate a Now Playing card.

    Returns the local file path of the generated PNG.
    """
    output_path = os.path.join(_OUTPUT_DIR, output_filename)

    # Background
    card = _gradient_bg(_CARD_W, _CARD_H)

    # Album art (left side)
    art_size = 400
    art_x, art_y = 80, (_CARD_H - art_size) // 2

    if thumbnail_url:
        art_img = await _fetch_image(thumbnail_url)
    else:
        art_img = None

    if art_img:
        art_img = art_img.resize((art_size, art_size), Image.LANCZOS)
        # Blur behind art for depth
        blurred = art_img.resize((_CARD_W, _CARD_H), Image.LANCZOS).filter(
            ImageFilter.GaussianBlur(radius=30)
        )
        blurred_overlay = Image.new("RGBA", (_CARD_W, _CARD_H), (0, 0, 0, 140))
        card = Image.alpha_composite(
            Image.alpha_composite(card, blurred.convert("RGBA")),
            blurred_overlay,
        )
        card.paste(art_img, (art_x, art_y), mask=art_img.split()[3] if art_img.mode == "RGBA" else None)
    else:
        # Music note placeholder
        placeholder = Image.new("RGBA", (art_size, art_size), (40, 40, 70, 255))
        draw_ph = ImageDraw.Draw(placeholder)
        draw_ph.text((art_size // 2, art_size // 2), "🎵", anchor="mm",
                     font=_load_font(120), fill=(180, 180, 220, 255))
        card.paste(placeholder, (art_x, art_y))

    draw = ImageDraw.Draw(card)

    # Text area
    text_x = art_x + art_size + 80
    text_max_w = _CARD_W - text_x - 60

    # "NOW PLAYING" label
    draw.text((text_x, 200), "NOW PLAYING", font=_load_font(22), fill=(150, 150, 255, 220))

    # Title (wrapped)
    title_lines = textwrap.wrap(title, width=28)
    title_y = 245
    for line in title_lines[:2]:
        draw.text((text_x, title_y), line, font=_load_font(52, bold=True), fill=(255, 255, 255, 255))
        title_y += 62

    # Artist
    if artist:
        draw.text((text_x, title_y + 10), artist, font=_load_font(34), fill=(200, 200, 200, 200))

    # Duration
    draw.text((text_x, _CARD_H - 220), f"⏱  {duration}", font=_load_font(30), fill=(180, 180, 255, 220))

    # Requested by
    draw.text(
        (text_x, _CARD_H - 170),
        f"Requested by  {requested_by}",
        font=_load_font(26),
        fill=(160, 160, 160, 200),
    )

    # Bottom accent bar
    draw.rectangle([(0, _CARD_H - 8), (_CARD_W, _CARD_H)], fill=(100, 100, 255, 255))

    # Save
    card.convert("RGB").save(output_path, "PNG", optimize=True)
    return output_path
