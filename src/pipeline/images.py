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
    "watermark": "#E9E7E2",  # giant ghost slide numeral behind every slide
    "highlight": "#DBE7FF",  # light-blue block behind the hook headline
    "tile_icon": "#1F2937",  # monochrome tech icon (frosted tiles + step accent)
    "progress_on": "#1D4ED8",   # filled progress segment (<= current slide)
    "progress_off": "#D9D7D2",  # empty progress segment
    "role_labels": {            # kicker-pill label per step role
        "what": "AI LÀM ĐƯỢC GÌ",
        "why": "BẠN ĐƯỢC GÌ",
        "how": "CÁCH BẮT ĐẦU",
        "close": "CHỐT LẠI",
    },
}

# the one monochrome accent icon each step slide carries in its upper-right
_ROLE_ICON = {"what": "chip", "why": "spark", "how": "bolt", "close": "chat"}


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


def _draw_icon_fan(img: Image.Image, b: dict, n: int = 5) -> None:
    """Composite a shallow arc of ``n`` frosted-glass icon tiles onto ``img`` in
    place (the hook slide's signature element).

    Middle tile flat and lifted ~30px; neighbours rotate +/-8 deg, outer
    +/-16 deg. Each tile carries a soft, blurred drop shadow offset +8,+12.
    """
    W, H = img.size
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


# --- shared storyboard skeleton --------------------------------------------

def _draw_progress(draw: ImageDraw.ImageDraw, b: dict, i: int, size: tuple[int, int],
                   total: int = 5) -> None:
    """5 small rounded segments near the top; segments ``<= i`` filled brand-blue,
    the rest light grey."""
    W, _ = size
    margin, gap, seg_h, y = 80, 14, 12, 92
    seg_w = (W - 2 * margin - gap * (total - 1)) / total
    for k in range(total):
        x0 = margin + k * (seg_w + gap)
        fill = b["progress_on"] if k <= i else b["progress_off"]
        draw.rounded_rectangle((x0, y, x0 + seg_w, y + seg_h),
                               radius=seg_h / 2, fill=fill)


def _draw_skeleton(img: Image.Image, draw: ImageDraw.ImageDraw, b: dict,
                   i: int, size: tuple[int, int]) -> None:
    """Everything the 5 slides share so they read as one story: warm-grey bg
    (already painted) + dot grid, a faint giant ghost numeral bottom-right, the
    progress bar up top, and the channel handle centred at the bottom."""
    W, H = size

    # faint giant ghost numeral (slide number), bleeding off the lower-right
    try:
        wm_font = ImageFont.truetype(str(media.FONT_PATH), 900)
        wm_text = str(i + 1)
        wl, wt, wr, wb = draw.textbbox((0, 0), wm_text, font=wm_font)
        tw, th = wr - wl, wb - wt
        draw.text((int(W - tw * 0.60) - wl, int(H - th * 0.82) - wt), wm_text,
                  font=wm_font, fill=b["watermark"])
    except Exception:  # noqa: BLE001 - a missing giant glyph must not sink a slide
        pass

    # faint 26px dot grid
    step, r = 26, 1
    for gy in range(step, H, step):
        for gx in range(step, W, step):
            draw.ellipse((gx - r, gy - r, gx + r, gy + r), fill=b["dot"])

    # progress bar
    _draw_progress(draw, b, i, size)

    # channel handle, centred near the bottom
    handle_font = _handle_font(30)
    hw = draw.textlength(b["handle"], font=handle_font)
    hasc, hdesc = handle_font.getmetrics()
    draw.text(((W - hw) / 2, H - 40 - (hasc + hdesc)), b["handle"],
              font=handle_font, fill=b["muted"])


def _render_hook_slide(article: ArticleContent, size: tuple[int, int],
                       brand: dict | None = None) -> Image.Image:
    """Slide 1 (role "hook"): the boldest slide. Shared skeleton + a big
    highlighted headline (light-blue block behind the last wrapped line, same
    treatment the old cover used) + the frosted-glass icon fan. Replaces the
    old standalone cover.
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    img = Image.new("RGB", (W, H), b["bg"])
    draw = ImageDraw.Draw(img)
    _draw_skeleton(img, draw, b, 0, size)

    margin = 80
    safe_w = W - 2 * margin

    title = (getattr(article, "cover_title", "") or "").strip()
    if not title:
        slides = getattr(article, "slides", None) or []
        if slides:
            title = str(slides[0].get("headline", "")).strip()

    head_size = 92
    hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
    lines = media._wrap(draw, title, hf, safe_w)
    while head_size > 44 and len(lines) > 3:
        head_size -= 4
        hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
        lines = media._wrap(draw, title, hf, safe_w)

    line_h = int(head_size * 1.18)
    y0_head = 300
    hasc, hdesc = hf.getmetrics()

    if lines:
        last = lines[-1]
        ly = y0_head + (len(lines) - 1) * line_h
        lw = draw.textlength(last, font=hf)
        draw.rounded_rectangle((margin - 10, ly - 4, margin + lw + 10,
                                ly + hasc + hdesc + 4), radius=8, fill=b["highlight"])

    y = y0_head
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=b["ink"])
        y += line_h

    # minimal brand-blue underline accent
    draw.rectangle((margin, y + 22, margin + 120, y + 26), fill=b["accent"])

    # signature frosted-glass icon fan in the lower-middle band
    _draw_icon_fan(img, b, 5)
    return img


def _render_step_slide(i: int, slide: dict, size: tuple[int, int],
                       brand: dict | None = None) -> Image.Image:
    """Slides 2-5 (what / why / how / close): shared skeleton + a small
    brand-blue kicker pill with the Vietnamese role label, the wrapped bold
    headline, a thin blue underline, then the body in #333, plus one small
    monochrome accent icon in the upper-right.
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    img = Image.new("RGB", (W, H), b["bg"])
    draw = ImageDraw.Draw(img)
    _draw_skeleton(img, draw, b, i, size)

    margin = 80
    safe_w = W - 2 * margin
    slide = slide or {}
    role = str(slide.get("role", "")).strip().lower()
    headline = str(slide.get("headline", "")).strip()
    body = str(slide.get("body", "")).strip()

    # brand-blue kicker pill with the role label (white text)
    labels = b.get("role_labels", {}) or {}
    label = str(labels.get(role, role.upper() or "BƯỚC"))
    pill_font = ImageFont.truetype(str(media.FONT_PATH), 26)
    pad_x, pad_y = 24, 13
    kw = draw.textlength(label, font=pill_font)
    asc, desc = pill_font.getmetrics()
    px0, py0 = margin, 175
    px1, py1 = px0 + kw + 2 * pad_x, py0 + (asc + desc) + 2 * pad_y
    draw.rounded_rectangle((px0, py0, px1, py1), radius=(py1 - py0) // 2,
                           fill=b["accent"])
    draw.text((px0 + pad_x, py0 + pad_y), label, font=pill_font, fill="#FFFFFF")

    # one small monochrome accent icon, upper-right, aligned with the pill
    icon_fn = _ICONS.get(_ROLE_ICON.get(role, "chip"))
    if icon_fn:
        isz = 96
        icon_fn(draw, (W - margin - isz, py0 - 6, W - margin, py0 - 6 + isz),
                b["tile_icon"])

    # headline: fit-and-wrap, auto-shrink to <=4 lines within the safe width
    head_size = 84
    hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
    lines = media._wrap(draw, headline, hf, safe_w)
    while head_size > 40 and len(lines) > 4:
        head_size -= 4
        hf = ImageFont.truetype(str(media.FONT_PATH), head_size)
        lines = media._wrap(draw, headline, hf, safe_w)

    line_h = int(head_size * 1.18)
    y = py1 + 80
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=b["ink"])
        y += line_h

    # thin brand-blue underline accent
    uy = y + 20
    draw.rectangle((margin, uy, margin + 120, uy + 4), fill=b["accent"])

    # body copy in #333
    if body:
        body_font = _handle_font(34)
        sy = uy + 42
        for ln in media._wrap(draw, body, body_font, safe_w):
            draw.text((margin, sy), ln, font=body_font, fill="#333333")
            sy += 46

    return img


def _legacy_fallback(article: ArticleContent, out_dir: Path,
                     size: tuple[int, int]) -> list[str]:
    stub = PostContent(
        angle="tin-tuc", caption_fb=article.caption_fb, caption_ig=article.caption_ig,
        hashtags=article.hashtags, thumbnail_prompt="",
        thumbnail_title=article.cover_title, youtube_title="", youtube_desc="",
        tiktok_caption="", source_url=article.sources[0]["url"],
        source_name=article.sources[0]["name"])
    from .models import Candidate
    from datetime import datetime, timezone
    cand = Candidate(url=article.sources[0]["url"], title=article.cover_title,
                     source=article.sources[0]["name"],
                     published_at=datetime.now(timezone.utc))
    paths, _ = media.build_media(cand, stub, Path(out_dir), "")
    # media.build_media returns mixed sizes/aspect ratios; Instagram rejects a
    # carousel whose images are not all the same size, so normalize every image
    # to the spec size before returning.
    normed: list[str] = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        normed.append(str(media._save_jpeg(im, Path(p), size)))
    return normed


def _safe_fallback(article: ArticleContent, out_dir: Path,
                   size: tuple[int, int]) -> list[str]:
    """Minimal safe output when the full storyboard render throws: the hook
    slide alone, or - if even that fails - legacy ``media.build_media``."""
    try:
        im = _render_hook_slide(article, size)
        return [str(media._save_jpeg(im, Path(out_dir) / "01.jpg", size))]
    except Exception as e:  # noqa: BLE001 - hook is the last thing we can salvage
        log.warning("hook-slide fallback failed (%s); using legacy media", e)
        return _legacy_fallback(article, out_dir, size)


def build_images(article: ArticleContent, out_dir, *, size: tuple[int, int],
                 brand: dict | None = None, **ignored) -> list[str]:
    """Render the 5-slide storyboard carousel: ``01.jpg`` .. ``05.jpg``, one per
    ``article.slides`` entry, all in one visual system (shared bg + dot grid,
    progress bar, handle, ghost numeral). Slide 1 is the bold hook slide with the
    icon fan; slides 2-5 are the what/why/how/close steps.

    On ANY exception the whole render degrades to a minimal safe fallback
    (hook slide alone, else ``media.build_media``); it never propagates.
    ``**ignored`` swallows retired kwargs (``style_prompt``, ``provider``, ``gen``).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    b = {**BRAND_DEFAULTS, **(brand or {})}

    try:
        slides = list(getattr(article, "slides", []) or [])
        paths: list[str] = []
        for i in range(5):
            slide = slides[i] if i < len(slides) else {}
            role = str(slide.get("role", "")).strip().lower() if isinstance(slide, dict) else ""
            if i == 0 or role == "hook":
                im = _render_hook_slide(article, size, b)
            else:
                im = _render_step_slide(i, slide, size, b)
            paths.append(str(media._save_jpeg(im, out_dir / f"{i + 1:02d}.jpg", size)))
        return paths
    except Exception as e:  # noqa: BLE001 - a broken slide must not sink the post
        log.warning("storyboard render failed (%s); using safe fallback", e)
        return _safe_fallback(article, out_dir, size)
