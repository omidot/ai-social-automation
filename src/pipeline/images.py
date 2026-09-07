from __future__ import annotations
import io, logging, os
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from . import media
from .models import ArticleContent, PostContent

log = logging.getLogger("images")

_FONT_DIR = Path("assets/fonts")

# Shared logo cache dir, resolved relative to the repo root passed into
# ``build_images``. ``scripts/commit_state.sh`` already stages ``assets/`` so a
# fetched logo is committed once and reused forever.
LOGO_DIR = Path("assets/logos")

# Hard-coded brand palette / copy; settings `images.brand` overrides any subset.
BRAND_DEFAULTS: dict = {
    "accent": "#1D4ED8",    # brand blue (numerals, underline, pill, progress)
    "ink": "#111111",       # near-black headline on the light item slides
    "handle": "A Hít Official",
    "kicker": "A HÍT OFFICIAL",   # brand pill on the hook slide
    # --- light "item" slides -------------------------------------------------
    "item_bg": "#F1F2F4",       # cool light background
    "item_dot": "#E2E4E8",      # faint dot grid
    "body_ink": "#3A3F4A",      # item body copy
    "progress_off": "#D4D7DD",  # empty progress segment (light slides)
    "swipe_hint": "#8A90A0",    # "Vuốt tiếp ›" bottom-right
    "watermark": "#E6E8EC",     # ghost numeral bottom-right
    "muted": "#6B6B6B",         # handle on the close slide
    "tile_icon": "#1F2937",     # monochrome glyph when no real logo
    # --- dark "hook" slide -------------------------------------------------
    "hook_bg": "#0B0B10",           # near-black
    "hook_dot": "#1A1A22",          # faint dot grid
    "hook_glow": "#1D4ED8",         # blue radial glow top-left (= accent)
    "hook_body": "#B9BDC9",         # hook sub-line
    "hook_progress_off": "#2A2A35", # empty progress segment (dark slide)
    "cta_border": "#6B7280",        # swipe-CTA outline
    "cta_text": "#E5E7EB",          # swipe-CTA label
    # retained so the legacy media fallback keeps its old look
    "bg": "#F4F3F0", "dot": "#E3E1DC", "highlight": "#DBE7FF",
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


# --- real tool logos -----------------------------------------------------

def _fetch_logo(domain: str, root: Path) -> Image.Image | None:
    """Return an RGBA logo image for ``domain`` or ``None`` — never raises.

    Cache: ``<root>/assets/logos/<domain>.png``. On a miss, try Google's
    favicon service (sz=256), then unavatar.io. Anything smaller than 32px or
    any failure falls through; a real hit is cached for next time.
    """
    try:
        cache = Path(root) / LOGO_DIR / f"{domain}.png"
        if cache.exists():
            try:
                im = Image.open(cache)
                im.load()
                return im.convert("RGBA")
            except Exception as e:  # noqa: BLE001 - a bad cache file, refetch
                log.warning("cached logo %s unreadable (%s); refetching", cache, e)

        sources = (
            f"https://www.google.com/s2/favicons?domain={domain}&sz=256",
            f"https://unavatar.io/{domain}",
        )
        logo: Image.Image | None = None
        for url in sources:
            try:
                r = httpx.get(url, timeout=10.0, follow_redirects=True)
                r.raise_for_status()
                cand = Image.open(io.BytesIO(r.content)).convert("RGBA")
            except Exception as e:  # noqa: BLE001 - try the next source
                log.warning("logo fetch failed for %s via %s (%s)", domain, url, e)
                continue
            if min(cand.size) < 32:
                log.warning("logo for %s from %s too small (%s)", domain, url, cand.size)
                continue
            logo = cand
            break
        if logo is None:
            log.warning("no usable logo for %s", domain)
            return None

        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            logo.save(cache, format="PNG")
        except Exception as e:  # noqa: BLE001 - caching is best-effort
            log.warning("could not cache logo %s (%s)", cache, e)
        return logo
    except Exception as e:  # noqa: BLE001 - a logo must never sink a slide
        log.warning("unexpected logo error for %s (%s)", domain, e)
        return None


# --- shared storyboard bits ---------------------------------------------

def _draw_progress(draw: ImageDraw.ImageDraw, b: dict, i: int, size: tuple[int, int],
                   total: int = 5, off: str | None = None) -> None:
    """``total`` rounded segments near the top; segments ``<= i`` filled
    brand-blue, the rest ``off`` (defaults to the light-slide empty colour)."""
    W, _ = size
    total = max(1, total)
    margin, gap, seg_h, y = 80, 14, 12, 92
    off = off or b["progress_off"]
    seg_w = (W - 2 * margin - gap * (total - 1)) / total
    for k in range(total):
        x0 = margin + k * (seg_w + gap)
        fill = b["accent"] if k <= i else off
        draw.rounded_rectangle((x0, y, x0 + seg_w, y + seg_h),
                               radius=seg_h / 2, fill=fill)


def _dot_grid(draw: ImageDraw.ImageDraw, size: tuple[int, int], colour: str,
              step: int = 40, r: int = 2) -> None:
    W, H = size
    for gy in range(step, H, step):
        for gx in range(step, W, step):
            draw.ellipse((gx - r, gy - r, gx + r, gy + r), fill=colour)


def _fit_lines(draw, text: str, start: int, floor: int, max_w: int,
               max_lines: int, step: int = 6):
    """Wrap ``text`` at the biggest font (``start`` .. ``floor``) that fits in
    ``max_lines``. Returns ``(font, lines, size)``."""
    sz = start
    hf = ImageFont.truetype(str(media.FONT_PATH), sz)
    lines = media._wrap(draw, text, hf, max_w)
    while sz > floor and len(lines) > max_lines:
        sz -= step
        hf = ImageFont.truetype(str(media.FONT_PATH), sz)
        lines = media._wrap(draw, text, hf, max_w)
    return hf, lines, sz


def _slide_total(article: ArticleContent) -> int:
    n = len(getattr(article, "slides", []) or [])
    return max(5, min(7, n)) if n else 5


def _render_hook_slide(article: ArticleContent, slide: dict, size: tuple[int, int],
                       brand: dict | None = None) -> Image.Image:
    """Slide 1 (role "hook"): a dark, high-punch slide — near-black bg with a
    soft blue radial glow, faint dot grid, a brand kicker pill, one line of the
    hook blown up in brand blue, a muted sub-line, and a swipe CTA near the
    bottom.
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    slide = slide or {}

    img = Image.new("RGB", (W, H), b["hook_bg"])
    # blue radial glow, top-left, on its own heavily-blurred layer
    glow = Image.new("RGB", (W, H), b["hook_bg"])
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-W * 0.35, -H * 0.32, W * 0.55, H * 0.42), fill=b["hook_glow"])
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img = Image.blend(img, glow, 0.22)
    draw = ImageDraw.Draw(img)

    _dot_grid(draw, size, b["hook_dot"], step=46, r=2)
    _draw_progress(draw, b, 0, size, total=_slide_total(article),
                   off=b["hook_progress_off"])

    margin = 70
    safe_w = W - 140

    # brand kicker pill, top-left under the progress bar
    kf = ImageFont.truetype(str(media.FONT_PATH), 26)
    kick = str(b.get("kicker", b["handle"]))
    kw = draw.textlength(kick, font=kf)
    kasc, kdesc = kf.getmetrics()
    kpad_x, kpad_y = 22, 12
    draw.rounded_rectangle((margin, 132, margin + kw + 2 * kpad_x,
                            132 + kasc + kdesc + 2 * kpad_y),
                           radius=(kasc + kdesc + 2 * kpad_y) // 2, fill=b["accent"])
    draw.text((margin + kpad_x, 132 + kpad_y), kick, font=kf, fill="#FFFFFF")

    # the hook headline: auto-fit, <=3 lines; then blow up one line in brand blue
    head = (str(slide.get("headline", "")).strip()
            or (getattr(article, "cover_title", "") or "").strip())
    hf, lines, hsz = _fit_lines(draw, head, 120, 56, safe_w, 3)

    big_idx = None
    for idx, ln in enumerate(lines):
        if len(ln.split()) == 1 and len(ln) >= 6:
            big_idx = idx
    if big_idx is None and lines:
        big_idx = len(lines) - 1
    big_sz = min(int(hsz * 1.5), 150)
    big_hf = ImageFont.truetype(str(media.FONT_PATH), big_sz)
    while big_sz > hsz and big_idx is not None and \
            draw.textlength(lines[big_idx], font=big_hf) > safe_w:
        big_sz -= 6
        big_hf = ImageFont.truetype(str(media.FONT_PATH), big_sz)

    y = int(H * 0.24)
    for idx, ln in enumerate(lines):
        if idx == big_idx:
            draw.text((margin, y), ln, font=big_hf, fill=b["accent"])
            y += int(big_sz * 1.16)
        else:
            draw.text((margin, y), ln, font=hf, fill="#FFFFFF")
            y += int(hsz * 1.18)

    # the hook sub-line, muted, <=2 lines
    sub = str(slide.get("body", "")).strip()
    if sub:
        sf = _handle_font(34)
        y += 16
        for ln in media._wrap(draw, sub, sf, safe_w)[:2]:
            draw.text((margin, y), ln, font=sf, fill=b["hook_body"])
            y += 46

    # swipe CTA: outlined rounded rect, centred, near the bottom
    cta_w, cta_h = 380, 74
    cx0, cy0 = (W - cta_w) // 2, int(H * 0.85)
    draw.rounded_rectangle((cx0, cy0, cx0 + cta_w, cy0 + cta_h),
                           radius=cta_h // 2, outline=b["cta_border"], width=2)
    cta_font = _handle_font(30)
    label = "Vuốt để xem tiếp  ›"
    lw = draw.textlength(label, font=cta_font)
    lasc, ldesc = cta_font.getmetrics()
    draw.text((cx0 + (cta_w - lw) / 2, cy0 + (cta_h - (lasc + ldesc)) / 2),
              label, font=cta_font, fill=b["cta_text"])
    return img


def _logo_tile(img: Image.Image, box: tuple[int, int, int, int], b: dict,
               logo: Image.Image | None, icon_fn) -> None:
    """A white rounded tile with a soft shadow at ``box``; inside it either the
    real ``logo`` (scaled to fit with padding) or a monochrome ``icon_fn``."""
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    rad = 20

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x0 + 6, y0 + 10, x1 + 6, y1 + 10), radius=rad,
                         fill=(17, 17, 17, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img.paste(shadow, (0, 0), shadow)

    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=rad, fill="#FFFFFF")

    pad = 24
    inner = (x0 + pad, y0 + pad, x1 - pad, y1 - pad)
    if logo is not None:
        target = min(tw, th) - 2 * pad
        lg = logo.copy()
        lg.thumbnail((target, target), Image.LANCZOS)
        ox = int(x0 + (tw - lg.width) / 2)
        oy = int(y0 + (th - lg.height) / 2)
        img.paste(lg, (ox, oy), lg if lg.mode == "RGBA" else None)
    else:
        icon_fn(d, inner, b["tile_icon"])


def _render_item_slide(i: int, total: int, slide: dict, size: tuple[int, int],
                       brand: dict | None = None, root: Path | None = None) -> Image.Image:
    """Slides 2..N (role "item", and the final "close"): light background + dot
    grid, progress bar, a big brand-blue index numeral top-left (or a "CHỐT LẠI"
    pill on the close slide), a top-right tile holding the tool's real logo (or
    a fallback glyph), an optional tool-name label, the auto-fit headline with a
    blue underline, the body, and a swipe hint (handle on the close slide).
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    slide = slide or {}
    root = Path(root) if root is not None else Path(".")
    role = str(slide.get("role", "")).strip().lower()
    is_close = role == "close"

    img = Image.new("RGB", (W, H), b["item_bg"])
    draw = ImageDraw.Draw(img)
    _dot_grid(draw, size, b["item_dot"], step=40, r=2)
    _draw_progress(draw, b, i - 1, size, total=total, off=b["progress_off"])

    # ghost numeral watermark, bottom-right
    try:
        wm_font = ImageFont.truetype(str(media.FONT_PATH), 900)
        wm = "?" if is_close else f"{i - 1}"
        wl, wt, wr, wb = draw.textbbox((0, 0), wm, font=wm_font)
        draw.text((int(W - (wr - wl) * 0.60) - wl, int(H - (wb - wt) * 0.82) - wt),
                  wm, font=wm_font, fill=b["watermark"])
    except Exception:  # noqa: BLE001
        pass

    margin = 80
    safe_w = W - 2 * margin
    top_y = 150

    # index numeral (or CHỐT LẠI pill on close)
    if is_close:
        pf = ImageFont.truetype(str(media.FONT_PATH), 40)
        txt = "CHỐT LẠI"
        tw = draw.textlength(txt, font=pf)
        pasc, pdesc = pf.getmetrics()
        pad_x, pad_y = 28, 14
        draw.rounded_rectangle((margin, top_y, margin + tw + 2 * pad_x,
                                top_y + pasc + pdesc + 2 * pad_y),
                               radius=(pasc + pdesc + 2 * pad_y) // 2, fill=b["accent"])
        draw.text((margin + pad_x, top_y + pad_y), txt, font=pf, fill="#FFFFFF")
    else:
        nf = ImageFont.truetype(str(media.FONT_PATH), 86)
        draw.text((margin, top_y - 8), f"{i - 1:02d}", font=nf, fill=b["accent"])

    # top-right tile: real logo when the slide names a tool, else a glyph
    tool = slide.get("tool") if isinstance(slide.get("tool"), dict) else None
    logo = None
    if tool and tool.get("domain"):
        logo = _fetch_logo(str(tool["domain"]).strip().lower(), root)
    tile = 132
    icon_name = _ICON_ORDER[(i - 1) % len(_ICON_ORDER)]
    _logo_tile(img, (W - margin - tile, top_y - 6, W - margin, top_y - 6 + tile),
               b, logo, _ICONS[icon_name])
    draw = ImageDraw.Draw(img)  # re-bind after tile paste

    y = top_y + 150

    # optional tool-name label above the headline
    if tool and tool.get("name"):
        lf = ImageFont.truetype(str(media.FONT_PATH), 28)
        draw.text((margin, y), str(tool["name"]).upper(), font=lf, fill=b["accent"])
        y += 44

    headline = str(slide.get("headline", "")).strip()
    hf, lines, hsz = _fit_lines(draw, headline, 74, 44, safe_w, 3)
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=b["ink"])
        y += int(hsz * 1.18)

    uy = y + 18
    draw.rectangle((margin, uy, margin + 120, uy + 4), fill=b["accent"])

    body = str(slide.get("body", "")).strip()
    if body:
        bf = _handle_font(34)
        sy = uy + 40
        for ln in media._wrap(draw, body, bf, safe_w)[:4]:
            draw.text((margin, sy), ln, font=bf, fill=b["body_ink"])
            sy += 46

    # swipe hint bottom-right — except the close slide, which shows the handle
    if is_close:
        hfont = _handle_font(30)
        hw = draw.textlength(b["handle"], font=hfont)
        hasc, hdesc = hfont.getmetrics()
        draw.text(((W - hw) / 2, H - 46 - (hasc + hdesc)), b["handle"],
                  font=hfont, fill=b["muted"])
    else:
        sf = _handle_font(26)
        hint = "Vuốt tiếp  ›"
        hw = draw.textlength(hint, font=sf)
        hasc, hdesc = sf.getmetrics()
        draw.text((W - margin - hw, H - 54 - (hasc + hdesc)), hint,
                  font=sf, fill=b["swipe_hint"])
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
        slides = getattr(article, "slides", None) or []
        hook = slides[0] if slides and isinstance(slides[0], dict) else {}
        im = _render_hook_slide(article, hook, size)
        return [str(media._save_jpeg(im, Path(out_dir) / "01.jpg", size))]
    except Exception as e:  # noqa: BLE001 - hook is the last thing we can salvage
        log.warning("hook-slide fallback failed (%s); using legacy media", e)
        return _legacy_fallback(article, out_dir, size)


def build_images(article: ArticleContent, out_dir, *, size: tuple[int, int],
                 brand: dict | None = None, root: Path | None = None,
                 **ignored) -> list[str]:
    """Render the storyboard carousel: ``01.jpg`` .. ``NN.jpg``, one image per
    ``article.slides`` entry (5-7 of them), all in one visual system. Slide 1 is
    the dark hook slide; the rest are the light numbered "item" slides (the last
    one being the "close"), each showing a named tool's real logo when the slide
    carries a ``tool``.

    ``root`` is the repo root — logos cache under ``<root>/assets/logos/``. On
    ANY exception the whole render degrades to a minimal safe fallback (hook
    slide alone, else ``media.build_media``); it never propagates. ``**ignored``
    swallows retired kwargs (``style_prompt``, ``provider``, ``gen``).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    b = {**BRAND_DEFAULTS, **(brand or {})}
    root = Path(root) if root is not None else Path(".")

    try:
        slides = [s for s in (getattr(article, "slides", []) or []) if isinstance(s, dict)]
        if not slides:
            raise ValueError("article has no slides")
        total = len(slides)
        paths: list[str] = []
        for idx, slide in enumerate(slides):
            role = str(slide.get("role", "")).strip().lower()
            if idx == 0 or role == "hook":
                im = _render_hook_slide(article, slide, size, b)
            else:
                im = _render_item_slide(idx + 1, total, slide, size, b, root)
            paths.append(str(media._save_jpeg(im, out_dir / f"{idx + 1:02d}.jpg", size)))
        return paths
    except Exception as e:  # noqa: BLE001 - a broken slide must not sink the post
        log.warning("storyboard render failed (%s); using safe fallback", e)
        return _safe_fallback(article, out_dir, size)
