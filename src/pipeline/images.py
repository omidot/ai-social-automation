from __future__ import annotations
import logging, os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import media
from .models import ArticleContent, PostContent

log = logging.getLogger("images")

_FONT_DIR = Path("assets/fonts")

# Hard-coded brand palette / copy; settings `images.brand` overrides any subset.
BRAND_DEFAULTS: dict = {
    "bg": "#F4F3F0",        # near-white warm grey background
    "dot": "#E3E1DC",       # faint dot-grid colour
    "accent": "#1D4ED8",    # brand blue (pill, underline)
    "ink": "#111111",       # near-black headline
    "muted": "#6B6B6B",     # channel handle grey
    "handle": "A Hít Official",
    "kicker_deep": "AI HÔM NAY",
    "kicker_roundup": "ĐIỂM TIN AI",
}


def _gemini_image(prompt: str, size: tuple[int, int]) -> bytes:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.6-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for part in resp.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob and blob.data:
            return blob.data
    raise RuntimeError("gemini returned no image")


def _handle_font(size: int) -> ImageFont.FreeTypeFont:
    """A non-bold face for the channel handle if one is shipped, else Bold."""
    for name in ("BeVietnamPro-Regular.ttf", "BeVietnamPro-Medium.ttf",
                 "BeVietnamPro-Light.ttf"):
        p = _FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype(str(media.FONT_PATH), size)


def _render_cover(article: ArticleContent, size: tuple[int, int],
                  brand: dict | None = None) -> Image.Image:
    """Draw the whole templated flat-editorial cover slide with Pillow.

    Layout (portrait, e.g. 1080x1350):
      - near-white warm-grey background with a faint 26px dot grid
      - a solid brand-blue pill (UPPERCASE kicker) near the top-left of the text block
      - the wrapped, bold, near-black headline (auto-shrink 92 -> 44px, <=3 lines,
        left-aligned within the W-160 safe width), sitting in the upper-middle band
      - a minimal 4px brand-blue underline accent under the headline
      - the channel handle, muted grey, centred ~40px above the bottom edge
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    img = Image.new("RGB", (W, H), b["bg"])
    draw = ImageDraw.Draw(img)

    # faint dot grid
    step, r = 26, 1
    for gy in range(step, H, step):
        for gx in range(step, W, step):
            draw.ellipse((gx - r, gy - r, gx + r, gy + r), fill=b["dot"])

    margin = 80
    safe_w = W - 2 * margin

    # pill kicker
    fmt = getattr(article, "format", "deep")
    kicker = (b["kicker_deep"] if fmt == "deep" else b["kicker_roundup"]).upper()
    pill_font = ImageFont.truetype(str(media.FONT_PATH), 26)
    pad_x, pad_y = 24, 13
    kw = draw.textlength(kicker, font=pill_font)
    asc, desc = pill_font.getmetrics()
    kh = asc + desc
    px0, py0 = margin, 210
    px1, py1 = px0 + kw + 2 * pad_x, py0 + kh + 2 * pad_y
    draw.rounded_rectangle((px0, py0, px1, py1), radius=(py1 - py0) // 2,
                           fill=b["accent"])
    draw.text((px0 + pad_x, py0 + pad_y), kicker, font=pill_font, fill="#FFFFFF")

    # headline: fit-and-wrap, auto-shrink to <=3 lines within the safe width
    title = (article.cover_title or "").strip()
    head_size = 92
    hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
    lines = media._wrap(draw, title, hf, safe_w)
    while head_size > 44 and len(lines) > 3:
        head_size -= 4
        hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
        lines = media._wrap(draw, title, hf, safe_w)

    line_h = int(head_size * 1.18)
    y = py1 + 70
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=b["ink"])
        y += line_h

    # minimal brand-blue underline accent
    uy = y + 22
    draw.rectangle((margin, uy, margin + 120, uy + 4), fill=b["accent"])

    # channel handle, centred near the bottom
    handle_font = _handle_font(30)
    hw = draw.textlength(b["handle"], font=handle_font)
    hasc, hdesc = handle_font.getmetrics()
    draw.text(((W - hw) / 2, H - 40 - (hasc + hdesc)), b["handle"],
              font=handle_font, fill=b["muted"])
    return img


def _render_slide(index: int, total: int, slide: dict, size: tuple[int, int],
                  brand: dict | None = None) -> Image.Image:
    """One flat-brand text card, same visual language as ``_render_cover``.

    Layout (portrait, e.g. 1080x1350):
      - the same near-white warm-grey background with a faint 26px dot grid
      - a small brand-blue index marker top-left, e.g. ``02 / 03``
      - ``slide["headline"]`` wrapped, bold, near-black (auto-shrink 84 -> 40px,
        <=4 lines, left-aligned within the W-160 safe width)
      - a minimal 4px brand-blue underline accent under the headline
      - ``slide["sub"]`` below it, ~34px, #333, wrapped
      - the channel handle, muted grey, centred ~40px above the bottom edge
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    img = Image.new("RGB", (W, H), b["bg"])
    draw = ImageDraw.Draw(img)

    # faint dot grid (identical to the cover)
    step, r = 26, 1
    for gy in range(step, H, step):
        for gx in range(step, W, step):
            draw.ellipse((gx - r, gy - r, gx + r, gy + r), fill=b["dot"])

    margin = 80
    safe_w = W - 2 * margin

    # brand-blue index marker, e.g. "02 / 03"
    marker = f"{index:02d} / {max(total, index):02d}"
    marker_font = ImageFont.truetype(str(media.FONT_PATH), 30)
    draw.text((margin, 150), marker, font=marker_font, fill=b["accent"])

    headline = str((slide or {}).get("headline", "")).strip()
    sub = str((slide or {}).get("sub", "")).strip()

    # headline: fit-and-wrap, auto-shrink to <=4 lines within the safe width
    head_size = 84
    hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
    lines = media._wrap(draw, headline, hf, safe_w)
    while head_size > 40 and len(lines) > 4:
        head_size -= 4
        hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
        lines = media._wrap(draw, headline, hf, safe_w)

    line_h = int(head_size * 1.18)
    y = 300
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=b["ink"])
        y += line_h

    # minimal brand-blue underline accent
    uy = y + 20
    draw.rectangle((margin, uy, margin + 120, uy + 4), fill=b["accent"])

    # takeaway / "so what" line
    if sub:
        sub_font = _handle_font(34)
        sy = uy + 40
        for ln in media._wrap(draw, sub, sub_font, safe_w):
            draw.text((margin, sy), ln, font=sub_font, fill="#333333")
            sy += 46

    # channel handle, centred near the bottom
    handle_font = _handle_font(30)
    hw = draw.textlength(b["handle"], font=handle_font)
    hasc, hdesc = handle_font.getmetrics()
    draw.text(((W - hw) / 2, H - 40 - (hasc + hdesc)), b["handle"],
              font=handle_font, fill=b["muted"])
    return img


def _legacy_fallback(article: ArticleContent, out_dir: Path,
                     size: tuple[int, int]) -> list[str]:
    stub = PostContent(
        angle="tin-tuc", caption_fb=article.caption_fb, caption_ig=article.caption_ig,
        hashtags=article.hashtags, thumbnail_prompt=article.cover_brief,
        thumbnail_title=article.cover_title, youtube_title="", youtube_desc="",
        tiktok_caption="", source_url=article.sources[0]["url"],
        source_name=article.sources[0]["name"])
    from .models import Candidate
    from datetime import datetime, timezone
    cand = Candidate(url=article.sources[0]["url"], title=article.cover_title,
                     source=article.sources[0]["name"],
                     published_at=datetime.now(timezone.utc))
    paths, _ = media.build_media(cand, stub, Path(out_dir), "")
    # media.build_media returns mixed sizes/aspect ratios (1200x630, 1280x720, ...);
    # Instagram rejects a carousel whose images are not all the same size, so
    # normalize every image to the spec size before returning.
    normed: list[str] = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        normed.append(str(media._save_jpeg(im, Path(p), size)))
    return normed


def build_images(article: ArticleContent, out_dir, *, size: tuple[int, int],
                 brand: dict | None = None, **ignored) -> list[str]:
    """Every image is a designed flat-brand slide: ``01_cover.jpg`` plus one
    ``NN.jpg`` per ``article.slides`` entry. No Gemini, no screenshots.

    Degradation ladder: if a slide render throws, return the cover alone; if even
    the cover render throws, fall back to ``media.build_media`` via
    ``_legacy_fallback``. ``**ignored`` swallows retired kwargs (``style_prompt``,
    ``provider``, ``gen``).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    b = {**BRAND_DEFAULTS, **(brand or {})}

    try:
        cover = _render_cover(article, size, b)
    except Exception as e:  # noqa: BLE001 - cover render is the last thing we can salvage
        log.warning("cover render failed (%s); using legacy media", e)
        return _legacy_fallback(article, out_dir, size)

    cover_path = str(media._save_jpeg(cover, out_dir / "01_cover.jpg", size))
    try:
        paths = [cover_path]
        slides = list(getattr(article, "slides", []) or [])
        for i, slide in enumerate(slides, start=2):
            im = _render_slide(i - 1, len(slides), slide, size, b)
            paths.append(str(media._save_jpeg(im, out_dir / f"{i:02d}.jpg", size)))
        return paths
    except Exception as e:  # noqa: BLE001 - a broken slide must not sink the whole post
        log.warning("slide render failed (%s); returning cover only", e)
        return [cover_path]
