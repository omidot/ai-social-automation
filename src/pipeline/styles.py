from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import media

log = logging.getLogger("styles")

LAYOUT_NAMES = ("centered", "left-rail", "bottom-bar", "split", "magazine", "ticket")
PALETTE_NAMES = ("ink-on-white", "white-on-navy", "warm-editorial", "mono-contrast")
FONT_NAMES = ("grotesk", "editorial", "mono", "rounded")
TEXTURE_NAMES = ("dots", "grid", "diagonal", "plain", "gradient-band")
ACCENT_SHAPES = ("underline", "bar", "bracket", "none")
LOGO_TREATMENTS = ("tile", "chip", "mono")

PALETTES: dict[str, dict] = {
    "ink-on-white":   {"bg": "#F4F5F7", "ink": "#111111", "accent": "#1D4ED8",
                       "muted": "#6B7280", "on_accent": "#FFFFFF"},
    "white-on-navy":  {"bg": "#0B1B3A", "ink": "#FFFFFF", "accent": "#6EA8FE",
                       "muted": "#93A4C4", "on_accent": "#0A0A0A"},
    "warm-editorial": {"bg": "#F3ECE2", "ink": "#241E1A", "accent": "#B4472E",
                       "muted": "#8A7C6C", "on_accent": "#FFFFFF"},
    "mono-contrast":  {"bg": "#0A0A0A", "ink": "#FAFAFA", "accent": "#FAFAFA",
                       "muted": "#9A9A9A", "on_accent": "#0A0A0A"},
}

_FONT_DIR = Path("assets/fonts")
# family key -> (regular, bold, black, italic) filenames under assets/fonts/
_FONT_FILES: dict[str, tuple[str, str, str, str]] = {
    "grotesk":  ("BeVietnamPro-Regular.ttf", "BeVietnamPro-Bold.ttf",
                 "BeVietnamPro-ExtraBold.ttf", "BeVietnamPro-Italic.ttf"),
    "editorial": ("Lora-Regular.ttf", "Lora-Bold.ttf", "Lora-Bold.ttf",
                  "Lora-Italic.ttf"),
    "mono":     ("JetBrainsMono-Regular.ttf", "JetBrainsMono-Bold.ttf",
                 "JetBrainsMono-Bold.ttf", "JetBrainsMono-Italic.ttf"),
    "rounded":  ("Nunito-Regular.ttf", "Nunito-Bold.ttf", "Nunito-ExtraBold.ttf",
                 "Nunito-Italic.ttf"),
}


class StyleError(Exception):
    pass


@dataclass(frozen=True)
class Style:
    name: str
    layout: str
    palette: str
    font: str
    texture: str
    accent_shape: str
    logo: str


def _validate(row: dict) -> Style:
    try:
        s = Style(row["name"], row["layout"], row["palette"], row["font"],
                  row["texture"], row["accent_shape"], row["logo"])
    except (KeyError, TypeError) as e:
        raise StyleError(f"bad style row {row!r}: {e}") from e
    checks = ((s.layout, LAYOUT_NAMES), (s.palette, PALETTE_NAMES),
              (s.font, FONT_NAMES), (s.texture, TEXTURE_NAMES),
              (s.accent_shape, ACCENT_SHAPES), (s.logo, LOGO_TREATMENTS))
    for val, allowed in checks:
        if val not in allowed:
            raise StyleError(f"style {s.name!r}: {val!r} not in {allowed}")
    return s


def load_styles(root) -> list[Style]:
    p = Path(root) / "config" / "styles.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = doc.get("styles") or []
    out = [_validate(r) for r in rows]
    if len(out) != 24:
        raise StyleError(f"expected 24 styles, got {len(out)}")
    if len({s.name for s in out}) != 24:
        raise StyleError("duplicate style name")
    return out


def _cursor_path(root) -> Path:
    return Path(root) / "data" / "style_cursor.json"


def pick_style(root, now=None) -> Style:
    """Positional cyclic pick: advance one step through the 24-style list each
    call. Full 24-cycle (25th == 1st) => no repeat within 23 picks, which
    covers the "no repeat within 15" requirement. `recent` is a debug
    breadcrumb only."""
    all_styles = load_styles(root)
    names = [s.name for s in all_styles]
    cp = _cursor_path(root)
    last = None
    recent: list[str] = []
    if cp.exists():
        try:
            doc = json.loads(cp.read_text("utf-8"))
            last = doc.get("last")
            recent = list(doc.get("recent", []))
        except Exception as e:  # noqa: BLE001 - a bad cursor just resets rotation
            log.warning("style cursor unreadable (%s); resetting", e)
    idx = names.index(last) if last in names else -1
    chosen = all_styles[(idx + 1) % len(all_styles)]
    recent = ([chosen.name] + [n for n in recent if n != chosen.name])[:15]
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps({"last": chosen.name, "recent": recent},
                             ensure_ascii=False, indent=2), encoding="utf-8")
    return chosen


def palette_for(style: Style, brand: dict | None) -> dict:
    base = dict(PALETTES[style.palette])
    for k in ("bg", "ink", "accent", "muted", "on_accent"):
        if brand and k in brand:
            base[k] = brand[k]
    return base


def font_paths(key: str) -> dict:
    reg, bold, black, ital = _FONT_FILES.get(key, _FONT_FILES["grotesk"])
    def pick(name: str) -> Path:
        p = _FONT_DIR / name
        return p if p.exists() else media.FONT_PATH
    return {"regular": pick(reg), "bold": pick(bold),
            "black": pick(black), "italic": pick(ital)}
