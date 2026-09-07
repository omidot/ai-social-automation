# Article Image Style Variety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every carousel is rendered in one of 24 rotating visual styles (6 Pillow layout archetypes × 4 palettes, each with its own font / texture / accent shape / logo treatment) instead of the single fixed v4 look; brand furniture (tool logos, "A Hít Official" handle, hook logo row, swipe hint, 40–70-word body) is identical across all styles.

**Architecture:** A new `src/pipeline/styles.py` holds a `Style` dataclass, the palette/font tables, `load_styles()` (reads `config/styles.yaml`, validates 24 entries) and `pick_style()` (cyclic, skips the last 15, cursor in `data/style_cursor.json`). `images.py` keeps `build_images()` as the entry point but gains a `style=` param and a `LAYOUTS` dispatch table of 6 functions; the current v4 renderers are retained verbatim as `_fallback_hook` / `_fallback_item` for the degrade path. Each layout function draws background + texture + headline + body + accent within its own regions and calls four shared furniture helpers (`_logo_lockup`, `_hook_logos`, `_handle_line`, `_swipe_hint`) so brand elements can't drift.

**Tech Stack:** Python 3.12, Pillow (`PIL`), PyYAML, `pytest`. No network image generation, no cutouts, no stock photos.

## Global Constraints

- Python 3.12 (CI floor). Local: `.venv/Scripts/python.exe`, `PYTHONUTF8=1`.
- Run tests: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q` from `D:\Automation Social`.
- Output images: exactly **1080×1350** JPEG, files `01.jpg` … `0N.jpg`, N = number of `article.slides` (4–9, not fixed).
- Slide roles: `slides[0]["role"] == "hook"`, `slides[-1]["role"] == "close"`, middle `"item"`. Per-role shape is documented in `src/pipeline/models.py` `ArticleContent.slides`.
- Every non-close slide shows the swipe hint. Every item slide with a `tool` shows a big logo + brand-name lockup. The hook shows a row of every tool logo the carousel covers. Every slide shows the `A Hít Official` handle. Item body is 40–70 words and must not be clipped (shrink font, allow up to 7 lines).
- Brand blue accent default `#1D4ED8`. `settings.yaml images.brand` still overrides individual colors and is passed through as `brand`.
- `build_images` must NEVER raise: on any failure it degrades (bad layout → `_fallback_*` for that slide; bad style config → default style; total failure → `media.build_media`).
- New state file `data/style_cursor.json` lives under `data/` so `scripts/commit_state.sh` commits it. Do not add other state paths.
- Fonts are best-effort: a missing family degrades to `assets/fonts/BeVietnamPro-Bold.ttf` (`media.FONT_PATH`). Never crash on a missing `.ttf`.
- This branch rebases on top of `feature/p1-style-autopublish` (the auto-publish plan). `article_run.draft()` there already writes `status="publishing"` then calls `publish.schedule_slot`; this plan only adds a `style=` field and the `pick_style` call.

---

### Task 1: `styles.py` + `config/styles.yaml` — the style registry

**Files:**
- Create: `src/pipeline/styles.py`
- Create: `config/styles.yaml`
- Test: `tests/test_styles.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Style` with `name: str`, `layout: str`, `palette: str`, `font: str`, `texture: str`, `accent_shape: str`, `logo: str`.
  - `LAYOUT_NAMES = ("centered", "left-rail", "bottom-bar", "split", "magazine", "ticket")`
  - `PALETTE_NAMES = ("ink-on-white", "white-on-navy", "warm-editorial", "mono-contrast")`
  - `FONT_NAMES = ("grotesk", "editorial", "mono", "rounded")`
  - `TEXTURE_NAMES = ("dots", "grid", "diagonal", "plain", "gradient-band")`
  - `ACCENT_SHAPES = ("underline", "bar", "bracket", "none")`
  - `LOGO_TREATMENTS = ("tile", "chip", "mono")`
  - `PALETTES: dict[str, dict]` — each has `bg, ink, accent, muted, on_accent` hex strings.
  - `load_styles(root) -> list[Style]` — reads `<root>/config/styles.yaml`, raises `StyleError` if not exactly 24 valid entries or any field out of range or any duplicate `name`.
  - `pick_style(root, now=None) -> Style` — **positional cyclic** pick: reads `data/style_cursor.json["last"]`, returns the style at `(index_of_last + 1) % 24` in `load_styles` order, writes the cursor back. This gives a clean 24-long cycle (25th pick == 1st) and therefore no repeat within 23 picks (⊇ the "no repeat within 15" spec requirement). `recent` (last ≤15 names) is still written as a debug breadcrumb but is NOT load-bearing. A `last` that isn't in the current list (YAML reordered/renamed) resets to index 0. `now` is accepted and ignored (future hook).
  - `palette_for(style: Style, brand: dict | None) -> dict` — `PALETTES[style.palette]` merged over by any matching keys in `brand` (so `settings.yaml` can still nudge a color).
  - `font_paths(key: str) -> dict` — `{"regular": Path, "bold": Path, "black": Path, "italic": Path}`, each guaranteed to point at an existing `.ttf` (family file if present under `assets/fonts/`, else `media.FONT_PATH`).
  - `class StyleError(Exception)`.

- [ ] **Step 1: Write `tests/test_styles.py`**

```python
import json
import pytest
from pipeline import styles
from pipeline.styles import Style, StyleError


def test_load_styles_returns_24_valid(tmp_path):
    # real repo config is copied into place by the fixture below
    st = styles.load_styles(REPO)
    assert len(st) == 24
    names = [s.name for s in st]
    assert len(set(names)) == 24
    for s in st:
        assert s.layout in styles.LAYOUT_NAMES
        assert s.palette in styles.PALETTE_NAMES
        assert s.font in styles.FONT_NAMES
        assert s.texture in styles.TEXTURE_NAMES
        assert s.accent_shape in styles.ACCENT_SHAPES
        assert s.logo in styles.LOGO_TREATMENTS
    # every layout and every palette is exercised at least once
    assert {s.layout for s in st} == set(styles.LAYOUT_NAMES)
    assert {s.palette for s in st} == set(styles.PALETTE_NAMES)


def test_load_styles_rejects_bad_count(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "styles.yaml").write_text(
        "styles:\n  - {name: a, layout: centered, palette: ink-on-white, "
        "font: grotesk, texture: dots, accent_shape: none, logo: tile}\n",
        encoding="utf-8")
    with pytest.raises(StyleError):
        styles.load_styles(tmp_path)


def test_load_styles_rejects_bad_field(tmp_path):
    (tmp_path / "config").mkdir()
    rows = "\n".join(
        f"  - {{name: s{i}, layout: centered, palette: ink-on-white, font: grotesk, "
        f"texture: dots, accent_shape: none, logo: tile}}" for i in range(23))
    (tmp_path / "config" / "styles.yaml").write_text(
        "styles:\n" + rows +
        "\n  - {name: bad, layout: NOPE, palette: ink-on-white, font: grotesk, "
        "texture: dots, accent_shape: none, logo: tile}\n", encoding="utf-8")
    with pytest.raises(StyleError):
        styles.load_styles(tmp_path)


def test_pick_style_cycles_without_repeat_in_15(tmp_path):
    (tmp_path / "config").mkdir()
    _write_real_config(tmp_path)                     # helper: copy repo styles.yaml
    seen = []
    for _ in range(24):
        seen.append(styles.pick_style(tmp_path).name)
    assert len(set(seen)) == 24                      # all distinct across one full cycle
    nxt = styles.pick_style(tmp_path).name
    assert nxt == seen[0]                            # 25th == 1st (cycle)
    cur = json.loads((tmp_path / "data" / "style_cursor.json").read_text("utf-8"))
    assert len(cur["recent"]) <= 15
    assert cur["recent"][0] == nxt


def test_pick_style_no_repeat_in_last_15(tmp_path):
    (tmp_path / "config").mkdir()
    _write_real_config(tmp_path)
    picks = [styles.pick_style(tmp_path).name for _ in range(40)]
    for i in range(15, len(picks)):
        assert picks[i] not in picks[i - 15:i]


def test_palette_for_merges_brand_override(tmp_path):
    s = Style("x", "centered", "ink-on-white", "grotesk", "dots", "none", "tile")
    p = styles.palette_for(s, {"accent": "#FF0000", "irrelevant": "z"})
    assert p["accent"] == "#FF0000"
    assert p["bg"] == styles.PALETTES["ink-on-white"]["bg"]


def test_font_paths_always_exist(tmp_path):
    for key in styles.FONT_NAMES:
        fp = styles.font_paths(key)
        for role in ("regular", "bold", "black", "italic"):
            assert fp[role].exists()
```

Add at the top of the file:

```python
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def _write_real_config(dst):
    src = (REPO / "config" / "styles.yaml").read_text("utf-8")
    (dst / "config" / "styles.yaml").write_text(src, encoding="utf-8")
```

and replace the bare `REPO` use in `test_load_styles_returns_24_valid` with a
`_write_real_config(tmp_path)` + `styles.load_styles(tmp_path)` pair for isolation.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_styles.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.styles'`.

- [ ] **Step 3: Create `config/styles.yaml`**

```yaml
# 24 carousel styles = 6 layouts x 4 palettes. pick_style() advances one step
# through this list per post (a full 24-long cycle), so no style repeats within
# 23 posts. Each row also picks a font, a background texture, an accent shape
# and a logo treatment so rows that share a layout+palette still read differently.
styles:
  - {name: white-centered,    layout: centered,    palette: ink-on-white,   font: grotesk,   texture: dots,          accent_shape: underline, logo: tile}
  - {name: navy-centered,     layout: centered,    palette: white-on-navy,  font: grotesk,   texture: gradient-band, accent_shape: bar,       logo: tile}
  - {name: warm-centered,     layout: centered,    palette: warm-editorial, font: editorial, texture: plain,         accent_shape: bracket,   logo: mono}
  - {name: mono-centered,     layout: centered,    palette: mono-contrast,  font: mono,      texture: grid,          accent_shape: none,      logo: mono}
  - {name: white-rail,        layout: left-rail,   palette: ink-on-white,   font: grotesk,   texture: plain,         accent_shape: bar,       logo: tile}
  - {name: navy-rail,         layout: left-rail,   palette: white-on-navy,  font: grotesk,   texture: dots,          accent_shape: none,      logo: chip}
  - {name: warm-rail,         layout: left-rail,   palette: warm-editorial, font: rounded,   texture: diagonal,      accent_shape: bar,       logo: mono}
  - {name: mono-rail,         layout: left-rail,   palette: mono-contrast,  font: mono,      texture: plain,         accent_shape: bar,       logo: mono}
  - {name: white-bar,         layout: bottom-bar,  palette: ink-on-white,   font: grotesk,   texture: grid,          accent_shape: none,      logo: tile}
  - {name: navy-bar,          layout: bottom-bar,  palette: white-on-navy,  font: rounded,   texture: plain,         accent_shape: none,      logo: chip}
  - {name: warm-bar,          layout: bottom-bar,  palette: warm-editorial, font: editorial, texture: plain,         accent_shape: none,      logo: mono}
  - {name: mono-bar,          layout: bottom-bar,  palette: mono-contrast,  font: mono,      texture: diagonal,      accent_shape: none,      logo: mono}
  - {name: white-split,       layout: split,       palette: ink-on-white,   font: grotesk,   texture: plain,         accent_shape: underline, logo: tile}
  - {name: navy-split,        layout: split,       palette: white-on-navy,  font: grotesk,   texture: dots,          accent_shape: bar,       logo: tile}
  - {name: warm-split,        layout: split,       palette: warm-editorial, font: rounded,   texture: plain,         accent_shape: bracket,   logo: mono}
  - {name: mono-split,        layout: split,       palette: mono-contrast,  font: mono,      texture: grid,          accent_shape: none,      logo: mono}
  - {name: white-magazine,    layout: magazine,    palette: ink-on-white,   font: editorial, texture: plain,         accent_shape: bracket,   logo: mono}
  - {name: navy-magazine,     layout: magazine,    palette: white-on-navy,  font: editorial, texture: plain,         accent_shape: underline, logo: mono}
  - {name: warm-magazine,     layout: magazine,    palette: warm-editorial, font: editorial, texture: plain,         accent_shape: bracket,   logo: mono}
  - {name: mono-magazine,     layout: magazine,    palette: mono-contrast,  font: editorial, texture: plain,         accent_shape: underline, logo: mono}
  - {name: white-ticket,      layout: ticket,      palette: ink-on-white,   font: rounded,   texture: dots,          accent_shape: none,      logo: tile}
  - {name: navy-ticket,       layout: ticket,      palette: white-on-navy,  font: rounded,   texture: plain,         accent_shape: none,      logo: chip}
  - {name: warm-ticket,       layout: ticket,      palette: warm-editorial, font: rounded,   texture: diagonal,      accent_shape: none,      logo: mono}
  - {name: mono-ticket,       layout: ticket,      palette: mono-contrast,  font: mono,      texture: grid,          accent_shape: none,      logo: mono}
```

- [ ] **Step 4: Create `src/pipeline/styles.py`**

```python
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
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_styles.py -q`
Expected: PASS (7 tests). `test_font_paths_always_exist` passes today because
every role falls back to `BeVietnamPro-Bold.ttf` (only file currently shipped).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/styles.py config/styles.yaml tests/test_styles.py
git commit -m "feat(styles): 24-style registry + cyclic pick_style with a 15-post cooldown"
```

---

### Task 2: vendor the extra font families (best-effort)

**Files:**
- Add: `assets/fonts/*.ttf` (Be Vietnam Pro Regular/ExtraBold/Italic, Lora Regular/Bold/Italic, JetBrains Mono Regular/Bold, Nunito Regular/Bold/ExtraBold)
- Modify: `.gitignore` — confirm `assets/fonts/` is NOT ignored (it isn't today; just verify).

**Interfaces:** none — `styles.font_paths` already degrades gracefully, so this task only widens the visual range. If a download fails, skip that file; the suite still passes.

- [ ] **Step 1: Download the OFL font files**

From repo root. All are SIL Open Font License, vendored from the `google/fonts` mirror:

```bash
cd assets/fonts
BASE=https://raw.githubusercontent.com/google/fonts/main/ofl
curl -fsSL -o BeVietnamPro-Regular.ttf    "$BASE/bevietnampro/BeVietnamPro-Regular.ttf"
curl -fsSL -o BeVietnamPro-ExtraBold.ttf  "$BASE/bevietnampro/BeVietnamPro-ExtraBold.ttf"
curl -fsSL -o BeVietnamPro-Italic.ttf     "$BASE/bevietnampro/BeVietnamPro-Italic.ttf"
curl -fsSL -o Lora-Regular.ttf            "$BASE/lora/Lora%5Bwght%5D.ttf"
curl -fsSL -o Lora-Italic.ttf             "$BASE/lora/Lora-Italic%5Bwght%5D.ttf"
curl -fsSL -o JetBrainsMono-Regular.ttf   "$BASE/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"
curl -fsSL -o Nunito-Regular.ttf          "$BASE/nunito/Nunito%5Bwght%5D.ttf"
cd ../..
```

`Lora[wght].ttf` and `JetBrainsMono[wght].ttf` and `Nunito[wght].ttf` are variable
fonts — Pillow renders their default instance, which is fine. Copy the regular to
the bold/black slots so `font_paths` finds a file:

```bash
cd assets/fonts
cp -n Lora-Regular.ttf Lora-Bold.ttf
cp -n JetBrainsMono-Regular.ttf JetBrainsMono-Bold.ttf
cp -n Nunito-Regular.ttf Nunito-Bold.ttf
cp -n Nunito-Regular.ttf Nunito-ExtraBold.ttf
cd ../..
```

If any `curl` fails (network), skip it — `font_paths` falls back to
`BeVietnamPro-Bold.ttf` for that family and the plan continues.

- [ ] **Step 2: Sanity-check they load**

Run:

```bash
.venv/Scripts/python.exe -c "from PIL import ImageFont; import glob; [ImageFont.truetype(f,40) for f in glob.glob('assets/fonts/*.ttf')]; print('ok', len(glob.glob('assets/fonts/*.ttf')))"
```

Expected: `ok <n>` with no traceback.

- [ ] **Step 3: Run the styles suite again**

Run: `.venv/Scripts/python.exe -m pytest tests/test_styles.py -q`
Expected: PASS — `test_font_paths_always_exist` still green (now with real family files where the download worked).

- [ ] **Step 4: Commit**

```bash
git add assets/fonts
git commit -m "chore(assets): vendor Lora / JetBrains Mono / Nunito / Be Vietnam Pro weights (OFL)"
```

---

### Task 3: `images.py` — style dispatch scaffolding + retain v4 as fallback

**Files:**
- Modify: `src/pipeline/images.py`
- Test: `tests/test_images.py` (append)

**Interfaces:**
- Consumes: `styles.Style`, `styles.pick_style`, `styles.palette_for`, `styles.font_paths`.
- Produces:
  - `@dataclass SlideModel` — `role: str`, `index: int` (1-based slide number), `total: int`, `headline: str`, `body: str`, `bullets: list[str]`, `tool: dict | None`, `tools: list[dict]`.
  - `_slide_models(article) -> list[SlideModel]` — maps `article.slides` → `SlideModel`s, filling `index`/`total`, coercing missing keys to `""`/`[]`/`None`.
  - `@dataclass RenderCtx` — `size: tuple[int,int]`, `palette: dict`, `fonts: dict` (from `styles.font_paths`), `style: Style`, `root: Path`, `brand: dict`, `article` (the `ArticleContent`, so a layout can read `cover_title`).
  - `LAYOUTS: dict[str, callable]` — keys = `styles.LAYOUT_NAMES`; each value `f(img, sm: SlideModel, ctx: RenderCtx) -> None` draws onto `img` in place. Task 3 ships all six as a thin stub that calls `_fallback_hook`/`_fallback_item` (so the dispatch is testable now; Tasks 5–10 replace them one by one).
  - `_fallback_hook(article, slide, size, brand, root) -> Image` — the CURRENT `_render_hook_slide`, renamed, byte-for-byte.
  - `_fallback_item(i, total, slide, size, brand, root) -> Image` — the CURRENT `_render_item_slide`, renamed, byte-for-byte.
  - `build_images(article, out_dir, *, size, brand=None, root=None, style=None, **ignored) -> list[str]` — if `style is None`, `style = styles.pick_style(root)`; build `RenderCtx`; for each `SlideModel` create a `1080×1350` RGB canvas filled `palette["bg"]`, call `LAYOUTS[style.layout](img, sm, ctx)`, save. Per-slide `try/except` → that slide falls back to `_fallback_hook`/`_fallback_item`. Outer `try/except` unchanged (`_safe_fallback`).

- [ ] **Step 1: Append tests to `tests/test_images.py`**

```python
from pipeline import images, styles
from pipeline.models import ArticleContent
from PIL import Image


def _story():
    slides = [
        {"role": "hook", "headline": "AI dựng phim tám giây", "body": "Một mô hình mới.",
         "tools": [{"name": "Sora", "domain": "openai.com"},
                   {"name": "Veo", "domain": "deepmind.google"}]},
        {"role": "item", "headline": "Nó làm được gì", "tool": {"name": "Sora", "domain": "openai.com"},
         "body": ("Mô hình nhận một câu tiếng Việt rồi trả về đoạn phim tám giây ở "
                  "1080p, giữ khuôn mặt nhân vật ổn định để cắt ghép thật chứ không "
                  "chỉ là bản trình diễn cho vui mắt, và bạn xuất được ngay."),
         "bullets": ["điểm nhấn một", "điểm nhấn hai"]},
        {"role": "close", "headline": "Chốt lại", "body": "Kỹ năng mới là viết mô tả."},
    ]
    return ArticleContent(format="share", caption_fb="fb", caption_ig="ig",
                          hashtags=["#AI"], cover_title="AI dựng phim",
                          slides=slides, sources=[])


def test_build_images_with_explicit_style(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    st = styles.Style("t", "centered", "ink-on-white", "grotesk", "dots", "underline", "tile")
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path, style=st)
    assert len(out) == 3
    for p in out:
        im = Image.open(p)
        assert im.size == (1080, 1350)


def test_build_images_picks_a_style_when_none(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    monkeypatch.setattr(styles, "pick_style",
                        lambda root, now=None: styles.Style(
                            "x", "left-rail", "white-on-navy", "grotesk",
                            "plain", "bar", "chip"))
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path)
    assert len(out) == 3


def test_one_bad_layout_slide_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    calls = {"n": 0}
    real_centered = images.LAYOUTS["centered"]

    def flaky(img, sm, ctx):
        calls["n"] += 1
        if sm.role == "item":
            raise RuntimeError("layout boom")
        return real_centered(img, sm, ctx)

    monkeypatch.setitem(images.LAYOUTS, "centered", flaky)
    st = styles.Style("t", "centered", "ink-on-white", "grotesk", "dots", "underline", "tile")
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path, style=st)
    assert len(out) == 3                          # still 3 images, item via _fallback_item
    assert Image.open(out[1]).size == (1080, 1350)


def test_bad_style_config_uses_default(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    monkeypatch.setattr(styles, "pick_style",
                        lambda *a, **k: (_ for _ in ()).throw(styles.StyleError("boom")))
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path)      # must not raise
    assert len(out) == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_images.py -q`
Expected: FAIL — `build_images` has no `style` kwarg wired; `images.LAYOUTS` missing.

- [ ] **Step 3: Edit `src/pipeline/images.py`**

Add near the top imports:

```python
from dataclasses import dataclass, field
from . import media, styles
```

Rename `_render_hook_slide` → `_fallback_hook` and `_render_item_slide` →
`_fallback_item` (definitions AND the two call sites in `_safe_fallback` and the
old `build_images` body). Leave their bodies untouched.

Add the models + dispatch, just above `build_images`:

```python
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
        return _fallback_hook(ctx.article, slide, ctx.size, b, ctx.root)
    return _fallback_item(sm.index, sm.total, slide, ctx.size, b, ctx.root)


# Tasks 5-10 replace these stubs one at a time with real layout functions.
def _layout_stub(img, sm, ctx):
    img.paste(_via_fallback(sm, ctx).convert("RGB"), (0, 0))


LAYOUTS: dict = {name: _layout_stub for name in styles.LAYOUT_NAMES}
```

Replace `build_images` with:

```python
def build_images(article, out_dir, *, size: tuple[int, int],
                 brand: dict | None = None, root: Path | None = None,
                 style=None, **ignored) -> list[str]:
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_images.py -q`
Expected: PASS (old tests still green because the stub reproduces the v4 output;
new tests green).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/images.py tests/test_images.py
git commit -m "refactor(images): style dispatch scaffold; v4 renderers retained as fallback"
```

---

### Task 4: shared furniture helpers

**Files:**
- Modify: `src/pipeline/images.py`
- Test: `tests/test_images.py` (append)

**Interfaces:**
- Produces (all draw in place, never raise — wrap risky bits in `try/except` + `log.warning`):
  - `_draw_texture(img, kind: str, palette: dict) -> None` — `dots` (reuse `_dot_grid` with `palette["muted"]` at ~10% via a faint colour), `grid` (thin lines every 90px), `diagonal` (parallel 45° hairlines every 120px), `plain` (no-op), `gradient-band` (a soft `bg`→`accent` vertical band down the right 22%, alpha ~12%).
  - `_accent_shape(draw, box: tuple, kind: str, colour: str) -> None` — `box` is the headline bbox; `underline` (4px rule 120px under the box's left), `bar` (filled rounded rect behind the box, drawn BEFORE text by callers that want it — see note), `bracket` (two 6px L-strokes at the box's top-left and bottom-right corners), `none` (no-op).
  - `_logo_lockup(img, box: tuple, palette: dict, tool: dict | None, treatment: str, root: Path, index: int) -> int` — draws the logo mark in `box` per `treatment` (`tile` = white rounded tile like today's `_logo_tile`; `chip` = `accent`-filled rounded tile, logo/`_ICONS` glyph in `on_accent`; `mono` = logo desaturated to `palette["ink"]`, no tile) and, if `tool` has a `name`, the brand name to the right in `fonts["bold"]` sized to fit. Returns the x where the name ends (or `box` right edge).
  - `_hook_logos(img, box: tuple, palette: dict, tools: list, treatment: str, root: Path) -> bool` — the hook logo row: one mark per tool centred in `box`, wrapping to a 2nd row past 4. Reuse the sizing logic of the existing `_hook_logo_row`. Returns True if ≥1 drawn.
  - `_handle_line(draw, size: tuple, palette: dict, fonts: dict, *, centred: bool) -> None` — `"A Hít Official"` in `fonts["regular"]` 30px, `palette["muted"]`, 46px above the bottom edge; centred or left at margin 80.
  - `_swipe_hint(draw, size: tuple, palette: dict, fonts: dict) -> None` — `"Vuốt tiếp  ›"` in `fonts["regular"]` 26px, `palette["muted"]`, bottom-right, margin 80.

Note on `bar`: callers that use `accent_shape == "bar"` must call `_accent_shape` with the headline box BEFORE drawing the headline text (so the text sits on the bar). Layouts document which order they use.

- [ ] **Step 1: Append tests**

```python
from PIL import ImageDraw
from pipeline import styles as _st


def _pal():
    return _st.PALETTES["ink-on-white"]


def test_draw_texture_variants_dont_crash_and_change_pixels(tmp_path):
    for kind in _st.TEXTURE_NAMES:
        im = Image.new("RGB", (1080, 1350), _pal()["bg"])
        before = im.tobytes()
        images._draw_texture(im, kind, _pal())
        if kind != "plain":
            assert im.tobytes() != before
        assert im.size == (1080, 1350)


def test_furniture_helpers_draw_expected_text(tmp_path):
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    d = ImageDraw.Draw(im)
    fonts = _st.font_paths("grotesk")
    images._handle_line(d, (1080, 1350), _pal(), fonts, centred=True)
    images._swipe_hint(d, (1080, 1350), _pal(), fonts)
    # bottom 120px band now has non-bg pixels
    band = im.crop((0, 1230, 1080, 1350)).getcolors(maxcolors=100000)
    assert len(band) > 1


def test_logo_lockup_returns_int_and_survives_no_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    x = images._logo_lockup(im, (80, 120, 270, 310), _pal(),
                            {"name": "Sora", "domain": "openai.com"}, "tile",
                            tmp_path, 1)
    assert isinstance(x, int) and x >= 270


def test_accent_shape_variants_dont_crash():
    for kind in _st.ACCENT_SHAPES:
        im = Image.new("RGB", (1080, 1350), _pal()["bg"])
        images._accent_shape(ImageDraw.Draw(im), (80, 400, 700, 480), kind,
                             _pal()["accent"])
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_images.py -q -k "texture or furniture or lockup or accent_shape"`
Expected: FAIL — helpers undefined.

- [ ] **Step 3: Implement the helpers in `images.py`**

Add after `_dot_grid`. Implement to the interface spec above. Reuse: `_dot_grid`
for `dots`; `_logo_tile` for the `tile` treatment; the sizing math from
`_hook_logo_row` for `_hook_logos`; `media._wrap` for any wrapping. Each helper
body wrapped so an internal failure is logged and swallowed (the slide still
renders without that ornament). Keep functions short — if `_draw_texture` grows
past ~40 lines, split per-kind sub-fns.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_images.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/images.py tests/test_images.py
git commit -m "feat(images): shared texture/accent/logo/handle/swipe helpers"
```

---

### Tasks 5–10: the six layout functions

Each task has the SAME shape. General rules for every layout function
`f(img, sm, ctx)`:

- Background is already filled `ctx.palette["bg"]` by `build_images`; call
  `_draw_texture(img, ctx.style.texture, ctx.palette)` first.
- Bind `draw = ImageDraw.Draw(img)`; re-bind after any `img.paste`.
- Headline: `_fit_lines`-style auto-fit using `ctx.fonts["black"]` (or `["bold"]`),
  colour `ctx.palette["ink"]` (or `on_accent` when on an accent block), ≤3 lines.
- Body: `ctx.fonts["regular"]`, colour derived from `palette` (ink at ~70% →
  reuse `BRAND_DEFAULTS["body_ink"]` only for `ink-on-white`; otherwise
  `palette["ink"]`), up to 7 lines, shrink 34→30→28 to fit. Never clip.
- Bullets (item only, ≤3): `palette["accent"]` dot + text.
- Call `_accent_shape(draw, headline_box, ctx.style.accent_shape, palette["accent"])`.
- Furniture — MANDATORY, via the shared helpers only:
  - item with `sm.tool`: `_logo_lockup(img, box, palette, sm.tool, ctx.style.logo, ctx.root, sm.index)`
  - hook: `_hook_logos(img, box, palette, sm.tools, ctx.style.logo, ctx.root)`
  - every role except `close`: `_swipe_hint(draw, ctx.size, palette, ctx.fonts)`
  - every role: `_handle_line(draw, ctx.size, palette, ctx.fonts, centred=<close>)`
  - `close`: no lockup, no swipe; show a `palette["accent"]` "CHỐT LẠI" pill where the lockup would be.
- Return `None`.

Per-task test shape (`tests/test_images.py`):

```python
import pipeline.images as images

def test_layout_<name>_renders_all_roles(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    spies = {k: [] for k in ("lockup", "hook", "swipe", "handle")}
    monkeypatch.setattr(images, "_logo_lockup",
                        lambda *a, **k: spies["lockup"].append(a) or 300)
    monkeypatch.setattr(images, "_hook_logos",
                        lambda *a, **k: spies["hook"].append(a) or True)
    monkeypatch.setattr(images, "_swipe_hint", lambda *a, **k: spies["swipe"].append(a))
    monkeypatch.setattr(images, "_handle_line", lambda *a, **k: spies["handle"].append(a))
    st = _st.Style("t", "<name>", "ink-on-white", "grotesk", "dots", "underline", "tile")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["ink-on-white"],
                           _st.font_paths("grotesk"), st, tmp_path, {})
    models = images._slide_models(_story())
    for sm in models:
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["<name>"](im, sm, ctx)
        assert im.size == (1080, 1350)
    assert len(spies["hook"]) == 1                       # hook drew the logo row
    assert len(spies["lockup"]) == 1                     # the one item with a tool
    assert len(spies["swipe"]) == 2                      # hook + item, not close
    assert len(spies["handle"]) == 3                     # all roles
```

(`_story()` is the fixture added in Task 3.)

---

### Task 5: `_layout_centered`

**Files:** Modify `src/pipeline/images.py`; Test `tests/test_images.py`.
**Interface:** `LAYOUTS["centered"] = _layout_centered`.

**Look:** the closest to v4. Everything centred. Hook: dark feel comes from
`white-on-navy`/`mono-contrast` palettes, not hard-coded. Kicker pill
"A HÍT OFFICIAL" top-centre; headline centred mid-canvas with one long word blown
up in `palette["accent"]` (reuse the `big_idx` trick from `_fallback_hook`);
sub-body centred; `_hook_logos` box `(margin, y+40, W-margin, y+40+320)`.
Item: `_logo_lockup` centred at top (`box` centred, 190px), brand name under or
beside; headline centred; underline/accent centred; body centred (wrap to ~80% W);
bullets left-aligned within a centred column.

- [ ] Step 1: write `test_layout_centered_renders_all_roles` (per shape above).
- [ ] Step 2: `pytest -k layout_centered` → FAIL (still the stub; spies not hit as asserted).
- [ ] Step 3: implement `_layout_centered`, set `LAYOUTS["centered"] = _layout_centered`.
- [ ] Step 4: `pytest tests/test_images.py -q` → PASS.
- [ ] Step 5: render a sample & eyeball —
  `.venv/Scripts/python.exe scripts/render_style_samples.py white-centered` (script from Task 12; if not present yet, inline a 6-line snippet). Confirm 1080×1350, headline not clipped, logos present on hook, handle on every slide.
- [ ] Step 6: `git add -A && git commit -m "feat(images): centered layout"`

---

### Task 6: `_layout_left_rail`

**Look:** a solid `palette["accent"]` vertical rail down the left ~11% (120px).
Big ghost slide number (`sm.index-1`) in `on_accent` at ~30% alpha inside the rail.
All content right of the rail, left-aligned at x≈170. Hook: `_hook_logos` box to
the right of the rail, single or double row. Item: `_logo_lockup` at
`(170, 120, 360, 310)`. Headline left-aligned; `accent_shape` sits under the
headline (skip `bar` visually clashing with the rail — if `ctx.style.accent_shape
== "bar"` fall back to `underline` here). Handle bottom-left of the content area.

- [ ] Step 1–6 as Task 5 (test `test_layout_left_rail_renders_all_roles`, sample `navy-rail`).

---

### Task 7: `_layout_bottom_bar`

**Look:** top ~55% is `palette["bg"]` + texture + a very large faint glyph
(`_ICONS` pick by `sm.index`) or the ghost number; the `_logo_lockup` /
`_hook_logos` live up here. Bottom ~45% is a filled `palette["accent"]` block
(full-bleed) holding the headline + body in `palette["on_accent"]`. Bullets in
`on_accent` with a lighter dot. `_swipe_hint` sits just inside the bottom bar,
`on_accent`. Handle inside the bar, `on_accent` at reduced alpha. Close: no bar —
centre the "CHỐT LẠI" pill + body + centred handle on the plain bg.

- [ ] Step 1–6 as Task 5 (test `test_layout_bottom_bar_renders_all_roles`, sample `white-bar`).

---

### Task 8: `_layout_split`

**Look:** top half (`0..H*0.46`) filled with `palette["accent"]` at ~14% tint
over `bg` (blend), holding a small-caps kicker + the headline in `palette["ink"]`.
A 3px `palette["accent"]` divider at `y=H*0.46`. Bottom half: body + bullets +
`_logo_lockup` (item) at bottom-left, `_handle_line` bottom. Hook: top half holds
headline, bottom half holds sub-body + `_hook_logos`.

- [ ] Step 1–6 as Task 5 (test `test_layout_split_renders_all_roles`, sample `navy-split`).

---

### Task 9: `_layout_magazine`

**Look:** force `ctx.fonts` from `styles.font_paths("editorial")` regardless of
`ctx.style.font` (this layout IS the serif one). Wide margins (110px). A thin
1px `palette["muted"]` rule above and below the headline. Kicker in tracked-out
uppercase (insert spaces between chars), `palette["muted"]`, 22px. Body in two
columns when > 6 wrapped lines, else one. First body character as a 2-line
drop-cap in `palette["accent"]`. `_logo_lockup` uses `mono` treatment look even
if `ctx.style.logo` differs (editorial restraint) — pass `"mono"` explicitly.
`_accent_shape` = `bracket` reads best; honour the style's value anyway.

- [ ] Step 1–6 as Task 5 (test `test_layout_magazine_renders_all_roles`, sample `warm-magazine`). Also assert the body wraps to 2 columns for the long item body (e.g. count distinct text x-offsets, or just assert no clip + image differs from a 1-column render).

---

### Task 10: `_layout_ticket`

**Look:** an inset rounded card (margin 64, radius 40) in a slightly lifted
shade of `bg` with a 2px `palette["muted"]` dashed border (draw dashes manually).
A vertical perforation line of small circles at x≈W*0.72 splits the card into a
body area (left) and a "stub" (right) that holds the ghost slide number + the
`_handle_line` rotated 90°… OR, to keep it simple and legible, the stub holds the
number and the handle stays horizontal at the card bottom. Headline + body in the
left area. `_logo_lockup` top-left inside the card. Texture is drawn on the
canvas OUTSIDE the card only (mask the card rect).

- [ ] Step 1–6 as Task 5 (test `test_layout_ticket_renders_all_roles`, sample `white-ticket`).

---

### Task 11: wire `pick_style` into `article_run.draft()` + store the style name

**Files:**
- Modify: `src/pipeline/article_run.py`
- Test: `tests/test_article_run.py`

**Interfaces:**
- Consumes: `styles.pick_style(root)`, `images.build_images(..., style=...)`.
- Produces: `draft()` picks the style once, passes it to `build_images`, and
  records `style=<name>` in the `ds.put(...)` content row. On `pick_style`
  failure it passes `style=None` (build_images then self-defaults) and records
  `style="default"`.

- [ ] **Step 1: Update `tests/test_article_run.py`**

In the `wired` fixture, make `build_images` capture its `style` kwarg:

```python
    captured = {}
    def fake_build(article, out_dir, *, size, brand=None, root=None, style=None, **k):
        captured["style"] = style
        return [str(tmp_path / f"{i:02d}.jpg") for i in range(1, 6)]
    monkeypatch.setattr(article_run.images, "build_images", fake_build)
    monkeypatch.setattr(article_run.styles, "pick_style",
                        lambda root, now=None: article_run.styles.Style(
                            "navy-rail", "left-rail", "white-on-navy", "grotesk",
                            "dots", "none", "chip"))
    return tmp_path, captured
```

Add:

```python
def test_draft_records_style_name(wired):
    root, captured = wired
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    article_run.draft("morning", root, now, tg=FakeTG(), meta=object())
    saved = DailyState(root / "data").get("2026-09-06", "morning")
    assert saved["style"] == "navy-rail"
    assert captured["style"].name == "navy-rail"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -q -k style`
Expected: FAIL — `article_run.styles` missing; no `style` in state.

- [ ] **Step 3: Edit `article_run.py`**

Add to imports: `from . import write, images, topics, collect, score, publish, styles`.

Before the `images.build_images` call in `draft()`:

```python
    try:
        chosen_style = styles.pick_style(root)
        style_name = chosen_style.name
    except Exception as e:  # noqa: BLE001 - bad styles.yaml -> build_images self-defaults
        log.warning("pick_style failed (%s)", e)
        chosen_style, style_name = None, "default"
```

Pass `style=chosen_style` into `images.build_images(...)`.

Add `style=style_name,` to the `ds.put(date, slot, status="publishing", ...)` kwargs.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_run.py tests/test_article_run.py
git commit -m "feat(article_run): pick a style per post and record it in state"
```

---

### Task 12: sample-render script + full suite + visual QA

**Files:**
- Create: `scripts/render_style_samples.py`
- Test: whole suite.

**Interface:** `python scripts/render_style_samples.py [style-name ...]` — with no
args renders all 24; writes `scratchpad/style-samples/<name>/01.jpg…` using a
built-in 6-slide fixture story. Prints each output dir.

- [ ] **Step 1: Create `scripts/render_style_samples.py`**

```python
"""Render the sample carousel for one or more styles into scratchpad/style-samples/.
Usage: python scripts/render_style_samples.py [style-name ...]"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import styles, images                      # noqa: E402
from pipeline.models import ArticleContent               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratchpad" / "style-samples"

STORY = ArticleContent(
    format="share", caption_fb="fb", caption_ig="ig", hashtags=["#AI"],
    cover_title="AI dựng phim tám giây từ một câu",
    slides=[
        {"role": "hook", "headline": "AI dựng phim tám giây từ một câu",
         "body": "Một mô hình video mới vừa ra mắt, ổn định đủ để cắt ghép thật.",
         "tools": [{"name": "Sora", "domain": "openai.com"},
                   {"name": "Veo", "domain": "deepmind.google"},
                   {"name": "Runway", "domain": "runwayml.com"}]},
        {"role": "item", "headline": "Nó thực sự làm được gì",
         "tool": {"name": "OpenAI Sora", "domain": "openai.com"},
         "body": ("Mô hình nhận một câu mô tả bằng tiếng Việt rồi trả về đoạn phim "
                  "tám giây ở 1080p, giữ khuôn mặt nhân vật và ánh sáng ổn định suốt "
                  "cả đoạn nên bạn cắt ghép được thật chứ không còn là bản trình diễn "
                  "cho vui mắt."),
         "bullets": ["xuất trực tiếp 1080p", "giữ nhân vật xuyên suốt"]},
        {"role": "item", "headline": "Khác gì bản cũ",
         "tool": {"name": "Google Veo", "domain": "deepmind.google"},
         "body": ("Bản trước chỉ dựng được ba giây và hay đổi mặt nhân vật giữa chừng; "
                  "bản này giữ bố cục, chuyển động mượt hơn và nhận prompt dài gấp đôi "
                  "nên ý tưởng phức tạp vẫn ra đúng."),
         "bullets": ["prompt dài gấp đôi", "chuyển động mượt hơn"]},
        {"role": "item", "headline": "Bắt đầu thế nào",
         "tool": {"name": "Runway", "domain": "runwayml.com"},
         "body": ("Viết một câu tả cảnh thật cụ thể — chủ thể, hành động, góc máy, ánh "
                  "sáng — rồi render thử ở bản thấp trước khi lên 1080p để tiết kiệm "
                  "thời gian chờ."),
         "bullets": ["tả cụ thể góc máy + ánh sáng", "render nháp trước"]},
        {"role": "close", "headline": "Điều đọng lại",
         "body": "Kỹ năng mới của người làm nội dung một mình là viết mô tả cho đúng."},
    ],
    sources=[])


def main(argv):
    names = argv or [s.name for s in styles.load_styles(ROOT)]
    by_name = {s.name: s for s in styles.load_styles(ROOT)}
    for n in names:
        st = by_name[n]
        d = OUT / n
        paths = images.build_images(STORY, d, size=(1080, 1350), brand={},
                                    root=ROOT, style=st)
        print(n, "->", d, f"({len(paths)} slides)")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 2: Render every style**

Run: `.venv/Scripts/python.exe scripts/render_style_samples.py`
Expected: 24 lines `name -> ...path... (5 slides)`, no traceback.

- [ ] **Step 3: Visual QA**

Open `scratchpad/style-samples/*/01.jpg` … `05.jpg`. For each style confirm:
1080×1350; headline never clipped; item body shows in full (not one cut line);
every item-with-tool slide has a big logo + brand name; the hook shows all 3
logos; the "A Hít Official" handle is on every slide; the close slide has the
"CHỐT LẠI" pill and no swipe hint; no top progress bar anywhere. Fix any layout
that fails and re-render just that one.

- [ ] **Step 4: Full suite + CI parity**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/render_style_samples.py
git commit -m "chore(images): style sample renderer for visual QA"
```

`scratchpad/` is git-ignored — the sample JPEGs are not committed.

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-09-07-article-style-variety-auto-publish-design.md` §2):
- §2.1 `config/styles.yaml` 24 entries, field set → Task 1 (YAML) + validation.
- §2.2 4 palettes with `on_accent` → Task 1 `PALETTES`.
- §2.3 4 font families bundled + `font_paths` fallback → Task 1 (`font_paths`) + Task 2 (vendoring).
- §2.4 `styles.py` `load_styles` / `pick_style` / cursor in `data/style_cursor.json` / skip-15 → Task 1.
- §2.5 `build_images(style=)`, `LAYOUTS` 6 fns, `SlideModel`, `RenderCtx`, mandatory furniture via helpers → Task 3 (scaffold) + Task 4 (helpers) + Tasks 5–10 (layouts).
- §2.5 six layout descriptions → Tasks 5–10 one each.
- §2.6 fallback: bad layout slide → `_fallback_*`; bad style → default; total → `media.build_media` → Task 3 `build_images` try/except tiers.
- §2.7 store `style` name in state → Task 11.
- §3 tests: `test_styles.py` → Task 1; `test_images.py` extensions → Tasks 3/4/5–10; sample render → Task 12.
- §4 YAGNI: no AI/cutout/stock/dashboard/A-B — nothing in the plan adds them.

**Placeholder scan:** Tasks 1–4, 11, 12 carry complete code. Tasks 5–10 give an
element/position spec + exact helper signatures + a concrete test shape rather
than final pixel code — deliberate: Pillow layout is iterative visual work with a
mandatory eyeball step (each task Step 5). The shared helpers (Task 4) and the
furniture contract (tested via spies) are fully specified, so "done" is
well-defined: renders 1080×1350 for all 3 roles, spies show the right furniture
calls, sample passes the Step-3 checklist.

**Type consistency:**
- `Style(name, layout, palette, font, texture, accent_shape, logo)` — 7 fields, same order in Task 1 dataclass, YAML rows, every test constructor, Task 11.
- `pick_style(root, now=None)` — Task 1 def, Task 3 call (`styles.pick_style(root)`), Task 11 call, all test monkeypatches use `(root, now=None)`.
- `build_images(article, out_dir, *, size, brand=None, root=None, style=None, **ignored)` — Task 3 def, Task 11 call, Task 12 script call, all tests.
- `LAYOUTS[name](img, sm, ctx)` — 3-arg in Task 3 stub, Tasks 5–10, all layout tests.
- `_logo_lockup(img, box, palette, tool, treatment, root, index) -> int` — Task 4 def, Tasks 5–10 calls, layout-test spy returns `300` (an int).
- `_hook_logos(img, box, palette, tools, treatment, root) -> bool` — Task 4 def, Tasks 5–10, spy returns `True`.
- `_handle_line(draw, size, palette, fonts, *, centred)` / `_swipe_hint(draw, size, palette, fonts)` — Task 4 defs, Tasks 5–10, Task 4 tests.
- `RenderCtx(size, palette, fonts, style, root, brand)` — Task 3 def, Task 11-adjacent tests, layout tests.
- `SlideModel(role, index, total, headline, body, bullets, tool, tools)` — Task 3 def; `_slide_models` builds it; layout tests iterate `images._slide_models(_story())`.

**Cross-plan note:** this plan assumes the auto-publish plan
(`2026-09-07-article-auto-publish.md`) has landed on the branch first —
`article_run.draft()` already has the `meta=` param and the
`status="publishing"` + `publish.schedule_slot` tail. Task 11 only inserts the
`pick_style` call and the `style=` kwargs.
