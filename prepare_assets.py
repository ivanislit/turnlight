from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw


APP_DIR = Path(__file__).resolve().parent
ICON_DIR = APP_DIR / "assets" / "icons"
PNG_DIR = ICON_DIR / "png"
APP_ASSETS_DIR = APP_DIR / "assets" / "app"

ICON_NAMES = [
    "app-icon",
    "settings",
    "dark-mode",
    "bright-mode",
    "crosshair",
    "play",
    "pause",
    "camera",
    "busy-stop",
    "ready-arrow",
    "ignored",
    "bell",
    "palette",
    "volume-on",
    "volume-off",
    "check-circle",
    "eye",
    "status-dot",
    "close",
    "minimize",
    "folder",
    "refresh",
    "info",
    "monitor",
    "single-monitor",
    "spark",
]


def transparent_white_from_image(image: Image.Image, size: int) -> Image.Image:
    image = image.convert("RGBA")
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))

    pixels = canvas.load()
    for y in range(size):
        for x in range(size):
            r, g, b, a = pixels[x, y]
            brightness = max(r, g, b)
            if a < 8 or brightness < 38:
                pixels[x, y] = (255, 255, 255, 0)
            else:
                alpha = min(255, max(a, int((brightness - 25) * 1.25)))
                pixels[x, y] = (255, 255, 255, alpha)
    return canvas


def image_from_embedded_png(svg_text: str, size: int) -> Image.Image | None:
    match = re.search(r"data:image/png;base64,([^\"']+)", svg_text)
    if not match:
        return None
    data = base64.b64decode(match.group(1))
    return transparent_white_from_image(Image.open(BytesIO(data)), size)


def line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], width: int) -> None:
    draw.line(points, fill=(255, 255, 255, 255), width=width, joint="curve")


def fallback_icon(name: str, size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size
    w = max(2, round(size * 0.075))
    white = (255, 255, 255, 255)

    def ellipse(box: tuple[float, float, float, float], width: int = w) -> None:
        draw.ellipse(box, outline=white, width=width)

    def rect(box: tuple[float, float, float, float], width: int = w, radius: int | None = None) -> None:
        if radius is None:
            draw.rectangle(box, outline=white, width=width)
        else:
            draw.rounded_rectangle(box, radius=radius, outline=white, width=width)

    if name in {"app-icon", "ready-arrow"}:
        ellipse((s * 0.14, s * 0.18, s * 0.80, s * 0.84))
        line(draw, [(s * 0.47, s * 0.64), (s * 0.47, s * 0.36)], w)
        line(draw, [(s * 0.32, s * 0.50), (s * 0.47, s * 0.35), (s * 0.62, s * 0.50)], w)
        if name == "app-icon":
            line(draw, [(s * 0.78, s * 0.18), (s * 0.90, s * 0.08)], max(2, w - 1))
            line(draw, [(s * 0.86, s * 0.30), (s * 0.98, s * 0.30)], max(2, w - 1))
    elif name == "busy-stop":
        ellipse((s * 0.12, s * 0.12, s * 0.88, s * 0.88))
        draw.rectangle((s * 0.38, s * 0.38, s * 0.62, s * 0.62), outline=white, width=w)
    elif name == "play":
        ellipse((s * 0.10, s * 0.10, s * 0.90, s * 0.90))
        draw.polygon([(s * 0.42, s * 0.32), (s * 0.42, s * 0.68), (s * 0.70, s * 0.50)], outline=white)
        line(draw, [(s * 0.42, s * 0.32), (s * 0.42, s * 0.68), (s * 0.70, s * 0.50), (s * 0.42, s * 0.32)], w)
    elif name == "pause":
        ellipse((s * 0.10, s * 0.10, s * 0.90, s * 0.90))
        line(draw, [(s * 0.40, s * 0.34), (s * 0.40, s * 0.66)], w)
        line(draw, [(s * 0.60, s * 0.34), (s * 0.60, s * 0.66)], w)
    elif name == "settings":
        ellipse((s * 0.30, s * 0.30, s * 0.70, s * 0.70))
        for angle in range(0, 360, 45):
            import math

            a = math.radians(angle)
            line(
                draw,
                [
                    (s * 0.50 + math.cos(a) * s * 0.30, s * 0.50 + math.sin(a) * s * 0.30),
                    (s * 0.50 + math.cos(a) * s * 0.43, s * 0.50 + math.sin(a) * s * 0.43),
                ],
                w,
            )
    elif name == "dark-mode":
        draw.ellipse((s * 0.20, s * 0.16, s * 0.78, s * 0.80), fill=white)
        draw.ellipse((s * 0.40, s * 0.08, s * 0.96, s * 0.68), fill=(0, 0, 0, 0))
    elif name == "bright-mode":
        import math

        ellipse((s * 0.30, s * 0.30, s * 0.70, s * 0.70), width=w)
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            line(
                draw,
                [
                    (s * 0.50 + math.cos(a) * s * 0.30, s * 0.50 + math.sin(a) * s * 0.30),
                    (s * 0.50 + math.cos(a) * s * 0.44, s * 0.50 + math.sin(a) * s * 0.44),
                ],
                w,
            )
    elif name == "crosshair":
        rect((s * 0.16, s * 0.16, s * 0.84, s * 0.84), width=max(2, w - 1), radius=0)
        ellipse((s * 0.38, s * 0.38, s * 0.62, s * 0.62), width=max(2, w - 1))
        line(draw, [(s * 0.50, s * 0.22), (s * 0.50, s * 0.78)], max(2, w - 1))
        line(draw, [(s * 0.22, s * 0.50), (s * 0.78, s * 0.50)], max(2, w - 1))
    elif name == "camera":
        rect((s * 0.18, s * 0.32, s * 0.82, s * 0.76), radius=round(s * 0.08))
        rect((s * 0.36, s * 0.22, s * 0.64, s * 0.36), radius=round(s * 0.04))
        ellipse((s * 0.39, s * 0.43, s * 0.61, s * 0.65))
    elif name == "ignored":
        ellipse((s * 0.14, s * 0.14, s * 0.86, s * 0.86))
        line(draw, [(s * 0.25, s * 0.75), (s * 0.75, s * 0.25)], w)
    elif name == "bell":
        line(draw, [(s * 0.30, s * 0.68), (s * 0.70, s * 0.68)], w)
        line(draw, [(s * 0.36, s * 0.68), (s * 0.36, s * 0.42), (s * 0.50, s * 0.26), (s * 0.64, s * 0.42), (s * 0.64, s * 0.68)], w)
        line(draw, [(s * 0.45, s * 0.78), (s * 0.55, s * 0.78)], w)
    elif name == "palette":
        ellipse((s * 0.15, s * 0.18, s * 0.85, s * 0.82))
        for x, y in [(0.38, 0.36), (0.55, 0.34), (0.65, 0.50), (0.42, 0.56)]:
            draw.ellipse((s * (x - 0.035), s * (y - 0.035), s * (x + 0.035), s * (y + 0.035)), fill=white)
    elif name in {"volume-on", "volume-off"}:
        draw.polygon([(s * 0.18, s * 0.42), (s * 0.34, s * 0.42), (s * 0.54, s * 0.26), (s * 0.54, s * 0.74), (s * 0.34, s * 0.58), (s * 0.18, s * 0.58)], fill=white)
        if name == "volume-on":
            draw.arc((s * 0.50, s * 0.30, s * 0.84, s * 0.70), -45, 45, fill=white, width=w)
            draw.arc((s * 0.58, s * 0.18, s * 0.98, s * 0.82), -45, 45, fill=white, width=w)
        else:
            line(draw, [(s * 0.66, s * 0.38), (s * 0.86, s * 0.62)], w)
            line(draw, [(s * 0.86, s * 0.38), (s * 0.66, s * 0.62)], w)
    elif name == "check-circle":
        ellipse((s * 0.12, s * 0.12, s * 0.88, s * 0.88))
        line(draw, [(s * 0.32, s * 0.52), (s * 0.46, s * 0.66), (s * 0.70, s * 0.38)], w)
    elif name == "eye":
        line(draw, [(s * 0.14, s * 0.50), (s * 0.32, s * 0.32), (s * 0.50, s * 0.26), (s * 0.68, s * 0.32), (s * 0.86, s * 0.50), (s * 0.68, s * 0.68), (s * 0.50, s * 0.74), (s * 0.32, s * 0.68), (s * 0.14, s * 0.50)], w)
        ellipse((s * 0.42, s * 0.42, s * 0.58, s * 0.58))
    elif name == "status-dot":
        ellipse((s * 0.20, s * 0.20, s * 0.80, s * 0.80), width=w)
    elif name == "close":
        line(draw, [(s * 0.25, s * 0.25), (s * 0.75, s * 0.75)], w)
        line(draw, [(s * 0.75, s * 0.25), (s * 0.25, s * 0.75)], w)
    elif name == "minimize":
        line(draw, [(s * 0.22, s * 0.55), (s * 0.78, s * 0.55)], w)
    elif name == "folder":
        line(draw, [(s * 0.16, s * 0.32), (s * 0.40, s * 0.32), (s * 0.48, s * 0.42), (s * 0.84, s * 0.42), (s * 0.84, s * 0.76), (s * 0.16, s * 0.76), (s * 0.16, s * 0.32)], w)
    elif name == "refresh":
        draw.arc((s * 0.18, s * 0.18, s * 0.82, s * 0.82), 35, 330, fill=white, width=w)
        line(draw, [(s * 0.74, s * 0.20), (s * 0.84, s * 0.20), (s * 0.84, s * 0.32)], w)
    elif name == "info":
        ellipse((s * 0.14, s * 0.14, s * 0.86, s * 0.86))
        line(draw, [(s * 0.50, s * 0.46), (s * 0.50, s * 0.68)], w)
        draw.ellipse((s * 0.46, s * 0.30, s * 0.54, s * 0.38), fill=white)
    elif name == "monitor":
        rect((s * 0.14, s * 0.24, s * 0.68, s * 0.64), radius=round(s * 0.03))
        rect((s * 0.34, s * 0.34, s * 0.86, s * 0.74), radius=round(s * 0.03))
        line(draw, [(s * 0.50, s * 0.74), (s * 0.50, s * 0.84), (s * 0.64, s * 0.84)], w)
    elif name == "single-monitor":
        rect((s * 0.18, s * 0.24, s * 0.82, s * 0.68), radius=round(s * 0.04))
        line(draw, [(s * 0.50, s * 0.68), (s * 0.50, s * 0.82), (s * 0.36, s * 0.82), (s * 0.64, s * 0.82)], w)
    else:
        line(draw, [(s * 0.50, s * 0.18), (s * 0.58, s * 0.42), (s * 0.82, s * 0.50), (s * 0.58, s * 0.58), (s * 0.50, s * 0.82), (s * 0.42, s * 0.58), (s * 0.18, s * 0.50), (s * 0.42, s * 0.42), (s * 0.50, s * 0.18)], w)

    return image


def build_icon(name: str, size: int = 96) -> Image.Image:
    svg_path = ICON_DIR / f"{name}.svg"
    if svg_path.exists():
        svg_text = svg_path.read_text(encoding="utf-8", errors="ignore")
        image = image_from_embedded_png(svg_text, size)
        if image is not None:
            return image
    return fallback_icon(name, size)


def main() -> int:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    APP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    rendered: dict[str, Image.Image] = {}
    for name in ICON_NAMES:
        image = build_icon(name, 96)
        image.save(PNG_DIR / f"{name}.png")
        rendered[name] = image

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    app_icon = rendered["app-icon"]
    app_icon.save(
        APP_ASSETS_DIR / "turnlight.ico",
        sizes=[(size, size) for size in ico_sizes],
    )
    print(f"Prepared {len(rendered)} icons in {PNG_DIR}")
    print(f"Prepared app icon at {APP_ASSETS_DIR / 'turnlight.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
