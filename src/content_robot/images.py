"""Render ảnh theo kênh: ghim Pinterest dọc 2:3 (1000×1500) và thẻ Facebook 1200×630."""
from __future__ import annotations

import io
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

BRAND_RED = (214, 0, 28)
WHITE = (255, 255, 255)
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONT_CANDIDATES = [
    str(FONT_DIR / "BeVietnamPro-Bold.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_REGULAR = [
    str(FONT_DIR / "BeVietnamPro-Regular.ttf"),
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES if bold else FONT_REGULAR:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def load_image(url_or_path: str | None) -> Image.Image | None:
    if not url_or_path:
        return None
    try:
        if url_or_path.startswith("http"):
            r = httpx.get(url_or_path, timeout=30, follow_redirects=True, headers={"User-Agent": "DoppelherzContentRobot/1.0"})
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGB")
        return Image.open(url_or_path).convert("RGB")
    except Exception:
        return None


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_text(draw: ImageDraw.ImageDraw, text: str, box_w: int, box_h: int, max_size: int, min_size: int = 34):
    size = max_size
    while size >= min_size:
        f = _font(size)
        lines = _wrap(draw, text, f, box_w)
        h = len(lines) * int(size * 1.22)
        if h <= box_h and len(lines) <= 4:
            return f, lines, size
        size -= 4
    f = _font(min_size)
    return f, _wrap(draw, text, f, box_w)[:4], min_size


def _placeholder(size: tuple[int, int]) -> Image.Image:
    img = Image.new("RGB", size, (248, 236, 236))
    d = ImageDraw.Draw(img)
    for i in range(-size[1], size[0], 60):
        d.line([(i, 0), (i + size[1], size[1])], fill=(240, 220, 220), width=18)
    return img


def render_pin(source: str | None, headline: str, label: str, out_path: Path) -> Path:
    W, H, PH = 1000, 1500, 960
    canvas = Image.new("RGB", (W, H), WHITE)
    photo = load_image(source)
    photo = ImageOps.fit(photo, (W, PH), method=Image.LANCZOS, centering=(0.5, 0.4)) if photo else _placeholder((W, PH))
    canvas.paste(photo, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, PH, W, H], fill=BRAND_RED)
    # nhãn chủ đề
    lf = _font(30)
    tw = d.textlength(label.upper(), font=lf)
    d.rounded_rectangle([60, PH - 34, 60 + tw + 48, PH + 26], radius=30, fill=WHITE)
    d.text((84, PH - 22), label.upper(), font=lf, fill=BRAND_RED)
    f, lines, size = _fit_text(d, headline, W - 120, 330, max_size=74)
    y = PH + 70
    for ln in lines:
        d.text((60, y), ln, font=f, fill=WHITE)
        y += int(size * 1.22)
    d.text((60, H - 70), "doppelherz.vn  ·  Kiến thức sức khỏe", font=_font(30, bold=False), fill=(255, 225, 225))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=88, optimize=True)
    return out_path


def render_fb_card(source: str | None, headline: str, out_path: Path) -> Path:
    W, H = 1200, 630
    canvas = Image.new("RGB", (W, H), WHITE)
    photo = load_image(source)
    photo = ImageOps.fit(photo, (720, H), method=Image.LANCZOS) if photo else _placeholder((720, H))
    canvas.paste(photo, (W - 720, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W - 720, H], fill=BRAND_RED)
    f, lines, size = _fit_text(d, headline, 400, 400, max_size=52, min_size=30)
    y = 110
    for ln in lines:
        d.text((40, y), ln, font=f, fill=WHITE)
        y += int(size * 1.22)
    d.text((40, H - 70), "doppelherz.vn", font=_font(28, bold=False), fill=(255, 225, 225))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=88, optimize=True)
    return out_path
