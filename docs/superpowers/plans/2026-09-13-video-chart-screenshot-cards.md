# Video Chart/Screenshot Cards + Visual Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new video-script card types (animated chart: line/bar/hbar; website screenshot via Google Custom Search + Playwright with graceful fallback) and restyle the existing plain-text and numeral cards to a bolder, accent-colored look, without changing the render architecture, background video, or audio/approval flow.

**Architecture:** The pipeline already has a mature Remotion kinetic-typography renderer: `src/pipeline/video/script.py` (LLM writes a JSON script) → `codegen.py` (serializes to positional-array `.mjs` files) → `tools/align.mjs` (Node forced-aligner merges the arrays with audio timing into `video/src/timeline.json`) → `video/src/layouts.tsx` (one React component per `variant`, all reading from `timeline.json`). This plan extends the Card shape end-to-end through every one of those layers with two new optional fields (`chart`, `screenshot`), adds two new layout components, and retints three existing ones.

**Tech Stack:** Python 3.12 (dataclasses, httpx, Playwright sync API — already a dependency), Node/TypeScript (Remotion, plain SVG for charts), pytest, `node --check` for generated-file syntax checks.

## Global Constraints

- Card shape: a card may set **at most one** of `num` / `chart` / `screenshot`. Enforced in `script.py`'s `_validate()`, which is the single validation chokepoint already wired into the retry-on-validation-error loop (`fix(video): retry on any validation error`, already on master) — no new retry plumbing needed.
- Chart data is **LLM-authored only** (no external data source) — same trust model as the existing `num` field ("Không bịa số").
- Screenshot resolution is **LLM-authored search query → Google Custom Search API → Playwright capture**, done at **render time** (`render_pending`, after audio is received), never at draft time.
- Any screenshot failure (missing secret, search error, no results, navigation timeout) must degrade that one card to a plain text card **without changing its spoken lines** and must never fail the whole render.
- Accent color for both new card types and the retinted existing ones: `#FF4D2E`, theme-independent (same value in both `LIGHT` and `DARK` palettes).
- New secrets (`GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX`) are consumed only by `.github/workflows/video-render.yml` — the user creates them; missing secrets must degrade gracefully (see above), never crash.
- Reference spec: `docs/superpowers/specs/2026-09-13-video-chart-screenshot-cards-design.md` (commit `72596f8`). Base commit for this plan: `a7543a9`.

---

## File Structure

| File | Change |
|---|---|
| `src/pipeline/video/models.py` | Add `ChartSpec`, `ScreenshotSpec`; extend `Card` with `chart`, `screenshot`, `screenshot_file` |
| `src/pipeline/video/variants.py` | `normalize()` must not reclassify chart/screenshot cards |
| `src/pipeline/video/script.py` | Prompt text + `_validate()` shape checks for the two new card types |
| `src/pipeline/video/codegen.py` | `render_variants_mjs` emits 2 new positional slots |
| `video/tools/align.mjs` | Destructure the 2 new positional slots into `timeline.json` cards |
| `video/src/palette.ts` | Add `accent: string` to `Pal`, `#FF4D2E` in both palettes |
| `video/src/layouts.tsx` | Retint `Stack`/`Strike`/`Stair` accent lines and `Numeral`'s badge; export `Frame`, `Card` chart/screenshotFile fields |
| `src/pipeline/media.py` | Expose the existing Playwright capture primitive for reuse (rename, keep wrapper) |
| `src/pipeline/video/screenshot.py` | **New.** Google Custom Search lookup + capture, with `ScreenshotError` |
| `src/pipeline/video/render.py` | Call screenshot capture before `codegen.write`, with per-card fallback |
| `video/src/Chart.tsx` | **New.** Line/bar/hbar chart component |
| `video/src/Screenshot.tsx` | **New.** Browser-chrome-framed screenshot component |
| `video/src/KineticShort.tsx` | Wire the two new components into `CardView`'s switch |
| `.github/workflows/video-render.yml` | Add Playwright/Chromium install step + new secrets |
| `src/pipeline/video/build_video.py` | Add one chart card + one pre-set screenshot card to the smoke fixture |
| `video/public/smoke-screenshot.png` | **New.** Tiny placeholder image for the smoke fixture's screenshot card |

---

### Task 1: `Card` model — `ChartSpec`, `ScreenshotSpec`, mutual-exclusion-ready fields

**Files:**
- Modify: `src/pipeline/video/models.py`
- Test: `tests/video/test_models.py`

**Interfaces:**
- Produces: `ChartSpec(kind: str, items: list[dict], unit: str = "")` with `.to_dict()`/`.from_dict()`. `ScreenshotSpec(query: str)` with `.to_dict()`/`.from_dict()`. `Card` gains `chart: ChartSpec | None = None`, `screenshot: ScreenshotSpec | None = None`, `screenshot_file: str | None = None` (all optional, default `None`, fully round-trip through `Card.to_dict()`/`from_dict()`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/video/test_models.py` (after the existing `test_script_roundtrip` test, before the `from pipeline.video.models import VideoMeta` import line — keep that import and the tests below it where they are):

```python
from pipeline.video.models import ChartSpec, ScreenshotSpec

def test_chartspec_roundtrip():
    c = ChartSpec(kind="bar", items=[{"label": "Astra", "value": 1.67},
                                     {"label": "Fable 5.1", "value": 3.76}], unit="$")
    assert ChartSpec.from_dict(c.to_dict()) == c

def test_screenshotspec_roundtrip():
    s = ScreenshotSpec(query="GitHub OpenAI Codex repository")
    assert ScreenshotSpec.from_dict(s.to_dict()) == s

def test_card_chart_and_screenshot_roundtrip():
    chart = ChartSpec(kind="line", items=[{"value": 1}, {"value": 2}, {"value": 5}])
    c = _card(["x"], num=None)
    c.chart = chart
    d = c.to_dict()
    assert d["chart"] == chart.to_dict()
    assert d["screenshot"] is None
    assert d["screenshot_file"] is None
    back = Card.from_dict(d)
    assert back.chart == chart
    assert back.screenshot is None

    shot = ScreenshotSpec(query="Anthropic Claude Fable 5.1")
    c2 = _card(["y"])
    c2.screenshot = shot
    c2.screenshot_file = "screenshots/2.png"
    d2 = c2.to_dict()
    back2 = Card.from_dict(d2)
    assert back2.screenshot == shot
    assert back2.screenshot_file == "screenshots/2.png"

def test_card_from_dict_defaults_chart_and_screenshot_to_none():
    # existing fixtures (norm_script.json etc.) never include these keys
    c = Card.from_dict({"lines": ["x"], "variant": "stack", "anchor": "mid",
                        "motion_in": "rise", "motion_out": "up"})
    assert c.chart is None and c.screenshot is None and c.screenshot_file is None
```

Add `from pipeline.video.models import Card` is already present at the top of the file (via `from pipeline.video.models import Card, SectionMark, Script`) — no new top-level import needed beyond `ChartSpec, ScreenshotSpec` shown above.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_models.py -k "chart or screenshot" -v`
Expected: FAIL with `ImportError: cannot import name 'ChartSpec'`

- [ ] **Step 3: Implement `ChartSpec`, `ScreenshotSpec`, extend `Card`**

In `src/pipeline/video/models.py`, add after the `Card` class's closing `from_dict` classmethod (i.e. right before `@dataclass\nclass SectionMark:`):

```python
@dataclass
class ChartSpec:
    kind: str
    items: list[dict]
    unit: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "items": [dict(i) for i in self.items], "unit": self.unit}

    @classmethod
    def from_dict(cls, d: dict) -> "ChartSpec":
        return cls(kind=d["kind"], items=[dict(i) for i in d["items"]], unit=d.get("unit", ""))


@dataclass
class ScreenshotSpec:
    query: str

    def to_dict(self) -> dict:
        return {"query": self.query}

    @classmethod
    def from_dict(cls, d: dict) -> "ScreenshotSpec":
        return cls(query=d["query"])
```

Then replace the `Card` class entirely with:

```python
@dataclass
class Card:
    lines: list[str]
    variant: str
    anchor: str
    motion_in: str
    motion_out: str
    num: int | float | None = None
    chart: ChartSpec | None = None
    screenshot: ScreenshotSpec | None = None
    screenshot_file: str | None = None

    @property
    def spoken(self) -> str:
        return " ".join(_strip_tilde(l).strip() for l in self.lines if _strip_tilde(l).strip())

    @property
    def displayed_words(self) -> int:
        return sum(len(_WORD.findall(l)) for l in self.lines if not l.startswith("~"))

    def to_dict(self) -> dict:
        return {"lines": list(self.lines), "variant": self.variant, "anchor": self.anchor,
                "motion_in": self.motion_in, "motion_out": self.motion_out, "num": self.num,
                "chart": self.chart.to_dict() if self.chart is not None else None,
                "screenshot": self.screenshot.to_dict() if self.screenshot is not None else None,
                "screenshot_file": self.screenshot_file}

    @classmethod
    def from_dict(cls, d: dict) -> "Card":
        chart = ChartSpec.from_dict(d["chart"]) if d.get("chart") else None
        screenshot = ScreenshotSpec.from_dict(d["screenshot"]) if d.get("screenshot") else None
        return cls(lines=list(d["lines"]), variant=d["variant"], anchor=d["anchor"],
                   motion_in=d["motion_in"], motion_out=d["motion_out"],
                   num=_coerce_num(d.get("num")), chart=chart, screenshot=screenshot,
                   screenshot_file=d.get("screenshot_file"))
```

(This is the full replacement — `spoken`, `displayed_words`, and the `_coerce_num` call on `num` are unchanged from today's version; only the three new fields and their handling in `to_dict`/`from_dict` are new.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_models.py -v`
Expected: all PASS (including the pre-existing tests in the file — this is a superset change)

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/models.py tests/video/test_models.py
git commit -m "feat(video): add ChartSpec/ScreenshotSpec and extend Card"
```

---

### Task 2: `variants.py` — protect chart/screenshot cards from reclassification

**Files:**
- Modify: `src/pipeline/video/variants.py`
- Test: `tests/video/test_variants.py`

**Interfaces:**
- Consumes: `Card.chart`, `Card.screenshot` from Task 1.
- Produces: `normalize(s: Script) -> Script` (signature unchanged) now leaves `variant`/`num` untouched for any card with `chart` or `screenshot` set.

**Why this task exists:** `normalize()`'s existing rule 2 ("digit card -> numeral") force-converts ANY card whose text contains a digit into `variant="numeral"` — a chart card discussing "95% vs 40%" would be silently destroyed. Rule 3 also force-converts the last card and every section-final card to `invert`/`strike`, which would clobber a chart/screenshot card unlucky enough to land on those positions.

- [ ] **Step 1: Write the failing tests**

Add to `tests/video/test_variants.py`:

```python
from pipeline.video.models import ChartSpec, ScreenshotSpec

def test_chart_card_with_digit_is_not_forced_to_numeral():
    chart_card = C(["Astra rẻ hơn Fable 5.1", "95% so với 40%"])
    chart_card.chart = ChartSpec(kind="hbar", items=[{"label": "Astra", "value": 95},
                                                     {"label": "Fable 5.1", "value": 40}])
    s = Script(cards=[C(["mở đầu"]), chart_card, C(["kết"])],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    assert out.cards[1].variant == chart_card.variant  # unchanged, still whatever the LLM picked
    assert out.cards[1].chart == chart_card.chart


def test_screenshot_card_as_last_card_is_not_forced_to_invert():
    shot_card = C(["Xem trang GitHub của repo này"])
    shot_card.screenshot = ScreenshotSpec(query="GitHub OpenAI Codex")
    s = Script(cards=[C(["mở đầu"]), shot_card],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    assert out.cards[-1].variant == shot_card.variant
    assert out.cards[-1].screenshot == shot_card.screenshot
```

Add `from pipeline.video.models import Card, SectionMark, Script` is already at the top of the file — add the `ChartSpec, ScreenshotSpec` import shown above alongside it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_variants.py -k "chart_card or screenshot_card" -v`
Expected: FAIL — `test_chart_card_with_digit_is_not_forced_to_numeral` fails because rule 2 still forces `variant="numeral"`.

- [ ] **Step 3: Guard the reclassification rules**

In `src/pipeline/video/variants.py`, inside the `for i, c in enumerate(s.cards):` loop in `normalize()`, wrap rules 2 and 3 with a guard. Replace:

```python
        # 2. digit card -> numeral
        joined = " ".join(l for l in c.lines if not l.startswith("~"))
        if _DIGIT.search(joined):
            if c.num is None:
                c.num = _first_int(joined)
            c.variant = "numeral"

        # 3. section-final / last-card variants
        if i == n - 1:
            c.variant = "invert"
        elif i in finals and c.variant in {"stack", "right"}:
            c.variant = "strike"
```

with:

```python
        typed = c.chart is not None or c.screenshot is not None

        # 2. digit card -> numeral (skip cards already typed as chart/screenshot)
        joined = " ".join(l for l in c.lines if not l.startswith("~"))
        if not typed and _DIGIT.search(joined):
            if c.num is None:
                c.num = _first_int(joined)
            c.variant = "numeral"

        # 3. section-final / last-card variants (skip cards already typed as chart/screenshot)
        if not typed:
            if i == n - 1:
                c.variant = "invert"
            elif i in finals and c.variant in {"stack", "right"}:
                c.variant = "strike"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_variants.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/variants.py tests/video/test_variants.py
git commit -m "fix(video): normalize() must not reclassify chart/screenshot cards"
```

---

### Task 3: `script.py` — prompt text + `_validate()` shape checks

**Files:**
- Modify: `src/pipeline/video/script.py`
- Test: `tests/video/test_script.py`

**Interfaces:**
- Consumes: `Card.chart`, `Card.screenshot`, `ChartSpec`, `ScreenshotSpec` from Task 1.
- Produces: `_validate(data, cfg)` now raises `VideoScriptError` for: more than one of `num`/`chart`/`screenshot` set on a card; `chart.kind` not in `{"line","bar","hbar"}`; wrong item count for the kind; a chart item missing a numeric `value`; an empty or >100-char `screenshot.query`. `build_prompt`'s system string now mentions both new card shapes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/video/test_script.py`:

```python
def _base_card():
    return {"lines": ["x"], "variant": "stack", "anchor": "mid",
            "motion_in": "rise", "motion_out": "up"}

def _script_with_card(extra_card_fields, n_extra_cards=8):
    # _validate() requires 8 <= len(cards) <= 20 -- 8 is the floor, so this
    # default must stay at 8 (not 7) or every test below would fail on the
    # card-count check before ever reaching the chart/screenshot validation
    # this helper exists to exercise.
    cards = [_base_card() for _ in range(n_extra_cards)]
    cards[3] = {**_base_card(), **extra_card_fields}
    return {"sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 4}],
            "cards": cards}

def test_validate_rejects_card_with_both_num_and_chart():
    data = _script_with_card({"num": 5, "chart": {"kind": "bar",
                              "items": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]}})
    with pytest.raises(VideoScriptError, match="chỉ được set 1 trong"):
        script._validate(data, CFG)

def test_validate_rejects_bad_chart_kind():
    data = _script_with_card({"chart": {"kind": "pie", "items": [{"value": 1}]}})
    with pytest.raises(VideoScriptError, match="kind"):
        script._validate(data, CFG)

def test_validate_rejects_bar_with_wrong_item_count():
    data = _script_with_card({"chart": {"kind": "bar",
                              "items": [{"label": "A", "value": 1}]}})
    with pytest.raises(VideoScriptError, match="items"):
        script._validate(data, CFG)

def test_validate_rejects_chart_item_without_numeric_value():
    data = _script_with_card({"chart": {"kind": "line",
                              "items": [{"value": 1}, {"value": 2}, {"value": "nhiều"}]}})
    with pytest.raises(VideoScriptError, match="value"):
        script._validate(data, CFG)

def test_validate_accepts_valid_line_chart():
    data = _script_with_card({"chart": {"kind": "line",
                              "items": [{"value": 1}, {"value": 2}, {"value": 5}], "unit": "%"}})
    s = script._validate(data, CFG)
    assert s.cards[3].chart.kind == "line"

def test_validate_rejects_empty_screenshot_query():
    data = _script_with_card({"screenshot": {"query": "  "}})
    with pytest.raises(VideoScriptError, match="query"):
        script._validate(data, CFG)

def test_validate_rejects_screenshot_query_too_long():
    data = _script_with_card({"screenshot": {"query": "x" * 101}})
    with pytest.raises(VideoScriptError, match="query"):
        script._validate(data, CFG)

def test_validate_accepts_valid_screenshot():
    data = _script_with_card({"screenshot": {"query": "GitHub OpenAI Codex"}})
    s = script._validate(data, CFG)
    assert s.cards[3].screenshot.query == "GitHub OpenAI Codex"

def test_build_prompt_mentions_chart_and_screenshot():
    sysp, _ = script.build_prompt(_cand(), _post(), VOICE, CFG)
    assert "chart" in sysp and "screenshot" in sysp
```

Check the top of `tests/video/test_script.py` already imports `pytest`, `VideoScriptError`, `CFG`, `_cand`, `_post`, `VOICE`, `script` — these all already exist in the file (confirmed by the existing tests using them); no new imports needed for the tests above.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_script.py -k "chart or screenshot" -v`
Expected: FAIL — `test_validate_rejects_card_with_both_num_and_chart` etc. fail because `_validate` doesn't check this yet; `test_build_prompt_mentions_chart_and_screenshot` fails because the prompt doesn't mention them yet.

- [ ] **Step 3: Implement the prompt text and validation**

In `src/pipeline/video/script.py`, in `build_prompt`, find this line (part of the existing system prompt build-up):

```python
        "phải nói thẳng điều này ảnh hưởng gì tới người xem (vd: người làm sản phẩm AI, "
        "người dùng công nghệ) thay vì chỉ chốt bằng câu hỏi mơ hồ."
    )
```

Add immediately after it, still inside the `system = (...)` parenthesized string (i.e. insert a new string segment before the closing `)`):

```python
        "phải nói thẳng điều này ảnh hưởng gì tới người xem (vd: người làm sản phẩm AI, "
        "người dùng công nghệ) thay vì chỉ chốt bằng câu hỏi mơ hồ. "
        "Một card có thể thêm 'chart' HOẶC 'screenshot' (không dùng chung với nhau hay với "
        "'num', tối đa một trong ba trên mỗi card, và cả hai đều KHÔNG bắt buộc): "
        "'chart': {kind:'line'|'bar'|'hbar', items:[...], unit?} — chỉ thêm khi có ít nhất "
        "2 số liệu THẬT đáng so sánh trong bài; kind='line' cần >=3 items dạng {value}, "
        "'bar' cần ĐÚNG 2 items dạng {label,value}, 'hbar' cần 2-4 items dạng {label,value}. "
        "'screenshot': {query} — chỉ thêm khi bài nhắc tới một sản phẩm/repo/trang web CỤ THỂ "
        "có thể tìm bằng Google (vd query='GitHub OpenAI Codex'), query tối đa 100 ký tự. "
        "Không bắt buộc mỗi kịch bản phải có chart hay screenshot."
    )
```

Then, in `_validate(data, cfg)`, find:

```python
    try:
        s = Script.from_dict(data)
    except (KeyError, TypeError) as e:
        raise VideoScriptError(f"bad card/section fields: {e}") from e
    if s.sections[0].card_start != 0:
```

Insert new validation right after the `try/except` block and before `if s.sections[0].card_start != 0:`:

```python
    _CHART_ITEM_BOUNDS = {"line": (3, None), "bar": (2, 2), "hbar": (2, 4)}
    for i, c in enumerate(s.cards):
        set_fields = [name for name, val in (("num", c.num), ("chart", c.chart),
                                             ("screenshot", c.screenshot)) if val is not None]
        if len(set_fields) > 1:
            raise VideoScriptError(f"card {i}: chỉ được set 1 trong num/chart/screenshot, có {set_fields}")
        if c.chart is not None:
            if c.chart.kind not in _CHART_ITEM_BOUNDS:
                raise VideoScriptError(f"card {i}: chart.kind {c.chart.kind!r} không hợp lệ")
            lo, hi = _CHART_ITEM_BOUNDS[c.chart.kind]
            n_items = len(c.chart.items)
            if n_items < lo or (hi is not None and n_items > hi):
                raise VideoScriptError(
                    f"card {i}: chart '{c.chart.kind}' có {n_items} items, cần {lo}..{hi or 'nhiều hơn'}")
            for item in c.chart.items:
                if not isinstance(item.get("value"), (int, float)):
                    raise VideoScriptError(f"card {i}: chart item thiếu 'value' dạng số: {item}")
        if c.screenshot is not None:
            q = c.screenshot.query
            if not isinstance(q, str) or not q.strip():
                raise VideoScriptError(f"card {i}: screenshot.query rỗng")
            if len(q) > 100:
                raise VideoScriptError(f"card {i}: screenshot.query dài {len(q)} > 100 ký tự")
```

(This block sits between the existing `Script.from_dict` try/except and the existing `sections[0].card_start` check — nothing else in `_validate` changes.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_script.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/script.py tests/video/test_script.py
git commit -m "feat(video): validate chart/screenshot card shapes, extend prompt"
```

---

### Task 4: `codegen.py` — serialize chart/screenshot into `variants.mjs`

**Files:**
- Modify: `src/pipeline/video/codegen.py`
- Modify: `tests/fixtures/video/expected_variants.mjs`
- Test: `tests/video/test_codegen.py`

**Interfaces:**
- Consumes: `Card.chart`, `Card.screenshot_file` from Task 1. **Not** `Card.screenshot` (the LLM's search-query spec) — only the render-time-resolved `screenshot_file` path gets serialized; `codegen.write` is called from `render.py` only after Task 10's capture-or-fallback step has already run.
- Produces: `render_variants_mjs(s)` output rows are now `[variant, anchor, num, motion_in, motion_out, chart, screenshot_file]` (7 positions instead of 5) — `chart` is `null` or a JSON object literal, `screenshot_file` is `null` or a quoted string.

- [ ] **Step 1: Update the golden fixture and write the new failing test**

Update `tests/fixtures/video/expected_variants.mjs` to add the 2 new trailing `null` positions to every existing row (the fixture's `norm_script.json` cards have no `chart`/`screenshot_file` set, so every row gets `null, null`):

```
// FILE TỰ SINH — đừng sửa tay. Nguồn: src/pipeline/video/codegen.py
export const LAYOUT = [
  ["stack", "mid", null, "rise", "up", null, null],
  ["strike", "top", null, "slideL", "up", null, null],
  ["numeral", "mid", 10, "wipe", "shrink", null, null],
  ["invert", "mid", null, "fall", "wipeOut", null, null],
];
```

Add to `tests/video/test_codegen.py` (this covers the actual chart/screenshot serialization the golden fixture above doesn't exercise):

```python
from pipeline.video.models import Card, ChartSpec, ScreenshotSpec, SectionMark, Script

def test_render_variants_mjs_includes_chart_and_screenshot_file():
    chart = ChartSpec(kind="bar", items=[{"label": "Astra", "value": 1.67},
                                         {"label": "Fable 5.1", "value": 3.76}], unit="$")
    c1 = Card(lines=["x"], variant="stack", anchor="mid", motion_in="rise", motion_out="up",
              chart=chart)
    c2 = Card(lines=["y"], variant="stack", anchor="mid", motion_in="fall", motion_out="up",
              screenshot=ScreenshotSpec(query="q"), screenshot_file="screenshots/1.png")
    s = Script(cards=[c1, c2], sections=[SectionMark("A", 0)])
    out = codegen.render_variants_mjs(s)
    assert '"kind": "bar"' in out
    assert '"label": "Astra"' in out
    assert '"screenshots/1.png"' in out
    assert out.count("null, null") == 0  # neither row should show both new slots as null
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_codegen.py -v`
Expected: FAIL — `test_variants_mjs_matches_golden` now fails (old code doesn't emit the trailing nulls); `test_render_variants_mjs_includes_chart_and_screenshot_file` fails with `AttributeError` or missing content.

- [ ] **Step 3: Implement**

In `src/pipeline/video/codegen.py`, replace `render_variants_mjs`:

```python
def render_variants_mjs(s: Script) -> str:
    lines = [_HEADER, "export const LAYOUT = [\n"]
    for c in s.cards:
        num = "null" if c.num is None else str(c.num)
        chart = "null" if c.chart is None else json.dumps(c.chart.to_dict(), ensure_ascii=False)
        shot = "null" if c.screenshot_file is None else _q(c.screenshot_file)
        lines.append(
            f"  [{_q(c.variant)}, {_q(c.anchor)}, {num}, "
            f"{_q(c.motion_in)}, {_q(c.motion_out)}, {chart}, {shot}],\n"
        )
    lines.append("];\n")
    return "".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_codegen.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/codegen.py tests/fixtures/video/expected_variants.mjs tests/video/test_codegen.py
git commit -m "feat(video): serialize chart/screenshot_file into variants.mjs"
```

---

### Task 5: `align.mjs` — thread chart/screenshotFile into `timeline.json`

**Files:**
- Modify: `video/tools/align.mjs`
- Test: `tests/video/test_remotion_project.py`

**Interfaces:**
- Consumes: the 7-element `LAYOUT[i]` rows from Task 4.
- Produces: each card object in `timeline.json` now carries `chart` (the parsed object, or absent) and `screenshotFile` (string, or absent) alongside the existing `variant`/`anchor`/`motion`/`exit`/`num`.

- [ ] **Step 1: Write the failing test**

Add to `tests/video/test_remotion_project.py`:

```python
def test_align_mjs_threads_chart_and_screenshot_file():
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "c.chart = ch" in src
    assert "c.screenshotFile = sf" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -k align_mjs_threads -v`
Expected: FAIL — the strings aren't in the file yet.

- [ ] **Step 3: Implement**

In `video/tools/align.mjs`, find:

```js
cards.forEach((c) => { c.section = sectionFor(c.index); const [v, a, n, mi, mo] = LAYOUT[c.index]; c.variant = v; c.anchor = a; c.motion = mi; c.exit = mo; if (n) c.num = n; });
```

Replace with:

```js
cards.forEach((c) => { c.section = sectionFor(c.index); const [v, a, n, mi, mo, ch, sf] = LAYOUT[c.index]; c.variant = v; c.anchor = a; c.motion = mi; c.exit = mo; if (n) c.num = n; if (ch) c.chart = ch; if (sf) c.screenshotFile = sf; });
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -v`
Expected: all PASS

Run (if Node is available locally): `.venv/Scripts/python.exe -m pytest tests/video -m needs_node -v`
Expected: `test_align_mjs_syntax_ok` still PASSES (the edit is still valid JS)

- [ ] **Step 5: Commit**

```bash
git add video/tools/align.mjs tests/video/test_remotion_project.py
git commit -m "feat(video): thread chart/screenshotFile from variants.mjs into timeline.json"
```

---

### Task 6: `palette.ts` — add the accent color

**Files:**
- Modify: `video/src/palette.ts`

**Interfaces:**
- Produces: `Pal.accent: string`, set to `'#FF4D2E'` in both `LIGHT` and `DARK`.

There is no JS/TS unit-test runner in this project for plain `.ts` files (only Python-side string/`node --check` assertions on generated `.mjs`, and `test_remotion_project.py`-style content checks) — verify this task with a content-check test instead, consistent with `test_two_segment_background`'s pattern in the same file.

**Files (add):**
- Test: `tests/video/test_remotion_project.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/video/test_remotion_project.py`:

```python
def test_palette_has_accent_color():
    src = (VIDEO / "src/palette.ts").read_text(encoding="utf-8")
    assert src.count("#FF4D2E") == 2  # once in LIGHT, once in DARK
    assert "accent: string;" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -k accent_color -v`
Expected: FAIL

- [ ] **Step 3: Implement**

In `video/src/palette.ts`, add `accent: string;` to the `Pal` type (right after `dark: boolean;`):

```ts
export type Pal = {
  dark: boolean;
  accent: string;   // màu nhấn thương hiệu, giống nhau ở cả 2 theme
  ink: string;      // chữ chính
  ink2: string;     // chữ phụ
  gray: string;     // dòng accent
  panel: string;    // nền tấm card "invert"
  panelInk: string; // chữ trên tấm invert
  boxInk: string;   // viền + chấm khung chọn
  boxRim: string;   // viền ngoài chấm (tương phản ngược)
  scrim: string;    // lớp phủ đảm bảo chữ đọc được trên video
  shadow: string;   // đổ bóng chữ
};
```

Add `accent: '#FF4D2E',` as the first field in both `LIGHT` and `DARK`:

```ts
export const LIGHT: Pal = {
  dark: false,
  accent: '#FF4D2E',
  ink: '#0B0B0B',
  ...
```

```ts
export const DARK: Pal = {
  dark: true,
  accent: '#FF4D2E',
  ink: '#FFFFFF',
  ...
```

(Leave every other field in both objects exactly as-is.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add video/src/palette.ts tests/video/test_remotion_project.py
git commit -m "feat(video): add brand accent color to the palette"
```

---

### Task 7: `layouts.tsx` — retint Stack/Strike/Stair accent lines, redesign Numeral's badge, export `Frame`

**Files:**
- Modify: `video/src/layouts.tsx`
- Test: `tests/video/test_remotion_project.py`

**Interfaces:**
- Consumes: `Pal.accent` from Task 6.
- Produces: `Frame` becomes `export const Frame` (was previously unexported, needed by Task 11/12's new components). `Card` type gains `chart?: import('./Chart').ChartSpec` and `screenshotFile?: string` (Task 11 defines and exports `ChartSpec` from `Chart.tsx`; this task only adds the two optional properties to the `Card` type using that import — Task 11 must land before this type-checks, but since there is no TS build step in the test suite, this ordering does not block tests. If executing tasks strictly in order, add the two properties as `chart?: any; screenshotFile?: string;` here and Task 11 is free to leave them as `any` too, since the runtime behavior is what the plan tests, not TS strictness.)

- [ ] **Step 1: Write the failing tests**

Add to `tests/video/test_remotion_project.py`:

```python
def test_layouts_export_frame():
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "export const Frame" in src

def test_layouts_stack_accent_uses_brand_color():
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "role === 'accent' ? pal.accent" in src

def test_layouts_numeral_badge_uses_accent_border():
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "border: `4px solid ${pal.accent}`" in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -k "frame or accent or numeral_badge" -v`
Expected: FAIL

- [ ] **Step 3: Implement**

In `video/src/layouts.tsx`:

**(a)** Export `Frame` — change:

```tsx
const Frame: React.FC<{ card: Card; align: 'flex-start' | 'center' | 'flex-end'; children: React.ReactNode }> = ({ card, align, children }) => {
```

to:

```tsx
export const Frame: React.FC<{ card: Card; align: 'flex-start' | 'center' | 'flex-end'; children: React.ReactNode }> = ({ card, align, children }) => {
```

**(b)** Add the two optional properties to the `Card` type — change:

```tsx
export type Card = {
  index: number; lines: Line[]; start: number; end: number; out: number; section: string;
  variant: string; anchor: 'top' | 'mid' | 'low'; num?: number; motion: Motion; exit: Exit;
};
```

to:

```tsx
export type Card = {
  index: number; lines: Line[]; start: number; end: number; out: number; section: string;
  variant: string; anchor: 'top' | 'mid' | 'low'; num?: number; motion: Motion; exit: Exit;
  chart?: { kind: 'line' | 'bar' | 'hbar'; items: { label?: string; value: number }[]; unit?: string };
  screenshotFile?: string;
};
```

**(c)** Retint `Stack`'s accent role — change:

```tsx
        const role = i === n - 1 ? 'accent' : n === 3 && i === 0 ? 'small' : 'big';
        const w = T.WEIGHT[role];
        const size = fit(l.text, ff, w, T.SIZE[role]);
        const a = useMotion(frame, fps, Math.max(l.start, card.start), leaving, T.EXIT, card.motion, card.exit);
        const color = role === 'accent' ? (n === 1 ? pal.ink : pal.gray) : role === 'small' ? pal.ink2 : pal.ink;
        return (
          <div key={i} style={{
            position: 'relative', display: 'inline-block', margin: '9px 0', opacity: a.opacity,
            transform: a.transform, filter: a.filter, clipPath: a.clipPath,
            transformOrigin: mirror ? 'right center' : 'left center',
          }}>
            <span style={{
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.04, color,
              letterSpacing: a.letterSpacing ?? '-0.02em', display: 'block', whiteSpace: 'pre', textShadow: pal.shadow,
            }}>{l.text}</span>
```

to:

```tsx
        const role = i === n - 1 ? 'accent' : n === 3 && i === 0 ? 'small' : 'big';
        const w = T.WEIGHT[role];
        const size = fit(l.text, ff, w, T.SIZE[role]);
        const a = useMotion(frame, fps, Math.max(l.start, card.start), leaving, T.EXIT, card.motion, card.exit);
        const color = role === 'accent' ? pal.accent : role === 'small' ? pal.ink2 : pal.ink;
        return (
          <div key={i} style={{
            position: 'relative', display: 'inline-block', margin: '9px 0', opacity: a.opacity,
            transform: a.transform, filter: a.filter, clipPath: a.clipPath,
            transformOrigin: mirror ? 'right center' : 'left center',
          }}>
            <span style={{
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.04, color,
              letterSpacing: a.letterSpacing ?? '-0.02em', display: 'block', whiteSpace: 'pre', textShadow: pal.shadow,
              textTransform: role === 'accent' ? 'uppercase' : 'none',
            }}>{l.text}</span>
```

**(d)** Retint `Stair`'s final line — in the `Stair` component, change:

```tsx
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.05, color: i === n - 1 ? pal.ink : pal.gray,
```

to (this line appears once, inside `Stair`):

```tsx
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.05, color: i === n - 1 ? pal.accent : pal.gray,
```

**(e)** Retint `Strike`'s final line — in the `Strike` component, change:

```tsx
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.05, color: i === n - 1 ? pal.ink : pal.gray,
```

to (this is the same literal text as in Stair but in a different component/function — make this edit in `Strike`, not `Stair`; both components have this exact line, so search for it within each function body separately):

```tsx
              fontFamily: ff, fontWeight: w, fontSize: size, lineHeight: 1.05, color: i === n - 1 ? pal.accent : pal.gray,
```

**(f)** Redesign `Numeral`'s badge — change:

```tsx
      <div style={{
        width: 168, height: 168, background: pal.ink, borderRadius: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 30, opacity: b.opacity, transform: `${b.transform} rotate(${spin}deg)`, filter: b.filter,
      }}>
        <span style={{ fontFamily: ff, fontWeight: '900', fontSize: 104, color: pal.dark ? '#0A0A0A' : '#FFFFFF', lineHeight: 1 }}>{card.num}</span>
      </div>
```

to:

```tsx
      <div style={{
        width: 168, height: 168, background: 'rgba(0,0,0,0.35)', border: `4px solid ${pal.accent}`, borderRadius: 22,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 30, opacity: b.opacity, transform: `${b.transform} rotate(${spin}deg)`, filter: b.filter,
      }}>
        <span style={{ fontFamily: ff, fontWeight: '900', fontSize: 104, color: pal.accent, lineHeight: 1 }}>{card.num}</span>
      </div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add video/src/layouts.tsx tests/video/test_remotion_project.py
git commit -m "feat(video): accent-color restyle for Stack/Stair/Strike/Numeral"
```

---

### Task 8: `media.py` — expose the Playwright capture primitive for reuse

**Files:**
- Modify: `src/pipeline/media.py`
- Test: `tests/test_media.py` (check this file exists first: `ls tests/test_media.py`; if it doesn't exist, add the two tests below as a new file with that name and `from pipeline import media` at the top)

**Interfaces:**
- Produces: `media.capture_screenshot(url: str, dest: Path) -> None` (renamed from the private `_shoot`, same behavior: Playwright chromium, 1280x800 viewport, `networkidle` wait with a 3s-timeout graceful fallback, screenshots to `dest`). `media.screenshot(url, dest)` (the existing public JPEG-cropping wrapper used by the article pipeline) calls `capture_screenshot` internally — its own behavior and signature are unchanged.

- [ ] **Step 1: Write the failing test**

First check whether `tests/test_media.py` already exists and what it covers:

Run: `ls tests/test_media.py 2>&1 || echo "no file"`

If it exists, add this test to it (keeping existing tests untouched); if not, create it with this content:

```python
from pathlib import Path
from pipeline import media

def test_capture_screenshot_is_public_and_used_by_screenshot(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(media, "capture_screenshot",
                        lambda url, dest: (calls.append((url, dest)), Path(dest).write_bytes(b"\x89PNG"))[-1])
    # media.screenshot() crops+re-saves as JPEG via PIL -- write real PNG bytes a decoder accepts
    from PIL import Image
    def fake_capture(url, dest):
        calls.append((url, dest))
        Image.new("RGB", (100, 100), "white").save(dest, format="PNG")
    monkeypatch.setattr(media, "capture_screenshot", fake_capture)
    out = media.screenshot("https://example.com", tmp_path / "shot.jpg")
    assert out is not None
    assert calls[0][0] == "https://example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_media.py -k capture_screenshot -v`
Expected: FAIL with `AttributeError: module 'pipeline.media' has no attribute 'capture_screenshot'`

- [ ] **Step 3: Implement — rename `_shoot` to `capture_screenshot`, update the one call site**

In `src/pipeline/media.py`, change:

```python
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
```

to:

```python
def capture_screenshot(url: str, dest: Path) -> None:
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
```

Then in `screenshot()`, change the one call site:

```python
def screenshot(url: str, dest: Path) -> Path | None:
    tmp = dest.with_suffix(".png")
    try:
        _shoot(url, tmp)
```

to:

```python
def screenshot(url: str, dest: Path) -> Path | None:
    tmp = dest.with_suffix(".png")
    try:
        capture_screenshot(url, tmp)
```

`tests/test_media.py` already has two existing tests that monkeypatch the old name directly — these must be updated in this same commit or they will break. In `test_build_media_orders_and_flags`, change:

```python
    monkeypatch.setattr(media, "_shoot", lambda url, dest: Image.new("RGB", (1280, 800)).save(dest))
```

to:

```python
    monkeypatch.setattr(media, "capture_screenshot", lambda url, dest: Image.new("RGB", (1280, 800)).save(dest))
```

In `test_build_media_low_flag_when_few`, change:

```python
    monkeypatch.setattr(media, "_shoot",
                        lambda url, dest: (_ for _ in ()).throw(RuntimeError("x")))
```

to:

```python
    monkeypatch.setattr(media, "capture_screenshot",
                        lambda url, dest: (_ for _ in ()).throw(RuntimeError("x")))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_media.py -v`
Expected: all PASS (7 tests: the 6 pre-existing — 2 of them internally updated to the new name, not removed — plus the 1 new `test_capture_screenshot_is_public_and_used_by_screenshot`)

Run: `grep -rn "_shoot" tests/ src/` and confirm it now returns **zero** matches (both the definition and every call site were renamed).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/media.py tests/test_media.py
git commit -m "refactor(media): expose capture_screenshot for reuse by the video pipeline"
```

---

### Task 9: `src/pipeline/video/screenshot.py` — Google Custom Search + capture

**Files:**
- Create: `src/pipeline/video/screenshot.py`
- Test: `tests/video/test_screenshot.py`

**Interfaces:**
- Consumes: `media.capture_screenshot(url, dest)` from Task 8.
- Produces: `class ScreenshotError(Exception)`. `search_top_url(query: str, *, api_key: str, cx: str, timeout: int = 10) -> str`. `search_and_capture(query: str, out_path: Path, *, api_key: str, cx: str) -> str` (returns the resolved URL).

- [ ] **Step 1: Write the failing tests**

Create `tests/video/test_screenshot.py`:

```python
import httpx
import pytest
from pipeline.video import screenshot as sc


def test_search_top_url_returns_first_result(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert params["q"] == "GitHub OpenAI Codex"
        assert params["key"] == "K" and params["cx"] == "CX"
        return httpx.Response(200, json={"items": [{"link": "https://github.com/openai/codex"},
                                                    {"link": "https://example.com/other"}]},
                              request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", fake_get)
    url = sc.search_top_url("GitHub OpenAI Codex", api_key="K", cx="CX")
    assert url == "https://github.com/openai/codex"


def test_search_top_url_raises_on_no_results(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"items": []}, request=httpx.Request("GET", "https://x")))
    with pytest.raises(sc.ScreenshotError, match="no results"):
        sc.search_top_url("truly nonexistent query", api_key="K", cx="CX")


def test_search_top_url_raises_on_http_error(monkeypatch):
    def fake_get(*a, **k):
        return httpx.Response(403, json={"error": "quota"}, request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(sc.ScreenshotError):
        sc.search_top_url("q", api_key="K", cx="CX")


def test_search_and_capture_calls_search_then_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "search_top_url", lambda q, *, api_key, cx, timeout=10: "https://found.example")
    captured = {}
    monkeypatch.setattr(sc._media, "capture_screenshot",
                        lambda url, dest: captured.update(url=url, dest=dest))
    out_path = tmp_path / "shot.png"
    url = sc.search_and_capture("q", out_path, api_key="K", cx="CX")
    assert url == "https://found.example"
    assert captured == {"url": "https://found.example", "dest": out_path}


def test_search_and_capture_propagates_capture_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "search_top_url", lambda q, *, api_key, cx, timeout=10: "https://found.example")
    def boom(url, dest):
        raise RuntimeError("playwright timeout")
    monkeypatch.setattr(sc._media, "capture_screenshot", boom)
    with pytest.raises(sc.ScreenshotError, match="playwright timeout"):
        sc.search_and_capture("q", tmp_path / "shot.png", api_key="K", cx="CX")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_screenshot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.video.screenshot'`

- [ ] **Step 3: Implement**

Create `src/pipeline/video/screenshot.py`:

```python
from __future__ import annotations
import logging
from pathlib import Path

import httpx

from .. import media as _media

log = logging.getLogger("video.screenshot")

_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class ScreenshotError(Exception):
    pass


def search_top_url(query: str, *, api_key: str, cx: str, timeout: int = 10) -> str:
    try:
        r = httpx.get(_ENDPOINT, params={"key": api_key, "cx": cx, "q": query}, timeout=timeout)
    except httpx.HTTPError as e:
        raise ScreenshotError(f"search request failed: {e}") from e
    if r.status_code != 200:
        raise ScreenshotError(f"search HTTP {r.status_code}: {r.text[:200]}")
    items = (r.json() or {}).get("items") or []
    if not items:
        raise ScreenshotError(f"no results for query: {query!r}")
    return items[0]["link"]


def search_and_capture(query: str, out_path: Path, *, api_key: str, cx: str) -> str:
    url = search_top_url(query, api_key=api_key, cx=cx)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _media.capture_screenshot(url, out_path)
    except Exception as e:  # noqa: BLE001 - any capture failure must degrade, never crash the render
        raise ScreenshotError(f"capture failed for {url}: {e}") from e
    return url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_screenshot.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/screenshot.py tests/video/test_screenshot.py
git commit -m "feat(video): add Google Custom Search + capture module"
```

---

### Task 10: `render.py` — capture screenshots before codegen, fall back on failure

**Files:**
- Modify: `src/pipeline/video/render.py`
- Test: `tests/video/test_render.py`

**Interfaces:**
- Consumes: `screenshot.search_and_capture`, `screenshot.ScreenshotError` from Task 9.
- Produces: `render_pending()` (signature unchanged) now, for each card with `card.screenshot is not None`, attempts capture and sets `card.screenshot_file`; on any failure (including missing `GOOGLE_CSE_API_KEY`/`GOOGLE_CSE_CX` env vars) sets `card.screenshot = None` instead and continues rendering.

- [ ] **Step 1: Write the failing tests**

Add to `tests/video/test_render.py` (near `test_render_pending_regenerates_script_and_renders` — reuse the existing `_seed`/`_mini_script_dict`/`_mock_pipeline`/`FakeTG` helpers already in the file):

```python
def _mini_script_with_screenshot(token="TOKZZZ"):
    d = _mini_script_dict(token)
    d["cards"][0]["screenshot"] = {"query": "GitHub OpenAI Codex"}
    return d


def test_render_pending_captures_screenshot_before_codegen(tmp_path, monkeypatch):
    ds = _seed(tmp_path, extra_status="audio_received",
              script=_mini_script_with_screenshot(), audio_file_id="V")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    (tmp_path / "video" / "tools" / "cards.mjs").write_text("//", encoding="utf-8")
    _mock_pipeline(monkeypatch)
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "K")
    monkeypatch.setenv("GOOGLE_CSE_CX", "CX")
    captured_calls = []
    def fake_search_and_capture(query, out_path, *, api_key, cx):
        captured_calls.append((query, out_path, api_key, cx))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x89PNG")
        return "https://github.com/openai/codex"
    monkeypatch.setattr(render._screenshot, "search_and_capture", fake_search_and_capture)
    seen_variants = {}
    inner_write = render._codegen.write
    def spy_write(s, video_dir):
        seen_variants["screenshot_file"] = s.cards[0].screenshot_file
        return inner_write(s, video_dir)
    monkeypatch.setattr(render._codegen, "write", spy_write)
    now = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    out = render.render_pending(ds, FakeTG(), tmp_path, now)
    assert out == ["rendered:2026-09-08:morning"]
    assert captured_calls[0][0] == "GitHub OpenAI Codex"
    assert seen_variants["screenshot_file"] is not None


def test_render_pending_falls_back_to_text_card_on_screenshot_failure(tmp_path, monkeypatch):
    ds = _seed(tmp_path, extra_status="audio_received",
              script=_mini_script_with_screenshot(), audio_file_id="V")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    (tmp_path / "video" / "tools" / "cards.mjs").write_text("//", encoding="utf-8")
    _mock_pipeline(monkeypatch)
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "K")
    monkeypatch.setenv("GOOGLE_CSE_CX", "CX")
    def boom(query, out_path, *, api_key, cx):
        raise render._screenshot.ScreenshotError("no results")
    monkeypatch.setattr(render._screenshot, "search_and_capture", boom)
    now = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    out = render.render_pending(ds, FakeTG(), tmp_path, now)
    # render must still succeed end to end -- the failed screenshot card degrades, nothing crashes
    assert out == ["rendered:2026-09-08:morning"]


def test_render_pending_screenshot_skipped_without_secrets(tmp_path, monkeypatch):
    ds = _seed(tmp_path, extra_status="audio_received",
              script=_mini_script_with_screenshot(), audio_file_id="V")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    (tmp_path / "video" / "tools" / "cards.mjs").write_text("//", encoding="utf-8")
    _mock_pipeline(monkeypatch)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)
    called = []
    monkeypatch.setattr(render._screenshot, "search_and_capture",
                        lambda *a, **k: called.append(1))
    now = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    out = render.render_pending(ds, FakeTG(), tmp_path, now)
    assert out == ["rendered:2026-09-08:morning"]
    assert called == []  # never even attempted a network call
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_render.py -k screenshot -v`
Expected: FAIL — `render` module has no `_screenshot` attribute yet.

- [ ] **Step 3: Implement**

In `src/pipeline/video/render.py`, the current top-of-file imports are:

```python
from __future__ import annotations
import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import AlignError
from . import align as _align
from ..publish import slot_unix
```

`os` is not yet imported. Replace this whole block with:

```python
from __future__ import annotations
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import AlignError
from . import align as _align
from . import screenshot as _screenshot
from ..publish import slot_unix
```

Then, inside `render_pending()`, find:

```python
            _codegen.write(Script.from_dict(v["script"]), video_dir)   # C1
```

Replace with:

```python
            s = Script.from_dict(v["script"])
            api_key, cx = os.environ.get("GOOGLE_CSE_API_KEY"), os.environ.get("GOOGLE_CSE_CX")
            for ci, card in enumerate(s.cards):
                if card.screenshot is None:
                    continue
                if not (api_key and cx):
                    card.screenshot = None
                    continue
                shot_path = video_dir / "public" / "screenshots" / f"{ci}.png"
                try:
                    _screenshot.search_and_capture(card.screenshot.query, shot_path,
                                                   api_key=api_key, cx=cx)
                    card.screenshot_file = f"screenshots/{ci}.png"
                except _screenshot.ScreenshotError as e:
                    log.warning("screenshot card %d failed (%s) -- falling back to text card", ci, e)
                    card.screenshot = None
            _codegen.write(s, video_dir)   # C1
```

Note this replaces `Script.from_dict(v["script"])` (previously inlined directly into the `_codegen.write(...)` call) with a named local `s` used both by the new screenshot loop and the `_codegen.write` call — this was the only call site using that inline expression (confirm with `grep -n "Script.from_dict(v\[.script.\])" src/pipeline/video/render.py` returning zero matches after this edit).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_render.py -v`
Expected: all PASS (including every pre-existing test in the file)

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/render.py tests/video/test_render.py
git commit -m "feat(video): capture screenshot cards at render time, fall back on failure"
```

---

### Task 11: `Chart.tsx` — line/bar/hbar chart component

**Files:**
- Create: `video/src/Chart.tsx`
- Modify: `video/src/KineticShort.tsx`
- Test: `tests/video/test_remotion_project.py`

**Interfaces:**
- Consumes: `Frame` (exported, Task 7), `usePal` (`palette.ts`), `useMotion` (`anim.ts`), `shown`/`P`/`Card` (`layouts.tsx`), `T` (`theme.ts`).
- Produces: `export const ChartCard: React.FC<P>` — a card renderer reading `card.chart` (set on `Card` in Task 7) and rendering an animated SVG line/bar/hbar chart plus the card's spoken lines as a caption underneath. Wired into `KineticShort.tsx`'s `CardView` switch as the branch taken whenever `card.chart` is present (checked before the existing `switch (card.variant)`, since chart cards can carry any `variant` string and must not fall through to a text layout).

- [ ] **Step 1: Write the failing tests**

Add to `tests/video/test_remotion_project.py`:

```python
def test_chart_tsx_exists_and_exports_chartcard():
    assert (VIDEO / "src/Chart.tsx").is_file()
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "export const ChartCard" in src
    assert "'line'" in src and "'bar'" in src and "'hbar'" in src

def test_kineticshort_renders_chart_before_variant_switch():
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "ChartCard" in src
    assert "card.chart" in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -k chart_tsx -v`
Expected: FAIL — `video/src/Chart.tsx` does not exist yet.

- [ ] **Step 3: Implement**

Create `video/src/Chart.tsx`:

```tsx
import React from 'react';
import { interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';
import { useMotion } from './anim';
import { Frame, shown, type P } from './layouts';
import { T } from './theme';

const W = 1080 - T.PAD * 2;

type ChartItem = { label?: string; value: number };

const LineChart: React.FC<{ items: ChartItem[]; unit: string; reveal: number; accent: string; ink: string }> = ({ items, unit, reveal, accent, ink }) => {
  const w = W, h = 420;
  const max = Math.max(...items.map((i) => i.value));
  const min = Math.min(0, ...items.map((i) => i.value));
  const span = max - min || 1;
  const pts = items.map((it, i) => {
    const x = (i / (items.length - 1)) * (w - 40) + 20;
    const y = h - 30 - ((it.value - min) / span) * (h - 60);
    return [x, y] as const;
  });
  const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <line x1={20} y1={h - 30} x2={w - 20} y2={h - 30} stroke={ink} strokeOpacity={0.35} strokeWidth={2} />
      <path d={path} fill="none" stroke={accent} strokeWidth={7}
           strokeDasharray={2000} strokeDashoffset={2000 - 2000 * reveal} />
      {reveal > 0.92 ? (
        <>
          <circle cx={last[0]} cy={last[1]} r={9} fill={accent} />
          <text x={last[0] - 10} y={last[1] - 20} fill={accent} fontWeight={900} fontSize={40} textAnchor="end">
            {items[items.length - 1].value}{unit}
          </text>
        </>
      ) : null}
    </svg>
  );
};

const BarChart: React.FC<{ items: ChartItem[]; unit: string; reveal: number; accent: string; ink: string }> = ({ items, unit, reveal, accent, ink }) => {
  const w = W, h = 420, barW = 220, gap = 90;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  const totalW = items.length * barW + (items.length - 1) * gap;
  const startX = (w - totalW) / 2;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {items.map((it, i) => {
        const bh = (it.value / max) * (h - 90) * reveal;
        const x = startX + i * (barW + gap);
        const y = h - 40 - bh;
        const isAccent = i === items.length - 1;
        const color = isAccent ? accent : ink;
        return (
          <g key={i}>
            <rect x={x} y={y} width={barW} height={bh} rx={14} fill={color} fillOpacity={isAccent ? 1 : 0.4} />
            <text x={x + barW / 2} y={y - 18} fill={color} fontWeight={900} fontSize={40} textAnchor="middle">
              {it.value}{unit}
            </text>
            {it.label ? (
              <text x={x + barW / 2} y={h - 12} fill={ink} fontWeight={700} fontSize={26} textAnchor="middle" opacity={0.8}>
                {it.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
};

const HBarChart: React.FC<{ items: ChartItem[]; unit: string; reveal: number; accent: string; ink: string }> = ({ items, unit, reveal, accent, ink }) => {
  const w = W, rowH = 96;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  return (
    <svg width={w} height={items.length * rowH} viewBox={`0 0 ${w} ${items.length * rowH}`}>
      {items.map((it, i) => {
        const fillW = (it.value / max) * w * reveal;
        const y = i * rowH;
        const isAccent = i === 0;
        const color = isAccent ? accent : ink;
        return (
          <g key={i}>
            <text x={0} y={y + 22} fill={ink} fontWeight={700} fontSize={28}>{it.label ?? ''}</text>
            <rect x={0} y={y + 32} width={w} height={36} rx={10} fill={ink} fillOpacity={0.15} />
            <rect x={0} y={y + 32} width={fillW} height={36} rx={10} fill={color} fillOpacity={isAccent ? 1 : 0.55} />
            <text x={Math.max(fillW - 10, 40)} y={y + 57} fill="#fff" fontWeight={900} fontSize={26} textAnchor="end">
              {it.value}{unit}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

export const ChartCard: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const chart = card.chart!;
  const a = useMotion(frame, fps, card.start, leaving, T.EXIT, card.motion, card.exit);
  const reveal = interpolate(frame, [card.start * fps + 6, card.start * fps + 36], [0, 1],
                             { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const unit = chart.unit ?? '';
  return (
    <Frame card={card} align="center">
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
                    opacity: a.opacity, transform: a.transform, filter: a.filter }}>
        {chart.kind === 'line' ? <LineChart items={chart.items} unit={unit} reveal={reveal} accent={pal.accent} ink={pal.ink} /> : null}
        {chart.kind === 'bar' ? <BarChart items={chart.items} unit={unit} reveal={reveal} accent={pal.accent} ink={pal.ink} /> : null}
        {chart.kind === 'hbar' ? <HBarChart items={chart.items} unit={unit} reveal={reveal} accent={pal.accent} ink={pal.ink} /> : null}
        {ls.map((l, i) => (
          <span key={i} style={{
            fontFamily: ff, fontWeight: '800', fontSize: 56, lineHeight: 1.2, color: pal.ink,
            textShadow: pal.shadow, marginTop: 20, textAlign: 'center', whiteSpace: 'pre-wrap',
            textTransform: 'uppercase',
          }}>{l.text}</span>
        ))}
      </div>
    </Frame>
  );
};
```

Then in `video/src/KineticShort.tsx`, add the import:

```tsx
import { BgVideo, palAt } from './BgVideo';
```

becomes (add one line after it):

```tsx
import { BgVideo, palAt } from './BgVideo';
import { ChartCard } from './Chart';
```

Then, in `CardView`, change:

```tsx
const CardView: React.FC<{ card: Card }> = ({ card }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const leaving = frame - (card.out * fps - T.EXIT);

  let activeIdx = 0;
  shown(card).forEach((l, i) => { if (t >= l.start - 0.02) activeIdx = i; });

  const p = { card, ff: fontFamily, leaving, activeIdx };
  switch (card.variant) {
```

to:

```tsx
const CardView: React.FC<{ card: Card }> = ({ card }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const leaving = frame - (card.out * fps - T.EXIT);

  let activeIdx = 0;
  shown(card).forEach((l, i) => { if (t >= l.start - 0.02) activeIdx = i; });

  const p = { card, ff: fontFamily, leaving, activeIdx };
  if (card.chart) return <ChartCard {...p} />;
  switch (card.variant) {
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add video/src/Chart.tsx video/src/KineticShort.tsx tests/video/test_remotion_project.py
git commit -m "feat(video): add ChartCard (line/bar/hbar) and wire into CardView"
```

---

### Task 12: `Screenshot.tsx` — browser-chrome-framed screenshot component

**Files:**
- Create: `video/src/Screenshot.tsx`
- Modify: `video/src/KineticShort.tsx`
- Test: `tests/video/test_remotion_project.py`

**Interfaces:**
- Consumes: `Frame`, `usePal`, `useMotion`, `shown`/`P` (same as Task 11), plus `staticFile`, `Img` from `remotion`.
- Produces: `export const ScreenshotCard: React.FC<P>` — renders `card.screenshotFile` (set by Task 5's `align.mjs` change, sourced from Task 10's render-time capture) inside a browser-chrome frame (3 dots + URL bar showing the resolved domain) with the card's spoken lines as a caption. Wired into `KineticShort.tsx`'s `CardView` alongside `ChartCard`, checked before the `switch (card.variant)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/video/test_remotion_project.py`:

```python
def test_screenshot_tsx_exists_and_exports_screenshotcard():
    assert (VIDEO / "src/Screenshot.tsx").is_file()
    src = (VIDEO / "src/Screenshot.tsx").read_text(encoding="utf-8")
    assert "export const ScreenshotCard" in src
    assert "staticFile" in src

def test_kineticshort_renders_screenshot_before_variant_switch():
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "ScreenshotCard" in src
    assert "card.screenshotFile" in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -k screenshot_tsx -v`
Expected: FAIL — `video/src/Screenshot.tsx` does not exist yet.

- [ ] **Step 3: Implement**

Create `video/src/Screenshot.tsx`:

```tsx
import React from 'react';
import { Img, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { usePal } from './palette';
import { useMotion } from './anim';
import { Frame, shown, type P } from './layouts';
import { T } from './theme';

const FRAME_W = 1080 - T.PAD * 2;

export const ScreenshotCard: React.FC<P> = ({ card, ff, leaving }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pal = usePal();
  const ls = shown(card);
  const a = useMotion(frame, fps, card.start, leaving, T.EXIT, card.motion, card.exit);
  return (
    <Frame card={card} align="center">
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
                    opacity: a.opacity, transform: a.transform, filter: a.filter }}>
        <div style={{ width: FRAME_W, borderRadius: 14, overflow: 'hidden',
                      boxShadow: '0 20px 60px rgba(0,0,0,0.5)', background: '#fff' }}>
          <div style={{ background: '#e8e8e8', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#ff5f57' }} />
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#febc2e' }} />
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#28c840' }} />
          </div>
          <Img src={staticFile(card.screenshotFile!)}
               style={{ width: '100%', display: 'block' }} />
        </div>
        {ls.map((l, i) => (
          <span key={i} style={{
            fontFamily: ff, fontWeight: '800', fontSize: 52, lineHeight: 1.2, color: pal.ink,
            textShadow: pal.shadow, marginTop: 24, textAlign: 'center', whiteSpace: 'pre-wrap',
            textTransform: 'uppercase',
          }}>{l.text}</span>
        ))}
      </div>
    </Frame>
  );
};
```

Then in `video/src/KineticShort.tsx`, add the import next to `ChartCard`'s:

```tsx
import { ChartCard } from './Chart';
```

becomes:

```tsx
import { ChartCard } from './Chart';
import { ScreenshotCard } from './Screenshot';
```

Then, in `CardView`, change:

```tsx
  if (card.chart) return <ChartCard {...p} />;
  switch (card.variant) {
```

to:

```tsx
  if (card.chart) return <ChartCard {...p} />;
  if (card.screenshotFile) return <ScreenshotCard {...p} />;
  switch (card.variant) {
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add video/src/Screenshot.tsx video/src/KineticShort.tsx tests/video/test_remotion_project.py
git commit -m "feat(video): add ScreenshotCard and wire into CardView"
```

---

### Task 13: `video-render.yml` — Playwright install step + new secrets

**Files:**
- Modify: `.github/workflows/video-render.yml`

**Interfaces:**
- Produces: the `render` job installs Chromium via Playwright whenever there is pending work (reusing the existing `steps.g.outputs.go == '1'` gate already used for the Node/Remotion install steps), and the "Render + publish" step's `env:` block carries `GOOGLE_CSE_API_KEY`/`GOOGLE_CSE_CX`.

No automated test covers workflow YAML content in this repo (confirmed: `grep -rn "video-render.yml" tests/` returns nothing) — verify this task by re-reading the file after editing and confirming it still parses as valid YAML (Step 4 below).

- [ ] **Step 1–2: N/A (no test-first cycle for YAML in this repo — go straight to implementation, per the existing pattern for every other workflow file in this session's history)**

- [ ] **Step 3: Implement**

In `.github/workflows/video-render.yml`, find:

```yaml
      - name: Video render deps
        if: steps.g.outputs.go == '1'
        run: |
          cd video && npm ci
          npx remotion browser ensure
      - name: Install deps
        if: steps.g.outputs.go == '1'
        run: |
          pip install -r requirements.txt
          pip install -e .
```

Replace with:

```yaml
      - name: Video render deps
        if: steps.g.outputs.go == '1'
        run: |
          cd video && npm ci
          npx remotion browser ensure
      - name: Install deps
        if: steps.g.outputs.go == '1'
        run: |
          pip install -r requirements.txt
          pip install -e .
          python -m playwright install --with-deps chromium
```

Then find:

```yaml
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          YOUTUBE_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
```

Replace with:

```yaml
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GOOGLE_CSE_API_KEY: ${{ secrets.GOOGLE_CSE_API_KEY }}
          GOOGLE_CSE_CX: ${{ secrets.GOOGLE_CSE_CX }}
          YOUTUBE_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
```

- [ ] **Step 4: Verify the YAML still parses**

Run: `.venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/video-render.yml', encoding='utf-8')); print('ok')"`
Expected: prints `ok`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/video-render.yml
git commit -m "chore(workflows): install Playwright and add CSE secrets to video-render"
```

---

### Task 14: Smoke fixture — exercise both new card types end to end

**Files:**
- Modify: `src/pipeline/video/build_video.py`
- Create: `video/public/smoke-screenshot.png`
- Test: `tests/video/test_build_video.py`

**Interfaces:**
- Produces: `_FAKE_SCRIPT_JSON` now includes one card with a `chart` and one card with a pre-set `screenshot_file` (bypassing live network capture, since `build_video.py`'s `build()` never calls `screenshot.search_and_capture` — that logic lives only in `render.py`'s production path from Task 10). `video-smoke.yml`'s existing `--render-smoke` CI step now exercises real `npx remotion render` on both `ChartCard` and `ScreenshotCard` with no network dependency.

- [ ] **Step 1: Create the placeholder image and write the failing test**

Create a tiny valid PNG at `video/public/smoke-screenshot.png`:

Run: `.venv/Scripts/python.exe -c "from PIL import Image; Image.new('RGB', (1280, 800), (240,240,240)).save('video/public/smoke-screenshot.png')"`

Add to `tests/video/test_build_video.py`:

```python
def test_fake_script_includes_chart_and_screenshot_cards():
    d = json.loads(build_video._FAKE_SCRIPT_JSON)
    chart_cards = [c for c in d["cards"] if c.get("chart")]
    shot_cards = [c for c in d["cards"] if c.get("screenshot_file")]
    assert len(chart_cards) == 1
    assert chart_cards[0]["chart"]["kind"] in {"line", "bar", "hbar"}
    assert len(shot_cards) == 1
    assert shot_cards[0]["screenshot_file"] == "smoke-screenshot.png"
```

(Add `import json` at the top of `tests/video/test_build_video.py` if not already present — check with `grep -n "^import json" tests/video/test_build_video.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_build_video.py -k chart_and_screenshot -v`
Expected: FAIL — no cards currently have `chart` or `screenshot_file`.

- [ ] **Step 3: Implement**

In `src/pipeline/video/build_video.py`, in `_FAKE_SCRIPT_JSON`, replace the two cards:

```python
        {"lines": ["Người biết dùng đúng cách", "mới thực sự bứt phá nhanh."],
         "variant": "stair", "anchor": "mid", "motion_in": "slam", "motion_out": "shrink"},
        {"lines": ["Vậy nên đừng chỉ tải về", "rồi để đó không đụng tới."],
         "variant": "right", "anchor": "low", "motion_in": "slideR", "motion_out": "dissolve"},
```

with:

```python
        {"lines": ["Chi phí giảm", "gần một nửa so với trước."],
         "variant": "stack", "anchor": "mid", "motion_in": "slam", "motion_out": "shrink",
         "chart": {"kind": "bar", "items": [{"label": "Trước", "value": 100},
                                            {"label": "Sau", "value": 55}], "unit": "$"}},
        {"lines": ["Đây là trang GitHub", "của dự án đang gây bão."],
         "variant": "right", "anchor": "low", "motion_in": "slideR", "motion_out": "dissolve",
         "screenshot_file": "smoke-screenshot.png"},
```

(Every other card in `_FAKE_SCRIPT_JSON` is unchanged; this replaces exactly the two cards shown above, keeping the total at 19 cards and ~166 words since both replacement cards have the same number of displayed words as the ones they replace.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_build_video.py -v`
Expected: all PASS

Run the full Python suite to confirm nothing else regressed: `.venv/Scripts/python.exe -m pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/build_video.py video/public/smoke-screenshot.png tests/video/test_build_video.py
git commit -m "test(video): exercise ChartCard and ScreenshotCard in the smoke fixture"
```

---

## Final Verification

After all 14 tasks:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: all tests pass (360+ pre-existing plus every new test added above).

If Node is available locally, also run:

```bash
.venv/Scripts/python.exe -m pytest -m needs_node -v
```

Expected: `test_node_check_passes`, `test_node_check_raises_on_garbage`, `test_align_mjs_syntax_ok` all pass — confirms the generated `.mjs` files and the edited `align.mjs` are still syntactically valid JavaScript after every change in this plan.

The full end-to-end proof (`npx remotion render` actually producing an MP4 with both new card types visible) only runs in CI via `video-smoke.yml` — trigger it manually (`workflow_dispatch`) after pushing and confirm it goes green, since that is the only environment with Node + a real Chromium install.
