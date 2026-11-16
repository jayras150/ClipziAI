"""Render caption overlay ke gambar thumbnail (Pillow).

Dipakai untuk thumbnail YouTube: frame viral + teks caption dengan salah satu
50 gaya di `caption_catalog`, posisi 9 anchor pilihan user.
"""
from __future__ import annotations

import io
import math
import re
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.services.caption_catalog import CAPTION_STYLES, FONT_FILES

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
OUT_W, OUT_H = 1280, 720
ANCHORS = (
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
)


def _hex(value: str | None, default: str = "#FFFFFF") -> Tuple[int, int, int]:
    text = (value or default).lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except Exception:
        return (255, 255, 255)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    candidate = FONT_DIR / FONT_FILES.get(name, "Inter-Bold.ttf")
    for path in (candidate, FONT_DIR / "Inter-Bold.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")):
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _gradient(size: Tuple[int, int], colors: Iterable[str], vertical: bool) -> Image.Image:
    stops = [_hex(color) for color in colors] or [(255, 255, 255)]
    width, height = size
    gradient = Image.new("RGB", size)
    pixels = gradient.load()
    span = height if vertical else width
    for index in range(span):
        position = index / max(1, span - 1) * (len(stops) - 1)
        low = int(math.floor(position))
        high = min(low + 1, len(stops) - 1)
        blend = position - low
        color = tuple(
            int(stops[low][channel] * (1 - blend) + stops[high][channel] * blend)
            for channel in range(3)
        )
        if vertical:
            for x in range(width):
                pixels[x, index] = color
        else:
            for y in range(height):
                pixels[index, y] = color
    return gradient


def render_caption_thumbnail(
    image_bytes: bytes,
    text: str,
    style_id: str,
    position: str = "bottom-center",
) -> bytes:
    """Tempel caption bergaya ke frame dan kembalikan JPEG 1280x720."""
    style = CAPTION_STYLES.get(style_id) or CAPTION_STYLES["hormozi-pop"]
    base = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    base = base.resize((OUT_W, OUT_H), Image.LANCZOS) if base.size != (OUT_W, OUT_H) else base

    label = text.strip() or "Sample caption"
    if style["uppercase"]:
        label = label.upper()

    font_size = max(24, int(OUT_H * float(style["size"])))
    margin = int(OUT_W * 0.045)
    max_text_width = int(OUT_W * 0.86)

    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    for _ in range(14):
        font = _font(style["font"], font_size)
        lines = _wrap(probe, label, font, max_text_width)
        if len(lines) <= 3:
            break
        font_size = int(font_size * 0.92)

    line_height = int(font_size * 1.16)
    text_w = max(int(probe.textlength(line, font=font)) for line in lines)
    text_h = line_height * len(lines)
    pad = int(style["pad"])

    layer = Image.new("RGBA", (text_w + pad * 2 + 40, text_h + pad * 2 + 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    box_color = _hex(style["bg"]) + (235,) if style["bg"] else None
    if box_color:
        radius = pad if style["radius"] >= 999 else style["radius"]
        draw.rounded_rectangle(
            (20, 20, 20 + text_w + pad * 2, 20 + text_h + pad * 2),
            radius=radius,
            fill=box_color,
        )

    y = 20 + pad
    fill = _hex(style["color"])
    stroke_width = int(style["stroke"])
    stroke_fill = _hex(style["stroke_color"], "#000000")
    for line in lines:
        if style["gradient"]:
            mask = Image.new("L", layer.size, 0)
            ImageDraw.Draw(mask).text((20 + pad, y), line, font=font, fill=255)
            gradient = _gradient(layer.size, style["gradient"], bool(style["gradient_vertical"]))
            layer.paste(gradient, (0, 0), mask)
            draw = ImageDraw.Draw(layer)
        draw.text(
            (20 + pad, y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        y += line_height

    canvas = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    if style["shadow"]:
        shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        y2 = 20 + pad
        for line in lines:
            shadow_draw.text((20 + pad, y2), line, font=font, fill=(0, 0, 0, 190))
            y2 += line_height
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, int(style["shadow"]))))
        canvas = Image.alpha_composite(canvas, shadow)
    canvas = Image.alpha_composite(canvas, layer)
    layer = canvas

    if style["rotate"]:
        layer = layer.rotate(float(style["rotate"]), expand=True, resample=Image.BICUBIC)

    anchor = position if position in ANCHORS else style["position"]
    vertical, _, horizontal = anchor.partition("-")
    x = {
        "left": margin,
        "center": (OUT_W - layer.width) // 2,
        "right": OUT_W - layer.width - margin,
    }.get(horizontal or "center", (OUT_W - layer.width) // 2)
    y_pos = {
        "top": margin,
        "center": (OUT_H - layer.height) // 2,
        "bottom": OUT_H - layer.height - margin,
    }.get(vertical or "bottom", OUT_H - layer.height - margin)

    composed = base.convert("RGBA")
    composed.alpha_composite(layer, (max(0, x), max(0, y_pos)))
    buffer = io.BytesIO()
    composed.convert("RGB").save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def style_options() -> List[dict]:
    return [
        {"id": key, "label": value["label"], "position": value["position"]}
        for key, value in CAPTION_STYLES.items()
    ]


__all__ = ["ANCHORS", "render_caption_thumbnail", "style_options"]
