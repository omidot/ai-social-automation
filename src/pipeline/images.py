from __future__ import annotations
import io, logging, os
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from . import media, styles
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
# NOTE: the v3 segmented progress bar was removed in v4 — the owner didn't want
# it. Nothing draws a top band any more.

def _dot_grid(draw: ImageDraw.ImageDraw, size: tuple[int, int], colour: str,
              step: int = 40, r: int = 2) -> None:
    W, H = size
    for gy in range(step, H, step):
        for gx in range(step, W, step):
            draw.ellipse((gx - r, gy - r, gx + r, gy + r), fill=colour)


# --- Task 4: shared "furniture" helpers -------------------------------------
# Every one of the 24 layout functions (Tasks 5-10) calls these so the brand
# elements (textures, accent shapes, tool logos, handle, swipe hint) render
# identically across styles. Each helper draws in place and swallows its own
# internal failure (a bad font / logo must never break the slide).

def _hex(c) -> tuple[int, int, int]:
    if isinstance(c, (tuple, list)):
        return tuple(int(v) for v in c[:3])  # type: ignore[return-value]
    s = str(c).lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _mix(c1, c2, t: float) -> tuple[int, int, int]:
    """Linear blend ``c1`` -> ``c2`` by ``t`` in [0, 1]."""
    a, b = _hex(c1), _hex(c2)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))  # type: ignore[return-value]


# --- textures -------------------------------------------------------------

def _tex_dots(img: Image.Image, palette: dict) -> None:
    _dot_grid(ImageDraw.Draw(img), img.size,
              _mix(palette["bg"], palette["muted"], 0.18), step=44, r=2)


def _tex_grid(img: Image.Image, palette: dict) -> None:
    W, H = img.size
    d = ImageDraw.Draw(img)
    col = _mix(palette["bg"], palette["muted"], 0.15)
    for gx in range(90, W, 90):
        d.line((gx, 0, gx, H), fill=col, width=1)
    for gy in range(90, H, 90):
        d.line((0, gy, W, gy), fill=col, width=1)


def _tex_diagonal(img: Image.Image, palette: dict) -> None:
    W, H = img.size
    d = ImageDraw.Draw(img)
    col = _mix(palette["bg"], palette["muted"], 0.15)
    for off in range(-H, W, 120):
        d.line((off, 0, off + H, H), fill=col, width=1)


def _tex_gradient_band(img: Image.Image, palette: dict) -> None:
    W, H = img.size
    bw = max(1, int(W * 0.22))
    band = Image.new("RGB", (bw, H), tuple(_hex(palette["bg"])))
    bd = ImageDraw.Draw(band)
    for x in range(bw):
        t = (x / max(1, bw - 1)) * 0.14
        bd.line((x, 0, x, H), fill=_mix(palette["bg"], palette["accent"], t))
    img.paste(band, (W - bw, 0))


_TEXTURES = {"dots": _tex_dots, "grid": _tex_grid, "diagonal": _tex_diagonal,
             "gradient-band": _tex_gradient_band}


def _draw_texture(img: Image.Image, kind: str, palette: dict) -> None:
    """Paint a faint full-bleed background texture. ``plain`` (and anything
    unknown) is a no-op."""
    fn = _TEXTURES.get(kind)
    if fn is None:
        return
    try:
        fn(img, palette)
    except Exception as e:  # noqa: BLE001 - a texture must never sink a slide
        log.warning("texture %r failed (%s); skipping", kind, e)


# --- accent shape behind / under the headline --------------------------

def _accent_shape(draw: ImageDraw.ImageDraw, box: tuple, kind: str,
                  colour: str) -> None:
    """Draw the headline's accent per ``kind``. ``box`` is the headline bbox.
    ``bar`` is drawn BEFORE the text by callers that want it. ``none`` no-ops."""
    if kind not in ("underline", "bar", "bracket"):
        return
    try:
        x0, y0, x1, y1 = (int(v) for v in box)
        if kind == "underline":
            uy = y1 + 16
            draw.rectangle((x0, uy, x0 + 120, uy + 4), fill=colour)
        elif kind == "bar":
            draw.rounded_rectangle((x0 - 24, y0 - 12, x1 + 24, y1 + 12),
                                   radius=18, fill=colour)
        else:  # bracket: 6px L-strokes at top-left + bottom-right
            t, arm = 6, 30
            draw.rectangle((x0, y0, x0 + arm, y0 + t), fill=colour)
            draw.rectangle((x0, y0, x0 + t, y0 + arm), fill=colour)
            draw.rectangle((x1 - arm, y1 - t, x1, y1), fill=colour)
            draw.rectangle((x1 - t, y1 - arm, x1, y1), fill=colour)
    except Exception as e:  # noqa: BLE001
        log.warning("accent shape %r failed (%s); skipping", kind, e)


# --- tool logo marks ---------------------------------------------------

def _mono_logo(logo: Image.Image | None, ink) -> Image.Image | None:
    """Recolour ``logo``'s silhouette to a flat ``ink`` (keeps its alpha)."""
    if logo is None:
        return None
    try:
        alpha = logo.convert("RGBA").getchannel("A")
        solid = Image.new("RGBA", alpha.size, tuple(_hex(ink)) + (255,))
        solid.putalpha(alpha)
        return solid
    except Exception as e:  # noqa: BLE001
        log.warning("mono logo failed: %s", e)
        return None


def _place_mark(img: Image.Image, box: tuple, logo: Image.Image | None,
                icon_fn, colour) -> None:
    """Centre ``logo`` (or a monochrome ``icon_fn`` glyph) in ``box``, no tile."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    pad = int(min(w, h) * 0.18)
    if logo is not None:
        lg = logo.copy()
        lg.thumbnail((max(1, w - 2 * pad), max(1, h - 2 * pad)), Image.LANCZOS)
        img.paste(lg, (int(x0 + (w - lg.width) / 2), int(y0 + (h - lg.height) / 2)),
                  lg if lg.mode == "RGBA" else None)
    else:
        icon_fn(ImageDraw.Draw(img), (x0 + pad, y0 + pad, x1 - pad, y1 - pad), colour)


def _draw_mark(img: Image.Image, box: tuple, palette: dict,
               logo: Image.Image | None, icon_fn, treatment: str) -> None:
    """One logo mark in ``box`` per ``treatment`` (no brand name)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    if treatment == "chip":
        ImageDraw.Draw(img).rounded_rectangle((x0, y0, x1, y1), radius=20,
                                              fill=palette["accent"])
        _place_mark(img, (x0, y0, x1, y1), logo, icon_fn, palette["on_accent"])
    elif treatment == "mono":
        _place_mark(img, (x0, y0, x1, y1), _mono_logo(logo, palette["ink"]),
                    icon_fn, palette["ink"])
    else:  # tile
        _logo_tile(img, (x0, y0, x1, y1), BRAND_DEFAULTS, logo, icon_fn)


def _logo_lockup(img: Image.Image, box: tuple, palette: dict,
                 tool: dict | None, treatment: str, root: Path,
                 index: int) -> int:
    """Draw the logo mark in ``box`` per ``treatment`` and, if ``tool`` has a
    ``name``, the brand name to its right (bundled bold face, auto-sized).
    Returns the x where the name ends, else ``box``'s right edge."""
    end_x = 0
    try:
        x0, y0, x1, y1 = (int(v) for v in box)
        end_x = x1
        dom = str((tool or {}).get("domain", "")).strip().lower()
        logo = _fetch_logo(dom, root) if dom else None
        icon_fn = _ICONS[_ICON_ORDER[(index - 1) % len(_ICON_ORDER)]]
        _draw_mark(img, (x0, y0, x1, y1), palette, logo, icon_fn, treatment)
        name = str((tool or {}).get("name", "")).strip()
        if name:
            draw = ImageDraw.Draw(img)
            name_x = x1 + 34
            sz = 54
            nf = ImageFont.truetype(str(media.FONT_PATH), sz)
            limit = img.size[0] - 80 - name_x
            while sz > 28 and draw.textlength(name, font=nf) > limit:
                sz -= 4
                nf = ImageFont.truetype(str(media.FONT_PATH), sz)
            asc, desc = nf.getmetrics()
            draw.text((name_x, y0 + (y1 - y0 - (asc + desc)) / 2), name,
                      font=nf, fill=palette["ink"])
            end_x = int(name_x + draw.textlength(name, font=nf))
    except Exception as e:  # noqa: BLE001 - a lockup must never sink a slide
        log.warning("logo lockup failed (%s); bare box", e)
    return int(end_x)


def _hook_logos(img: Image.Image, box: tuple, palette: dict, tools: list,
                treatment: str, root: Path) -> bool:
    """One mark per tool centred in ``box``; wrap to a 2nd row past 4 (the
    ``_hook_logo_row`` sizing: 150px tiles, 30px gaps). True if >=1 drawn."""
    try:
        x0, y0, x1, y1 = (int(v) for v in box)
        picked = [t for t in (tools or []) if isinstance(t, dict)][:6]
        marks: list[tuple[dict, Image.Image | None]] = []
        for t in picked:
            dom = str(t.get("domain", "")).strip().lower()
            marks.append((t, _fetch_logo(dom, root) if dom else None))
        if treatment == "tile":  # no empty tile — drop failed fetches
            marks = [m for m in marks if m[1] is not None] or marks
        if not marks:
            return False

        tile, gap = 150, 30
        n = len(marks)
        per_row = n if n <= 4 else (n + 1) // 2
        rows = [marks[i:i + per_row] for i in range(0, n, per_row)]
        total_h = len(rows) * tile + (len(rows) - 1) * gap
        y = y0 + max(0, ((y1 - y0) - total_h) // 2)
        drew = 0
        for ri, row in enumerate(rows):
            row_w = len(row) * tile + (len(row) - 1) * gap
            x = x0 + max(0, ((x1 - x0) - row_w) // 2)
            for ci, (_t, lg) in enumerate(row):
                gi = _ICONS[_ICON_ORDER[(ri * per_row + ci) % len(_ICON_ORDER)]]
                _draw_mark(img, (x, y, x + tile, y + tile), palette, lg, gi, treatment)
                drew += 1
                x += tile + gap
            y += tile + gap
        return drew > 0
    except Exception as e:  # noqa: BLE001
        log.warning("hook logos failed (%s); skipping", e)
        return False


# --- handle + swipe hint ---------------------------------------------

def _handle_line(draw: ImageDraw.ImageDraw, size: tuple, palette: dict,
                 fonts: dict, *, centred: bool, left: int = 80) -> None:
    """"A Hít Official" ~30px in ``fonts["regular"]``, ``palette["muted"]``,
    ~46px above the bottom edge; centred or left-aligned at x=``left`` (default
    margin 80). ``left`` is ignored when ``centred`` is True."""
    try:
        W, H = size
        txt = "A Hít Official"
        f = ImageFont.truetype(str(fonts["regular"]), 30)
        asc, desc = f.getmetrics()
        x = (W - draw.textlength(txt, font=f)) / 2 if centred else left
        draw.text((x, H - 46 - (asc + desc)), txt, font=f, fill=palette["muted"])
    except Exception as e:  # noqa: BLE001
        log.warning("handle line failed (%s); skipping", e)


def _swipe_hint(draw: ImageDraw.ImageDraw, size: tuple, palette: dict,
                fonts: dict) -> None:
    """"Vuốt tiếp  ›" ~26px in ``fonts["regular"]``, ``palette["muted"]``,
    bottom-right at margin 80."""
    try:
        W, H = size
        txt = "Vuốt tiếp  ›"
        f = ImageFont.truetype(str(fonts["regular"]), 26)
        asc, desc = f.getmetrics()
        draw.text((W - 80 - draw.textlength(txt, font=f), H - 54 - (asc + desc)),
                  txt, font=f, fill=palette["muted"])
    except Exception as e:  # noqa: BLE001
        log.warning("swipe hint failed (%s); skipping", e)


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


def _hook_logo_row(img: Image.Image, b: dict, tools: list, root: Path,
                   y_top: int) -> bool:
    """Render the hook slide's logo row: one white rounded ~150px tile per tool
    (logo scaled to ~100px inside, soft shadow), centred — a single row for up
    to 4 tools, two rows for 5-6. A tool whose logo fails to fetch is skipped
    (no empty tile). Returns True if at least one logo was drawn."""
    resolved: list[Image.Image] = []
    for t in (tools or [])[:6]:
        dom = str((t or {}).get("domain", "")).strip().lower()
        lg = _fetch_logo(dom, root) if dom else None
        if lg is not None:
            resolved.append(lg)
    if not resolved:
        return False

    W, _ = img.size
    tile, gap = 150, 30
    n = len(resolved)
    per_row = n if n <= 4 else (n + 1) // 2
    rows = [resolved[i:i + per_row] for i in range(0, n, per_row)]
    y = y_top
    for row in rows:
        row_w = len(row) * tile + (len(row) - 1) * gap
        x = (W - row_w) // 2
        for lg in row:
            _logo_tile(img, (x, y, x + tile, y + tile), b, lg, _ICONS["spark"])
            x += tile + gap
        y += tile + gap
    return True


def _render_hook_slide(article: ArticleContent, slide: dict, size: tuple[int, int],
                       brand: dict | None = None, root: Path | None = None) -> Image.Image:
    """Slide 1 (role "hook"): a dark, high-punch slide — near-black bg with a
    soft blue radial glow, faint dot grid, a brand kicker pill, one line of the
    hook blown up in brand blue, a muted sub-line, a row of the logos the
    carousel will cover, and a swipe CTA near the bottom. No progress bar.
    """
    b = {**BRAND_DEFAULTS, **(brand or {})}
    W, H = size
    slide = slide or {}
    root = Path(root) if root is not None else Path(".")

    img = Image.new("RGB", (W, H), b["hook_bg"])
    # blue radial glow, top-left, on its own heavily-blurred layer
    glow = Image.new("RGB", (W, H), b["hook_bg"])
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-W * 0.35, -H * 0.32, W * 0.55, H * 0.42), fill=b["hook_glow"])
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img = Image.blend(img, glow, 0.22)
    draw = ImageDraw.Draw(img)

    _dot_grid(draw, size, b["hook_dot"], step=46, r=2)

    margin = 70
    safe_w = W - 140

    # brand kicker pill, top-left
    kf = ImageFont.truetype(str(media.FONT_PATH), 26)
    kick = str(b.get("kicker", b["handle"]))
    kw = draw.textlength(kick, font=kf)
    kasc, kdesc = kf.getmetrics()
    kpad_x, kpad_y = 22, 12
    draw.rounded_rectangle((margin, 104, margin + kw + 2 * kpad_x,
                            104 + kasc + kdesc + 2 * kpad_y),
                           radius=(kasc + kdesc + 2 * kpad_y) // 2, fill=b["accent"])
    draw.text((margin + kpad_x, 104 + kpad_y), kick, font=kf, fill="#FFFFFF")

    # the hook headline: auto-fit, <=3 lines; then blow up one line in brand blue
    head = (str(slide.get("headline", "")).strip()
            or (getattr(article, "cover_title", "") or "").strip())
    hf, lines, hsz = _fit_lines(draw, head, 118, 54, safe_w, 3)

    big_idx = None
    for idx, ln in enumerate(lines):
        if len(ln.split()) == 1 and len(ln) >= 6:
            big_idx = idx
    if big_idx is None and lines:
        big_idx = len(lines) - 1
    big_sz = min(int(hsz * 1.5), 148)
    big_hf = ImageFont.truetype(str(media.FONT_PATH), big_sz)
    while big_sz > hsz and big_idx is not None and \
            draw.textlength(lines[big_idx], font=big_hf) > safe_w:
        big_sz -= 6
        big_hf = ImageFont.truetype(str(media.FONT_PATH), big_sz)

    y = int(H * 0.16)
    for idx, ln in enumerate(lines):
        if idx == big_idx:
            draw.text((margin, y), ln, font=big_hf, fill=b["accent"])
            y += int(big_sz * 1.16)
        else:
            draw.text((margin, y), ln, font=hf, fill="#FFFFFF")
            y += int(hsz * 1.18)

    # the hook sub-line, muted, <=3 lines
    sub = str(slide.get("body", "")).strip()
    if sub:
        sf = _handle_font(34)
        y += 16
        for ln in media._wrap(draw, sub, sf, safe_w)[:3]:
            draw.text((margin, y), ln, font=sf, fill=b["hook_body"])
            y += 46

    # logo row: the products this carousel will cover, between sub-body and CTA
    tools = slide.get("tools") or []
    row_y = max(int(y + 40), int(H * 0.52))
    drew_logos = False
    if tools:
        drew_logos = _hook_logo_row(img, b, tools, root, row_y)
        if not drew_logos:
            _draw_icon_fan(img, b, n=min(max(len(tools), 3), 6))
        draw = ImageDraw.Draw(img)  # re-bind after paste

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
    grid, NO progress bar. An item slide opens with a horizontal lockup — a BIG
    white logo tile at the left margin with the brand name right next to it — then
    the auto-fit headline + blue underline, a substantial body (40-70 words), and
    up to 3 brand-blue bullet lines. The close slide swaps the lockup for a
    "CHỐT LẠI" pill and centres the handle at the bottom. A ghost index numeral
    sits bottom-right; every item but the close shows a "Vuốt tiếp ›" hint.
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
    top_y = 120
    lock_h = 190

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
        y = top_y + pasc + pdesc + 2 * pad_y + 56
    else:
        # --- horizontal lockup: BIG logo tile + brand name to its right ------
        tool = slide.get("tool") if isinstance(slide.get("tool"), dict) else None
        logo = None
        if tool and tool.get("domain"):
            logo = _fetch_logo(str(tool["domain"]).strip().lower(), root)
        icon_name = _ICON_ORDER[(i - 1) % len(_ICON_ORDER)]
        _logo_tile(img, (margin, top_y, margin + lock_h, top_y + lock_h),
                   b, logo, _ICONS[icon_name])
        draw = ImageDraw.Draw(img)  # re-bind after tile paste

        if tool and tool.get("name"):
            name = str(tool["name"]).strip()
            name_x = margin + lock_h + 34
            nsz = 54
            nf = ImageFont.truetype(str(media.FONT_PATH), nsz)
            while nsz > 34 and draw.textlength(name, font=nf) > (W - margin - name_x):
                nsz -= 4
                nf = ImageFont.truetype(str(media.FONT_PATH), nsz)
            nasc, ndesc = nf.getmetrics()
            draw.text((name_x, top_y + (lock_h - (nasc + ndesc)) / 2),
                      name, font=nf, fill=b["ink"])
        y = top_y + lock_h + 46

    # headline: auto-fit, <=3 lines, then the 4px brand-blue underline
    headline = str(slide.get("headline", "")).strip()
    hf, lines, hsz = _fit_lines(draw, headline, 68, 42, safe_w, 3)
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=b["ink"])
        y += int(hsz * 1.18)

    uy = y + 16
    draw.rectangle((margin, uy, margin + 120, uy + 4), fill=b["accent"])

    # body: substantial (40-70 words) — up to 7 lines at ~34px, shrink to 30 if
    # it would overflow that.
    body = str(slide.get("body", "")).strip()
    by = uy + 40
    max_lines = 6 if is_close else 7
    if body:
        bsz = 34
        bf = _handle_font(bsz)
        blines = media._wrap(draw, body, bf, safe_w)
        if len(blines) > max_lines:
            bsz = 30
            bf = _handle_font(bsz)
            blines = media._wrap(draw, body, bf, safe_w)
        step = int(bsz * 1.34)
        for ln in blines[:max_lines + 1]:
            draw.text((margin, by), ln, font=bf, fill=b["body_ink"])
            by += step

    # bullets: brand-blue dot + text, one line each (item slides only)
    if not is_close:
        bullets = [str(x).strip() for x in (slide.get("bullets") or []) if str(x).strip()]
        if bullets:
            by += 14
            gsz = 30
            gf = _handle_font(gsz)
            for bl in bullets[:3]:
                cy = by + gsz // 2
                draw.ellipse((margin, cy - 7, margin + 14, cy + 7), fill=b["accent"])
                line = media._wrap(draw, bl, gf, safe_w - 44)[:1]
                if line:
                    draw.text((margin + 34, by), line[0], font=gf, fill=b["body_ink"])
                by += int(gsz * 1.55)

    # bottom-right swipe hint — except the close slide, which centres the handle
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
        im = _render_hook_slide(article, hook, size, None, Path("."))
        return [str(media._save_jpeg(im, Path(out_dir) / "01.jpg", size))]
    except Exception as e:  # noqa: BLE001 - hook is the last thing we can salvage
        log.warning("hook-slide fallback failed (%s); using legacy media", e)
        return _legacy_fallback(article, out_dir, size)


@dataclass
class SlideModel:
    role: str
    index: int
    total: int
    headline: str
    body: str
    bullets: list = field(default_factory=list)
    tool: dict | None = None
    tools: list = field(default_factory=list)


def _slide_models(article) -> list["SlideModel"]:
    raw = [s for s in (getattr(article, "slides", []) or []) if isinstance(s, dict)]
    total = len(raw)
    out: list[SlideModel] = []
    for i, s in enumerate(raw):
        role = str(s.get("role", "")).strip().lower() or ("hook" if i == 0 else "item")
        out.append(SlideModel(
            role=role, index=i + 1, total=total,
            headline=str(s.get("headline", "")).strip(),
            body=str(s.get("body", "")).strip(),
            bullets=[str(b).strip() for b in (s.get("bullets") or []) if str(b).strip()],
            tool=s.get("tool") if isinstance(s.get("tool"), dict) else None,
            tools=[t for t in (s.get("tools") or []) if isinstance(t, dict)]))
    return out


@dataclass
class RenderCtx:
    size: tuple
    palette: dict
    fonts: dict
    style: "styles.Style"
    root: Path
    brand: dict
    article: object = None


def _via_fallback(sm: "SlideModel", ctx: "RenderCtx"):
    """Render one slide with the retained v4 renderer (used as each layout's
    stub in Task 3 and as the per-slide degrade path afterwards)."""
    b = {**BRAND_DEFAULTS, **(ctx.brand or {})}
    slide = {"role": sm.role, "headline": sm.headline, "body": sm.body,
             "bullets": sm.bullets, "tool": sm.tool, "tools": sm.tools}
    if sm.role == "hook":
        return _render_hook_slide(ctx.article, slide, ctx.size, b, ctx.root)
    return _render_item_slide(sm.index, sm.total, slide, ctx.size, b, ctx.root)


# Tasks 5-10 replace these stubs one at a time with real layout functions.
def _layout_stub(img, sm, ctx):
    img.paste(_via_fallback(sm, ctx).convert("RGB"), (0, 0))


# --- Task 5: the "centered" archetype -------------------------------------
# Everything centred on the canvas. Shared helpers below feed Tasks 6-10 too.

def _fit_lines_font(draw, text: str, font_path, start: int, floor: int,
                    max_w: int, max_lines: int, step: int = 6):
    """``_fit_lines`` but with a caller-supplied face: wrap ``text`` at the
    biggest size in ``start``..``floor`` that fits ``max_lines``. Returns
    ``(font, lines, size)``."""
    sz = start
    hf = ImageFont.truetype(str(font_path), sz)
    lines = media._wrap(draw, text, hf, max_w) or [""]
    while sz > floor and len(lines) > max_lines:
        sz -= step
        hf = ImageFont.truetype(str(font_path), sz)
        lines = media._wrap(draw, text, hf, max_w) or [""]
    return hf, lines, sz


def _centre_lines(draw, lines, font, cx: float, y: int, fill, line_h: int) -> int:
    """Draw each of ``lines`` horizontally centred on ``cx``; return the y below."""
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text((cx - w / 2, y), ln, font=font, fill=fill)
        y += line_h
    return y


def _pill(draw, cx: float, y: int, text: str, font, fill, text_fill) -> int:
    """A rounded pill centred on ``cx`` at top ``y``; return the y below it."""
    tw = draw.textlength(text, font=font)
    asc, desc = font.getmetrics()
    px, py = 26, 13
    h = asc + desc + 2 * py
    x0 = cx - (tw + 2 * px) / 2
    draw.rounded_rectangle((x0, y, x0 + tw + 2 * px, y + h), radius=h // 2, fill=fill)
    draw.text((x0 + px, y + py), text, font=font, fill=text_fill)
    return y + h


def _centered_body_fill(ctx) -> str:
    """Item/close body ink: the muted near-black only on the white palette."""
    return BRAND_DEFAULTS["body_ink"] if ctx.style.palette == "ink-on-white" \
        else ctx.palette["ink"]


def _centered_hook(img, sm, ctx, draw) -> None:
    W, H = ctx.size
    margin, cx = 80, W / 2
    safe_w = W - 2 * margin
    pal = ctx.palette

    kf = ImageFont.truetype(str(ctx.fonts["bold"]), 26)
    _pill(draw, cx, 96, str(BRAND_DEFAULTS["kicker"]), kf,
          pal["accent"], pal["on_accent"])

    head = sm.headline or ""
    hf, lines, hsz = _fit_lines_font(draw, head, ctx.fonts["black"], 112, 54,
                                     safe_w, 3)
    big_idx = None
    for idx, ln in enumerate(lines):
        if len(ln.split()) == 1 and len(ln) >= 6:
            big_idx = idx
    if big_idx is None and lines:
        big_idx = len(lines) - 1
    big_sz = min(int(hsz * 1.5), 148)
    big_hf = ImageFont.truetype(str(ctx.fonts["black"]), big_sz)
    while big_sz > hsz and big_idx is not None and \
            draw.textlength(lines[big_idx], font=big_hf) > safe_w:
        big_sz -= 6
        big_hf = ImageFont.truetype(str(ctx.fonts["black"]), big_sz)

    y = int(H * 0.20)
    hy0 = y
    for idx, ln in enumerate(lines):
        if idx == big_idx:
            w = draw.textlength(ln, font=big_hf)
            draw.text((cx - w / 2, y), ln, font=big_hf, fill=pal["accent"])
            y += int(big_sz * 1.16)
        else:
            w = draw.textlength(ln, font=hf)
            draw.text((cx - w / 2, y), ln, font=hf, fill=pal["ink"])
            y += int(hsz * 1.18)
    # the hook's blown-up word is its own accent; only the line marks make
    # sense over it (a filled "bar" would bury the headline, "none" no-ops).
    if ctx.style.accent_shape in ("underline", "bracket"):
        _accent_shape(draw, (cx - 60, hy0, cx + 60, y), ctx.style.accent_shape,
                      pal["accent"])

    sub = sm.body or ""
    if sub:
        sf = ImageFont.truetype(str(ctx.fonts["regular"]), 34)
        y += 24
        y = _centre_lines(draw, media._wrap(draw, sub, sf, safe_w)[:3], sf,
                          cx, y, pal["muted"], 46)

    _hook_logos(img, (margin, y + 40, W - margin, y + 40 + 320), pal,
                sm.tools, ctx.style.logo, ctx.root)
    draw = ImageDraw.Draw(img)  # re-bind after paste
    _swipe_hint(draw, ctx.size, pal, ctx.fonts)
    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=False)


def _centered_item(img, sm, ctx, draw) -> None:
    W, H = ctx.size
    margin, cx = 80, W / 2
    safe_w = W - 2 * margin
    pal = ctx.palette

    top_y = 120
    y = top_y
    if sm.tool:
        lh = 190
        _logo_lockup(img, (int(cx - lh / 2), top_y, int(cx + lh / 2), top_y + lh),
                     pal, sm.tool, ctx.style.logo, ctx.root, sm.index)
        draw = ImageDraw.Draw(img)  # re-bind after paste
        y = top_y + lh + 46

    hf, lines, hsz = _fit_lines_font(draw, sm.headline or "", ctx.fonts["black"],
                                     64, 40, safe_w, 3)
    line_h = int(hsz * 1.18)
    widths = [draw.textlength(ln, font=hf) for ln in lines] or [0]
    hbox = (cx - max(widths) / 2, y, cx + max(widths) / 2, y + line_h * len(lines))
    on_bar = ctx.style.accent_shape == "bar"
    if on_bar:
        _accent_shape(draw, hbox, "bar", pal["accent"])
    y = _centre_lines(draw, lines, hf, cx, y,
                      pal["on_accent"] if on_bar else pal["ink"], line_h)
    if not on_bar:
        _accent_shape(draw, (cx - 60, hbox[1], cx + 60, y),
                      ctx.style.accent_shape, pal["accent"])

    body = sm.body or ""
    y += 40
    if body:
        bsz = 34
        wrap_w = int(safe_w * 0.8)
        bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
        blines = media._wrap(draw, body, bf, wrap_w)
        for bsz in (30, 28):
            if len(blines) <= 7:
                break
            bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
            blines = media._wrap(draw, body, bf, wrap_w)
        y = _centre_lines(draw, blines, bf, cx, y, _centered_body_fill(ctx),
                          int(bsz * 1.34))

    bullets = sm.bullets[:3]
    if bullets:
        y += 14
        gsz = 30
        gf = ImageFont.truetype(str(ctx.fonts["regular"]), gsz)
        colw = min(int(safe_w), 760)
        col_x0 = cx - colw / 2
        for bl in bullets:
            cyc = y + gsz / 2
            draw.ellipse((col_x0, cyc - 7, col_x0 + 14, cyc + 7), fill=pal["accent"])
            seg = media._wrap(draw, bl, gf, colw - 44)[:1]
            if seg:
                draw.text((col_x0 + 34, y), seg[0], font=gf,
                          fill=_centered_body_fill(ctx))
            y += int(gsz * 1.55)

    _swipe_hint(draw, ctx.size, pal, ctx.fonts)
    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=False)


def _centered_close(img, sm, ctx, draw) -> None:
    W, H = ctx.size
    margin, cx = 80, W / 2
    safe_w = W - 2 * margin
    pal = ctx.palette

    pf = ImageFont.truetype(str(ctx.fonts["bold"]), 40)
    y = _pill(draw, cx, 150, "CHỐT LẠI", pf, pal["accent"], pal["on_accent"])
    y += 56

    hf, lines, hsz = _fit_lines_font(draw, sm.headline or "", ctx.fonts["black"],
                                     64, 40, safe_w, 3)
    line_h = int(hsz * 1.18)
    widths = [draw.textlength(ln, font=hf) for ln in lines] or [0]
    hbox = (cx - max(widths) / 2, y, cx + max(widths) / 2, y + line_h * len(lines))
    on_bar = ctx.style.accent_shape == "bar"
    if on_bar:
        _accent_shape(draw, hbox, "bar", pal["accent"])
    y = _centre_lines(draw, lines, hf, cx, y,
                      pal["on_accent"] if on_bar else pal["ink"], line_h)
    if not on_bar:
        _accent_shape(draw, (cx - 60, hbox[1], cx + 60, y),
                      ctx.style.accent_shape, pal["accent"])

    body = sm.body or ""
    y += 40
    if body:
        bsz = 34
        wrap_w = int(safe_w * 0.8)
        bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
        blines = media._wrap(draw, body, bf, wrap_w)
        for bsz in (30, 28):
            if len(blines) <= 7:
                break
            bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
            blines = media._wrap(draw, body, bf, wrap_w)
        _centre_lines(draw, blines, bf, cx, y, _centered_body_fill(ctx),
                      int(bsz * 1.34))

    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=True)


def _layout_centered(img, sm, ctx) -> None:
    """The "centered" archetype: kicker/pill, headline, accent, body and (hook)
    logo row all centred on the canvas. Furniture via the shared helpers."""
    _draw_texture(img, ctx.style.texture, ctx.palette)
    draw = ImageDraw.Draw(img)
    if sm.role == "hook":
        _centered_hook(img, sm, ctx, draw)
    elif sm.role == "close":
        _centered_close(img, sm, ctx, draw)
    else:
        _centered_item(img, sm, ctx, draw)


# --- Task 6: the "left-rail" archetype ----------------------------------
# A solid accent rail down the left ~11%; a big ghost slide number inside it;
# every bit of content left-aligned to the right of the rail.

_RAIL_W = 120          # rail width in px (~11% of 1080)
_RAIL_X = 170          # left edge of all content (clears the rail + a margin)


def _left_rail_accent_kind(ctx) -> str:
    """A filled ``bar`` clashes with the accent rail — use ``underline`` instead
    for this layout; every other accent shape passes straight through."""
    return "underline" if ctx.style.accent_shape == "bar" else ctx.style.accent_shape


def _rail_ghost_number(img: Image.Image, ctx, text: str) -> None:
    """The big translucent slide number painted INSIDE the accent rail."""
    try:
        W, H = ctx.size
        f = ImageFont.truetype(str(ctx.fonts["black"]), 160)  # fits inside the 120px rail
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        l, t, r, b = od.textbbox((0, 0), text, font=f)
        gx = (_RAIL_W - (r - l)) / 2 - l
        gy = (H - (b - t)) / 2 - t
        od.text((gx, gy), text, font=f,
                fill=tuple(_hex(ctx.palette["on_accent"])) + (76,))  # ~30% alpha
        img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"),
                  (0, 0))
    except Exception as e:  # noqa: BLE001 - the ghost number is decorative
        log.warning("rail ghost number failed (%s); skipping", e)


def _left_rail_base(img: Image.Image, sm, ctx) -> ImageDraw.ImageDraw:
    """Texture, the solid accent rail and the ghost number; returns a fresh
    ``ImageDraw`` bound to ``img`` (rebound after the ghost-number paste)."""
    _draw_texture(img, ctx.style.texture, ctx.palette)
    W, H = ctx.size
    ImageDraw.Draw(img).rectangle((0, 0, _RAIL_W, H), fill=ctx.palette["accent"])
    _rail_ghost_number(img, ctx, str(max(sm.index - 1, 0)))
    return ImageDraw.Draw(img)


def _left_rail_headline(draw, sm, ctx, y: int):
    """Left-aligned auto-fit headline; draws it and its accent shape. Returns the
    y below the accent."""
    pal = ctx.palette
    right = ctx.size[0] - 80
    safe_w = right - _RAIL_X
    hf, lines, hsz = _fit_lines_font(draw, sm.headline or "", ctx.fonts["black"],
                                     64, 40, safe_w, 3)
    line_h = int(hsz * 1.18)
    hy0 = y
    widths = [draw.textlength(ln, font=hf) for ln in lines] or [0]
    for ln in lines:
        draw.text((_RAIL_X, y), ln, font=hf, fill=pal["ink"])
        y += line_h
    hbox = (_RAIL_X, hy0, _RAIL_X + max(widths), y)
    _accent_shape(draw, hbox, _left_rail_accent_kind(ctx), pal["accent"])
    return y + 40


def _left_rail_body(draw, sm, ctx, y: int) -> int:
    """Left-aligned body paragraph, shrink 34->30->28, <=7 lines. Returns y below."""
    body = sm.body or ""
    if not body:
        return y
    right = ctx.size[0] - 80
    safe_w = right - _RAIL_X
    bsz = 34
    bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
    blines = media._wrap(draw, body, bf, safe_w)
    for bsz in (30, 28):
        if len(blines) <= 7:
            break
        bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
        blines = media._wrap(draw, body, bf, safe_w)
    step = int(bsz * 1.34)
    for ln in blines[:7]:
        draw.text((_RAIL_X, y), ln, font=bf, fill=_centered_body_fill(ctx))
        y += step
    return y


def _left_rail_hook(img, sm, ctx, draw) -> None:
    W, H = ctx.size
    pal = ctx.palette
    y = int(H * 0.14)
    y = _left_rail_headline(draw, sm, ctx, y)

    sub = sm.body or ""
    if sub:
        sf = ImageFont.truetype(str(ctx.fonts["regular"]), 34)
        for ln in media._wrap(draw, sub, sf, W - 80 - _RAIL_X)[:3]:
            draw.text((_RAIL_X, y), ln, font=sf, fill=pal["muted"])
            y += 46
        y += 20

    _hook_logos(img, (_RAIL_X, y + 20, W - 80, y + 20 + 300), pal,
                sm.tools, ctx.style.logo, ctx.root)
    draw = ImageDraw.Draw(img)  # re-bind after paste
    _swipe_hint(draw, ctx.size, pal, ctx.fonts)
    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=False, left=_RAIL_X)


def _left_rail_item(img, sm, ctx, draw) -> None:
    W, H = ctx.size
    pal = ctx.palette
    top_y = 120
    y = top_y
    if sm.tool:
        _logo_lockup(img, (_RAIL_X, top_y, _RAIL_X + 190, top_y + 190),
                     pal, sm.tool, ctx.style.logo, ctx.root, sm.index)
        draw = ImageDraw.Draw(img)  # re-bind after paste
        y = top_y + 190 + 46

    y = _left_rail_headline(draw, sm, ctx, y)
    y = _left_rail_body(draw, sm, ctx, y)

    bullets = sm.bullets[:3]
    if bullets:
        y += 14
        gsz = 30
        gf = ImageFont.truetype(str(ctx.fonts["regular"]), gsz)
        safe_w = W - 80 - _RAIL_X
        for bl in bullets:
            cy = y + gsz / 2
            draw.ellipse((_RAIL_X, cy - 7, _RAIL_X + 14, cy + 7), fill=pal["accent"])
            seg = media._wrap(draw, bl, gf, safe_w - 44)[:1]
            if seg:
                draw.text((_RAIL_X + 34, y), seg[0], font=gf,
                          fill=_centered_body_fill(ctx))
            y += int(gsz * 1.55)

    _swipe_hint(draw, ctx.size, pal, ctx.fonts)
    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=False, left=_RAIL_X)


def _left_rail_close(img, sm, ctx, draw) -> None:
    pal = ctx.palette
    pf = ImageFont.truetype(str(ctx.fonts["bold"]), 40)
    # a left-aligned "CHỐT LẠI" pill where the lockup would sit
    tw = draw.textlength("CHỐT LẠI", font=pf)
    cx = _RAIL_X + (tw + 52) / 2  # 52 = 2 * _pill's internal px padding (26)
    y = _pill(draw, cx, 130, "CHỐT LẠI", pf, pal["accent"], pal["on_accent"])
    y += 56

    y = _left_rail_headline(draw, sm, ctx, y)
    _left_rail_body(draw, sm, ctx, y)

    # furniture contract: close keeps the CENTRED handle, no swipe, no lockup
    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=True)


def _layout_left_rail(img, sm, ctx) -> None:
    """The "left-rail" archetype: a solid accent rail down the left edge with a
    ghost slide number, all content left-aligned to its right. Furniture via the
    shared helpers."""
    draw = _left_rail_base(img, sm, ctx)
    if sm.role == "hook":
        _left_rail_hook(img, sm, ctx, draw)
    elif sm.role == "close":
        _left_rail_close(img, sm, ctx, draw)
    else:
        _left_rail_item(img, sm, ctx, draw)


# --- Task 7: the "bottom-bar" archetype --------------------------------
# Top ~55% = bg + texture + a big FAINT decorative glyph + the logo(s).
# Bottom ~45% (y >= _BAR_TOP) = a full-bleed accent block holding the headline
# + body (+ bullets on item) in ``on_accent`` — no accent shape, the bar itself
# IS the accent block. The close slide drops the bar entirely for a plain
# centred pill + body, exactly like ``_layout_centered``.

_BAR_TOP = 742          # top edge of the accent bar (~55% of 1350)


def _bottom_bar_shadow_pal(ctx) -> dict:
    """A palette copy whose ``muted`` reads as ``on_accent`` so the shared
    handle / swipe helpers stay legible where they land on the filled bar.
    Passing a recoloured palette dict is explicitly allowed by the contract."""
    return {**ctx.palette, "muted": ctx.palette["on_accent"]}


def _bottom_bar_mark(img: Image.Image, ctx, sm) -> None:
    """A very large, very faint decorative glyph high in the top zone — an
    ``_ICONS`` glyph picked by ``sm.index``, drawn at ~10% alpha in ``muted``."""
    try:
        W, _ = ctx.size
        s = 460
        x0 = W - s - 24
        y0 = int(_BAR_TOP * 0.46 - s / 2)
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        icon = _ICONS[_ICON_ORDER[(sm.index - 1) % len(_ICON_ORDER)]]
        icon(od, (x0, y0, x0 + s, y0 + s), tuple(_hex(ctx.palette["muted"])) + (26,))
        img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"),
                  (0, 0))
    except Exception as e:  # noqa: BLE001 - the mark is decorative
        log.warning("bottom-bar mark failed (%s); skipping", e)


def _bottom_bar_block(img: Image.Image, ctx) -> ImageDraw.ImageDraw:
    """Paint the full-bleed accent bar across the bottom ~45%; return a fresh
    ``ImageDraw`` bound to ``img`` (callers draw the copy on top of it)."""
    W, H = ctx.size
    ImageDraw.Draw(img).rectangle((0, _BAR_TOP, W, H), fill=ctx.palette["accent"])
    return ImageDraw.Draw(img)


def _bottom_bar_copy(draw, sm, ctx, *, with_bullets: bool) -> None:
    """Headline + body (+ optional bullets) inside the accent bar, all in
    ``on_accent``. NO ``_accent_shape`` — an accent-coloured mark on the filled
    accent bar is invisible."""
    W, H = ctx.size
    margin = 80
    safe_w = W - 2 * margin
    pal = ctx.palette

    # Bullets carry the scannable takeaways; when they're actually drawn the
    # headline + body + 3 bullets all have to fit above the fixed handle/swipe
    # (y ~= H-46 / H-54). A maxed 3-line 58px headline eats ~200px, so for the
    # bulleted case we start the block higher, shorten the head/body gaps and
    # cap the body at 3 lines — that lands the last bullet ~30px clear of the
    # handle on the narrow ``mono`` face. A bulletless slide (the hook, or an
    # item with no bullets) keeps the roomier start and the <=7 body cap.
    drawing_bullets = bool(with_bullets and sm.bullets)
    if drawing_bullets:
        y = _BAR_TOP + 30
        head_gap, body_cap, bullet_gap = 18, 3, 10
    else:
        y = _BAR_TOP + 54
        head_gap, body_cap, bullet_gap = 24, 7, 12

    hf, lines, hsz = _fit_lines_font(draw, sm.headline or "", ctx.fonts["black"],
                                     58, 38, safe_w, 3)
    line_h = int(hsz * 1.16)
    for ln in lines:
        draw.text((margin, y), ln, font=hf, fill=pal["on_accent"])
        y += line_h
    y += head_gap

    body = sm.body or ""
    if body:
        bsz = 34
        bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
        blines = media._wrap(draw, body, bf, safe_w)
        for bsz in (30, 28):
            if len(blines) <= body_cap:
                break
            bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
            blines = media._wrap(draw, body, bf, safe_w)
        step = int(bsz * 1.34)
        for ln in blines[:body_cap]:
            draw.text((margin, y), ln, font=bf, fill=pal["on_accent"])
            y += step

    if with_bullets:
        bullets = sm.bullets[:3]
        if bullets:
            y += bullet_gap
            gsz = 28
            gf = ImageFont.truetype(str(ctx.fonts["regular"]), gsz)
            dot = _mix(pal["accent"], pal["on_accent"], 0.6)  # a lighter tint
            for bl in bullets:
                cy = y + gsz / 2
                draw.ellipse((margin, cy - 7, margin + 14, cy + 7), fill=dot)
                seg = media._wrap(draw, bl, gf, safe_w - 44)[:1]
                if seg:
                    draw.text((margin + 34, y), seg[0], font=gf, fill=pal["on_accent"])
                y += int(gsz * 1.5)


def _bottom_bar_hook(img, sm, ctx, draw) -> None:
    W, H = ctx.size
    pal = ctx.palette
    _bottom_bar_mark(img, ctx, sm)
    _hook_logos(img, (80, 150, W - 80, _BAR_TOP - 60), pal, sm.tools,
                ctx.style.logo, ctx.root)
    draw = _bottom_bar_block(img, ctx)  # re-bind after the paste(s) above
    _bottom_bar_copy(draw, sm, ctx, with_bullets=False)
    shad = _bottom_bar_shadow_pal(ctx)
    _swipe_hint(draw, ctx.size, shad, ctx.fonts)
    _handle_line(draw, ctx.size, shad, ctx.fonts, centred=False)


def _bottom_bar_item(img, sm, ctx, draw) -> None:
    W, H = ctx.size
    pal = ctx.palette
    _bottom_bar_mark(img, ctx, sm)
    if sm.tool:
        _logo_lockup(img, (80, 150, 80 + 190, 150 + 190), pal, sm.tool,
                     ctx.style.logo, ctx.root, sm.index)
    draw = _bottom_bar_block(img, ctx)  # re-bind after the paste(s) above
    _bottom_bar_copy(draw, sm, ctx, with_bullets=True)
    shad = _bottom_bar_shadow_pal(ctx)
    _swipe_hint(draw, ctx.size, shad, ctx.fonts)
    _handle_line(draw, ctx.size, shad, ctx.fonts, centred=False)


def _bottom_bar_close(img, sm, ctx, draw) -> None:
    """NO bar. Plain ``bg`` centred wrap-up — identical to the "centered"
    archetype's close slide (centred "CHỐT LẠI" pill, centred headline + accent
    shape, centred body, centred handle; no swipe, no lockup), so just delegate."""
    _centered_close(img, sm, ctx, draw)


def _layout_bottom_bar(img, sm, ctx) -> None:
    """The "bottom-bar" archetype: bg + texture + a big faint glyph + logo(s) in
    the top ~55%; a full-bleed accent bar across the bottom ~45% carrying the
    headline + body (+ bullets on item) in ``on_accent``. The close slide drops
    the bar for a plain centred pill + body. Furniture via the shared helpers,
    shadow-recoloured where it lands on the bar."""
    _draw_texture(img, ctx.style.texture, ctx.palette)
    draw = ImageDraw.Draw(img)
    if sm.role == "hook":
        _bottom_bar_hook(img, sm, ctx, draw)
    elif sm.role == "close":
        _bottom_bar_close(img, sm, ctx, draw)
    else:
        _bottom_bar_item(img, sm, ctx, draw)


# --- Task 8: the "split" archetype ------------------------------------
# Top ~46% = a soft accent TINT band (bg blended ~14% toward accent) holding a
# tracked small-caps kicker + the headline; a 3px solid accent divider at the
# midline; the lower half carries body (+ bullets on item) and the furniture.
# The close slide drops the band for the plain centred wrap-up (``_centered_close``).

_SPLIT_MARGIN = 90


def _split_band(img: Image.Image, ctx) -> tuple[ImageDraw.ImageDraw, int]:
    """Texture over the whole canvas, then the top ~46% blended ~14% toward the
    accent, then the 3px accent divider. Returns ``(draw, mid_y)`` — a fresh
    ``ImageDraw`` bound to ``img`` (rebound after the blend paste) + the midline."""
    _draw_texture(img, ctx.style.texture, ctx.palette)
    W, H = ctx.size
    mid = int(H * 0.46)
    band = img.crop((0, 0, W, mid))
    fill = Image.new("RGB", band.size, tuple(_hex(ctx.palette["accent"])))
    img.paste(Image.blend(band, fill, 0.14), (0, 0))
    draw = ImageDraw.Draw(img)  # re-bind after the paste
    draw.rectangle((0, mid, W, mid + 2), fill=ctx.palette["accent"])  # 3px divider
    return draw, mid


def _split_kicker(draw, ctx, text: str) -> None:
    """A small-caps, tracked-out kicker at the top of the tint band."""
    kf = ImageFont.truetype(str(ctx.fonts["bold"]), 22)
    x = _SPLIT_MARGIN
    for ch in str(text).upper():
        draw.text((x, 74), ch, font=kf, fill=ctx.palette["muted"])
        x += draw.textlength(ch, font=kf) + 4


def _split_headline(draw, sm, ctx, y0: int, start: int, floor: int) -> int:
    """Left-aligned auto-fit headline in the tint band + its accent shape. A
    ``bar`` is painted BEHIND the text (the tint band gives it contrast); every
    other shape is drawn normally after. Returns the y below the text."""
    m = _SPLIT_MARGIN
    pal = ctx.palette
    safe_w = ctx.size[0] - 2 * m
    hf, lines, hsz = _fit_lines_font(draw, sm.headline or "", ctx.fonts["black"],
                                     start, floor, safe_w, 3)
    line_h = int(hsz * 1.16)
    widths = [draw.textlength(ln, font=hf) for ln in lines] or [0]
    hbox = (m, y0, m + max(widths), y0 + line_h * len(lines))
    on_bar = ctx.style.accent_shape == "bar"
    if on_bar:
        _accent_shape(draw, hbox, "bar", pal["accent"])
    y = y0
    for ln in lines:
        draw.text((m, y), ln, font=hf,
                  fill=pal["on_accent"] if on_bar else pal["ink"])
        y += line_h
    if not on_bar:
        _accent_shape(draw, hbox, ctx.style.accent_shape, pal["accent"])
    return y


def _split_body(draw, sm, ctx, y: int, *, muted: bool = False) -> int:
    """Left-aligned body paragraph in the lower half, shrink 34->30->28,
    ``blines[:7]``. Returns the y below."""
    body = sm.body or ""
    if not body:
        return y
    m = _SPLIT_MARGIN
    safe_w = ctx.size[0] - 2 * m
    bsz = 34
    bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
    blines = media._wrap(draw, body, bf, safe_w)
    for bsz in (30, 28):
        if len(blines) <= 7:
            break
        bf = ImageFont.truetype(str(ctx.fonts["regular"]), bsz)
        blines = media._wrap(draw, body, bf, safe_w)
    fill = ctx.palette["muted"] if muted else _centered_body_fill(ctx)
    step = int(bsz * 1.34)
    for ln in blines[:7]:
        draw.text((m, y), ln, font=bf, fill=fill)
        y += step
    return y


def _split_hook(img, sm, ctx, draw, mid: int) -> None:
    W, H = ctx.size
    pal = ctx.palette
    _split_kicker(draw, ctx, BRAND_DEFAULTS["kicker"])
    _split_headline(draw, sm, ctx, 132, 92, 50)

    y = _split_body(draw, sm, ctx, mid + 46, muted=True) + 24
    _hook_logos(img, (_SPLIT_MARGIN, y, W - _SPLIT_MARGIN, H - 150), pal,
                sm.tools, ctx.style.logo, ctx.root)
    draw = ImageDraw.Draw(img)  # re-bind after paste
    _swipe_hint(draw, ctx.size, pal, ctx.fonts)
    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=False)


def _split_item(img, sm, ctx, draw, mid: int) -> None:
    W, H = ctx.size
    m = _SPLIT_MARGIN
    pal = ctx.palette
    kick = str((sm.tool or {}).get("name", "")).strip() or "CÔNG CỤ"
    _split_kicker(draw, ctx, kick)
    _split_headline(draw, sm, ctx, 128, 84, 46)

    y = _split_body(draw, sm, ctx, mid + 46)

    bullets = sm.bullets[:3]
    if bullets:
        y += 14
        gsz = 30
        gf = ImageFont.truetype(str(ctx.fonts["regular"]), gsz)
        safe_w = W - 2 * m
        for bl in bullets:
            cy = y + gsz / 2
            draw.ellipse((m, cy - 7, m + 14, cy + 7), fill=pal["accent"])
            seg = media._wrap(draw, bl, gf, safe_w - 44)[:1]
            if seg:
                draw.text((m + 34, y), seg[0], font=gf,
                          fill=_centered_body_fill(ctx))
            y += int(gsz * 1.55)

    if sm.tool:
        lh = 140
        top_y = H - 100 - lh
        _logo_lockup(img, (m, top_y, m + lh, top_y + lh), pal, sm.tool,
                     ctx.style.logo, ctx.root, sm.index)
        draw = ImageDraw.Draw(img)  # re-bind after paste
    _swipe_hint(draw, ctx.size, pal, ctx.fonts)
    _handle_line(draw, ctx.size, pal, ctx.fonts, centred=False)


def _layout_split(img, sm, ctx) -> None:
    """The "split" archetype: a soft accent tint band over the top ~46% holding a
    tracked kicker + the headline, a 3px accent divider at the midline, and body
    (+ bullets on item) + furniture in the lower half. The close slide drops the
    band for the plain centred wrap-up. Furniture via the shared helpers."""
    if sm.role == "close":
        _draw_texture(img, ctx.style.texture, ctx.palette)
        _centered_close(img, sm, ctx, ImageDraw.Draw(img))
        return
    draw, mid = _split_band(img, ctx)
    if sm.role == "hook":
        _split_hook(img, sm, ctx, draw, mid)
    else:
        _split_item(img, sm, ctx, draw, mid)


LAYOUTS: dict = {name: _layout_stub for name in styles.LAYOUT_NAMES}
LAYOUTS["centered"] = _layout_centered
LAYOUTS["left-rail"] = _layout_left_rail
LAYOUTS["bottom-bar"] = _layout_bottom_bar
LAYOUTS["split"] = _layout_split


def build_images(article: ArticleContent, out_dir, *, size: tuple[int, int],
                 brand: dict | None = None, root: Path | None = None,
                 style=None, **ignored) -> list[str]:
    """Render the storyboard carousel: ``01.jpg`` .. ``0N.jpg``, one image per
    ``article.slides`` entry (4-9 of them — the count is not fixed), all in one
    visual system.

    ``style`` selects one of the 24 rotating carousel styles; when ``None`` it
    is drawn from ``styles.pick_style(root)`` (a bad ``config/styles.yaml`` ->
    a hardcoded default look). ``LAYOUTS[style.layout]`` draws each slide; in
    Task 3 every layout is a thin stub that reproduces the v4 renderers, which
    are retained as the degrade path.

    ``root`` is the repo root — logos cache under ``<root>/assets/logos/``. A
    single failing layout slide re-renders via the v4 fallback; on ANY other
    exception the whole render degrades to a minimal safe fallback (hook slide
    alone, else ``media.build_media``); it never propagates. ``**ignored``
    swallows retired kwargs (``style_prompt``, ``provider``, ``gen``).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    root = Path(root) if root is not None else Path(".")
    b = {**BRAND_DEFAULTS, **(brand or {})}

    try:
        if style is None:
            try:
                style = styles.pick_style(root)
            except Exception as e:  # noqa: BLE001 - bad styles.yaml -> default look
                log.warning("pick_style failed (%s); using default style", e)
                style = styles.Style("default", "centered", "white-on-navy",
                                     "grotesk", "dots", "bar", "tile")
        ctx = RenderCtx(size=size, palette=styles.palette_for(style, brand),
                        fonts=styles.font_paths(style.font), style=style,
                        root=root, brand=b, article=article)
        models = _slide_models(article)
        if not models:
            raise ValueError("article has no slides")
        layout_fn = LAYOUTS.get(style.layout, _layout_stub)
        paths: list[str] = []
        for sm in models:
            img = Image.new("RGB", size, ctx.palette["bg"])
            try:
                layout_fn(img, sm, ctx)
            except Exception as e:  # noqa: BLE001 - one bad slide -> v4 fallback
                log.warning("layout %s slide %d failed (%s); v4 fallback",
                            style.layout, sm.index, e)
                img = _via_fallback(sm, ctx).convert("RGB")
            paths.append(str(media._save_jpeg(img, out_dir / f"{sm.index:02d}.jpg", size)))
        return paths
    except Exception as e:  # noqa: BLE001 - a broken render must not sink the post
        log.warning("storyboard render failed (%s); using safe fallback", e)
        return _safe_fallback(article, out_dir, size)
