"""Premium photo-first 4:5 sports news covers for Chao Felicevich.

Design principles: one strong subject image, one clear headline, one small
category label and quiet branding. No fake location cues, random stadium photo,
decorative football clipart, "LA NOTICIA" or "IMAGEN REFERENCIAL" watermarks.
The fallback drawn from scratch is an original image safe to auto-publish.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 1080, 1350
BASE = (8, 16, 27)
THEMES = {
    "FICHAJES": ("MERCADO", (180, 140, 255)),
    "PARTIDOS": ("PARTIDOS", (247, 206, 75)),
    "SELECCIONES": ("SELECCIONES", (53, 229, 166)),
    "LESIONES": ("ACTUALIDAD", (255, 117, 105)),
    "ACTUALIDAD": ("ÚLTIMA HORA", (88, 212, 234)),
    "TENIS": ("TENIS", (187, 237, 100)),
    "GOLF": ("GOLF", (109, 208, 155)),
    "F1": ("FÓRMULA 1", (255, 100, 92)),
    "NBA": ("NBA", (255, 160, 100)),
}
FONTS_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
)
FONTS_NORMAL = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
)


def font(size: int, bold: bool = True):
    for candidate in (FONTS_BOLD if bold else FONTS_NORMAL):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, words, chosen_font, limit):
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=chosen_font)[2] <= limit:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_lines(draw, value: str, limit: int, top_size=92, max_lines=4):
    """Shrink text to a readable 3–4 lines without silently changing meaning."""
    words = re.sub(r"\s+", " ", value or "").strip().upper().split()
    if not words:
        return font(70), ["NOTICIA EN REVISIÓN"]
    for size in range(top_size, 42, -2):
        candidate = font(size)
        lines = _wrap(draw, words, candidate, limit)
        if len(lines) <= max_lines and all(
            draw.textbbox((0, 0), line, font=candidate)[2] <= limit
            for line in lines
        ):
            return candidate, lines
    # Preview-only fallback. Publishing checks headline length upstream.
    candidate = font(44)
    short = words[:]
    while short:
        lines = _wrap(draw, short + ["…"], candidate, limit)
        if len(lines) <= max_lines:
            return candidate, lines
        short.pop()
    return candidate, ["NOTICIA EN REVISIÓN"]


def _original_background(accent):
    """Original editorial pattern for previews AND automatic publication."""
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (*BASE, 255))
    layer = ImageDraw.Draw(canvas, "RGBA")
    # A restrained spotlight and diagonal facets — NOT a random fake photo.
    for r in range(470, 40, -12):
        k = 470 - r
        alpha = max(0, min(12, int(10 * k / 470)))
        layer.ellipse((580-r, 340-r, 580+r, 340+r), fill=(*accent, alpha))
    layer.polygon([(650, 0), (1080, 0), (1080, 980), (935, 750)],
                  fill=(*accent, 27))
    layer.line((750, 0, 1080, 330), fill=(*accent, 65), width=6)
    return canvas


def _photo_background(path: Path):
    with Image.open(path) as original:
        oriented = ImageOps.exif_transpose(original).convert("RGB")
        if min(oriented.size) < 400:
            raise ValueError("Photography has insufficient resolution")
        # Full-bleed editorial image: subject's upper body dominates top two thirds.
        canvas = ImageOps.fit(
            oriented, (WIDTH, HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.29),
        ).convert("RGBA")
    return canvas


def _cinematic_shade(canvas):
    """Smooth, full-width shade: readable type without visible dark rectangles."""
    mask = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay = ImageDraw.Draw(mask, "RGBA")
    for y in range(HEIGHT):
        if y < 210:
            opacity = int(135 * (1-y/210) + 33)
        elif y < 510:
            opacity = 37
        else:
            t = (y - 510) / (HEIGHT - 510)
            opacity = int(40 + 213 * (t**1.4))
        overlay.line((0, y, WIDTH, y), fill=(4, 11, 21, min(252, opacity)), width=1)
    return Image.alpha_composite(canvas, mask)


def _brand(draw, brand, accent):
    # A quiet, premium publisher stamp, not a big banner.
    draw.rounded_rectangle((62, 65, 130, 133), radius=16, fill=(*accent, 255))
    draw.text((75, 80), "CF", font=font(30), fill=(4, 16, 23, 255))
    draw.text((151, 78), brand.upper()[:25], font=font(31),
              fill=(250, 253, 255, 255))
    draw.ellipse((970, 94, 985, 109), fill=(*accent, 255))


def render_card(item: dict, brand="CHAO FELICEVICH", destination: Path | None = None,
                portrait_path: Path | None = None, ai_art: bool = False,
                reference_photo: bool = False) -> Path:
    """Produce a factual, clean 1080x1350 editorial card.

    Generic reference photos are rejected: a stadium in another country must
    never visually masquerade as the venue of a specific news event.
    """
    if reference_photo:
        raise ValueError("Generic reference photography is not a valid news cover")
    category = str(item.get("category", "ACTUALIDAD")).upper()
    ribbon, accent = THEMES.get(category, THEMES["ACTUALIDAD"])
    key = str(item.get("id") or "preview")[:36]
    output = Path(destination or Path("output/previews") / f"{key}.jpg")
    output.parent.mkdir(parents=True, exist_ok=True)

    canvas = _photo_background(Path(portrait_path)) if portrait_path else _original_background(accent)
    canvas = _cinematic_shade(canvas)
    draw = ImageDraw.Draw(canvas, "RGBA")
    _brand(draw, brand, accent)

    headline = str(item.get("headline") or item.get("title") or "").strip()
    title_font, lines = fit_lines(draw, headline, 940, top_size=88, max_lines=4)
    line_h = getattr(title_font, "size", 60) + 15
    height = len(lines) * line_h
    title_bottom = 1182
    title_top = max(738, title_bottom-height)

    # Sports tag is small, above—not competing with—the actual news.
    tag_face = font(25)
    tag_label = ribbon
    tag_width = min(520, draw.textbbox((0, 0), tag_label, font=tag_face)[2] + 45)
    tag_y = max(617, title_top - 88)
    draw.rounded_rectangle((66, tag_y, 66+tag_width, tag_y+54),
                           radius=8, fill=(*accent, 245))
    draw.text((87, tag_y+12), tag_label, font=tag_face, fill=(3, 18, 27, 255))

    y = title_top
    for line in lines:
        draw.text((64, y), line, font=title_font,
                  fill=(255, 255, 255, 255),
                  stroke_width=1, stroke_fill=(2, 6, 11, 135))
        y += line_h

    # One restrained accent mark, no decorative footer boilerplate.
    draw.rounded_rectangle((64, 1256, 175, 1263), radius=3, fill=(*accent, 245))
    # AI-origin disclosure is handled in the caption, not burned into the image.

    canvas.convert("RGB").save(output, "JPEG", quality=91, optimize=True)
    return output
