# Phase 2A — Script + Voice + Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a story chosen by the Phase 1 pipeline, auto-generate the full Remotion input set (`cards.mjs`, `variants.mjs`, cloned-voice `voice.mp3`, `silence.txt`, `timeline.json`) for a ~40s vertical kinetic-typography video.

**Architecture:** Bring the existing Remotion project into `video/` in the Phase 1 repo. Add a Python sub-package `src/pipeline/video/` with focused modules: `models` (dataclasses) → `script` (LLM → Script) → `variants` (heuristic normaliser) → `codegen` (Script → ESM files) → `tts` (voice clone, backend chain) → `align` (ffmpeg silencedetect + existing `align.mjs`) → `build_video` (orchestrator). Wire an optional call into `run.build()` gated by `settings.video.enabled`.

**Tech Stack:** Python 3.12+ (`httpx`, `PyYAML`, existing `pipeline.llm`), `faster-whisper` (one-off sample transcription), `gradio_client` (HF Space fallback), Node 18+ / npm (existing Remotion project, `align.mjs`, `ffmpeg-static`). TTS engine chosen by Task 1 spike: GPT-SoVITS (MIT) primary, F5-TTS-Vietnamese fallback, HF Space last.

## Global Constraints

- Python **3.12+** (local dev on 3.14; CI pins 3.12). Node **>=18** for `video/`.
- **Zero recurring cost.** TTS runs CPU-only on the GitHub Actions runner; HF Space free tier only.
- All generated on-screen and spoken text is **100% Vietnamese**.
- Video: **1080×1920, 30fps, 35–45 seconds, 110–140 displayed Vietnamese words**. One file for Shorts/TikTok/Reels.
- Remotion composition id is **`CodexShort`** (from `video/src/Root.tsx`). Do not rename.
- `video/tools/cards.mjs` and `video/tools/variants.mjs` are **generated files, overwritten every run**. The existing hand-authored versions are backed up to `*.manual.bak` during Task 2.
- `video/tools/align.mjs` is **reused unchanged**. It reads `ref/silence.txt` + `tools/cards.mjs` + `tools/variants.mjs` (relative paths) and writes `src/timeline.json`; must run with `cwd=video/`. It takes `duration` seconds as `process.argv[2]`.
- Valid enums: variant `stack|right|hero|invert|mark|stair|numeral|strike`; anchor `top|mid|low`; motion_in `rise|fall|slideR|slideL|wipe|pop|slam`; motion_out `up|down|dissolve|shrink|wipeOut`.
- Line prefix `~` = spoken-but-hidden timing filler. Filler words ARE read by the TTS; they are NOT counted in the 110–140 displayed-word budget.
- `settings.video.enabled` defaults to **false** — Phase 1 behaviour is unchanged until 2A is done.
- Phase 1 tests must keep passing; every new dependency is imported lazily so `pytest` runs without the heavy TTS stack installed.
- New exceptions all subclass `pipeline.video.VideoError`: `VideoScriptError`, `CodegenError`, `TTSError`, `AlignError`.
- Interpreter for local runs: `C:\Users\Admin\AppData\Local\Programs\Python\Python314\python` (referred to as `python` below).

---

## File Structure

| File | Responsibility |
|---|---|
| `video/` (whole tree) | Existing Remotion project, moved in from `D:\video ahitofficial short` |
| `video/tools/cards.manual.bak`, `video/tools/variants.manual.bak` | Backup of hand-authored versions |
| `src/pipeline/video/__init__.py` | Sub-package marker; exports `VideoError` + subclasses |
| `src/pipeline/video/models.py` | `Card`, `SectionMark`, `Script` dataclasses + enum constants |
| `src/pipeline/video/script.py` | `build_prompt`, `generate` (LLM → `Script`, validate, one retry), `write_script_json` |
| `src/pipeline/video/variants.py` | `normalize(Script) -> Script` heuristic post-check (pure, idempotent) |
| `src/pipeline/video/codegen.py` | `render_cards_mjs`, `render_variants_mjs`, `write`, `node_check` |
| `src/pipeline/video/align.py` | `make_silence_txt`, `run_aligner`, `_ffmpeg_bin` |
| `src/pipeline/video/tts.py` | `ensure_sample_text`, `synthesize` (backend chain + `--fake`) |
| `src/pipeline/video/build_video.py` | `build` orchestrator, `main` CLI, `_load_story` |
| `scripts/tts_gptsovits.sh` | Spike-authored GPT-SoVITS zero-shot inference wrapper |
| `scripts/tts_f5.sh` | Spike-authored F5-TTS-VN inference wrapper |
| `.github/workflows/video-smoke.yml` | CI: `npm ci` + `build_video --fake --render-smoke` |
| `config/settings.yaml` | + `video:` block |
| `requirements.txt` | + `faster-whisper`, `gradio-client` |
| `docs/superpowers/notes/2026-09-03-tts-spike.md` | Task 1 spike result + decision |
| `tests/fixtures/video/*` | `raw_script.json`, `raw_script_short.json`, `norm_script.json`, `expected_cards.mjs`, `expected_variants.mjs`, `voice_fixture.wav`, `story.json`, `sample_ref.wav`, `sample_ref.txt` |
| `tests/video/test_*.py` | One test module per pipeline.video module |

---

## Task 1: Spike — GPT-SoVITS zero-shot on CPU (decision gate)

**Not a TDD task.** Produces a decision and a wrapper script, not tested code. Everything downstream uses the stable `tts.synthesize` interface regardless of outcome.

**Files:**
- Create: `docs/superpowers/notes/2026-09-03-tts-spike.md`
- Create: `scripts/tts_gptsovits.sh` (or `.py`), `scripts/tts_f5.sh`
- Maybe modify: `config/settings.yaml` default `tts_provider`

- [ ] **Step 1: Prepare a reference clip**

Use `assets/voice/sample.wav` if the user has supplied it. Otherwise record/borrow any 5–10 min single-speaker Vietnamese clip for the spike and note that it is a stand-in. Also create `assets/voice/sample.txt` with its transcript (or a 30–60s excerpt's transcript for zero-shot ref).

- [ ] **Step 2: Stand up GPT-SoVITS locally, CPU-only**

```bash
git clone https://github.com/RVC-Boss/GPT-SoVITS "$HOME/GPT-SoVITS"
cd "$HOME/GPT-SoVITS"
python -m pip install -r requirements.txt        # torch CPU wheel
# download pretrained models per repo README into GPT_SoVITS/pretrained_models/
```

Write `scripts/tts_gptsovits.sh` that runs its **zero-shot inference** entrypoint headless:
```bash
#!/usr/bin/env bash
# Args: REF_WAV REF_TEXT TARGET_TEXT OUT_WAV
set -euo pipefail
: "${GPTSOVITS_DIR:?set GPTSOVITS_DIR}"
cd "$GPTSOVITS_DIR"
python GPT_SoVITS/inference_cli.py \
  --ref_wav "$1" --ref_text "$2" --ref_lang vi \
  --target_text "$3" --target_lang vi \
  --out "$4"
```
(Adjust flag names to the repo's actual `inference_cli.py` / `api.py`. The point of the spike is to nail this command.)

- [ ] **Step 3: Synthesize a 40s Vietnamese sample and measure**

Feed ~120 words of Vietnamese tech-news style text. Record:
- wall-clock seconds for one synth (cold vs warm model),
- real-time factor (synth_seconds / audio_seconds),
- subjective quality vs the reference (1–5),
- model download size + whether it caches cleanly.

- [ ] **Step 4: Run the same test on `ubuntu-latest` semantics**

Either via `act`, or a throwaway branch + a temporary `workflow_dispatch` job that installs GPT-SoVITS and times one synth. Confirm it finishes inside ~30 min including model download with `actions/cache` warm.

- [ ] **Step 5: If GPT-SoVITS fails the bar, evaluate F5-TTS-Vietnamese**

```bash
pip install f5-tts
# checkpoint: huggingface hynt/F5-TTS-Vietnamese-ViVoice (or current best VN)
```
Write `scripts/tts_f5.sh` with the same 4-arg contract. Measure the same numbers.

- [ ] **Step 6: Record the decision**

`docs/superpowers/notes/2026-09-03-tts-spike.md`:
- table of measurements for each engine tried,
- **DECISION:** which engine is `tts_provider: auto`'s first backend,
- exact working command lines (copied into the `scripts/tts_*.sh`),
- any model env vars needed (`GPTSOVITS_DIR`, `F5TTS_CKPT`, `HF_SPACE_ID`).

- [ ] **Step 7: Set the default**

Edit `config/settings.yaml` `video.tts_provider` if the spike shows GPT-SoVITS is not the right default. Commit.

```bash
git add scripts/tts_gptsovits.sh scripts/tts_f5.sh docs/superpowers/notes/2026-09-03-tts-spike.md config/settings.yaml
git commit -m "spike: TTS engine evaluation on CPU + decision"
```

---

## Task 2: Move the Remotion project into `video/`

**Files:**
- Create: `video/**` (copied), `video/tools/cards.manual.bak`, `video/tools/variants.manual.bak`
- Modify: `.gitignore`
- Test: `tests/video/test_remotion_project.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a working Remotion project at `<repo>/video/` where `npm ci` succeeds and `node --check tools/align.mjs` passes. `video/src/Root.tsx` exposes composition `CodexShort`.

- [ ] **Step 1: Copy the project (exclude build/deps)**

```bash
cd "D:/Automation Social"
mkdir -p video
rsync -a --exclude node_modules --exclude out --exclude .remotion --exclude .git \
  "/d/video ahitofficial short/" video/
```
(Windows without rsync: `robocopy "D:\video ahitofficial short" "D:\Automation Social\video" /E /XD node_modules out .remotion .git`.)

- [ ] **Step 2: Back up the hand-authored generated files**

```bash
cd "D:/Automation Social/video/tools"
cp cards.mjs cards.manual.bak
cp variants.mjs variants.manual.bak
```

- [ ] **Step 3: Ignore build artefacts**

Append to `.gitignore`:
```
video/node_modules/
video/out/
video/.remotion/
data/voice_cache/
assets/voice/*.wav
```

- [ ] **Step 4: Write the failing test**

`tests/video/test_remotion_project.py`:
```python
import json, subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"

def test_project_present():
    assert (VIDEO / "package.json").is_file()
    assert (VIDEO / "src/Root.tsx").is_file()
    assert (VIDEO / "tools/align.mjs").is_file()
    assert (VIDEO / "tools/cards.manual.bak").is_file()
    assert (VIDEO / "tools/variants.manual.bak").is_file()

def test_composition_id_is_codexshort():
    assert "CodexShort" in (VIDEO / "src/Root.tsx").read_text(encoding="utf-8")

@pytest.mark.needs_node
def test_align_mjs_syntax_ok():
    r = subprocess.run(["node", "--check", "tools/align.mjs"], cwd=VIDEO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
```

Add to `pytest.ini`:
```ini
markers =
    needs_node: test requires Node.js on PATH
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/video/test_remotion_project.py -v`
Expected: `test_project_present`, `test_composition_id_is_codexshort` PASS; `test_align_mjs_syntax_ok` PASS if Node present.

- [ ] **Step 6: Verify npm install works (one-time, not in pytest)**

Run:
```bash
cd "D:/Automation Social/video" && npm ci && npx remotion versions
```
Expected: install completes, Remotion prints its version.

- [ ] **Step 7: Commit**

```bash
git add .gitignore video/ tests/video/test_remotion_project.py pytest.ini
git commit -m "chore: vendor Remotion kinetic-typography project into video/"
```

---

## Task 3: `pipeline.video.models`

**Files:**
- Create: `src/pipeline/video/__init__.py`, `src/pipeline/video/models.py`
- Test: `tests/video/__init__.py`, `tests/video/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `pipeline.video.VideoError`, `VideoScriptError`, `CodegenError`, `TTSError`, `AlignError` (all in `__init__.py`).
  - `models.VALID_VARIANTS`, `VALID_ANCHORS`, `VALID_MOTION_IN`, `VALID_MOTION_OUT` — `frozenset[str]`.
  - `models.Card(lines:list[str], variant:str, anchor:str, motion_in:str, motion_out:str, num:int|None=None)` with `spoken:str` (all lines, `~` stripped, space-joined) and `displayed_words:int` (words in non-`~` lines).
  - `models.SectionMark(label:str, card_start:int)`.
  - `models.Script(cards:list[Card], sections:list[SectionMark])` with `spoken_text:str` (`"\n".join(card.spoken)`), `word_count:int` (`sum(displayed_words)`), `to_dict()`, `from_dict(d)`.

- [ ] **Step 1: Write the failing test**

`tests/video/test_models.py`:
```python
import pytest
from pipeline.video.models import Card, SectionMark, Script

def _card(lines, **kw):
    kw.setdefault("variant", "stack"); kw.setdefault("anchor", "mid")
    kw.setdefault("motion_in", "rise"); kw.setdefault("motion_out", "up")
    return Card(lines=lines, **kw)

def test_card_spoken_includes_filler_without_tilde():
    c = _card(["Bây giờ", "~cái", "AI nghĩ hộ bạn"])
    assert c.spoken == "Bây giờ cái AI nghĩ hộ bạn"

def test_card_displayed_words_excludes_filler():
    c = _card(["Bây giờ muốn", "~cái", "AI nghĩ hộ bạn"])
    assert c.displayed_words == 2 + 4

def test_script_spoken_text_newline_between_cards():
    s = Script(cards=[_card(["một hai"]), _card(["ba bốn năm"])],
               sections=[SectionMark("MỞ", 0)])
    assert s.spoken_text == "một hai\nba bốn năm"
    assert s.word_count == 5

def test_script_roundtrip():
    s = Script(cards=[_card(["x y"], num=None), _card(["2000 lính"], variant="numeral", num=2000)],
               sections=[SectionMark("A", 0), SectionMark("B", 1)])
    assert Script.from_dict(s.to_dict()).to_dict() == s.to_dict()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/video/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.video'`.

- [ ] **Step 3: Implement `src/pipeline/video/__init__.py`**

```python
class VideoError(Exception):
    """Base for all Phase 2A video-stage failures."""

class VideoScriptError(VideoError):
    pass

class CodegenError(VideoError):
    pass

class TTSError(VideoError):
    pass

class AlignError(VideoError):
    pass
```

- [ ] **Step 4: Implement `src/pipeline/video/models.py`**

```python
from __future__ import annotations
import re
from dataclasses import dataclass, field

VALID_VARIANTS = frozenset({"stack", "right", "hero", "invert", "mark", "stair", "numeral", "strike"})
VALID_ANCHORS = frozenset({"top", "mid", "low"})
VALID_MOTION_IN = frozenset({"rise", "fall", "slideR", "slideL", "wipe", "pop", "slam"})
VALID_MOTION_OUT = frozenset({"up", "down", "dissolve", "shrink", "wipeOut"})

_WORD = re.compile(r"\S+")


def _strip_tilde(line: str) -> str:
    return line[1:] if line.startswith("~") else line


@dataclass
class Card:
    lines: list[str]
    variant: str
    anchor: str
    motion_in: str
    motion_out: str
    num: int | None = None

    @property
    def spoken(self) -> str:
        return " ".join(_strip_tilde(l).strip() for l in self.lines if _strip_tilde(l).strip())

    @property
    def displayed_words(self) -> int:
        return sum(len(_WORD.findall(l)) for l in self.lines if not l.startswith("~"))

    def to_dict(self) -> dict:
        return {"lines": list(self.lines), "variant": self.variant, "anchor": self.anchor,
                "motion_in": self.motion_in, "motion_out": self.motion_out, "num": self.num}

    @classmethod
    def from_dict(cls, d: dict) -> "Card":
        return cls(lines=list(d["lines"]), variant=d["variant"], anchor=d["anchor"],
                   motion_in=d["motion_in"], motion_out=d["motion_out"], num=d.get("num"))


@dataclass
class SectionMark:
    label: str
    card_start: int

    def to_dict(self) -> dict:
        return {"label": self.label, "card_start": self.card_start}

    @classmethod
    def from_dict(cls, d: dict) -> "SectionMark":
        return cls(label=d["label"], card_start=int(d["card_start"]))


@dataclass
class Script:
    cards: list[Card]
    sections: list[SectionMark]

    @property
    def spoken_text(self) -> str:
        return "\n".join(c.spoken for c in self.cards)

    @property
    def word_count(self) -> int:
        return sum(c.displayed_words for c in self.cards)

    def to_dict(self) -> dict:
        return {"cards": [c.to_dict() for c in self.cards],
                "sections": [s.to_dict() for s in self.sections]}

    @classmethod
    def from_dict(cls, d: dict) -> "Script":
        return cls(cards=[Card.from_dict(c) for c in d["cards"]],
                   sections=[SectionMark.from_dict(s) for s in d["sections"]])
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/video/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/video/__init__.py src/pipeline/video/models.py tests/video/
git commit -m "feat(video): Script/Card/SectionMark models and video error types"
```

---

## Task 4: `pipeline.video.script`

**Files:**
- Create: `src/pipeline/video/script.py`
- Create fixtures: `tests/fixtures/video/raw_script.json`, `tests/fixtures/video/raw_script_short.json`
- Test: `tests/video/test_script.py`

**Interfaces:**
- Consumes: `pipeline.models.Candidate`, `pipeline.models.PostContent`, `pipeline.llm.generate`, `pipeline.llm.parse_json_response`, `models.Script`.
- Produces:
  - `script.build_prompt(cand, post, voice:dict, cfg:dict) -> tuple[str,str]`.
  - `script.generate(cand, post, voice:dict, cfg:dict, llm=None) -> Script` — `llm` defaults to `pipeline.llm.generate`; validates schema + word band; on word-band miss, retries once with a corrective user message; raises `VideoScriptError`.
  - `script.write_script_json(s:Script, out_dir:Path) -> Path` — writes `<out_dir>/script.json`.

- [ ] **Step 1: Create fixtures**

`tests/fixtures/video/raw_script.json` — a valid LLM response, ~120 displayed words, 14 cards, 4 sections. Abridged shape (fill to ~120 words):
```json
{
  "sections": [
    {"label": "AI VIẾT HỘ BẠN", "card_start": 0},
    {"label": "CHUYỆN GÌ ĐANG XẢY RA", "card_start": 4},
    {"label": "CON SỐ", "card_start": 9},
    {"label": "SỰ THẬT", "card_start": 12}
  ],
  "cards": [
    {"lines": ["Hôm nay", "~thì", "AI lại vừa có một bước nhảy lớn."], "variant": "stack", "anchor": "mid", "motion_in": "rise", "motion_out": "up"},
    {"lines": ["Một mô hình mới", "vừa được công bố"], "variant": "stack", "anchor": "top", "motion_in": "fall", "motion_out": "down"},
    {"lines": ["nhanh gấp đôi", "~cái", "bản trước đó."], "variant": "right", "anchor": "low", "motion_in": "slideR", "motion_out": "dissolve"},
    {"lines": ["Chi phí thì", "giảm gần một nửa."], "variant": "mark", "anchor": "mid", "motion_in": "wipe", "motion_out": "up"},
    {"lines": ["Nghĩa là", "người bình thường"], "variant": "stack", "anchor": "mid", "motion_in": "slideL", "motion_out": "shrink"},
    {"lines": ["cũng chạy được", "những tác vụ", "trước đây rất tốn kém."], "variant": "stair", "anchor": "mid", "motion_in": "slam", "motion_out": "shrink"},
    {"lines": ["Các công ty lớn", "đã bắt đầu tích hợp nó."], "variant": "right", "anchor": "top", "motion_in": "slideR", "motion_out": "shrink"},
    {"lines": ["Còn bạn", "~thì", "vẫn đang làm thủ công."], "variant": "mark", "anchor": "mid", "motion_in": "fall", "motion_out": "wipeOut"},
    {"lines": ["Khoảng cách", "đang giãn ra từng ngày."], "variant": "stack", "anchor": "top", "motion_in": "rise", "motion_out": "down"},
    {"lines": ["Chỉ trong 6 tháng", "số lượt gọi API"], "variant": "stack", "anchor": "mid", "motion_in": "wipe", "motion_out": "up"},
    {"lines": ["đã tăng", "gấp 10 lần."], "variant": "numeral", "anchor": "mid", "motion_in": "slam", "motion_out": "shrink", "num": 10},
    {"lines": ["Ai bắt nhịp sớm", "sẽ đi trước rất xa."], "variant": "right", "anchor": "mid", "motion_in": "slideR", "motion_out": "shrink"},
    {"lines": ["Sự thật là", "công cụ đã có sẵn."], "variant": "invert", "anchor": "mid", "motion_in": "pop", "motion_out": "wipeOut"},
    {"lines": ["Chỉ là", "bạn đã bắt đầu chưa."], "variant": "invert", "anchor": "mid", "motion_in": "fall", "motion_out": "wipeOut"}
  ]
}
```

`tests/fixtures/video/raw_script_short.json` — same shape but only 3 cards, ~18 words (triggers the retry path).

- [ ] **Step 2: Write the failing test**

`tests/video/test_script.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.models import Candidate, PostContent
from pipeline.video import script, VideoScriptError
from pipeline.video.models import Script

FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"
CFG = {"target_seconds": 40, "words_min": 110, "words_max": 140}
VOICE = {"xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "giong": "thân thiện",
         "cam_ky": ["không giật tít sai"], "ten_kenh": "A Hít Official"}

def _cand():
    return Candidate(url="https://openai.com/x", title="OpenAI ra model mới",
                     source="rss:OpenAI Blog",
                     published_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                     summary="model mới", full_text="OpenAI ra model nhanh gấp đôi, rẻ hơn.")

def _post():
    return PostContent(angle="phan-tich", caption_fb="x", caption_ig="y", hashtags=["#AI"],
                       thumbnail_prompt="p", thumbnail_title="T", youtube_title="a",
                       youtube_desc="b", tiktok_caption="c",
                       source_url="https://openai.com/x", source_name="OpenAI Blog")

def test_build_prompt_carries_constraints():
    sysp, usr = script.build_prompt(_cand(), _post(), VOICE, CFG)
    assert "110" in sysp and "140" in sysp
    assert "A Hít Official" in sysp
    assert "OpenAI ra model nhanh gấp đôi" in usr

def test_generate_parses_valid_response():
    raw = (FX / "raw_script.json").read_text(encoding="utf-8")
    s = script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: raw)
    assert isinstance(s, Script)
    assert len(s.cards) == 14 and len(s.sections) == 4
    assert s.sections[0].card_start == 0
    assert s.cards[10].num == 10

def test_generate_retries_on_short_script():
    short = (FX / "raw_script_short.json").read_text(encoding="utf-8")
    full = (FX / "raw_script.json").read_text(encoding="utf-8")
    calls = []
    def fake_llm(sy, u, **k):
        calls.append(u)
        return short if len(calls) == 1 else full
    s = script.generate(_cand(), _post(), VOICE, CFG, llm=fake_llm)
    assert len(calls) == 2
    assert "từ" in calls[1].lower()   # corrective feedback mentions word count
    assert 95 <= s.word_count <= 155

def test_generate_raises_after_second_bad():
    short = (FX / "raw_script_short.json").read_text(encoding="utf-8")
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: short)

def test_generate_raises_on_bad_schema():
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: '{"cards": []}')

def test_write_script_json(tmp_path):
    raw = (FX / "raw_script.json").read_text(encoding="utf-8")
    s = script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: raw)
    p = script.write_script_json(s, tmp_path)
    assert p.exists() and json.loads(p.read_text(encoding="utf-8"))["cards"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/video/test_script.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.video.script'`.

- [ ] **Step 4: Implement `src/pipeline/video/script.py`**

```python
from __future__ import annotations
import json
from pathlib import Path

from ..llm import generate as _default_generate, parse_json_response, LLMError
from ..models import Candidate, PostContent
from . import VideoScriptError
from .models import Script

_NUDGE = 15  # allow spoken/pacing slack around the displayed-word band


def build_prompt(cand: Candidate, post: PostContent, voice: dict, cfg: dict) -> tuple[str, str]:
    wmin, wmax = cfg["words_min"], cfg["words_max"]
    system = (
        f"Bạn viết kịch bản video dọc ~{cfg['target_seconds']} giây cho kênh "
        f"\"{voice.get('ten_kenh', '')}\" về AI, phong cách kinetic typography. "
        f"Giọng: {voice.get('giong', '')}. Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Góc bài: {post.angle}. Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. "
        "CHỈ trả về một object JSON: "
        "{sections:[{label,card_start}], cards:[{lines,variant,anchor,motion_in,motion_out,num?}]}. "
        f"Tổng số TỪ HIỂN THỊ trên màn hình từ {wmin} đến {wmax} (không tính dòng bắt đầu bằng '~'). "
        "12-18 card; 3-5 section; sections[0].card_start=0; card_start tăng dần. "
        "Card 0 là HOOK (0-3s). Card cuối là câu chốt mạnh. Mỗi 'line' <= 7 từ. "
        "Thêm line '~cái' hoặc '~thì' khi cần nhịp đọc (được đọc, không hiện). "
        "variant ∈ stack|right|hero|invert|mark|stair|numeral|strike; "
        "anchor ∈ top|mid|low; motion_in ∈ rise|fall|slideR|slideL|wipe|pop|slam; "
        "motion_out ∈ up|down|dissolve|shrink|wipeOut. "
        "Hai card liền nhau KHÔNG cùng motion_in. Số liệu THẬT thì đặt riêng một card và set 'num'. "
        "Không bịa số. Toàn bộ tiếng Việt."
    )
    article = (cand.full_text or cand.summary or cand.title)[:5000]
    user = (
        f"TIÊU ĐỀ: {cand.title}\nNGUỒN: {cand.source}\nURL: {cand.url}\n\n"
        f"TÓM TẮT/BÀI GỐC:\n{article}\n\n"
        f"CAPTION FACEBOOK (tham khảo giọng, đừng chép):\n{post.caption_fb}\n"
    )
    return system, user


def _validate(data: dict, cfg: dict) -> Script:
    if not isinstance(data, dict) or "cards" not in data or "sections" not in data:
        raise VideoScriptError("missing 'cards'/'sections'")
    cards, sections = data["cards"], data["sections"]
    if not (8 <= len(cards) <= 20):
        raise VideoScriptError(f"card count {len(cards)} out of 8..20")
    if not (2 <= len(sections) <= 6):
        raise VideoScriptError(f"section count {len(sections)} out of 2..6")
    try:
        s = Script.from_dict(data)
    except (KeyError, TypeError) as e:
        raise VideoScriptError(f"bad card/section fields: {e}") from e
    if s.sections[0].card_start != 0:
        raise VideoScriptError("sections[0].card_start must be 0")
    starts = [sec.card_start for sec in s.sections]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise VideoScriptError("section card_start not strictly increasing")
    if starts[-1] >= len(s.cards):
        raise VideoScriptError("section card_start beyond last card")
    return s


def generate(cand: Candidate, post: PostContent, voice: dict, cfg: dict, llm=None) -> Script:
    llm = llm or _default_generate
    system, user = build_prompt(cand, post, voice, cfg)
    wmin, wmax = cfg["words_min"], cfg["words_max"]

    for attempt in (1, 2):
        try:
            raw = llm(system, user, provider="auto")
            data = parse_json_response(raw)
            s = _validate(data, cfg)
        except LLMError as e:
            raise VideoScriptError(f"LLM failed: {e}") from e
        wc = s.word_count
        if wmin - _NUDGE <= wc <= wmax + _NUDGE:
            return s
        if attempt == 2:
            raise VideoScriptError(f"word count {wc} outside {wmin}-{wmax} after retry")
        user = (user + f"\n\n[SỬA] Bản vừa rồi có {wc} từ hiển thị. "
                f"Viết lại cho đủ {wmin}-{wmax} từ, giữ nguyên cấu trúc JSON.")
    raise VideoScriptError("unreachable")  # for type-checkers


def write_script_json(s: Script, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "script.json"
    p.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/video/test_script.py -v`
Expected: 6 passed. (If `raw_script.json` word count is outside 95–155, adjust the fixture wording until `word_count` lands ~120.)

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/video/script.py tests/fixtures/video/ tests/video/test_script.py
git commit -m "feat(video): LLM script generation with schema + word-band validation"
```

---

## Task 5: `pipeline.video.variants`

**Files:**
- Create: `src/pipeline/video/variants.py`
- Test: `tests/video/test_variants.py`

**Interfaces:**
- Consumes: `models.Script`, `models.Card`, enum constants.
- Produces: `variants.normalize(s:Script) -> Script` — returns a new `Script`; pure; `normalize(normalize(s)) == normalize(s)`.

- [ ] **Step 1: Write the failing test**

`tests/video/test_variants.py`:
```python
import re
from pipeline.video.models import Card, SectionMark, Script
from pipeline.video import variants

def C(lines, variant="stack", anchor="mid", mi="rise", mo="up", num=None):
    return Card(lines=lines, variant=variant, anchor=anchor, motion_in=mi, motion_out=mo, num=num)

def test_digit_card_becomes_numeral():
    s = Script(cards=[C(["mở đầu"]), C(["đã tăng gấp 10 lần"]), C(["kết"])],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    assert out.cards[1].variant == "numeral" and out.cards[1].num == 10

def test_no_adjacent_shared_motion_in():
    s = Script(cards=[C([f"c{i}"], mi="rise") for i in range(6)],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    for a, b in zip(out.cards, out.cards[1:]):
        assert a.motion_in != b.motion_in

def test_section_final_stack_becomes_strike_and_last_is_invert():
    s = Script(cards=[C(["a"]), C(["b"]), C(["c"]), C(["d"])],
               sections=[SectionMark("S1", 0), SectionMark("S2", 2)])
    out = variants.normalize(s)
    assert out.cards[1].variant == "strike"   # last of S1
    assert out.cards[3].variant == "invert"   # last of whole script

def test_invalid_fields_get_defaults():
    s = Script(cards=[C(["x"], variant="weird", anchor="??", mi="zzz", mo="qqq")],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    c = out.cards[0]
    assert c.variant in {"stack", "invert"} and c.anchor == "mid"
    assert c.motion_in == "rise" and c.motion_out in {"up", "wipeOut"}

def test_idempotent():
    s = Script(cards=[C([f"c{i} có {i}0 thứ"]) for i in range(7)],
               sections=[SectionMark("A", 0), SectionMark("B", 3), SectionMark("C", 5)])
    once = variants.normalize(s)
    twice = variants.normalize(once)
    assert once.to_dict() == twice.to_dict()

def test_anchor_breaks_three_in_a_row():
    s = Script(cards=[C(["a"], anchor="mid"), C(["b"], anchor="mid"), C(["c"], anchor="mid")],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    assert not (out.cards[0].anchor == out.cards[1].anchor == out.cards[2].anchor)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/video/test_variants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.video.variants'`.

- [ ] **Step 3: Implement `src/pipeline/video/variants.py`**

```python
from __future__ import annotations
import copy
import re

from .models import (Card, Script, VALID_VARIANTS, VALID_ANCHORS,
                     VALID_MOTION_IN, VALID_MOTION_OUT)

_MI_ORDER = ["rise", "slideL", "wipe", "fall", "slideR", "pop", "slam"]
_ANCHOR_CYCLE = ["mid", "top", "low"]
_DIGIT = re.compile(r"\d[\d.,]*")


def _first_int(text: str) -> int | None:
    m = _DIGIT.search(text)
    if not m:
        return None
    try:
        return int(m.group(0).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _section_final_indices(s: Script) -> set[int]:
    starts = sorted(sec.card_start for sec in s.sections)
    finals = {st - 1 for st in starts if st - 1 >= 0}
    finals.add(len(s.cards) - 1)
    return finals


def normalize(s: Script) -> Script:
    s = copy.deepcopy(s)
    n = len(s.cards)
    finals = _section_final_indices(s)

    for i, c in enumerate(s.cards):
        # 1. defaults for invalid enum values
        if c.variant not in VALID_VARIANTS:
            c.variant = "stack"
        if c.anchor not in VALID_ANCHORS:
            c.anchor = "mid"
        if c.motion_in not in VALID_MOTION_IN:
            c.motion_in = "rise"
        if c.motion_out not in VALID_MOTION_OUT:
            c.motion_out = "up"

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

    # 4. anchor: no 3 in a row
    for i in range(2, n):
        a = s.cards
        if a[i].anchor == a[i - 1].anchor == a[i - 2].anchor:
            nxt = _ANCHOR_CYCLE[(_ANCHOR_CYCLE.index(a[i].anchor) + 1) % 3]
            a[i].anchor = nxt

    # 5. motion_in: differ from previous card
    for i in range(1, n):
        if s.cards[i].motion_in == s.cards[i - 1].motion_in:
            for cand in _MI_ORDER:
                if cand != s.cards[i - 1].motion_in:
                    s.cards[i].motion_in = cand
                    break

    # 6. closer cards exit hard
    for c in s.cards:
        if c.variant in {"invert", "strike"} and c.motion_out == "up":
            c.motion_out = "wipeOut"

    return s
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/video/test_variants.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/variants.py tests/video/test_variants.py
git commit -m "feat(video): heuristic post-check normaliser for card layout"
```

---

## Task 6: `pipeline.video.codegen`

**Files:**
- Create: `src/pipeline/video/codegen.py`
- Create fixtures: `tests/fixtures/video/norm_script.json`, `tests/fixtures/video/expected_cards.mjs`, `tests/fixtures/video/expected_variants.mjs`
- Test: `tests/video/test_codegen.py`

**Interfaces:**
- Consumes: `models.Script`.
- Produces:
  - `codegen.render_cards_mjs(s:Script) -> str`
  - `codegen.render_variants_mjs(s:Script) -> str`
  - `codegen.write(s:Script, video_dir:Path) -> tuple[Path,Path]` — writes `<video_dir>/tools/cards.mjs` and `.../variants.mjs`.
  - `codegen.node_check(video_dir:Path) -> None` — `node --check` both; raises `CodegenError`.

- [ ] **Step 1: Create `norm_script.json`**

A small already-normalised `Script.to_dict()` — 4 cards, 2 sections, one `numeral` with `num`:
```json
{
  "sections": [{"label": "MỞ", "card_start": 0}, {"label": "CHỐT", "card_start": 2}],
  "cards": [
    {"lines": ["Hôm nay", "~thì", "AI có bước nhảy lớn."], "variant": "stack", "anchor": "mid", "motion_in": "rise", "motion_out": "up", "num": null},
    {"lines": ["Nhanh gấp", "hai lần."], "variant": "strike", "anchor": "top", "motion_in": "slideL", "motion_out": "up", "num": null},
    {"lines": ["Gọi API tăng", "gấp 10 lần."], "variant": "numeral", "anchor": "mid", "motion_in": "wipe", "motion_out": "shrink", "num": 10},
    {"lines": ["Bạn bắt đầu chưa?"], "variant": "invert", "anchor": "mid", "motion_in": "fall", "motion_out": "wipeOut", "num": null}
  ]
}
```

- [ ] **Step 2: Write the failing test**

`tests/video/test_codegen.py`:
```python
import json, subprocess
from pathlib import Path
import pytest
from pipeline.video.models import Script
from pipeline.video import codegen, CodegenError

FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"

def _script():
    return Script.from_dict(json.loads((FX / "norm_script.json").read_text(encoding="utf-8")))

def test_cards_mjs_matches_golden():
    got = codegen.render_cards_mjs(_script())
    assert got == (FX / "expected_cards.mjs").read_text(encoding="utf-8")

def test_variants_mjs_matches_golden():
    got = codegen.render_variants_mjs(_script())
    assert got == (FX / "expected_variants.mjs").read_text(encoding="utf-8")

def test_write_creates_both(tmp_path):
    (tmp_path / "tools").mkdir()
    a, b = codegen.write(_script(), tmp_path)
    assert a.read_text(encoding="utf-8").startswith("// FILE TỰ SINH")
    assert "export const LAYOUT" in b.read_text(encoding="utf-8")

@pytest.mark.needs_node
def test_node_check_passes(tmp_path):
    (tmp_path / "tools").mkdir()
    codegen.write(_script(), tmp_path)
    codegen.node_check(tmp_path)  # must not raise

@pytest.mark.needs_node
def test_node_check_raises_on_garbage(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/cards.mjs").write_text("export const CARDS = [ ( ;", encoding="utf-8")
    (tmp_path / "tools/variants.mjs").write_text("export const LAYOUT = [];", encoding="utf-8")
    with pytest.raises(CodegenError):
        codegen.node_check(tmp_path)
```

- [ ] **Step 3: Implement `src/pipeline/video/codegen.py`**

```python
from __future__ import annotations
import json
import subprocess
from pathlib import Path

from . import CodegenError
from .models import Script

_HEADER = "// FILE TỰ SINH — đừng sửa tay. Nguồn: src/pipeline/video/codegen.py\n"


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render_cards_mjs(s: Script) -> str:
    lines = [_HEADER, "export const CARDS = [\n"]
    for c in s.cards:
        inner = ", ".join(_q(l) for l in c.lines)
        lines.append(f"  [{inner}],\n")
    lines.append("];\n\nexport const SECTIONS = [\n")
    for sec in s.sections:
        lines.append(f"  [{sec.card_start}, {_q(sec.label)}],\n")
    lines.append("];\n")
    return "".join(lines)


def render_variants_mjs(s: Script) -> str:
    lines = [_HEADER, "export const LAYOUT = [\n"]
    for c in s.cards:
        num = "null" if c.num is None else str(c.num)
        lines.append(
            f"  [{_q(c.variant)}, {_q(c.anchor)}, {num}, "
            f"{_q(c.motion_in)}, {_q(c.motion_out)}],\n"
        )
    lines.append("];\n")
    return "".join(lines)


def write(s: Script, video_dir: Path) -> tuple[Path, Path]:
    tools = Path(video_dir) / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    a = tools / "cards.mjs"
    b = tools / "variants.mjs"
    a.write_text(render_cards_mjs(s), encoding="utf-8")
    b.write_text(render_variants_mjs(s), encoding="utf-8")
    return a, b


def node_check(video_dir: Path) -> None:
    for name in ("cards.mjs", "variants.mjs"):
        r = subprocess.run(["node", "--check", f"tools/{name}"],
                           cwd=str(video_dir), capture_output=True, text=True)
        if r.returncode != 0:
            raise CodegenError(f"node --check {name} failed: {r.stderr.strip()}")
```

- [ ] **Step 4: Generate the golden files from the implementation**

Run once to materialise the goldens, then eyeball them:
```bash
python - <<'PY'
import json
from pathlib import Path
from pipeline.video.models import Script
from pipeline.video import codegen
FX = Path("tests/fixtures/video")
s = Script.from_dict(json.loads((FX/"norm_script.json").read_text(encoding="utf-8")))
(FX/"expected_cards.mjs").write_text(codegen.render_cards_mjs(s), encoding="utf-8")
(FX/"expected_variants.mjs").write_text(codegen.render_variants_mjs(s), encoding="utf-8")
print((FX/"expected_cards.mjs").read_text(encoding="utf-8"))
print((FX/"expected_variants.mjs").read_text(encoding="utf-8"))
PY
```
Confirm the output matches the format of `video/tools/cards.manual.bak` (2-space indent, one card per line, `export const CARDS` / `SECTIONS` / `LAYOUT`).

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/video/test_codegen.py -v`
Expected: 3 passed + 2 `needs_node` passed (Node present).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/video/codegen.py tests/fixtures/video/norm_script.json \
        tests/fixtures/video/expected_cards.mjs tests/fixtures/video/expected_variants.mjs \
        tests/video/test_codegen.py
git commit -m "feat(video): codegen for cards.mjs / variants.mjs with node --check"
```

---

## Task 7: `pipeline.video.align`

**Files:**
- Create: `src/pipeline/video/align.py`
- Create fixture: `tests/fixtures/video/voice_fixture.wav` (generated in Step 1)
- Test: `tests/video/test_align.py`

**Interfaces:**
- Consumes: the vendored `video/tools/align.mjs`, `ffmpeg-static` inside `video/node_modules`.
- Produces:
  - `align._ffmpeg_bin(video_dir:Path) -> str` — env `FFMPEG_BIN`, else `video/node_modules/ffmpeg-static/ffmpeg(.exe)`, else `"ffmpeg"`.
  - `align.make_silence_txt(voice:Path, out_txt:Path, video_dir:Path, noise_db:int=-32, min_silence:float=0.35) -> float` — runs `ffmpeg -af silencedetect`, writes raw `silence_start/…_end/…_duration` lines, returns clip duration in seconds.
  - `align.run_aligner(video_dir:Path, duration:float) -> Path` — `node tools/align.mjs <duration>` with `cwd=video_dir`; validates `src/timeline.json`; raises `AlignError`.

- [ ] **Step 1: Generate the fixture wav (needs ffmpeg or ffmpeg-static)**

```bash
FF="video/node_modules/ffmpeg-static/ffmpeg.exe"   # or system ffmpeg
"$FF" -y -f lavfi -i "sine=frequency=180:duration=1.4" \
      -f lavfi -i "anullsrc=r=44100:cl=mono:d=0.5" \
      -f lavfi -i "sine=frequency=200:duration=1.6" \
      -f lavfi -i "anullsrc=r=44100:cl=mono:d=0.5" \
      -f lavfi -i "sine=frequency=170:duration=1.5" \
      -filter_complex "[0][1][2][3][4]concat=n=5:v=0:a=1[a]" -map "[a]" -ar 44100 -ac 1 \
      tests/fixtures/video/voice_fixture.wav
```
Result: ~5.5s, 3 "speech" tones separated by 2 silence gaps.

- [ ] **Step 2: Write the failing test**

`tests/video/test_align.py`:
```python
import json, shutil
from pathlib import Path
import pytest
from pipeline.video import align, AlignError

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "fixtures" if False else Path(__file__).resolve().parents[1] / "fixtures" / "video"
VIDEO = ROOT / "video"

pytestmark = pytest.mark.needs_node

@pytest.fixture
def stage(tmp_path):
    """A minimal video/ dir: real align.mjs + node_modules, generated cards/variants."""
    d = tmp_path / "video"
    (d / "tools").mkdir(parents=True)
    (d / "src").mkdir()
    (d / "ref").mkdir()
    shutil.copy(VIDEO / "tools/align.mjs", d / "tools/align.mjs")
    # 3 cards so align maps onto the 3 speech bursts of the fixture
    (d / "tools/cards.mjs").write_text(
        'export const CARDS = [["một hai ba"],["bốn năm sáu"],["bảy tám chín"]];\n'
        'export const SECTIONS = [[0,"A"]];\n', encoding="utf-8")
    (d / "tools/variants.mjs").write_text(
        'export const LAYOUT = [["stack","mid",null,"rise","up"],'
        '["stack","top",null,"fall","down"],'
        '["invert","mid",null,"pop","wipeOut"]];\n', encoding="utf-8")
    # symlink/copy node_modules for ffmpeg-static + node builtin only (align.mjs uses node:fs only)
    return d

def test_make_silence_txt_finds_gaps(stage):
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    txt = (stage / "ref/silence.txt").read_text(encoding="utf-8")
    assert "silence_start" in txt and "silence_end" in txt
    assert 4.5 <= dur <= 6.5

def test_run_aligner_builds_timeline(stage):
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    out = align.run_aligner(stage, dur)
    tl = json.loads(out.read_text(encoding="utf-8"))
    assert len(tl["cards"]) == 3
    starts = [c["start"] for c in tl["cards"]]
    assert starts == sorted(starts)
    assert 4.0 <= tl["duration"] <= 7.0

def test_run_aligner_raises_without_cards(stage, tmp_path):
    (stage / "tools/cards.mjs").unlink()
    with pytest.raises(AlignError):
        align.run_aligner(stage, 5.0)
```

- [ ] **Step 3: Implement `src/pipeline/video/align.py`**

```python
from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path

from . import AlignError

_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
_SIL = re.compile(r"silence_(start|end|duration):\s*(-?\d+\.?\d*)")


def _ffmpeg_bin(video_dir: Path) -> str:
    env = os.environ.get("FFMPEG_BIN")
    if env:
        return env
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = Path(video_dir) / "node_modules" / "ffmpeg-static" / name
        if p.exists():
            return str(p)
    return "ffmpeg"


def make_silence_txt(voice: Path, out_txt: Path, video_dir: Path,
                     noise_db: int = -32, min_silence: float = 0.35) -> float:
    ff = _ffmpeg_bin(video_dir)
    r = subprocess.run(
        [ff, "-hide_banner", "-i", str(voice),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    err = r.stderr or ""
    kept = [ln for ln in err.splitlines() if "silence_" in ln]
    Path(out_txt).parent.mkdir(parents=True, exist_ok=True)
    Path(out_txt).write_text("\n".join(kept) + "\n", encoding="utf-8")

    m = _DUR.search(err)
    if not m:
        raise AlignError(f"could not read duration from ffmpeg: {err[-300:]}")
    h, mm, ss = m.groups()
    return int(h) * 3600 + int(mm) * 60 + float(ss)


def run_aligner(video_dir: Path, duration: float) -> Path:
    video_dir = Path(video_dir)
    r = subprocess.run(["node", "tools/align.mjs", f"{duration:.3f}"],
                       cwd=str(video_dir), capture_output=True, text=True)
    if r.returncode != 0:
        raise AlignError(f"align.mjs exit {r.returncode}: {r.stderr.strip()[:400]}")
    tl_path = video_dir / "src" / "timeline.json"
    if not tl_path.exists():
        raise AlignError("align.mjs produced no src/timeline.json")
    try:
        tl = json.loads(tl_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AlignError(f"timeline.json invalid: {e}") from e
    if not tl.get("cards"):
        raise AlignError("timeline.json has no cards")
    return tl_path
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/video/test_align.py -v`
Expected: 3 passed (Node + ffmpeg-static present via `video/node_modules`). If `make_silence_txt` finds no gaps, loosen `noise_db` to `-40` and regenerate the fixture with quieter `anullsrc` gaps.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/align.py tests/fixtures/video/voice_fixture.wav tests/video/test_align.py
git commit -m "feat(video): ffmpeg silencedetect + align.mjs wrapper"
```

---

## Task 8: `pipeline.video.tts`

**Files:**
- Create: `src/pipeline/video/tts.py`
- Modify: `requirements.txt` (+ `faster-whisper==1.0.3`, `gradio-client==1.4.0`)
- Test: `tests/video/test_tts.py`

**Interfaces:**
- Consumes: `scripts/tts_gptsovits.sh`, `scripts/tts_f5.sh` (from Task 1), env `GPTSOVITS_DIR`/`F5TTS_CKPT`/`HF_SPACE_ID`, `ffmpeg-static` via `align._ffmpeg_bin`.
- Produces:
  - `tts.ensure_sample_text(sample_wav:Path, sample_txt:Path, cache_dir:Path) -> str`.
  - `tts.synthesize(target_text:str, out_mp3:Path, cfg:dict, video_dir:Path, fake:bool=False) -> float` — returns audio duration seconds; raises `TTSError` if every backend fails.
  - Internal `_BACKENDS: dict[str, callable]` mapping `"gptsovits"|"f5tts"|"hfspace"` to `fn(ref_wav, ref_text, target_text, out_wav) -> None`; monkeypatched in tests.
  - `tts._order(provider:str) -> list[str]` — `"auto"` → `["gptsovits","f5tts","hfspace"]`.

- [ ] **Step 1: Write the failing test**

`tests/video/test_tts.py`:
```python
import wave
from pathlib import Path
import pytest
from pipeline.video import tts, TTSError

CFG = {"tts_provider": "auto"}
ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"

def _wav_seconds(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / w.getframerate()

def test_order_auto():
    assert tts._order("auto") == ["gptsovits", "f5tts", "hfspace"]
    assert tts._order("f5tts") == ["f5tts"]

def test_ensure_sample_text_reads_existing(tmp_path):
    stxt = tmp_path / "sample.txt"
    stxt.write_text("xin chào đây là giọng mẫu", encoding="utf-8")
    got = tts.ensure_sample_text(tmp_path / "sample.wav", stxt, tmp_path / "cache")
    assert got == "xin chào đây là giọng mẫu"

def test_synthesize_falls_through_backends(tmp_path, monkeypatch):
    calls = []
    def ok_wav(ref_wav, ref_text, target, out_wav):
        calls.append("f5")
        import wave, struct
        with wave.open(str(out_wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
            w.writeframes(struct.pack("<" + "h" * 44100, *([0] * 44100)))
    monkeypatch.setitem(tts._BACKENDS, "gptsovits",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("no torch")))
    monkeypatch.setitem(tts._BACKENDS, "f5tts", ok_wav)
    monkeypatch.setattr(tts, "ensure_sample_text", lambda *a, **k: "ref text")
    monkeypatch.setattr(tts, "_ref_wav", lambda root: tmp_path / "ref.wav")
    (tmp_path / "ref.wav").write_bytes(b"RIFF")   # presence only; backend is faked
    dur = tts.synthesize("một hai ba bốn năm", tmp_path / "out.mp3", CFG, VIDEO,
                         )
    assert calls == ["f5"]
    assert (tmp_path / "out.mp3").exists()
    assert dur > 0.5

def test_synthesize_all_fail_raises(tmp_path, monkeypatch):
    for k in ("gptsovits", "f5tts", "hfspace"):
        monkeypatch.setitem(tts._BACKENDS, k,
                            lambda *a: (_ for _ in ()).throw(RuntimeError("nope")))
    monkeypatch.setattr(tts, "ensure_sample_text", lambda *a, **k: "ref")
    monkeypatch.setattr(tts, "_ref_wav", lambda root: tmp_path / "r.wav")
    (tmp_path / "r.wav").write_bytes(b"RIFF")
    with pytest.raises(TTSError):
        tts.synthesize("abc", tmp_path / "o.mp3", CFG, VIDEO)

@pytest.mark.needs_node
def test_fake_produces_wav_of_expected_length(tmp_path):
    dur = tts.synthesize("một hai ba bốn năm sáu bảy tám chín mười",
                         tmp_path / "o.mp3", CFG, VIDEO, fake=True)
    assert (tmp_path / "o.mp3").exists()
    assert 2.0 <= dur <= 8.0
```

- [ ] **Step 2: Implement `src/pipeline/video/tts.py`**

```python
from __future__ import annotations
import os
import subprocess
import wave
from pathlib import Path

from . import TTSError
from .align import _ffmpeg_bin

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _order(provider: str) -> list[str]:
    if provider == "auto":
        return ["gptsovits", "f5tts", "hfspace"]
    return [provider]


def _ref_wav(root: Path) -> Path:
    return Path(root) / "assets" / "voice" / "sample.wav"


def ensure_sample_text(sample_wav: Path, sample_txt: Path, cache_dir: Path) -> str:
    sample_txt = Path(sample_txt)
    if sample_txt.exists():
        return sample_txt.read_text(encoding="utf-8").strip()
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / "sample.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8").strip()
    if not Path(sample_wav).exists():
        raise TTSError(f"missing voice sample: {sample_wav}. "
                       "Đặt assets/voice/sample.wav (3-10 phút) + assets/voice/sample.txt.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TTSError("faster-whisper not installed and no sample.txt provided") from e
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(sample_wav), language="vi")
    text = " ".join(seg.text.strip() for seg in segments).strip()
    cached.write_text(text, encoding="utf-8")
    return text


# ---- backends: fn(ref_wav, ref_text, target_text, out_wav) -> None ----
def _run_script(script: Path, ref_wav, ref_text, target, out_wav) -> None:
    if not script.exists():
        raise RuntimeError(f"{script.name} not present (spike Task 1 authored it?)")
    r = subprocess.run(["bash", str(script), str(ref_wav), ref_text, target, str(out_wav)],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not Path(out_wav).exists():
        raise RuntimeError(f"{script.name} failed: {r.stderr.strip()[:400]}")


def _gptsovits(ref_wav, ref_text, target, out_wav):
    _run_script(_SCRIPTS / "tts_gptsovits.sh", ref_wav, ref_text, target, out_wav)


def _f5tts(ref_wav, ref_text, target, out_wav):
    _run_script(_SCRIPTS / "tts_f5.sh", ref_wav, ref_text, target, out_wav)


def _hfspace(ref_wav, ref_text, target, out_wav):
    space = os.environ.get("HF_SPACE_ID")
    if not space:
        raise RuntimeError("HF_SPACE_ID not set")
    from gradio_client import Client, handle_file
    last = None
    for attempt in range(3):
        try:
            client = Client(space, hf_token=os.environ.get("HF_TOKEN"))
            res = client.predict(handle_file(str(ref_wav)), ref_text, target,
                                 api_name="/infer")
            src = res[0] if isinstance(res, (list, tuple)) else res
            Path(out_wav).write_bytes(Path(src).read_bytes())
            return
        except Exception as e:  # noqa: BLE001
            last = e
            import time
            time.sleep(60)
    raise RuntimeError(f"HF Space failed after retries: {last}")


_BACKENDS = {"gptsovits": _gptsovits, "f5tts": _f5tts, "hfspace": _hfspace}


def _to_mp3(wav_path: Path, out_mp3: Path, video_dir: Path) -> float:
    ff = _ffmpeg_bin(video_dir)
    out_mp3 = Path(out_mp3)
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ff, "-y", "-i", str(wav_path),
         "-af", "silenceremove=start_periods=1:start_silence=0.3:start_threshold=-40dB:"
                "stop_periods=1:stop_silence=0.5:stop_threshold=-40dB",
         "-ar", "44100", "-ac", "1", "-q:a", "2", str(out_mp3)],
        check=True, capture_output=True, text=True,
    )
    # duration
    with wave.open(str(wav_path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _fake_wav(target_text: str, out_wav: Path) -> None:
    import struct
    words = max(1, len(target_text.split()))
    secs = max(2.0, words * 0.38)
    n = int(44100 * secs)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(struct.pack("<%dh" % n, *([0] * n)))


def synthesize(target_text: str, out_mp3: Path, cfg: dict, video_dir: Path,
               fake: bool = False) -> float:
    import tempfile
    tmp_wav = Path(tempfile.mkstemp(suffix=".wav")[1])
    try:
        if fake:
            _fake_wav(target_text, tmp_wav)
            return _to_mp3(tmp_wav, out_mp3, video_dir)

        root = Path(video_dir).parent
        ref_wav = _ref_wav(root)
        ref_text = ensure_sample_text(ref_wav, root / "assets/voice/sample.txt",
                                      root / "data/voice_cache")
        errors = []
        for name in _order(cfg.get("tts_provider", "auto")):
            try:
                _BACKENDS[name](ref_wav, ref_text, target_text, tmp_wav)
                return _to_mp3(tmp_wav, out_mp3, video_dir)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")
        raise TTSError("all TTS backends failed -> " + " | ".join(errors))
    finally:
        tmp_wav.unlink(missing_ok=True)
```

- [ ] **Step 3: Add dependencies**

`requirements.txt` add:
```
faster-whisper==1.0.3
gradio-client==1.4.0
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/video/test_tts.py -v`
Expected: 4 passed + 1 `needs_node` passed. `faster-whisper`/`gradio-client` are only imported inside functions, so the non-fake tests pass without them installed.

- [ ] **Step 5: Manual backend check (not pytest)**

After Task 1's engine is wired, once:
```bash
python -m pipeline.video.build_video --tts-check --root .
```
Confirm `video/public/voice.mp3` plays and sounds like the sample voice.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/video/tts.py requirements.txt tests/video/test_tts.py
git commit -m "feat(video): TTS backend chain (GPT-SoVITS/F5-TTS/HF Space) + fake mode"
```

---

## Task 9: `pipeline.video.build_video`

**Files:**
- Create: `src/pipeline/video/build_video.py`
- Create fixture: `tests/fixtures/video/story.json`
- Test: `tests/video/test_build_video.py`

**Interfaces:**
- Consumes: everything above; `pipeline.models.Candidate`, `pipeline.models.PostContent`.
- Produces:
  - `build_video._load_story(path:Path) -> tuple[Candidate, PostContent]` — reads `{"candidate": {...}, "post": {...}}`.
  - `build_video.build(root:Path, cand, post, now:datetime, cfg:dict, fake=False, render_smoke=False, llm=None) -> dict` — runs script→normalize→codegen→tts→align; copies artefacts to `output/<date>/<id>/video/`; returns manifest `{"id","seconds","word_count","cards","sections","timeline_off","voice_path","video_dir","tts_backend"}`. Raises `Video*Error` subclasses.
  - `build_video.main(argv=None) -> int` — args `--root`, `--fake`, `--render-smoke`, `--tts-check`, `--story <path>`.

- [ ] **Step 1: Create `story.json`**

```json
{
  "candidate": {
    "url": "https://openai.com/blog/demo-model",
    "title": "OpenAI ra mô hình AI mới nhanh gấp đôi",
    "source": "rss:OpenAI Blog",
    "published_at": "2026-09-03T00:00:00+00:00",
    "raw_score_hint": 900.0,
    "summary": "OpenAI công bố mô hình mới nhanh gấp đôi, rẻ hơn.",
    "full_text": "OpenAI vừa công bố mô hình mới, nhanh gấp đôi thế hệ trước và rẻ hơn khoảng một nửa.",
    "top_image": null
  },
  "post": {
    "angle": "phan-tich",
    "caption_fb": "AI lại có biến. OpenAI ra model mới nhanh gấp đôi.\n\nNguồn: OpenAI Blog — https://openai.com/blog/demo-model",
    "caption_ig": "OpenAI ra model mới. #AI",
    "hashtags": ["#AI", "#OpenAI"],
    "thumbnail_prompt": "neural core",
    "thumbnail_title": "OPENAI RA MODEL MỚI",
    "youtube_title": "OpenAI ra model mới",
    "youtube_desc": "Tóm tắt.",
    "tiktok_caption": "OpenAI ra model mới 👀",
    "source_url": "https://openai.com/blog/demo-model",
    "source_name": "OpenAI Blog"
  }
}
```

- [ ] **Step 2: Write the failing test**

`tests/video/test_build_video.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.video import build_video, VideoScriptError

ROOT = Path(__file__).resolve().parents[2]
FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"
NOW = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)
CFG = {"enabled": True, "target_seconds": 40, "words_min": 110, "words_max": 140,
       "tts_provider": "auto"}

pytestmark = pytest.mark.needs_node  # align.mjs + ffmpeg-static


def _story():
    return build_video._load_story(FX / "story.json")


def test_load_story_roundtrips():
    cand, post = _story()
    assert cand.title.startswith("OpenAI") and post.angle == "phan-tich"


def test_build_fake_writes_all_artefacts(tmp_path, monkeypatch):
    # isolated repo copy: video/ + assets + config + tests fixtures reachable
    repo = tmp_path
    (repo / "video").mkdir()
    for sub in ("tools", "src", "ref", "public", "node_modules"):
        (repo / "video" / sub).mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(ROOT / "video/tools/align.mjs", repo / "video/tools/align.mjs")
    shutil.copytree(ROOT / "video/node_modules/ffmpeg-static",
                    repo / "video/node_modules/ffmpeg-static", dirs_exist_ok=True)

    raw = (FX / "raw_script.json").read_text(encoding="utf-8")
    voice = {"xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "giong": "thân thiện",
             "cam_ky": [], "ten_kenh": "A Hít Official"}
    monkeypatch.setattr(build_video, "_load_voice", lambda root: voice)

    cand, post = _story()
    man = build_video.build(repo, cand, post, NOW, CFG, fake=True,
                            llm=lambda s, u, **k: raw)
    assert (repo / "video/tools/cards.mjs").exists()
    assert (repo / "video/tools/variants.mjs").exists()
    assert (repo / "video/public/voice.mp3").exists()
    assert (repo / "video/src/timeline.json").exists()
    vdir = repo / "output/2026-09-03" / man["id"] / "video"
    assert (vdir / "script.json").exists() and (vdir / "timeline.json").exists()
    assert man["word_count"] >= 95 and man["cards"] == 14
    assert man["tts_backend"] == "fake"


def test_build_disabled_returns_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(build_video, "_load_voice", lambda root: {})
    cand, post = _story()
    man = build_video.build(tmp_path, cand, post, NOW, {"enabled": False}, fake=True)
    assert man.get("skipped")


def test_build_propagates_script_error(tmp_path, monkeypatch):
    monkeypatch.setattr(build_video, "_load_voice", lambda root: {
        "xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "cam_ky": [], "ten_kenh": "X"})
    cand, post = _story()
    with pytest.raises(VideoScriptError):
        build_video.build(tmp_path, cand, post, NOW, CFG, fake=True,
                          llm=lambda s, u, **k: '{"cards": [], "sections": []}')
```

- [ ] **Step 3: Implement `src/pipeline/video/build_video.py`**

```python
from __future__ import annotations
import argparse
import json
import logging
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..models import Candidate, PostContent
from . import VideoError
from . import script as _script
from . import variants as _variants
from . import codegen as _codegen
from . import tts as _tts
from . import align as _align

log = logging.getLogger("video.build")


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)


def _make_id(cand: Candidate, now: datetime) -> str:
    return f"{now:%Y-%m-%d}-{_slug(cand.title)[:40]}".rstrip("-")


def _load_voice(root: Path) -> dict:
    return yaml.safe_load((Path(root) / "config/voice.yaml").read_text(encoding="utf-8"))


def _load_story(path: Path) -> tuple[Candidate, PostContent]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return Candidate.from_dict(d["candidate"]), PostContent.from_dict(d["post"])


def build(root: Path, cand: Candidate, post: PostContent, now: datetime, cfg: dict,
          fake: bool = False, render_smoke: bool = False, llm=None) -> dict:
    if not cfg.get("enabled"):
        return {"skipped": "video.enabled=false"}

    root = Path(root)
    video_dir = root / "video"
    voice = _load_voice(root)

    s = _script.generate(cand, post, voice, cfg, llm=llm)
    s = _variants.normalize(s)
    _codegen.write(s, video_dir)
    try:
        _codegen.node_check(video_dir)
    except FileNotFoundError:
        log.warning("node not available, skipping --check")

    pid = _make_id(cand, now)
    out_dir = root / "output" / f"{now:%Y-%m-%d}" / pid / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    _script.write_script_json(s, out_dir)

    voice_mp3 = video_dir / "public" / "voice.mp3"
    seconds = _tts.synthesize(s.spoken_text, voice_mp3, cfg, video_dir, fake=fake)
    backend = "fake" if fake else cfg.get("tts_provider", "auto")

    sil_dur = _align.make_silence_txt(voice_mp3, video_dir / "ref" / "silence.txt", video_dir)
    tl_path = _align.run_aligner(video_dir, sil_dur)
    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    timeline_off = not (25.0 <= tl.get("duration", 0) <= 55.0)

    for f in (video_dir / "tools/cards.mjs", video_dir / "tools/variants.mjs",
              tl_path, voice_mp3):
        shutil.copy(f, out_dir / f.name)

    manifest = {
        "id": pid, "seconds": round(tl.get("duration", seconds), 2),
        "word_count": s.word_count, "cards": len(s.cards),
        "sections": [sec.label for sec in s.sections],
        "timeline_off": timeline_off, "voice_path": str(voice_mp3),
        "video_dir": str(video_dir), "tts_backend": backend,
    }

    if render_smoke:
        r = subprocess.run(
            ["npx", "remotion", "render", "CodexShort", "out/smoke.mp4", "--frames=0-30"],
            cwd=str(video_dir), capture_output=True, text=True)
        manifest["render_smoke_ok"] = r.returncode == 0
        if r.returncode != 0:
            log.error("render smoke failed: %s", r.stderr[-500:])

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Phase 2A — build Remotion inputs for one story")
    ap.add_argument("--root", default=".")
    ap.add_argument("--story", required=False)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--render-smoke", action="store_true")
    ap.add_argument("--tts-check", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root)
    cfg = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")).get("video", {})

    if args.tts_check:
        secs = _tts.synthesize("Xin chào, đây là bản kiểm tra giọng đọc của kênh.",
                               root / "video/public/voice.mp3", cfg, root / "video",
                               fake=args.fake)
        print(f"SUMMARY: tts-check ok, {secs:.1f}s -> video/public/voice.mp3")
        return 0

    if not args.story:
        ap.error("--story is required unless --tts-check")
    cand, post = _load_story(Path(args.story))
    cfg.setdefault("enabled", True)
    try:
        man = build(root, cand, post, datetime.now(timezone.utc), cfg,
                    fake=args.fake, render_smoke=args.render_smoke)
    except VideoError as e:
        print(f"SUMMARY: video build failed: {e}")
        return 1
    print(f"SUMMARY: built {man.get('id')} — {man.get('cards')} cards, "
          f"{man.get('seconds')}s, tts={man.get('tts_backend')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/video/test_build_video.py -v`
Expected: 4 passed (Node + ffmpeg-static present).

- [ ] **Step 5: Offline end-to-end**

Run: `python -m pipeline.video.build_video --fake --story tests/fixtures/video/story.json --root .`
Expected: `SUMMARY: built 2026-… — 14 cards, ~Ns, tts=fake`, and `video/src/timeline.json` + `video/public/voice.mp3` exist.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/video/build_video.py tests/fixtures/video/story.json tests/video/test_build_video.py
git commit -m "feat(video): build_video orchestrator + CLI (--fake/--render-smoke/--tts-check)"
```

---

## Task 10: Wire into Phase 1 + config + README

**Files:**
- Modify: `src/pipeline/run.py`, `config/settings.yaml`, `README.md`
- Test: `tests/test_run.py` (extend)

**Interfaces:**
- Consumes: `pipeline.video.build_video.build`, `pipeline.video.VideoError`.
- Produces: `run.build()` attaches `pending["video"]` when `settings["video"]["enabled"]`; a video failure logs + notifies and leaves the image post untouched (`pending` still returned).

- [ ] **Step 1: Write the failing test (extend `tests/test_run.py`)**

```python
def test_build_attaches_video_manifest_when_enabled(project, monkeypatch):
    (project / "config/settings.yaml").write_text(
        "approval_mode: telegram\nmin_score: 45\nposts_per_day: 1\n"
        "rsshub_base: http://rss\npending_ttl_hours: 12\n"
        "video:\n  enabled: true\n  tts_provider: auto\n", encoding="utf-8")
    monkeypatch.setattr(run.collect, "collect", lambda *a, **k: [_fake_candidate()])
    monkeypatch.setattr(run.media, "build_media",
                        lambda c, p, o, ch: ([_touch(Path(o) / "img/01_thumbnail.jpg")], True))
    import pipeline.video.build_video as bv
    monkeypatch.setattr(bv, "build", lambda *a, **k: {"id": "vid1", "cards": 14, "seconds": 40})
    pending = run.build(project, NOW, dry_run=True, local=False,
                        generate=lambda s, u, **k: LLM_JSON)
    assert pending["video"]["id"] == "vid1"


def test_build_survives_video_error(project, monkeypatch):
    (project / "config/settings.yaml").write_text(
        "approval_mode: telegram\nmin_score: 45\nposts_per_day: 1\n"
        "rsshub_base: http://rss\npending_ttl_hours: 12\nvideo:\n  enabled: true\n",
        encoding="utf-8")
    monkeypatch.setattr(run.collect, "collect", lambda *a, **k: [_fake_candidate()])
    monkeypatch.setattr(run.media, "build_media",
                        lambda c, p, o, ch: ([_touch(Path(o) / "img/01_thumbnail.jpg")], True))
    import pipeline.video.build_video as bv
    from pipeline.video import VideoScriptError
    monkeypatch.setattr(bv, "build",
                        lambda *a, **k: (_ for _ in ()).throw(VideoScriptError("boom")))
    notes = []
    monkeypatch.setattr(run, "_notify", lambda m: notes.append(m))
    pending = run.build(project, NOW, dry_run=True, local=False,
                        generate=lambda s, u, **k: LLM_JSON)
    assert "video" not in pending
    assert notes and "video" in notes[0].lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_run.py -k video -v`
Expected: FAIL — `KeyError: 'video'` / no notify.

- [ ] **Step 3: Patch `src/pipeline/run.py`**

After `pending = review.build_pending(post, images, pid, low_media, now)` and before the `if dry_run:` block:
```python
    if settings.get("video", {}).get("enabled"):
        try:
            from .video import build_video as _bv
            vman = _bv.build(root, best, post, now,
                             {**settings["video"]}, fake=dry_run, llm=generate)
            if not vman.get("skipped"):
                pending["video"] = vman
        except Exception as e:  # noqa: BLE001 - never let video break the image post
            log.error("video stage failed: %s", e)
            _notify(f"Video hôm nay lỗi, chỉ đăng ảnh: {e}")
```
(`fake=dry_run` so `--dry-run` never invokes real TTS; a real run with `video.enabled` uses the configured backend.)

- [ ] **Step 4: Update `config/settings.yaml`**

Append:
```yaml
video:
  enabled: false
  target_seconds: 40
  words_min: 110
  words_max: 140
  tts_provider: auto
```

- [ ] **Step 5: Update `README.md`**

Add a "Phase 2A — video (thử nghiệm)" section:
```markdown
## Phase 2A — video (kịch bản + giọng + timeline)

Bật `config/settings.yaml` → `video.enabled: true`. Chuẩn bị:
- `assets/voice/sample.wav` — 3–10 phút giọng kể (WAV mono 44.1kHz)
- `assets/voice/sample.txt` — lời thoại của mẫu (không có thì pipeline tự transcribe)
- `video/public/bg-*.mp4` — pool nền (2B dùng)

Thử offline (không gọi TTS thật):
    python -m pipeline.video.build_video --fake --story tests/fixtures/video/story.json

Kiểm tra giọng clone thật:
    python -m pipeline.video.build_video --tts-check

TTS engine do spike chọn (xem docs/superpowers/notes/2026-09-03-tts-spike.md).
F5-TTS checkpoint tiếng Việt có ràng buộc license — chỉ dùng làm fallback.
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass (Phase 1 + Phase 2A; `needs_node` tests pass with Node present).

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/run.py config/settings.yaml README.md tests/test_run.py
git commit -m "feat(video): wire optional video stage into Phase 1 build (enabled=false default)"
```

---

## Task 11: CI — `video-smoke` workflow

**Files:**
- Create: `.github/workflows/video-smoke.yml`
- Modify: `pytest.ini` (register `needs_node` marker — done in Task 2; verify)
- Test: `tests/video/test_workflows_video.py`

**Interfaces:**
- Consumes: repo secrets are NOT needed (fake path only).
- Produces: a workflow that on changes to `video/**` or `src/pipeline/video/**` runs `npm ci` + pytest (incl. `needs_node`) + `build_video --fake --render-smoke`.

- [ ] **Step 1: Write the failing test**

`tests/video/test_workflows_video.py`:
```python
from pathlib import Path
import yaml

WF = Path(__file__).resolve().parents[2] / ".github/workflows/video-smoke.yml"

def test_workflow_valid_and_targeted():
    data = yaml.safe_load(WF.read_text(encoding="utf-8"))
    assert data["jobs"]
    text = WF.read_text(encoding="utf-8")
    assert "npm ci" in text
    assert "pipeline.video.build_video --fake" in text
    assert "render-smoke" in text
    assert "video/**" in text
```

- [ ] **Step 2: Create `.github/workflows/video-smoke.yml`**

```yaml
name: video-smoke
on:
  push:
    paths:
      - 'video/**'
      - 'src/pipeline/video/**'
      - '.github/workflows/video-smoke.yml'
  workflow_dispatch:
jobs:
  smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - name: Python deps
        run: |
          pip install -r requirements.txt
          pip install -e .
      - name: Node deps
        run: cd video && npm ci
      - name: Ensure Chromium for Remotion
        run: cd video && npx remotion browser ensure
      - name: Unit tests (incl. needs_node)
        run: python -m pytest tests/video -q
      - name: End-to-end fake build + render smoke
        run: python -m pipeline.video.build_video --fake --story tests/fixtures/video/story.json --render-smoke --root .
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/video/test_workflows_video.py -v`
Expected: 1 passed.

- [ ] **Step 4: Full suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/video-smoke.yml tests/video/test_workflows_video.py
git commit -m "ci(video): smoke workflow — npm ci, video tests, fake build + render 0-30"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task(s) |
|---|---|
| §1 outputs (`cards.mjs`, `variants.mjs`, `voice.mp3`, `silence.txt`, `timeline.json`) | 6, 8, 7, 9 |
| §1 "definition of done" (`--frames=0-30` renders) | 9 (`render_smoke`), 11 |
| §2 decisions (enabled=false default, backup manual files, engine spike) | 1, 2, 10 |
| §2 existing-system facts (composition id, align.mjs contract, `~` filler) | 2, 3, 6, 7 |
| §3.1 repo tree / `.gitignore` | 2 |
| §3.2 models | 3 |
| §3.3 script.py (prompt, validate, retry, script.json) | 4 |
| §3.4 variants.py (all 6 rules, idempotent) | 5 |
| §3.5 codegen.py (ESM format, node --check) | 6 |
| §3.6 tts.py (ensure_sample_text, backend chain, fake, mp3 convert, trim) | 8 |
| §3.7 align.py (silencedetect format, run in cwd, duration bounds warn) | 7, 9 |
| §3.8 build_video.py (flow steps 1–8, manifest keys) | 9 |
| §3.9 settings.video block | 10 |
| §4 spike + decision gate + notes doc | 1 |
| §5 error matrix | 4 (script/retry), 6 (codegen), 7 (align), 8 (tts chain), 9 (propagate), 10 (survive in run) |
| §6 tests (per module + needs_node + e2e offline + CI smoke) | every task + 11 |
| §7 license/security (F5-TTS caveat in README, private repo, HF_TOKEN) | 8, 10 |
| §9 manifest for 2B | 9 |
| §10 user prep (sample.wav/.txt, bg pool) | 10 (README) |

No uncovered requirement. (2B/2C are explicitly out of scope.)

**2. Placeholder scan**

- Task 1 is intentionally a spike (no test cycle) — allowed by writing-plans "Task Right-Sizing" for research; its steps carry concrete commands and a written-decision deliverable.
- `scripts/tts_gptsovits.sh` flag names are marked "adjust to the repo's actual entrypoint" — this is the spike's job by definition, not a hidden TODO in shipped code; `tts.py` only depends on the 4-arg contract.
- No "TBD"/"implement later" elsewhere. Every code step has complete code.

**3. Type consistency**

- `Script` / `Card` / `SectionMark` field names identical across Tasks 3–9.
- `script.generate(cand, post, voice, cfg, llm=None) -> Script` — Task 4 def, Task 9 call agree.
- `variants.normalize(Script) -> Script` — Task 5 def, Task 9 call agree.
- `codegen.write(s, video_dir) -> (Path, Path)` and `codegen.node_check(video_dir)` — Task 6 def, Task 9 call agree.
- `tts.synthesize(target_text, out_mp3, cfg, video_dir, fake=False) -> float` — Task 8 def; Task 9 calls with exactly these args; Task 8 tests call the same.
- `align.make_silence_txt(voice, out_txt, video_dir, ...) -> float` and `align.run_aligner(video_dir, duration) -> Path` — Task 7 def, Task 9 call agree (note `video_dir` positional in both).
- `build_video.build(root, cand, post, now, cfg, fake=False, render_smoke=False, llm=None) -> dict` — Task 9 def; Task 10 `run.py` calls `_bv.build(root, best, post, now, {**settings["video"]}, fake=dry_run, llm=generate)` — matches.
- `_BACKENDS` keys `"gptsovits"|"f5tts"|"hfspace"` consistent between `_order`, the dict, and the tests.
- Manifest keys (`id`, `seconds`, `word_count`, `cards`, `sections`, `timeline_off`, `voice_path`, `video_dir`, `tts_backend`) — produced in Task 9, consumed by Task 10 test (`["video"]["id"]`) and spec §9 (2B).

One fix applied inline: Task 8 test `test_synthesize_falls_through_backends` referenced `tts._ref_wav`; ensured `tts.py` defines `_ref_wav(root)` and `synthesize` uses it via `root = video_dir.parent`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-03-phase2a-script-voice-timeline.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
