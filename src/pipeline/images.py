from __future__ import annotations
import logging, os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

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
    "watermark": "#E9E7E2",  # giant ghost digit/glyph behind the cover
    "highlight": "#DBE7FF",  # light-blue block behind the last headline line
    "tile_icon": "#1F2937",  # monochrome tech icon inside the frosted tiles
}


# --- tiny monochrome tech icons, drawn purely with ImageDraw -----------------
# Each fn signature: ``_icon_x(draw, box, colour)`` where ``box`` is
# ``(x0, y0, x1, y1)``. They render inside that box on whatever image ``draw``
# is bound to (used both on the cover's frosted tiles and, in tests, straight
# onto a blank canvas).

def _icon_spark(draw, box, colour):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    ix, iy = rx * 0.30, ry * 0.30
    draw.polygon(
        [(cx, y0), (cx + ix, cy - iy), (x1, cy), (cx + ix, cy + iy),
         (cx, y1), (cx - ix, cy + iy), (x0, cy), (cx - ix, cy - iy)],
        fill=colour)


def _icon_chip(draw, box, colour):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    inset = w * 0.18
    bx0, by0, bx1, by1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    lw = max(2, int(w * 0.05))
    draw.rounded_rectangle((bx0, by0, bx1, by1), radius=w * 0.08,
                           outline=colour, width=lw)
    draw.rectangle((bx0 + w * 0.14, by0 + h * 0.14, bx1 - w * 0.14, by1 - h * 0.14),
                   outline=colour, width=max(1, int(w * 0.035)))
    pin = w * 0.06
    for f in (0.30, 0.5, 0.70):
        draw.rectangle((x0 + w * f - pin / 2, y0 + inset * 0.15, x0 + w * f + pin / 2, by0), fill=colour)
        draw.rectangle((x0 + w * f - pin / 2, by1, x0 + w * f + pin / 2, y1 - inset * 0.15), fill=colour)
        draw.rectangle((x0 + inset * 0.15, y0 + h * f - pin / 2, bx0, y0 + h * f + pin / 2), fill=colour)
        draw.rectangle((bx1, y0 + h * f - pin / 2, x1 - inset * 0.15, y0 + h * f + pin / 2), fill=colour)


def _icon_brain(draw, box, colour):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    lw = max(2, int(w * 0.05))
    draw.rounded_rectangle((x0 + w * 0.06, y0 + h * 0.18, x0 + w * 0.58, y1 - h * 0.18),
                           radius=h * 0.30, outline=colour, width=lw)
    draw.rounded_rectangle((x0 + w * 0.42, y0 + h * 0.18, x1 - w * 0.06, y1 - h * 0.18),
                           radius=h * 0.30, outline=colour, width=lw)
    draw.line((x0 + w * 0.5, y0 + h * 0.12, x0 + w * 0.5, y1 - h * 0.12), fill=colour, width=lw)


def _icon_bolt(draw, box, colour):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    draw.polygon(
        [(x0 + w * 0.56, y0), (x0 + w * 0.18, y0 + h * 0.58), (x0 + w * 0.46, y0 + h * 0.58),
         (x0 + w * 0.40, y1), (x0 + w * 0.82, y0 + h * 0.40), (x0 + w * 0.54, y0 + h * 0.40)],
        fill=colour)


def _icon_globe(draw, box, colour):
    x0, y0, x1, y1 = box
    w = x1 - x0
    lw = max(2, int(w * 0.045))
    m = w * 0.10
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    draw.ellipse((x0 + m, y0 + m, x1 - m, y1 - m), outline=colour, width=lw)
    draw.ellipse((cx - w * 0.14, y0 + m, cx + w * 0.14, y1 - m), outline=colour, width=lw)
    draw.ellipse((cx - w * 0.30, y0 + m, cx + w * 0.30, y1 - m), outline=colour, width=lw)
    draw.line((x0 + m, cy, x1 - m, cy), fill=colour, width=lw)


def _icon_graph(draw, box, colour):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    bw, gap = w * 0.20, w * 0.10
    base = y1 - h * 0.10
    bx = x0 + w * 0.08
    for frac in (0.35, 0.62, 0.92):
        draw.rectangle((bx, base - h * frac, bx + bw, base), fill=colour)
        bx += bw + gap


def _icon_robot(draw, box, colour):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    lw = max(2, int(w * 0.05))
    hx0, hy0, hx1, hy1 = x0 + w * 0.14, y0 + h * 0.30, x1 - w * 0.14, y1 - h * 0.12
    draw.rounded_rectangle((hx0, hy0, hx1, hy1), radius=w * 0.12, outline=colour, width=lw)
    cx = (x0 + x1) / 2
    draw.line((cx, y0 + h * 0.08, cx, hy0), fill=colour, width=lw)
    draw.ellipse((cx - w * 0.05, y0 + h * 0.02, cx + w * 0.05, y0 + h * 0.12), fill=colour)
    ey = (hy0 + hy1) / 2
    r = w * 0.06
    draw.ellipse((x0 + w * 0.34 - r, ey - r, x0 + w * 0.34 + r, ey + r), fill=colour)
    draw.ellipse((x1 - w * 0.34 - r, ey - r, x1 - w * 0.34 + r, ey + r), fill=colour)


def _icon_chat(draw, box, colour):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    lw = max(2, int(w * 0.05))
    bx0, by0, bx1, by1 = x0 + w * 0.10, y0 + h * 0.14, x1 - w * 0.10, y0 + h * 0.66
    draw.rounded_rectangle((bx0, by0, bx1, by1), radius=h * 0.16, outline=colour, width=lw)
    draw.polygon([(x0 + w * 0.30, by1 - lw), (x0 + w * 0.30, by1 + h * 0.20),
                  (x0 + w * 0.52, by1 - lw)], fill=colour)


_ICONS: dict = {
    "spark": _icon_spark, "chip": _icon_chip, "brain": _icon_brain,
    "bolt": _icon_bolt, "globe": _icon_globe, "graph": _icon_graph,
    "robot": _icon_robot, "chat": _icon_chat,
}
# deterministic pick order for the fan (cycled if more tiles than icons)
_ICON_ORDER = ["spark", "chip", "bolt", "graph", "globe", "brain", "robot", "chat"]


def _make_tile(px: int, icon_fn, colour) -> Image.Image:
    """A single frosted-glass icon tile as an RGBA image (with transparent pad)."""
    pad = 26
    S = px + 2 * pad
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    box = (pad, pad, pad + px, pad + px)
    rad = int(px * 0.22)
    d.rounded_rectangle(box, radius=rad, fill=(255, 255, 255, 200))
    d.rounded_rectangle(box, radius=rad, outline=(255, 255, 255, 236), width=2)
    inset = px * 0.26
    icon_fn(d, (pad + inset, pad + inset, pad + px - inset, pad + px - inset), colour)
    return tile


def _draw_icon_fan(img: Image.Image, b: dict, fmt: str) -> None:
    """Composite a shallow arc of frosted-glass icon tiles onto ``img`` in place.

    5 tiles for a roundup, 3 for a deep. Middle tile flat and lifted ~30px;
    neighbours rotate +/-8 deg, outer +/-16 deg. Each tile carries a soft,
    blurred drop shadow offset +8,+12.
    """
    W, H = img.size
    n = 5 if fmt == "roundup" else 3
    names = [_ICON_ORDER[i % len(_ICON_ORDER)] for i in range(n)]
    tile_px, step = 140, 200
    base_y = int(H * 0.70)
    half = n // 2
    for k, name in enumerate(names):
        rel = k - half
        angle = -rel * 8
        lift = int(30 * (1 - abs(rel) / half)) if half else 30
        cx = W // 2 + rel * step
        cy = base_y - lift
        tile = _make_tile(tile_px, _ICONS[name], b["tile_icon"])
        rot = tile.rotate(angle, expand=True, resample=Image.BICUBIC)
        ox, oy = cx - rot.width // 2, cy - rot.height // 2
        shadow = Image.new("RGBA", rot.size, (0, 0, 0, 0))
        shadow.paste((17, 17, 17, 90), (0, 0), rot.split()[3])
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        img.paste(shadow, (ox + 8, oy + 12), shadow)
        img.paste(rot, (ox, oy), rot)


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
    """Draw the whole templated designer-carousel cover slide with Pillow.

    Layer order (back -> front):
      1. near-white warm-grey background
      2. a giant faint watermark digit/glyph (roundup: slide count; deep: "AI"),
         ~900px tall, ghost grey, bleeding off the lower-right edge
      3. the faint 26px dot grid
      4. a white kicker pill (thin border + soft shadow, brand-blue UPPERCASE text)
      5. the wrapped bold near-black headline (auto-shrink 92 -> 44px, <=3 lines
         within the W-160 safe width); a light-blue highlight block sits behind
         the last wrapped line
      6. a minimal 4px brand-blue underline accent under the headline
      7. a shallow arc of frosted-glass icon tiles (5 roundup / 3 deep) in the
         lower-middle band
      8. the channel handle, muted grey, centred ~40px above the bottom edge
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    img = Image.new("RGB", (W, H), b["bg"])
    draw = ImageDraw.Draw(img)

    fmt = getattr(article, "format", "deep")
    n_slides = len(getattr(article, "slides", []) or [])

    # 2. giant ghost watermark, bleeding off the lower-right
    wm_text = str(n_slides) if fmt == "roundup" else "AI"
    try:
        wm_font = ImageFont.truetype(str(media.FONT_PATH), 900)
        wl, wt, wr, wb = draw.textbbox((0, 0), wm_text, font=wm_font)
        tw, th = wr - wl, wb - wt
        draw.text((int(W - tw * 0.62) - wl, int(H - th * 0.80) - wt), wm_text,
                  font=wm_font, fill=b["watermark"])
    except Exception:  # noqa: BLE001 - a missing giant glyph must not sink the cover
        pass

    # 3. faint dot grid
    step, r = 26, 1
    for gy in range(step, H, step):
        for gx in range(step, W, step):
            draw.ellipse((gx - r, gy - r, gx + r, gy + r), fill=b["dot"])

    margin = 80
    safe_w = W - 2 * margin

    # 4. white kicker pill with a soft shadow + thin border, brand-blue text
    kicker = (b["kicker_deep"] if fmt == "deep" else b["kicker_roundup"]).upper()
    pill_font = ImageFont.truetype(str(media.FONT_PATH), 26)
    pad_x, pad_y = 24, 13
    kw = draw.textlength(kicker, font=pill_font)
    asc, desc = pill_font.getmetrics()
    kh = asc + desc
    px0, py0 = margin, 210
    px1, py1 = px0 + kw + 2 * pad_x, py0 + kh + 2 * pad_y
    pill_rad = (py1 - py0) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (px0 + 3, py0 + 7, px1 + 3, py1 + 7), radius=pill_rad, fill=(17, 17, 17, 55))
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    img.paste(shadow, (0, 0), shadow)
    draw.rounded_rectangle((px0, py0, px1, py1), radius=pill_rad,
                           fill="#FFFFFF", outline=b["dot"], width=1)
    draw.text((px0 + pad_x, py0 + pad_y), kicker, font=pill_font, fill=b["accent"])

    # 5. headline: fit-and-wrap, auto-shrink to <=3 lines within the safe width
    title = (article.cover_title or "").strip()
    head_size = 92
    hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
    lines = media._wrap(draw, title, hf, safe_w)
    while head_size > 44 and len(lines) > 3:
        head_size -= 4
        hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
        lines = media._wrap(draw, title, hf, safe_w)

    line_h = int(head_size * 1.18)
    y0_head = py1 + 70
    hasc, hdesc = hf.getmetrics()

    # light-blue highlight block behind the last wrapped line
    if lines:
        last = lines[-1]
        ly = y0_head + (len(lines) - 1) * line_h
        lw = draw.textlength(last, font=hf)
        draw.rounded_rectangle((margin - 10, ly - 4, margin + lw + 10, ly + hasc + hdesc + 4),
                               radius=8, fill=b["highlight"])

    y = y0_head
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=b["ink"])
        y += line_h

    # 6. minimal brand-blue underline accent
    uy = y + 22
    draw.rectangle((margin, uy, margin + 120, uy + 4), fill=b["accent"])

    # 7. shallow arc of frosted-glass icon tiles
    _draw_icon_fan(img, b, fmt)

    # 8. channel handle, centred near the bottom
    handle_font = _handle_font(30)
    hw = draw.textlength(b["handle"], font=handle_font)
    hha, hhd = handle_font.getmetrics()
    draw.text(((W - hw) / 2, H - 40 - (hha + hhd)), b["handle"],
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
