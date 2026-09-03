from __future__ import annotations
import io, logging, urllib.parse
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from .models import Candidate, PostContent

log = logging.getLogger("media")
FONT_PATH = Path("assets/fonts/BeVietnamPro-Bold.ttf")
MIN_EDGE = 500
_HTTP = httpx.Client(timeout=60.0, follow_redirects=True,
                     headers={"User-Agent": "ai-social-bot/0.1"})


def _download(url: str, timeout: int = 60) -> bytes:
    r = _HTTP.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def _shoot(url: str, dest: Path) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:  # noqa: BLE001
            page.wait_for_timeout(3000)
        page.screenshot(path=str(dest))
        browser.close()


def _save_jpeg(im: Image.Image, dest: Path, size: tuple[int, int] | None = None) -> Path:
    im = im.convert("RGB")
    if size:
        im = im.resize(size)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="JPEG", quality=88)
    return dest


def _gradient(w: int, h: int) -> Image.Image:
    base = Image.new("RGB", (w, h))
    for y in range(h):
        t = y / h
        base.paste((int(18 + 30 * t), int(24 + 40 * t), int(72 + 80 * t)), (0, y, w, y + 1))
    return base


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def make_thumbnail(prompt: str, title: str, dest: Path, channel: str) -> Path:
    W, H = 1200, 630
    try:
        q = urllib.parse.quote(prompt)
        raw = _download(f"https://image.pollinations.ai/prompt/{q}"
                        f"?width={W}&height={H}&nologo=true", timeout=60)
        bg = Image.open(io.BytesIO(raw)).convert("RGB").resize((W, H))
    except Exception as e:  # noqa: BLE001
        log.warning("pollinations thumbnail bg failed: %s", e)
        bg = _gradient(W, H)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 90))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)
    font = ImageFont.truetype(str(FONT_PATH), 74)
    small = ImageFont.truetype(str(FONT_PATH), 30)
    lines = _wrap(draw, title.upper(), font, W - 140)
    line_h = 88
    total = line_h * len(lines)
    y = H - 90 - total
    for ln in lines:
        x = (W - draw.textlength(ln, font=font)) / 2
        draw.text((x, y), ln, font=font, fill="white",
                  stroke_width=4, stroke_fill=(10, 10, 30))
        y += line_h
    draw.text((40, H - 46), channel, font=small, fill=(230, 230, 230),
              stroke_width=2, stroke_fill=(0, 0, 0))
    return _save_jpeg(bg, dest)


def fetch_source_image(url: str | None, dest: Path) -> Path | None:
    if not url:
        return None
    try:
        im = Image.open(io.BytesIO(_download(url)))
    except Exception as e:  # noqa: BLE001
        log.warning("source image %s failed: %s", url, e)
        return None
    if max(im.size) < MIN_EDGE:
        return None
    return _save_jpeg(im, dest)


def screenshot(url: str, dest: Path) -> Path | None:
    tmp = dest.with_suffix(".png")
    try:
        _shoot(url, tmp)
        im = Image.open(tmp)
        w, h = im.size
        im = im.crop((0, 0, w, min(h, int(w * 9 / 16))))
        out = _save_jpeg(im, dest)
        tmp.unlink(missing_ok=True)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("screenshot %s failed: %s", url, e)
        tmp.unlink(missing_ok=True)
        return None


def ai_image(prompt: str, dest: Path) -> Path | None:
    try:
        q = urllib.parse.quote(f"{prompt}, editorial illustration, alternate composition")
        raw = _download(f"https://image.pollinations.ai/prompt/{q}"
                        f"?width=1200&height=800&nologo=true")
        return _save_jpeg(Image.open(io.BytesIO(raw)), dest)
    except Exception as e:  # noqa: BLE001
        log.warning("ai_image failed: %s", e)
        return None


def build_media(cand: Candidate, post: PostContent, outdir: Path,
                channel: str) -> tuple[list[str], bool]:
    img_dir = Path(outdir) / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    thumb = make_thumbnail(post.thumbnail_prompt, post.thumbnail_title,
                           img_dir / "01_thumbnail.jpg", channel)
    paths.append(str(thumb))

    src = fetch_source_image(cand.top_image, img_dir / "02_source.jpg")
    if src:
        paths.append(str(src))

    shot = screenshot(cand.url, img_dir / "03_screenshot.jpg")
    if shot:
        paths.append(str(shot))

    if len(paths) < 4:
        ai = ai_image(post.thumbnail_prompt, img_dir / "04_ai.jpg")
        if ai:
            paths.append(str(ai))

    # dedupe by file size, cap at 4
    seen, uniq = set(), []
    for p in paths[:4]:
        key = Path(p).stat().st_size
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq, len(uniq) < 3
