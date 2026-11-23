"""Original, football-first Instagram graphics (1080x1350).

No third-party photography or club logos are embedded. The graphic language
uses our own football-pitch geometry and matchday-style broadcast treatments.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 1080, 1350
BASE = (7, 18, 30)
THEMES = {
    "FICHAJES": ("MERCADO DE PASES", (146, 104, 255)),
    "PARTIDOS": ("EN LA CANCHA", (255, 197, 53)),
    "SELECCIONES": ("FÚTBOL MUNDIAL", (58, 223, 168)),
    "LESIONES": ("ACTUALIDAD", (255, 113, 103)),
    "ACTUALIDAD": ("FÚTBOL AL DÍA", (55, 199, 251)),
}
FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]
FONT_NORMAL = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
]


def font(size: int, bold=True):
    for candidate in (FONT_BOLD if bold else FONT_NORMAL):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_lines(draw, value: str, limit: int, top_size=90, max_lines=5):
    """Fit a compact title without chopping sentences in the image."""
    value = re.sub(r"\s+", " ", value).strip().upper()
    for size in range(top_size, 37, -2):
        face = font(size)
        words = value.split()
        lines, line = [], ""
        for word in words:
            trial = (line + " " + word).strip()
            if draw.textbbox((0, 0), trial, font=face)[2] <= limit:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        if len(lines) <= max_lines and all(draw.textbbox((0, 0), s, font=face)[2] <= limit for s in lines):
            return face, lines
    # Oversized RSS headlines are previews only; shrink and safely ellipsize.
    face = font(38)
    words = value.split()
    while words:
        short = " ".join(words) + "…"
        lines, line = [], ""
        for word in short.split():
            trial = (line + " " + word).strip()
            if draw.textbbox((0, 0), trial, font=face)[2] <= limit:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        if len(lines) <= max_lines and all(draw.textbbox((0, 0), s, font=face)[2] <= limit for s in lines):
            return face, lines
        words.pop()
    return face, ["TITULAR EN REVISIÓN"]


def _pitch(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int], offset: int):
    """Abstract football pitch details, no team intellectual property."""
    faint = (*accent, 47)
    draw.rounded_rectangle((80, 330, 1005, 1020), radius=20, outline=faint, width=3)
    draw.line((542, 330, 542, 1020), fill=faint, width=3)
    draw.ellipse((355, 510, 730, 885), outline=faint, width=3)
    draw.rectangle((80, 470, 235, 875), outline=faint, width=3)
    draw.rectangle((850, 470, 1005, 875), outline=faint, width=3)
    for i in range(6):
        x = 85 + i * 225 + (offset % 45)
        draw.line((x, 300, x + 320, 900), fill=(*accent, 16), width=4)


def _illustration(layer: Image.Image, accent, seed: int, category: str):
    draw = ImageDraw.Draw(layer, "RGBA")
    _pitch(draw, accent, seed)
    cx, cy, r = (780, 590, 265)
    # Branded abstract football on an illuminated pitch.
    draw.ellipse((cx-r-35, cy-r-35, cx+r+35, cy+r+35), fill=(*accent, 13))
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(7, 18, 30, 208),
                 outline=(*accent, 195), width=7)
    for k in range(10):
        t = 2 * math.pi * k / 10 + (seed % 8) * .01
        ix, iy = cx + math.cos(t) * 110, cy + math.sin(t) * 110
        ox, oy = cx + math.cos(t) * 255, cy + math.sin(t) * 255
        draw.line([(ix, iy), (ox, oy)], fill=(*accent, 85), width=6)
    polygon = []
    for i in range(5):
        a = (math.pi * 2 * i / 5) - math.pi / 2
        polygon.append((cx + 99 * math.cos(a), cy + 99 * math.sin(a)))
    draw.polygon(polygon, fill=(*accent, 135))
    draw.line(polygon + polygon[:1], fill=(255, 255, 255, 160), width=5, joint="curve")
    if category == "FICHAJES":
        for i in range(4):
            x = 62 + i * 82
            draw.polygon([(x, 465), (x + 33, 514), (x, 563), (x + 20, 563),
                          (x + 53, 514), (x + 20, 465)], fill=(*accent, 55))
    elif category == "PARTIDOS":
        draw.arc((180, 310, 1000, 1100), start=195, end=345, fill=(*accent, 122), width=10)
    else:
        for i in range(6):
            draw.ellipse((85 + i * 32, 440 + i * 32, 95 + i * 32, 450 + i * 32),
                         fill=(*accent, 110))


def render_card(item: dict, brand="CHAO FELICEVICH", destination: Path | None = None,
                portrait_path: Path | None = None, ai_art: bool = False) -> Path:
    category = str(item.get("category", "ACTUALIDAD")).upper()
    ribbon, accent = THEMES.get(category, THEMES["ACTUALIDAD"])
    identity = str(item.get("id", "news"))[:36]
    output = Path(destination or Path("output/previews") / f"{identity}.jpg")
    output.parent.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGB", (WIDTH, HEIGHT), BASE)
    draw = ImageDraw.Draw(canvas)
    for y in range(HEIGHT):
        s = y / HEIGHT
        draw.line((0, y, WIDTH, y), fill=(int(6 + 4*s), int(16 + 12*s), int(27 + 20*s)))

    decorative = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay = ImageDraw.Draw(decorative, "RGBA")
    overlay.polygon([(660, 0), (1080, 0), (1080, 360), (990, 360)],
                    fill=(*accent, 39))
    overlay.polygon([(0, 1100), (175, 1350), (0, 1350)], fill=(*accent, 44))
    if not portrait_path:
        _illustration(decorative, accent, sum(ord(c) for c in identity), category)
    else:
        # Keep pitch artwork subtly behind identity-verified photography.
        _pitch(overlay, accent, sum(ord(c) for c in identity))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), decorative)
    if portrait_path:
        try:
            with Image.open(portrait_path) as portrait_src:
                portrait = ImageOps.fit(
                    ImageOps.exif_transpose(portrait_src).convert("RGB"),
                    (740, 825), method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.30),
                ).convert("RGBA")
            # Right-weighted licensed portrait, feathered left and bottom edges.
            mask = Image.new("L", (740, 825), 0)
            mask_draw = ImageDraw.Draw(mask)
            for x in range(740):
                alpha = int(237 * min(1, max(0, (x - 10) / 225)))
                mask_draw.line((x, 0, x, 825), fill=alpha)
            shadow = Image.new("L", (740, 825), 0)
            shadow_draw = ImageDraw.Draw(shadow)
            for y in range(825):
                fade = min(1, max(0, (825 - y) / 185))
                shadow_draw.line((0, y, 740, y), fill=int(255 * fade))
            from PIL import ImageChops
            mask = ImageChops.multiply(mask, shadow)
            portrait.putalpha(mask)
            canvas.alpha_composite(portrait, dest=(340, 235))
            photo_draw = ImageDraw.Draw(canvas, "RGBA")
            photo_draw.line((1010, 285, 1010, 760), fill=(*accent, 230), width=7)
        except (OSError, ValueError):
            # Broken licensed image should never break the newsletter.
            pass

    # Dark lower-third separates short headlines from background geometry.
    overlay2 = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shade = ImageDraw.Draw(overlay2, "RGBA")
    for y in range(625, 1235, 4):
        opacity = min(244, 110 + int((y-625) / 610 * 136))
        shade.rectangle((0, y, WIDTH, y+4), fill=(5, 13, 23, opacity))
    canvas = Image.alpha_composite(canvas, overlay2)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Broadcast brand bar.
    draw.rounded_rectangle((66, 63, 164, 160), radius=24, fill=(*accent, 255))
    draw.text((83, 82), "CF", font=font(42), fill=(5, 13, 23, 255))
    draw.text((188, 77), brand.upper()[:27], font=font(34), fill=(248, 250, 255, 255))
    draw.text((188, 126), "EL FÚTBOL SE VIVE ACÁ.", font=font(19, False),
              fill=(168, 185, 198, 255))
    draw.rectangle((65, 198, 1015, 203), fill=(*accent, 255))

    label_width = min(730, max(285, draw.textbbox((0, 0), ribbon, font=font(28))[2] + 55))
    draw.rounded_rectangle((68, 238, 68+label_width, 302), radius=12, fill=(*accent, 245))
    draw.text((93, 255), ribbon, font=font(28), fill=(8, 19, 30, 255))
    draw.text((75, 639), "LA NOTICIA", font=font(22), fill=(*accent, 255))
    if ai_art:
        # Prevent fictional AI art from being mistaken for a documentary photo.
        draw.rounded_rectangle((765, 316, 1009, 370), radius=14,
                               fill=(4, 14, 26, 224), outline=(*accent, 245), width=2)
        draw.text((782, 331), "ILUSTRACIÓN IA", font=font(22),
                  fill=(255, 255, 255, 255))

    headline = str(item.get("headline") or item.get("title") or "").strip()
    face, lines = fit_lines(draw, headline, 935, top_size=82, max_lines=5)
    line_h = face.size + 17 if hasattr(face, "size") else 65
    y = max(726, 1082 - len(lines) * line_h)
    for line in lines:
        draw.text((70, y), line, font=face, fill=(250, 251, 255, 255),
                  stroke_width=1, stroke_fill=(10, 17, 25, 200))
        y += line_h

    draw.rectangle((70, 1190, 1010, 1193), fill=(*accent, 190))
    draw.text((72, 1221), "CHAO FELICEVICH • FÚTBOL SIN FILTRO",
              font=font(23, False), fill=(174, 193, 208, 255))
    draw.text((73, 1282), "NOTICIAS • PASIÓN • DEBATE", font=font(19),
              fill=(*accent, 255))
    draw.text((1000, 1280), "24/7", anchor="ra", font=font(24),
              fill=(185, 201, 212, 255))

    canvas.convert("RGB").save(output, "JPEG", quality=90, optimize=True)
    return output
