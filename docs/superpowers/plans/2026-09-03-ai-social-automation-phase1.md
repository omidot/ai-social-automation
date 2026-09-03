# AI Social Automation — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully-automated, zero-cost GitHub Actions pipeline that each day collects viral AI news, picks the hottest story, writes Vietnamese social copy, generates 3–4 images, sends a Telegram preview for approval, and auto-posts to a Facebook Page + Instagram.

**Architecture:** A modular Python package (`src/pipeline/`) split into six stages (`collect → score → write → media → review → publish`) plus four helper modules (`llm`, `telegram`, `meta`, `state`) and shared `models`. A thin `run.py` wires the build stages; a separate `approve_poll.py` handles Telegram button callbacks. State lives in committed JSON files under `data/`. Three GitHub Actions workflows drive it on cron.

**Tech Stack:** Python 3.12, `httpx`, `feedparser`, `trafilatura`, `PyYAML`, `Pillow`, `playwright` (Chromium), `google-genai` (Gemini fallback), `pytest`. LLM primary = Claude CLI (`@anthropic-ai/claude-code`) authenticated with `CLAUDE_CODE_OAUTH_TOKEN`.

## Global Constraints

- Python **3.12**. All code targets 3.12 syntax.
- **Zero recurring cost** — every external service must use a free tier.
- Repo is **private**. All tokens/keys come from **GitHub Actions Secrets** only; never commit secrets; `.env` is git-ignored.
- All generated user-facing text (captions, hashtags, thumbnail text, YT/TikTok copy) is **100% Vietnamese**.
- Facebook/Instagram Graph API base: **`https://graph.facebook.com/v21.0`**.
- Images below **500px** on the long edge are rejected. Thumbnail is exactly **1200×630**.
- Virality threshold **`min_score = 45`**; below it, no post that run (clean exit 0).
- `APPROVAL_MODE` is read from `config/settings.yaml`: `telegram` (default) or `auto`.
- Build runs daily at **08:00 ICT = 01:00 UTC** (`cron: '0 1 * * *'`).
- Pending posts expire after **12 hours**.
- Allowed `angle` values: `tin-tuc`, `ung-dung-mmo`, `phan-tich`, `giat-gan`.
- Every `caption_fb` ends with a source attribution line: `Nguồn: <name> — <url>`.

---

## File Structure

| File | Responsibility |
|---|---|
| `requirements.txt` | Pinned dependencies |
| `pytest.ini` | Test config (`pythonpath = src`) |
| `config/sources.yaml` | RSS feeds, subreddits, Facebook page ids |
| `config/voice.yaml` | Vietnamese voice profile |
| `config/settings.yaml` | `approval_mode`, `posts_per_day`, `min_score`, `rsshub_base` |
| `config/facebook_urls.txt` | Manual fallback: one FB post URL per line |
| `src/pipeline/__init__.py` | Package marker + version |
| `src/pipeline/models.py` | `Candidate`, `PostContent` dataclasses + (de)serialisation |
| `src/pipeline/state.py` | Atomic JSON state: `seen`, `pending/`, `posted/`, telegram offset |
| `src/pipeline/llm.py` | `generate()` with Claude→Gemini auto-fallback + `parse_json_response()` |
| `src/pipeline/collect.py` | Gather `Candidate`s from RSS/HN/Reddit/Facebook/manual |
| `src/pipeline/score.py` | Score candidates, pick top or `None` |
| `src/pipeline/write.py` | LLM → `PostContent` |
| `src/pipeline/media.py` | Thumbnail, source image, screenshot, AI image → list of paths |
| `src/pipeline/telegram.py` | Telegram Bot API wrapper |
| `src/pipeline/meta.py` | Facebook/Instagram Graph API wrapper + tmpfiles upload |
| `src/pipeline/review.py` | Build pending record + send Telegram preview |
| `src/pipeline/publish.py` | Post to FB + IG, write YT/TikTok files, record result |
| `src/pipeline/run.py` | Build-stage orchestrator; `--dry-run`, `--local` |
| `src/pipeline/approve_poll.py` | Consume Telegram callbacks; publish/reject/expire pending |
| `.github/workflows/build.yml` | Daily build |
| `.github/workflows/approve.yml` | Every 10 min: process approvals |
| `.github/workflows/refresh-token.yml` | Monthly: mint new Meta long-lived token + Telegram reminder |
| `README.md` | Setup: secrets, enabling workflows, dry-run |
| `tests/fixtures/*` | Frozen sample feed/article/HN/Reddit/LLM payloads |
| `tests/test_*.py` | One test module per pipeline module |

---

## Task 1: Project scaffold & configuration

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `src/pipeline/__init__.py`, `tests/__init__.py`, `tests/conftest.py`
- Create: `config/sources.yaml`, `config/voice.yaml`, `config/settings.yaml`, `config/facebook_urls.txt`
- Create: `assets/fonts/.gitkeep`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: nothing
- Produces: importable package `pipeline` (`pipeline.__version__: str`); config files at the paths above with the exact keys used by later tasks (`settings.yaml` → `approval_mode`, `min_score`, `posts_per_day`, `rsshub_base`, `run_hour_utc`).

- [ ] **Step 1: Write the failing test**

`tests/test_scaffold.py`:
```python
import subprocess, sys
from pathlib import Path
import yaml

def test_package_imports():
    import pipeline
    assert isinstance(pipeline.__version__, str)

def test_config_files_present_and_valid():
    root = Path(__file__).resolve().parents[1]
    settings = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["approval_mode"] in {"telegram", "auto"}
    assert settings["min_score"] == 45
    assert "rsshub_base" in settings
    sources = yaml.safe_load((root / "config/sources.yaml").read_text(encoding="utf-8"))
    assert isinstance(sources["rss"], list) and sources["rss"]
    assert isinstance(sources["subreddits"], list)
    voice = yaml.safe_load((root / "config/voice.yaml").read_text(encoding="utf-8"))
    assert "xung_ho" in voice and "cam_ky" in voice

def test_requirements_pinned():
    root = Path(__file__).resolve().parents[1]
    lines = [l for l in (root / "requirements.txt").read_text().splitlines() if l and not l.startswith("#")]
    assert all("==" in l for l in lines), "every dependency must be pinned"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scaffold.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline'`.

- [ ] **Step 3: Create the scaffold**

`requirements.txt`:
```
httpx==0.27.2
feedparser==6.0.11
trafilatura==1.12.2
PyYAML==6.0.2
Pillow==10.4.0
playwright==1.47.0
google-genai==0.8.0
python-dateutil==2.9.0.post0
pytest==8.3.3
```

`pytest.ini`:
```ini
[pytest]
pythonpath = src
testpaths = tests
```

`src/pipeline/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

`tests/conftest.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIXTURES = Path(__file__).parent / "fixtures"
```

`config/settings.yaml`:
```yaml
approval_mode: telegram      # telegram | auto
posts_per_day: 1
min_score: 45
run_hour_utc: 1              # 08:00 ICT
rsshub_base: "https://rsshub.app"
pending_ttl_hours: 12
```

`config/sources.yaml`:
```yaml
rss:
  - name: "OpenAI Blog"
    url: "https://openai.com/blog/rss.xml"
  - name: "Google DeepMind"
    url: "https://deepmind.google/blog/rss.xml"
  - name: "Anthropic News"
    url: "https://www.anthropic.com/rss.xml"
  - name: "TechCrunch AI"
    url: "https://techcrunch.com/category/artificial-intelligence/feed/"
  - name: "The Verge AI"
    url: "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
  - name: "VentureBeat AI"
    url: "https://venturebeat.com/category/ai/feed/"
  - name: "MIT Technology Review"
    url: "https://www.technologyreview.com/feed/"
  - name: "Ars Technica"
    url: "https://feeds.arstechnica.com/arstechnica/technology-lab"
subreddits: ["artificial", "LocalLLaMA", "OpenAI", "singularity"]
reddit_min_ups: 100
hn_min_points: 50
facebook_pages: []          # list of {name, id}; empty = rely on facebook_urls.txt
keywords: ["AI","LLM","GPT","mô hình","model","OpenAI","Anthropic","Gemini",
          "Claude","agent","trí tuệ nhân tạo","chatbot","nvidia","training"]
```

`config/voice.yaml`:
```yaml
xung_ho:
  nguoi_noi: "mình"
  nguoi_nghe: "bạn"
giong: "thân thiện, dễ hiểu, có chút hài, không hàn lâm"
do_dai_cau: "ngắn–vừa, tránh câu lê thê"
emoji: "vừa phải, 2–5 cái mỗi bài"
mo_bai_mau:
  - "Có tin này hay nè:"
  - "AI tuần này lại có biến:"
  - "Nghe thử cái này xem:"
cam_ky:
  - "không giật tít sai sự thật"
  - "không hứa hẹn kiếm tiền phi thực tế"
  - "không chê bai cá nhân"
cta_mau:
  - "Bạn nghĩ sao? Comment cho mình biết nhé."
  - "Lưu lại để dùng dần nha."
ten_kenh: "A Hít Official"
```

`config/facebook_urls.txt`:
```
# Mỗi dòng một URL bài Facebook công khai. Dòng bắt đầu bằng # bị bỏ qua.
```

`assets/fonts/.gitkeep`: empty file.

- [ ] **Step 4: Download the Vietnamese font**

Run:
```bash
curl -L -o assets/fonts/BeVietnamPro-Bold.ttf \
  https://github.com/google/fonts/raw/main/ofl/bevietnampro/BeVietnamPro-Bold.ttf
python -c "from PIL import ImageFont; ImageFont.truetype('assets/fonts/BeVietnamPro-Bold.ttf', 40); print('font ok')"
```
Expected: `font ok`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_scaffold.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini src/ tests/ config/ assets/
git commit -m "chore: project scaffold, config templates, test harness"
```

---

## Task 2: `models.py` + `state.py`

**Files:**
- Create: `src/pipeline/models.py`, `src/pipeline/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `models.Candidate` dataclass: `url:str, title:str, source:str, published_at:datetime, raw_score_hint:float, summary:str, full_text:str, top_image:str|None`; methods `to_dict()->dict`, `from_dict(d)->Candidate`, property `url_hash:str` (sha1 of normalised url).
  - `models.PostContent` dataclass: `angle:str, caption_fb:str, caption_ig:str, hashtags:list[str], thumbnail_prompt:str, thumbnail_title:str, youtube_title:str, youtube_desc:str, tiktok_caption:str, source_url:str, source_name:str`; `to_dict()`, `from_dict()`.
  - `state.State(data_dir:Path)` with: `seen_has(url_hash)->bool`, `seen_add_many(hashes:Iterable[str])->None`, `pending_add(record:dict)->Path`, `pending_list()->list[dict]`, `pending_remove(pid:str)->None`, `posted_save(record:dict)->Path`, `offset_load()->int`, `offset_save(v:int)->None`. All writes atomic via temp file + `os.replace`.

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
from datetime import datetime, timezone
from pathlib import Path
from pipeline.models import Candidate, PostContent
from pipeline.state import State

def _cand():
    return Candidate(url="https://x.com/a?b=1", title="T", source="rss:x",
                     published_at=datetime(2026,9,3,tzinfo=timezone.utc),
                     raw_score_hint=10.0, summary="s", full_text="", top_image=None)

def test_candidate_roundtrip_and_hash():
    c = _cand()
    assert c.url_hash == Candidate.from_dict(c.to_dict()).url_hash
    # trailing slash / scheme differences normalise to same hash
    c2 = Candidate.from_dict({**c.to_dict(), "url": "http://x.com/a?b=1/"})
    assert c2.url_hash == c.url_hash

def test_postcontent_roundtrip():
    p = PostContent(angle="tin-tuc", caption_fb="a", caption_ig="b", hashtags=["#AI"],
                    thumbnail_prompt="p", thumbnail_title="t", youtube_title="y",
                    youtube_desc="d", tiktok_caption="tk", source_url="u", source_name="n")
    assert PostContent.from_dict(p.to_dict()) == p

def test_seen_add_and_check(tmp_path):
    s = State(tmp_path)
    assert not s.seen_has("h1")
    s.seen_add_many(["h1", "h2"])
    assert s.seen_has("h1") and s.seen_has("h2")
    s2 = State(tmp_path)  # reload from disk
    assert s2.seen_has("h2")

def test_pending_lifecycle(tmp_path):
    s = State(tmp_path)
    p = s.pending_add({"id": "p1", "created_at": "2026-09-03T00:00:00Z"})
    assert p.exists()
    assert [r["id"] for r in s.pending_list()] == ["p1"]
    s.pending_remove("p1")
    assert s.pending_list() == []

def test_offset(tmp_path):
    s = State(tmp_path)
    assert s.offset_load() == 0
    s.offset_save(42)
    assert State(tmp_path).offset_load() == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.models'`.

- [ ] **Step 3: Implement `models.py`**

```python
from __future__ import annotations
import hashlib, re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

def _normalise_url(url: str) -> str:
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"/+$", "", u)
    return u

@dataclass
class Candidate:
    url: str
    title: str
    source: str
    published_at: datetime
    raw_score_hint: float = 0.0
    summary: str = ""
    full_text: str = ""
    top_image: str | None = None

    @property
    def url_hash(self) -> str:
        return hashlib.sha1(_normalise_url(self.url).encode()).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = self.published_at.astimezone(timezone.utc).isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        d = dict(d)
        pa = d["published_at"]
        if isinstance(pa, str):
            d["published_at"] = datetime.fromisoformat(pa.replace("Z", "+00:00"))
        return cls(**d)

@dataclass
class PostContent:
    angle: str
    caption_fb: str
    caption_ig: str
    hashtags: list[str]
    thumbnail_prompt: str
    thumbnail_title: str
    youtube_title: str
    youtube_desc: str
    tiktok_caption: str
    source_url: str
    source_name: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PostContent":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})
```

- [ ] **Step 4: Implement `state.py`**

```python
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Iterable

def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

class State:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.seen_path = self.dir / "seen.json"
        self.pending_dir = self.dir / "pending"
        self.posted_dir = self.dir / "posted"
        self.offset_path = self.dir / "telegram_offset.json"

    # ---- seen ----
    def _seen(self) -> dict:
        return _read_json(self.seen_path, {})

    def seen_has(self, url_hash: str) -> bool:
        return url_hash in self._seen()

    def seen_add_many(self, hashes: Iterable[str]) -> None:
        from datetime import datetime, timezone
        data = self._seen()
        now = datetime.now(timezone.utc).isoformat()
        for h in hashes:
            data.setdefault(h, now)
        _atomic_write(self.seen_path, json.dumps(data, ensure_ascii=False, indent=2))

    # ---- pending ----
    def pending_add(self, record: dict) -> Path:
        p = self.pending_dir / f"{record['id']}.json"
        _atomic_write(p, json.dumps(record, ensure_ascii=False, indent=2))
        return p

    def pending_list(self) -> list[dict]:
        if not self.pending_dir.exists():
            return []
        return [json.loads(f.read_text(encoding="utf-8"))
                for f in sorted(self.pending_dir.glob("*.json"))]

    def pending_remove(self, pid: str) -> None:
        p = self.pending_dir / f"{pid}.json"
        if p.exists():
            p.unlink()

    # ---- posted ----
    def posted_save(self, record: dict) -> Path:
        p = self.posted_dir / f"{record['id']}.json"
        _atomic_write(p, json.dumps(record, ensure_ascii=False, indent=2))
        return p

    # ---- telegram offset ----
    def offset_load(self) -> int:
        return int(_read_json(self.offset_path, {"offset": 0})["offset"])

    def offset_save(self, v: int) -> None:
        _atomic_write(self.offset_path, json.dumps({"offset": int(v)}))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_state.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/models.py src/pipeline/state.py tests/test_state.py
git commit -m "feat: data models and atomic JSON state store"
```

---

## Task 3: `llm.py` — Claude → Gemini fallback

**Files:**
- Create: `src/pipeline/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `llm.LLMError(Exception)`.
  - `llm.parse_json_response(text:str)->dict` — strips ```` ```json ```` / ```` ``` ```` fences and leading prose, returns first JSON object.
  - `llm.generate(system:str, user:str, provider:str="auto", timeout:int=90)->str` — returns raw model text. `provider` ∈ `{"auto","claude","gemini"}`. `auto` tries Claude then Gemini; raises `LLMError` if all configured backends fail.
  - Internal `_claude(system,user,timeout)->str` and `_gemini(system,user,timeout)->str` (monkeypatched in tests).

- [ ] **Step 1: Write the failing test**

`tests/test_llm.py`:
```python
import pytest
from pipeline import llm

def test_parse_json_strips_fences():
    txt = 'Đây là kết quả:\n```json\n{"a": 1, "b": "x"}\n```\n'
    assert llm.parse_json_response(txt) == {"a": 1, "b": "x"}

def test_parse_json_plain_object():
    assert llm.parse_json_response('{"a": 2}') == {"a": 2}

def test_parse_json_bad_raises():
    with pytest.raises(llm.LLMError):
        llm.parse_json_response("no json here")

def test_auto_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(llm, "_claude", lambda s, u, t: (_ for _ in ()).throw(RuntimeError("no token")))
    monkeypatch.setattr(llm, "_gemini", lambda s, u, t: '{"ok": true}')
    assert llm.generate("sys", "usr", provider="auto") == '{"ok": true}'

def test_auto_all_fail_raises(monkeypatch):
    monkeypatch.setattr(llm, "_claude", lambda s, u, t: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(llm, "_gemini", lambda s, u, t: (_ for _ in ()).throw(RuntimeError("y")))
    with pytest.raises(llm.LLMError):
        llm.generate("s", "u", provider="auto")

def test_explicit_claude_only(monkeypatch):
    called = {}
    monkeypatch.setattr(llm, "_claude", lambda s, u, t: called.setdefault("c", True) or "OUT")
    monkeypatch.setattr(llm, "_gemini", lambda s, u, t: called.setdefault("g", True) or "NOPE")
    assert llm.generate("s", "u", provider="claude") == "OUT"
    assert "g" not in called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.llm'`.

- [ ] **Step 3: Implement `llm.py`**

```python
from __future__ import annotations
import json, os, re, subprocess

class LLMError(Exception):
    pass

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

def parse_json_response(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    m = _JSON_RE.search(text)
    if not m:
        raise LLMError(f"no JSON object in model output: {text[:200]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMError(f"invalid JSON in model output: {e}") from e

def _claude(system: str, user: str, timeout: int) -> str:
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN not set")
    prompt = f"{system}\n\n{user}"
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude cli exit {proc.returncode}: {proc.stderr[:300]}")
    payload = json.loads(proc.stdout)
    if payload.get("is_error"):
        raise RuntimeError(f"claude returned error: {payload.get('result','')[:300]}")
    return payload["result"]

def _gemini(system: str, user: str, timeout: int) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"{system}\n\n{user}",
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return resp.text

_ORDER = {"auto": ["_claude", "_gemini"], "claude": ["_claude"], "gemini": ["_gemini"]}

def generate(system: str, user: str, provider: str = "auto", timeout: int = 90) -> str:
    backends = _ORDER.get(provider)
    if backends is None:
        raise LLMError(f"unknown provider {provider!r}")
    errors = []
    for name in backends:
        fn = globals()[name]
        try:
            return fn(system, user, timeout)
        except Exception as e:  # noqa: BLE001 - deliberate: try next backend
            errors.append(f"{name}: {e}")
    raise LLMError("all LLM backends failed -> " + " | ".join(errors))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/llm.py tests/test_llm.py
git commit -m "feat: LLM abstraction with Claude CLI primary and Gemini fallback"
```

---

## Task 4: `collect.py` — gather candidates

**Files:**
- Create: `src/pipeline/collect.py`
- Create fixtures: `tests/fixtures/sample_feed.xml`, `tests/fixtures/sample_hn.json`, `tests/fixtures/sample_reddit.json`, `tests/fixtures/sample_article.html`
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `models.Candidate`, `state.State`.
- Produces:
  - `collect._get(url:str, params:dict|None=None)->httpx.Response` — single choke-point for HTTP GET (monkeypatched in tests).
  - `collect._extract(url:str)->tuple[str,str|None]` — `(full_text, top_image)` via trafilatura (monkeypatched in tests).
  - `collect.from_rss(feeds:list[dict], now:datetime)->list[Candidate]`
  - `collect.from_hn(min_points:int, now:datetime)->list[Candidate]`
  - `collect.from_reddit(subs:list[str], min_ups:int, now:datetime)->list[Candidate]`
  - `collect.from_facebook(pages:list[dict], rsshub_base:str, now:datetime)->list[Candidate]`
  - `collect.from_manual(path:Path)->list[Candidate]`
  - `collect.collect(sources:dict, settings:dict, seen:State, now:datetime, fulltext_top:int=5)->list[Candidate]` — merges all sources, drops candidates whose `url_hash` is in `seen`, dedupes by `url_hash`, sorts by `published_at` desc, fills `full_text`/`top_image` for the newest `fulltext_top`. Per-source exceptions are caught and logged; if **all** sources yield nothing **and** at least one raised, raises `collect.CollectError`.

- [ ] **Step 1: Create fixtures**

`tests/fixtures/sample_feed.xml`:
```xml
<?xml version="1.0"?>
<rss version="2.0"><channel><title>Demo</title>
  <item><title>OpenAI ra model mới</title><link>https://openai.com/blog/new-model</link>
    <description>Tóm tắt về model mới.</description>
    <pubDate>Wed, 03 Sep 2026 00:00:00 GMT</pubDate></item>
  <item><title>Bài cũ không liên quan</title><link>https://openai.com/blog/old</link>
    <description>abc</description>
    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
</channel></rss>
```

`tests/fixtures/sample_hn.json`:
```json
{"hits":[
  {"title":"New AI agent framework","url":"https://example.com/agent","points":180,
   "created_at":"2026-09-03T00:00:00Z"},
  {"title":"Low score AI post","url":"https://example.com/low","points":10,
   "created_at":"2026-09-03T00:00:00Z"}
]}
```

`tests/fixtures/sample_reddit.json`:
```json
{"data":{"children":[
  {"data":{"title":"LLaMA 4 leaked","url":"https://reddit.com/r/LocalLLaMA/x","ups":500,
    "created_utc":1788393600,"selftext":"details"}},
  {"data":{"title":"weak post","url":"https://reddit.com/r/LocalLLaMA/y","ups":20,
    "created_utc":1788393600,"selftext":""}}
]}}
```

`tests/fixtures/sample_article.html`:
```html
<html><head><meta property="og:image" content="https://example.com/hero.jpg"></head>
<body><article><p>Đây là nội dung đầy đủ của bài viết về AI. Nó dài hơn phần tóm tắt.</p>
</article></body></html>
```

- [ ] **Step 2: Write the failing test**

`tests/test_collect.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import collect
from pipeline.state import State
from tests.conftest import FIXTURES

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)

class FakeResp:
    def __init__(self, text="", data=None, status=200):
        self._text = text
        self._data = data
        self.status_code = status
    @property
    def text(self): return self._text
    def json(self): return self._data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

def test_from_rss_filters_old_and_builds_candidate(monkeypatch):
    xml = (FIXTURES / "sample_feed.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(text=xml))
    cands = collect.from_rss([{"name": "OpenAI Blog", "url": "http://x/feed"}], NOW)
    assert len(cands) == 1
    c = cands[0]
    assert c.title == "OpenAI ra model mới"
    assert c.source == "rss:OpenAI Blog"
    assert c.url == "https://openai.com/blog/new-model"

def test_from_hn_applies_min_points(monkeypatch):
    data = json.loads((FIXTURES / "sample_hn.json").read_text())
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(data=data))
    cands = collect.from_hn(min_points=50, now=NOW)
    assert [c.title for c in cands] == ["New AI agent framework"]
    assert cands[0].raw_score_hint == 180

def test_from_reddit_applies_min_ups(monkeypatch):
    data = json.loads((FIXTURES / "sample_reddit.json").read_text())
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(data=data))
    cands = collect.from_reddit(["LocalLLaMA"], min_ups=100, now=NOW)
    assert [c.title for c in cands] == ["LLaMA 4 leaked"]
    assert cands[0].source == "reddit:LocalLLaMA"

def test_from_manual_reads_urls(tmp_path, monkeypatch):
    f = tmp_path / "fb.txt"
    f.write_text("# comment\nhttps://facebook.com/post/1\n\nhttps://facebook.com/post/2\n",
                 encoding="utf-8")
    monkeypatch.setattr(collect, "_extract", lambda url: ("full text", "https://img/x.jpg"))
    cands = collect.from_manual(f)
    assert [c.url for c in cands] == ["https://facebook.com/post/1", "https://facebook.com/post/2"]
    assert all(c.source == "manual" for c in cands)

def test_collect_dedupes_and_drops_seen(tmp_path, monkeypatch):
    xml = (FIXTURES / "sample_feed.xml").read_text(encoding="utf-8")
    hn = json.loads((FIXTURES / "sample_hn.json").read_text())
    def fake_get(url, params=None):
        return FakeResp(text=xml) if "feed" in url else FakeResp(data=hn)
    monkeypatch.setattr(collect, "_get", fake_get)
    monkeypatch.setattr(collect, "_extract", lambda url: ("body", "https://img/a.jpg"))
    sources = {"rss": [{"name": "OpenAI Blog", "url": "http://x/feed"}],
               "subreddits": [], "reddit_min_ups": 100, "hn_min_points": 50,
               "facebook_pages": [], "keywords": []}
    st = State(tmp_path)
    first = collect.collect(sources, {"rsshub_base": "http://rss"}, st, NOW)
    assert len(first) == 2
    st.seen_add_many([c.url_hash for c in first])
    second = collect.collect(sources, {"rsshub_base": "http://rss"}, st, NOW)
    assert second == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_collect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.collect'`.

- [ ] **Step 4: Implement `collect.py`**

```python
from __future__ import annotations
import logging, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx

from .models import Candidate
from .state import State

log = logging.getLogger("collect")
_HTTP = httpx.Client(timeout=20.0, follow_redirects=True,
                     headers={"User-Agent": "ai-social-bot/0.1 (+github actions)"})
MAX_AGE_HOURS = 48

class CollectError(Exception):
    pass

def _get(url: str, params: dict | None = None) -> httpx.Response:
    r = _HTTP.get(url, params=params)
    r.raise_for_status()
    return r

def _extract(url: str) -> tuple[str, str | None]:
    import trafilatura
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return "", None
    text = trafilatura.extract(downloaded, include_comments=False) or ""
    meta = trafilatura.extract_metadata(downloaded)
    image = getattr(meta, "image", None) if meta else None
    return text, image

def _fresh(dt: datetime, now: datetime) -> bool:
    return (now - dt) <= timedelta(hours=MAX_AGE_HOURS) and dt <= now + timedelta(hours=1)

def _parse_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        v = entry.get(key)
        if v:
            return datetime(*v[:6], tzinfo=timezone.utc)
    return None

def from_rss(feeds: list[dict], now: datetime) -> list[Candidate]:
    out: list[Candidate] = []
    for feed in feeds:
        try:
            raw = _get(feed["url"]).text
        except Exception as e:  # noqa: BLE001
            log.warning("rss %s failed: %s", feed["name"], e)
            continue
        parsed = feedparser.parse(raw)
        for e in parsed.entries:
            dt = _parse_date(e)
            if not dt or not _fresh(dt, now):
                continue
            out.append(Candidate(
                url=e.get("link", ""), title=e.get("title", "").strip(),
                source=f"rss:{feed['name']}", published_at=dt,
                summary=feedparser.util.FeedParserDict(e).get("summary", "")[:500]))
    return out

def from_hn(min_points: int, now: datetime) -> list[Candidate]:
    data = _get("http://hn.algolia.com/api/v1/search_by_date",
                params={"tags": "story", "query": "AI", "numericFilters": f"points>={min_points}"}).json()
    out = []
    for h in data.get("hits", []):
        if not h.get("url") or (h.get("points") or 0) < min_points:
            continue
        dt = datetime.fromisoformat(h["created_at"].replace("Z", "+00:00"))
        if not _fresh(dt, now):
            continue
        out.append(Candidate(url=h["url"], title=h["title"].strip(), source="hn",
                             published_at=dt, raw_score_hint=float(h["points"]),
                             summary=h["title"]))
    return out

def from_reddit(subs: list[str], min_ups: int, now: datetime) -> list[Candidate]:
    out = []
    for sub in subs:
        try:
            data = _get(f"https://www.reddit.com/r/{sub}/top.json",
                        params={"t": "day", "limit": 25}).json()
        except Exception as e:  # noqa: BLE001
            log.warning("reddit r/%s failed: %s", sub, e)
            continue
        for child in data.get("data", {}).get("children", []):
            d = child["data"]
            if (d.get("ups") or 0) < min_ups or not d.get("url"):
                continue
            dt = datetime.fromtimestamp(d["created_utc"], tz=timezone.utc)
            if not _fresh(dt, now):
                continue
            out.append(Candidate(url=d["url"], title=d["title"].strip(),
                                 source=f"reddit:{sub}", published_at=dt,
                                 raw_score_hint=float(d["ups"]),
                                 summary=(d.get("selftext") or d["title"])[:500]))
    return out

def from_facebook(pages: list[dict], rsshub_base: str, now: datetime) -> list[Candidate]:
    out = []
    for pg in pages:
        url = f"{rsshub_base.rstrip('/')}/facebook/page/{pg['id']}"
        try:
            raw = _get(url).text
        except Exception as e:  # noqa: BLE001
            log.warning("facebook page %s via rss-bridge failed: %s", pg.get("name"), e)
            continue
        parsed = feedparser.parse(raw)
        for e in parsed.entries:
            dt = _parse_date(e) or now
            if not _fresh(dt, now):
                continue
            out.append(Candidate(url=e.get("link", ""), title=e.get("title", "").strip()[:200],
                                 source=f"facebook:{pg.get('name', pg['id'])}",
                                 published_at=dt, summary=e.get("summary", "")[:500]))
    return out

def from_manual(path: Path) -> list[Candidate]:
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        text, image = _extract(line)
        out.append(Candidate(url=line, title=(text[:80] or "Bài Facebook"), source="manual",
                             published_at=datetime.now(timezone.utc),
                             summary=text[:500], full_text=text, top_image=image))
    return out

def collect(sources: dict, settings: dict, seen: State, now: datetime,
            fulltext_top: int = 5) -> list[Candidate]:
    raised = False
    merged: list[Candidate] = []
    jobs = [
        lambda: from_rss(sources.get("rss", []), now),
        lambda: from_hn(sources.get("hn_min_points", 50), now),
        lambda: from_reddit(sources.get("subreddits", []), sources.get("reddit_min_ups", 100), now),
        lambda: from_facebook(sources.get("facebook_pages", []),
                              settings.get("rsshub_base", "https://rsshub.app"), now),
        lambda: from_manual(Path("config/facebook_urls.txt")),
    ]
    for job in jobs:
        try:
            merged.extend(job())
        except Exception as e:  # noqa: BLE001
            raised = True
            log.warning("source job failed: %s", e)

    dedup: dict[str, Candidate] = {}
    for c in merged:
        if not c.url or seen.seen_has(c.url_hash):
            continue
        dedup.setdefault(c.url_hash, c)
    result = sorted(dedup.values(), key=lambda c: c.published_at, reverse=True)

    if not result and raised:
        raise CollectError("all collect sources failed and produced nothing")

    for c in result[:fulltext_top]:
        if c.full_text:
            continue
        try:
            c.full_text, img = _extract(c.url)
            c.top_image = c.top_image or img
        except Exception as e:  # noqa: BLE001
            log.warning("extract %s failed: %s", c.url, e)
        time.sleep(0.5)
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_collect.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/collect.py tests/test_collect.py tests/fixtures/
git commit -m "feat: multi-source candidate collection (RSS/HN/Reddit/Facebook/manual)"
```

---

## Task 5: `score.py` — rank and pick

**Files:**
- Create: `src/pipeline/score.py`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `models.Candidate`.
- Produces:
  - `score.score_candidate(c:Candidate, now:datetime, cohort:list[Candidate], keywords:list[str])->float` — 0..100, sum of `recency` (≤40), `popularity` (≤30), `cross_source` (≤20), `keyword_fit` (≤10).
  - `score.pick(cands:list[Candidate], min_score:float, now:datetime, keywords:list[str])->tuple[Candidate|None, float]` — returns `(best, best_score)`; `(None, best_score)` when below threshold or empty.

- [ ] **Step 1: Write the failing test**

`tests/test_score.py`:
```python
import math
from datetime import datetime, timedelta, timezone
from pipeline.models import Candidate
from pipeline import score

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
KW = ["AI", "mô hình", "OpenAI"]

def mk(title, hours_old, hint, url="https://a.com/x", src="hn", summary=""):
    return Candidate(url=url, title=title, source=src,
                     published_at=NOW - timedelta(hours=hours_old),
                     raw_score_hint=hint, summary=summary or title)

def test_recency_component_decays():
    fresh = score.score_candidate(mk("AI model", 0, 0), NOW, [], KW)
    old = score.score_candidate(mk("AI model", 48, 0), NOW, [], KW)
    assert fresh > old
    assert fresh <= 100 and old >= 0

def test_popularity_is_log_scaled():
    low = score.score_candidate(mk("AI", 0, 50), NOW, [], KW)
    high = score.score_candidate(mk("AI", 0, 5000), NOW, [], KW)
    assert high > low
    assert (high - low) < 30  # log, not linear blow-up

def test_cross_source_bonus():
    a = mk("OpenAI ra GPT-5", 1, 100, url="https://openai.com/gpt5", src="hn")
    b = mk("OpenAI ra GPT-5", 1, 0, url="https://theverge.com/gpt5", src="rss:The Verge AI")
    solo = score.score_candidate(a, NOW, [a], KW)
    paired = score.score_candidate(a, NOW, [a, b], KW)
    assert paired - solo >= 15

def test_keyword_fit():
    on = score.score_candidate(mk("OpenAI ra mô hình AI mới", 1, 0), NOW, [], KW)
    off = score.score_candidate(mk("Chuyện thời tiết hôm nay", 1, 0), NOW, [], KW)
    assert on > off

def test_pick_respects_threshold():
    weak = [mk("Tin nhạt", 47, 0, summary="abc")]
    best, sc = score.pick(weak, min_score=45, now=NOW, keywords=KW)
    assert best is None and sc < 45

def test_pick_returns_top():
    cands = [mk("AI nhạt", 40, 5, url="https://a/1"),
             mk("OpenAI ra mô hình AI cực mạnh", 1, 900, url="https://a/2")]
    best, sc = score.pick(cands, min_score=45, now=NOW, keywords=KW)
    assert best.url == "https://a/2" and sc >= 45
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_score.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.score'`.

- [ ] **Step 3: Implement `score.py`**

```python
from __future__ import annotations
import math
from datetime import datetime
from difflib import SequenceMatcher

from .models import Candidate

def _recency(c: Candidate, now: datetime) -> float:
    hours = max(0.0, (now - c.published_at).total_seconds() / 3600.0)
    return max(0.0, 40.0 * (1.0 - hours / 48.0))

def _popularity(c: Candidate) -> float:
    if c.raw_score_hint <= 0:
        return 0.0
    # log10(50)->~1.7 .. log10(5000)->~3.7 ; map ~[1.5,4.0] to [0,30]
    v = (math.log10(c.raw_score_hint) - 1.5) / (4.0 - 1.5)
    return max(0.0, min(1.0, v)) * 30.0

def _cross_source(c: Candidate, cohort: list[Candidate]) -> float:
    for other in cohort:
        if other is c or other.url == c.url:
            continue
        if SequenceMatcher(None, c.title.lower(), other.title.lower()).ratio() >= 0.6:
            return 20.0
    return 0.0

def _keyword_fit(c: Candidate, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    text = f"{c.title} {c.summary}".lower()
    hits = sum(1 for k in keywords if k.lower() in text)
    return min(1.0, hits / 3.0) * 10.0

def score_candidate(c: Candidate, now: datetime, cohort: list[Candidate],
                    keywords: list[str]) -> float:
    return round(_recency(c, now) + _popularity(c) + _cross_source(c, cohort)
                 + _keyword_fit(c, keywords), 2)

def pick(cands: list[Candidate], min_score: float, now: datetime,
         keywords: list[str]) -> tuple[Candidate | None, float]:
    if not cands:
        return None, 0.0
    scored = [(score_candidate(c, now, cands, keywords), c) for c in cands]
    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best = scored[0]
    if best_score < min_score:
        return None, best_score
    return best, best_score
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_score.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/score.py tests/test_score.py
git commit -m "feat: virality scoring and top-story selection"
```

---

## Task 6: `write.py` — LLM to PostContent

**Files:**
- Create: `src/pipeline/write.py`
- Create fixture: `tests/fixtures/sample_llm_response.json`
- Test: `tests/test_write.py`

**Interfaces:**
- Consumes: `models.Candidate`, `models.PostContent`, `llm.generate`, `llm.parse_json_response`, `llm.LLMError`.
- Produces:
  - `write.WriteError(Exception)`.
  - `write.ALLOWED_ANGLES: set[str]` = `{"tin-tuc","ung-dung-mmo","phan-tich","giat-gan"}`.
  - `write.build_prompt(cand:Candidate, voice:dict)->tuple[str,str]` — `(system, user)`.
  - `write.write_post(cand:Candidate, voice:dict, generate=llm.generate)->PostContent` — calls `generate`, parses JSON, validates required keys and `angle`; missing/invalid → `WriteError`. Guarantees `caption_fb` ends with `Nguồn: <source_name> — <source_url>` (appends if the model omitted it).

- [ ] **Step 1: Create fixture**

`tests/fixtures/sample_llm_response.json`:
```json
{
  "angle": "tin-tuc",
  "caption_fb": "AI tuần này lại có biến: OpenAI vừa ra model mới nhanh hơn 2 lần. Mình thấy điểm đáng chú ý là chi phí giảm mạnh. Bạn nghĩ sao?",
  "caption_ig": "OpenAI ra model mới, nhanh gấp đôi, rẻ hơn. Chi tiết ở bài. #AI",
  "hashtags": ["#AI", "#OpenAI", "#congnghe", "#trituenhantao", "#tin247"],
  "thumbnail_prompt": "futuristic glowing neural network core, blue and violet, cinematic, no text",
  "thumbnail_title": "OpenAI RA MODEL MỚI",
  "youtube_title": "OpenAI vừa ra model mới - nhanh gấp đôi, rẻ hơn",
  "youtube_desc": "Tóm tắt tin OpenAI ra model mới. Nguồn trong mô tả.",
  "tiktok_caption": "OpenAI ra model mới nè 👀 #AI #OpenAI"
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_write.py`:
```python
import json
from datetime import datetime, timezone
import pytest
from pipeline.models import Candidate
from pipeline import write
from tests.conftest import FIXTURES

VOICE = {"xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "giong": "thân thiện",
         "cam_ky": ["không giật tít sai"], "ten_kenh": "A Hít Official",
         "mo_bai_mau": ["Có tin này hay nè:"], "cta_mau": ["Bạn nghĩ sao?"]}

def _cand():
    return Candidate(url="https://openai.com/blog/new", title="OpenAI new model",
                     source="rss:OpenAI Blog",
                     published_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                     summary="new model", full_text="OpenAI released a faster model...")

def test_build_prompt_includes_voice_and_article():
    sysp, usr = write.build_prompt(_cand(), VOICE)
    assert "A Hít Official" in sysp
    assert "OpenAI released a faster model" in usr
    assert "JSON" in sysp

def test_write_post_parses_and_validates():
    payload = (FIXTURES / "sample_llm_response.json").read_text(encoding="utf-8")
    post = write.write_post(_cand(), VOICE, generate=lambda s, u, **k: payload)
    assert post.angle == "tin-tuc"
    assert post.hashtags[0] == "#AI"
    assert post.caption_fb.strip().endswith("Nguồn: OpenAI Blog — https://openai.com/blog/new")

def test_write_post_appends_source_if_missing():
    data = json.loads((FIXTURES / "sample_llm_response.json").read_text())
    data["caption_fb"] = "Nội dung không có nguồn."
    post = write.write_post(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))
    assert post.caption_fb.endswith("Nguồn: OpenAI Blog — https://openai.com/blog/new")

def test_write_post_bad_angle_raises():
    data = json.loads((FIXTURES / "sample_llm_response.json").read_text())
    data["angle"] = "clickbait-xyz"
    with pytest.raises(write.WriteError):
        write.write_post(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))

def test_write_post_missing_key_raises():
    data = json.loads((FIXTURES / "sample_llm_response.json").read_text())
    del data["caption_ig"]
    with pytest.raises(write.WriteError):
        write.write_post(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.write'`.

- [ ] **Step 4: Implement `write.py`**

```python
from __future__ import annotations
import json

from .llm import generate as _default_generate, parse_json_response, LLMError
from .models import Candidate, PostContent

class WriteError(Exception):
    pass

ALLOWED_ANGLES = {"tin-tuc", "ung-dung-mmo", "phan-tich", "giat-gan"}
_REQUIRED = ("angle", "caption_fb", "caption_ig", "hashtags", "thumbnail_prompt",
             "thumbnail_title", "youtube_title", "youtube_desc", "tiktok_caption")

def build_prompt(cand: Candidate, voice: dict) -> tuple[str, str]:
    system = (
        f"Bạn là biên tập viên nội dung tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" "
        f"chuyên về AI. Giọng: {voice.get('giong','')}. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. "
        "Tự chọn 'angle' phù hợp nhất với tin trong: "
        "tin-tuc (cập nhật nhanh), ung-dung-mmo (dùng để làm gì / kiếm tiền), "
        "phan-tich (góc nhìn, tác động), giat-gan (tiêu đề mạnh, cảm xúc). "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "angle, caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "thumbnail_prompt (tiếng Anh, mô tả HÌNH ẢNH, KHÔNG chứa chữ), "
        "thumbnail_title (4-10 từ tiếng Việt IN HOA), youtube_title, youtube_desc, tiktok_caption. "
        "caption_fb 150-400 từ, có xuống dòng, kết bằng một CTA. "
        "Không bịa số liệu. Toàn bộ tiếng Việt trừ thumbnail_prompt."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = (
        f"TIÊU ĐỀ GỐC: {cand.title}\n"
        f"NGUỒN: {cand.source}\n"
        f"URL: {cand.url}\n\n"
        f"NỘI DUNG BÀI GỐC:\n{article}\n"
    )
    return system, user

def _source_name(cand: Candidate) -> str:
    return cand.source.split(":", 1)[1] if ":" in cand.source else cand.source

def write_post(cand: Candidate, voice: dict, generate=_default_generate) -> PostContent:
    try:
        raw = generate(*build_prompt(cand, voice), provider="auto")
        data = parse_json_response(raw)
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e

    missing = [k for k in _REQUIRED if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"LLM response missing keys: {missing}")
    if data["angle"] not in ALLOWED_ANGLES:
        raise WriteError(f"invalid angle: {data['angle']!r}")
    if not isinstance(data["hashtags"], list):
        raise WriteError("hashtags must be a list")

    src_name = _source_name(cand)
    src_line = f"Nguồn: {src_name} — {cand.url}"
    caption_fb = data["caption_fb"].rstrip()
    if src_line not in caption_fb:
        caption_fb = f"{caption_fb}\n\n{src_line}"

    return PostContent(
        angle=data["angle"], caption_fb=caption_fb, caption_ig=data["caption_ig"].strip(),
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        thumbnail_prompt=data["thumbnail_prompt"].strip(),
        thumbnail_title=data["thumbnail_title"].strip(),
        youtube_title=data["youtube_title"].strip(), youtube_desc=data["youtube_desc"].strip(),
        tiktok_caption=data["tiktok_caption"].strip(),
        source_url=cand.url, source_name=src_name,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_write.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/write.py tests/test_write.py tests/fixtures/sample_llm_response.json
git commit -m "feat: LLM-driven Vietnamese post generation with validation"
```

---

## Task 7: `media.py` — build 3–4 images

**Files:**
- Create: `src/pipeline/media.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: `models.Candidate`, `models.PostContent`.
- Produces:
  - `media._download(url:str, timeout:int=60)->bytes` (monkeypatched in tests).
  - `media._shoot(url:str, dest:Path)->None` — Playwright screenshot to `dest` (monkeypatched in tests).
  - `media.FONT_PATH: Path` = `assets/fonts/BeVietnamPro-Bold.ttf`.
  - `media.make_thumbnail(prompt:str, title:str, dest:Path, channel:str)->Path` — 1200×630 JPEG; Pollinations bg or gradient fallback; Vietnamese title with stroke.
  - `media.fetch_source_image(url:str|None, dest:Path)->Path|None` — `None` if missing / <500px / error.
  - `media.screenshot(url:str, dest:Path)->Path|None`.
  - `media.ai_image(prompt:str, dest:Path)->Path|None`.
  - `media.build_media(cand:Candidate, post:PostContent, outdir:Path, channel:str)->tuple[list[str], bool]` — returns `(paths, low_media)`; `paths[0]` is always the thumbnail; `low_media=True` when `len(paths) < 3`; never more than 4.

- [ ] **Step 1: Write the failing test**

`tests/test_media.py`:
```python
import io
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
import pytest
from pipeline.models import Candidate, PostContent
from pipeline import media

def _png_bytes(w=1200, h=630, color=(20, 40, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()

def _post():
    return PostContent(angle="tin-tuc", caption_fb="a", caption_ig="b", hashtags=["#AI"],
                       thumbnail_prompt="glowing neural net", thumbnail_title="OPENAI RA MODEL MỚI",
                       youtube_title="y", youtube_desc="d", tiktok_caption="t",
                       source_url="https://openai.com/x", source_name="OpenAI Blog")

def _cand():
    return Candidate(url="https://openai.com/x", title="t", source="rss:OpenAI Blog",
                     published_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                     top_image="https://img/hero.jpg")

def test_make_thumbnail_dimensions(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes())
    dest = tmp_path / "01.jpg"
    out = media.make_thumbnail("neural", "TIÊU ĐỀ TIẾNG VIỆT CÓ DẤU", dest, "A Hít Official")
    with Image.open(out) as im:
        assert im.size == (1200, 630)

def test_make_thumbnail_gradient_fallback_on_download_error(tmp_path, monkeypatch):
    def boom(url, timeout=60): raise RuntimeError("pollinations down")
    monkeypatch.setattr(media, "_download", boom)
    out = media.make_thumbnail("x", "DỰ PHÒNG", tmp_path / "01.jpg", "A Hít Official")
    with Image.open(out) as im:
        assert im.size == (1200, 630)

def test_fetch_source_image_rejects_small(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes(100, 100))
    assert media.fetch_source_image("https://img/small.jpg", tmp_path / "02.jpg") is None

def test_fetch_source_image_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes(1000, 800))
    out = media.fetch_source_image("https://img/big.jpg", tmp_path / "02.jpg")
    assert out and Path(out).exists()

def test_build_media_orders_and_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes(1000, 800))
    monkeypatch.setattr(media, "_shoot", lambda url, dest: Image.new("RGB", (1280, 800)).save(dest))
    paths, low = media.build_media(_cand(), _post(), tmp_path, "A Hít Official")
    assert 3 <= len(paths) <= 4
    assert Path(paths[0]).name.startswith("01_thumbnail")
    assert low is False

def test_build_media_low_flag_when_few(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(media, "_shoot", lambda url, dest: (_ for _ in ()).throw(RuntimeError("x")))
    cand = _cand(); cand.top_image = None
    paths, low = media.build_media(cand, _post(), tmp_path, "A Hít Official")
    assert paths and Path(paths[0]).exists()  # thumbnail gradient fallback still there
    assert low is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_media.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.media'`.

- [ ] **Step 3: Implement `media.py`**

```python
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
            lines.append(cur); cur = wd
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
        raw = _download(f"https://image.pollinations.ai/prompt/{q}?width=1200&height=800&nologo=true")
        return _save_jpeg(Image.open(io.BytesIO(raw)), dest)
    except Exception as e:  # noqa: BLE001
        log.warning("ai_image failed: %s", e)
        return None

def build_media(cand: Candidate, post: PostContent, outdir: Path, channel: str) -> tuple[list[str], bool]:
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

    # dedupe by file size+first bytes, cap at 4
    seen, uniq = set(), []
    for p in paths[:4]:
        key = Path(p).stat().st_size
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq, len(uniq) < 3
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_media.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/media.py tests/test_media.py
git commit -m "feat: image pipeline (AI thumbnail, source image, screenshot, AI illustration)"
```

---

## Task 8: `telegram.py` — Bot API wrapper

**Files:**
- Create: `src/pipeline/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Consumes: env `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Produces `telegram.Telegram(token:str|None=None, chat_id:str|None=None)` with:
  - `send_message(text:str, buttons:list[tuple[str,str]]|None=None)->dict` — buttons = `(label, callback_data)` rendered as one inline-keyboard row.
  - `send_media_group(image_paths:list[str], caption:str="")->dict`
  - `send_document(path:str, caption:str="")->dict`
  - `get_updates(offset:int, timeout:int=0)->list[dict]`
  - `answer_callback(callback_id:str, text:str="")->dict`
  - `_post(method:str, data=None, files=None)->dict` — single HTTP choke-point (monkeypatched in tests).

- [ ] **Step 1: Write the failing test**

`tests/test_telegram.py`:
```python
import pytest
from pipeline.telegram import Telegram

class Recorder:
    def __init__(self): self.calls = []
    def __call__(self, method, data=None, files=None):
        self.calls.append((method, data, files)); return {"ok": True, "result": {}}

def test_send_message_with_buttons(monkeypatch):
    tg = Telegram(token="T", chat_id="C")
    rec = Recorder(); monkeypatch.setattr(tg, "_post", rec)
    tg.send_message("xin chào", buttons=[("✅ Đăng", "approve:p1"), ("❌ Bỏ", "reject:p1")])
    method, data, _ = rec.calls[0]
    assert method == "sendMessage"
    assert data["chat_id"] == "C" and data["text"] == "xin chào"
    kb = data["reply_markup"]
    assert kb["inline_keyboard"][0][0] == {"text": "✅ Đăng", "callback_data": "approve:p1"}

def test_send_media_group_builds_attachments(tmp_path, monkeypatch):
    imgs = []
    for i in range(3):
        p = tmp_path / f"{i}.jpg"; p.write_bytes(b"x"); imgs.append(str(p))
    tg = Telegram(token="T", chat_id="C")
    rec = Recorder(); monkeypatch.setattr(tg, "_post", rec)
    tg.send_media_group(imgs, caption="chú thích")
    method, data, files = rec.calls[0]
    assert method == "sendMediaGroup"
    assert len(files) == 3
    assert '"caption": "ch\\u00fa th\\u00edch"' in data["media"] or "chú thích" in data["media"]

def test_get_updates_returns_result_list(monkeypatch):
    tg = Telegram(token="T", chat_id="C")
    monkeypatch.setattr(tg, "_post", lambda m, data=None, files=None:
                        {"ok": True, "result": [{"update_id": 5}]})
    assert tg.get_updates(offset=0) == [{"update_id": 5}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.telegram'`.

- [ ] **Step 3: Implement `telegram.py`**

```python
from __future__ import annotations
import json, os
from pathlib import Path

import httpx

class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
        self.base = f"https://api.telegram.org/bot{self.token}"
        self._client = httpx.Client(timeout=60.0)

    def _post(self, method: str, data=None, files=None) -> dict:
        r = self._client.post(f"{self.base}/{method}", data=data, files=files)
        r.raise_for_status()
        return r.json()

    def send_message(self, text: str, buttons: list[tuple[str, str]] | None = None) -> dict:
        data = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        if buttons:
            data["reply_markup"] = {"inline_keyboard": [
                [{"text": lbl, "callback_data": cb} for lbl, cb in buttons]]}
        # reply_markup must be JSON-encoded when sent as form data
        if "reply_markup" in data:
            data["reply_markup"] = json.dumps(data["reply_markup"], ensure_ascii=False)
        return self._post("sendMessage", data=data)

    def send_media_group(self, image_paths: list[str], caption: str = "") -> dict:
        media, files = [], {}
        for i, p in enumerate(image_paths):
            key = f"photo{i}"
            item = {"type": "photo", "media": f"attach://{key}"}
            if i == 0 and caption:
                item["caption"] = caption
            media.append(item)
            files[key] = (Path(p).name, open(p, "rb"), "image/jpeg")
        try:
            return self._post("sendMediaGroup",
                              data={"chat_id": self.chat_id,
                                    "media": json.dumps(media, ensure_ascii=False)},
                              files=files)
        finally:
            for _, fh, _ in files.values():
                fh.close()

    def send_document(self, path: str, caption: str = "") -> dict:
        with open(path, "rb") as fh:
            return self._post("sendDocument",
                              data={"chat_id": self.chat_id, "caption": caption},
                              files={"document": (Path(path).name, fh)})

    def get_updates(self, offset: int, timeout: int = 0) -> list[dict]:
        resp = self._post("getUpdates", data={"offset": offset, "timeout": timeout})
        return resp.get("result", [])

    def answer_callback(self, callback_id: str, text: str = "") -> dict:
        return self._post("answerCallbackQuery",
                          data={"callback_query_id": callback_id, "text": text})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/telegram.py tests/test_telegram.py
git commit -m "feat: Telegram Bot API wrapper"
```

---

## Task 9: `meta.py` — Facebook/Instagram Graph API

**Files:**
- Create: `src/pipeline/meta.py`
- Test: `tests/test_meta.py`

**Interfaces:**
- Consumes: env `META_PAGE_ID`, `META_PAGE_TOKEN`, `IG_BUSINESS_ID`.
- Produces `meta.Meta(page_id, page_token, ig_id)` with classmethod `from_env()`, and:
  - `_get(path, params)->dict`, `_post(path, data=None, files=None)->dict` — HTTP choke-points; prepend `https://graph.facebook.com/v21.0/`.
  - `fb_upload_photo(image_path:str)->str` — returns `media_fbid` (`published=false`).
  - `fb_create_post(message:str, media_fbids:list[str])->dict` — returns `{"id": "<post_id>", "url": "https://facebook.com/<post_id>"}`.
  - `ig_upload_temp(image_path:str)->str` — POST to `https://tmpfiles.org/api/v1/upload`, returns direct URL (`/dl/` form).
  - `ig_create_item(image_url:str)->str` — returns child `creation_id`.
  - `ig_create_carousel(child_ids:list[str], caption:str)->str` — returns carousel `creation_id`.
  - `ig_publish(creation_id:str)->dict` — returns `{"id": "<ig_media_id>"}`.
  - `exchange_long_lived_token(app_id, app_secret, short_token)->dict`, `debug_token(token)->dict`.

- [ ] **Step 1: Write the failing test**

`tests/test_meta.py`:
```python
import pytest
from pipeline.meta import Meta

class FakeHTTP:
    def __init__(self, responses): self.responses = list(responses); self.log = []
    def _next(self, url, **kw):
        self.log.append((url, kw))
        return _R(self.responses.pop(0))

class _R:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def raise_for_status(self): pass
    def json(self): return self._p

def _meta(http):
    m = Meta(page_id="PID", page_token="TOK", ig_id="IGID")
    m._client = http
    return m

def test_fb_upload_photo_returns_fbid(monkeypatch):
    http = FakeHTTP([{"id": "111"}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    # patch open
    monkeypatch.setattr("builtins.open", lambda *a, **k: __import__("io").BytesIO(b"x"))
    assert m.fb_upload_photo("x.jpg") == "111"
    url, kw = http.log[0]
    assert "PID/photos" in url
    assert kw["data"]["published"] == "false"

def test_fb_create_post_builds_attached_media(monkeypatch):
    http = FakeHTTP([{"id": "999_888"}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    res = m.fb_create_post("nội dung", ["1", "2"])
    assert res["id"] == "999_888"
    assert res["url"].endswith("999_888")
    url, kw = http.log[0]
    assert "PID/feed" in url
    assert kw["data"]["attached_media[0]"] == '{"media_fbid":"1"}'
    assert kw["data"]["attached_media[1]"] == '{"media_fbid":"2"}'

def test_ig_upload_temp_returns_dl_url(monkeypatch):
    http = FakeHTTP([{"data": {"url": "https://tmpfiles.org/12345/pic.jpg"}}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    monkeypatch.setattr("builtins.open", lambda *a, **k: __import__("io").BytesIO(b"x"))
    assert m.ig_upload_temp("pic.jpg") == "https://tmpfiles.org/dl/12345/pic.jpg"

def test_ig_carousel_flow(monkeypatch):
    http = FakeHTTP([{"id": "c1"}, {"id": "c2"}, {"id": "caro"}, {"id": "pub"}])
    m = _meta(http)
    monkeypatch.setattr(m._client, "post", http._next, raising=False)
    a = m.ig_create_item("http://img/1.jpg")
    b = m.ig_create_item("http://img/2.jpg")
    caro = m.ig_create_carousel([a, b], "chú thích")
    pub = m.ig_publish(caro)
    assert (a, b, caro) == ("c1", "c2", "caro")
    assert pub["id"] == "pub"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_meta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.meta'`.

- [ ] **Step 3: Implement `meta.py`**

```python
from __future__ import annotations
import json, os
from pathlib import Path

import httpx

BASE = "https://graph.facebook.com/v21.0"

class Meta:
    def __init__(self, page_id: str, page_token: str, ig_id: str | None = None):
        self.page_id = page_id
        self.token = page_token
        self.ig_id = ig_id
        self._client = httpx.Client(timeout=120.0)

    @classmethod
    def from_env(cls) -> "Meta":
        return cls(os.environ["META_PAGE_ID"], os.environ["META_PAGE_TOKEN"],
                   os.environ.get("IG_BUSINESS_ID"))

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "access_token": self.token}
        r = self._client.get(f"{BASE}/{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, url: str, data=None, files=None) -> dict:
        r = self._client.post(url, data=data, files=files)
        r.raise_for_status()
        return r.json()

    # ---------- Facebook ----------
    def fb_upload_photo(self, image_path: str) -> str:
        with open(image_path, "rb") as fh:
            res = self._post(f"{BASE}/{self.page_id}/photos",
                             data={"published": "false", "access_token": self.token},
                             files={"source": (Path(image_path).name, fh, "image/jpeg")})
        return str(res["id"])

    def fb_create_post(self, message: str, media_fbids: list[str]) -> dict:
        data = {"message": message, "access_token": self.token}
        for i, fbid in enumerate(media_fbids):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": str(fbid)},
                                                      separators=(",", ":"))
        res = self._post(f"{BASE}/{self.page_id}/feed", data=data)
        pid = str(res["id"])
        return {"id": pid, "url": f"https://facebook.com/{pid}"}

    # ---------- Instagram ----------
    def ig_upload_temp(self, image_path: str) -> str:
        with open(image_path, "rb") as fh:
            res = self._post("https://tmpfiles.org/api/v1/upload",
                             files={"file": (Path(image_path).name, fh, "image/jpeg")})
        url = res["data"]["url"]           # https://tmpfiles.org/12345/pic.jpg
        return url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)

    def ig_create_item(self, image_url: str) -> str:
        res = self._post(f"{BASE}/{self.ig_id}/media",
                         data={"image_url": image_url, "is_carousel_item": "true",
                               "access_token": self.token})
        return str(res["id"])

    def ig_create_carousel(self, child_ids: list[str], caption: str) -> str:
        res = self._post(f"{BASE}/{self.ig_id}/media",
                         data={"media_type": "CAROUSEL", "children": ",".join(child_ids),
                               "caption": caption, "access_token": self.token})
        return str(res["id"])

    def ig_publish(self, creation_id: str) -> dict:
        return self._post(f"{BASE}/{self.ig_id}/media_publish",
                          data={"creation_id": creation_id, "access_token": self.token})

    # ---------- tokens ----------
    def exchange_long_lived_token(self, app_id: str, app_secret: str, short_token: str) -> dict:
        return self._get("oauth/access_token",
                         {"grant_type": "fb_exchange_token", "client_id": app_id,
                          "client_secret": app_secret, "fb_exchange_token": short_token})

    def debug_token(self, token: str) -> dict:
        return self._get("debug_token", {"input_token": token})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_meta.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/meta.py tests/test_meta.py
git commit -m "feat: Facebook/Instagram Graph API wrapper + tmpfiles image host"
```

---

## Task 10: `review.py` — pending record + Telegram preview

**Files:**
- Create: `src/pipeline/review.py`
- Test: `tests/test_review.py`

**Interfaces:**
- Consumes: `models.PostContent`, `telegram.Telegram`.
- Produces:
  - `review.build_pending(post:PostContent, images:list[str], pid:str, low_media:bool, now:datetime)->dict` — schema per spec §5.5.
  - `review.send_preview(pending:dict, tg:Telegram)->None` — sends media group + message with buttons `[("✅ Đăng","approve:<id>"),("✏️ Sửa","edit:<id>"),("❌ Bỏ","reject:<id>")]`; prefixes a `⚠️ Ít ảnh` warning line when `low_media`.

- [ ] **Step 1: Write the failing test**

`tests/test_review.py`:
```python
from datetime import datetime, timezone
from pipeline.models import PostContent
from pipeline import review

def _post():
    return PostContent(angle="tin-tuc", caption_fb="Nội dung dài.\n\nNguồn: X — https://x/y",
                       caption_ig="ngắn", hashtags=["#AI", "#OpenAI"],
                       thumbnail_prompt="p", thumbnail_title="T", youtube_title="yt",
                       youtube_desc="desc", tiktok_caption="tt",
                       source_url="https://x/y", source_name="X")

NOW = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)

def test_build_pending_schema():
    p = review.build_pending(_post(), ["a.jpg", "b.jpg", "c.jpg"], "2026-09-03-x", False, NOW)
    assert p["id"] == "2026-09-03-x"
    assert p["created_at"] == "2026-09-03T01:00:00+00:00"
    assert p["images"] == ["a.jpg", "b.jpg", "c.jpg"]
    assert p["youtube"]["title"] == "yt" and p["tiktok"]["caption"] == "tt"
    assert p["source"]["url"] == "https://x/y"
    assert p["low_media"] is False

class FakeTG:
    def __init__(self): self.msgs = []; self.groups = []
    def send_media_group(self, imgs, caption=""): self.groups.append((imgs, caption))
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))

def test_send_preview_sends_group_and_buttons():
    tg = FakeTG()
    p = review.build_pending(_post(), ["a.jpg", "b.jpg", "c.jpg"], "pid1", False, NOW)
    review.send_preview(p, tg)
    assert tg.groups and tg.groups[0][0] == ["a.jpg", "b.jpg", "c.jpg"]
    text, buttons = tg.msgs[0]
    assert [b[1] for b in buttons] == ["approve:pid1", "edit:pid1", "reject:pid1"]
    assert "⚠️" not in text

def test_send_preview_low_media_warning():
    tg = FakeTG()
    p = review.build_pending(_post(), ["a.jpg"], "pid2", True, NOW)
    review.send_preview(p, tg)
    assert "⚠️" in tg.msgs[0][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.review'`.

- [ ] **Step 3: Implement `review.py`**

```python
from __future__ import annotations
from datetime import datetime

from .models import PostContent
from .telegram import Telegram

def build_pending(post: PostContent, images: list[str], pid: str,
                  low_media: bool, now: datetime) -> dict:
    return {
        "id": pid,
        "created_at": now.isoformat(),
        "angle": post.angle,
        "caption_fb": post.caption_fb,
        "caption_ig": post.caption_ig,
        "hashtags": post.hashtags,
        "images": list(images),
        "youtube": {"title": post.youtube_title, "desc": post.youtube_desc},
        "tiktok": {"caption": post.tiktok_caption},
        "source": {"url": post.source_url, "name": post.source_name},
        "low_media": low_media,
    }

def send_preview(pending: dict, tg: Telegram) -> None:
    tg.send_media_group(pending["images"])
    lines = []
    if pending.get("low_media"):
        lines.append("⚠️ Ít ảnh (<3). Kiểm tra kỹ trước khi đăng.")
    lines.append(f"[{pending['angle']}] {pending['source']['name']}")
    lines.append("")
    cap = pending["caption_fb"]
    lines.append(cap if len(cap) <= 900 else cap[:900] + " …")
    lines.append("")
    lines.append(" ".join(pending["hashtags"]))
    pid = pending["id"]
    tg.send_message("\n".join(lines),
                    buttons=[("✅ Đăng", f"approve:{pid}"),
                             ("✏️ Sửa", f"edit:{pid}"),
                             ("❌ Bỏ", f"reject:{pid}")])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_review.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/review.py tests/test_review.py
git commit -m "feat: pending-post record and Telegram approval preview"
```

---

## Task 11: `publish.py` — post to FB + IG, write YT/TikTok files

**Files:**
- Create: `src/pipeline/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `meta.Meta`, pending dict (Task 10 schema).
- Produces:
  - `publish.publish(pending:dict, meta:Meta, outdir:Path)->dict` — posts FB (upload each image → create post), then IG (upload each temp → create items → carousel → publish). Writes `outdir/youtube.txt` and `outdir/tiktok.txt`. Returns record:
    ```python
    {"id": pid, "posted_at": iso, "angle": ...,
     "facebook": {"ok": bool, "post_id"?: str, "url"?: str, "error"?: str},
     "instagram": {"ok": bool, "media_id"?: str, "error"?: str},
     "youtube_file": "…/youtube.txt", "tiktok_file": "…/tiktok.txt"}
    ```
    A failure in one platform is caught, recorded as `ok:false` + `error`, and does **not** prevent the other platform or the file writes. Raises only if **both** platforms fail.
  - `publish.PublishError(Exception)`.

- [ ] **Step 1: Write the failing test**

`tests/test_publish.py`:
```python
from pathlib import Path
import pytest
from pipeline import publish

def _pending(imgs):
    return {"id": "2026-09-03-x", "angle": "tin-tuc",
            "caption_fb": "FB caption\n\nNguồn: X — https://x/y",
            "caption_ig": "IG caption", "hashtags": ["#AI", "#OpenAI"],
            "images": imgs,
            "youtube": {"title": "YT title", "desc": "YT desc"},
            "tiktok": {"caption": "TT caption"},
            "source": {"url": "https://x/y", "name": "X"}, "low_media": False}

class FakeMeta:
    def __init__(self, fail=None):
        self.fail = fail or set()
    def fb_upload_photo(self, p):
        if "fb" in self.fail: raise RuntimeError("fb upload down")
        return "fbid-" + Path(p).stem
    def fb_create_post(self, msg, ids):
        if "fb" in self.fail: raise RuntimeError("fb post down")
        return {"id": "100_200", "url": "https://facebook.com/100_200"}
    def ig_upload_temp(self, p): return "https://tmpfiles.org/dl/1/" + Path(p).name
    def ig_create_item(self, url):
        if "ig" in self.fail: raise RuntimeError("ig item down")
        return "c-" + url[-5:]
    def ig_create_carousel(self, ids, cap): return "caro"
    def ig_publish(self, cid): return {"id": "ig-media-1"}

def test_publish_happy_path(tmp_path):
    imgs = []
    for i in range(3):
        p = tmp_path / f"{i}.jpg"; p.write_bytes(b"x"); imgs.append(str(p))
    rec = publish.publish(_pending(imgs), FakeMeta(), tmp_path)
    assert rec["facebook"]["ok"] and rec["facebook"]["url"].endswith("100_200")
    assert rec["instagram"]["ok"] and rec["instagram"]["media_id"] == "ig-media-1"
    yt = (tmp_path / "youtube.txt").read_text(encoding="utf-8")
    assert "YT title" in yt and "YT desc" in yt
    assert (tmp_path / "tiktok.txt").read_text(encoding="utf-8").strip().startswith("TT caption")

def test_publish_ig_fails_fb_ok(tmp_path):
    p = tmp_path / "a.jpg"; p.write_bytes(b"x")
    rec = publish.publish(_pending([str(p)]), FakeMeta(fail={"ig"}), tmp_path)
    assert rec["facebook"]["ok"] is True
    assert rec["instagram"]["ok"] is False and "ig item down" in rec["instagram"]["error"]

def test_publish_both_fail_raises(tmp_path):
    p = tmp_path / "a.jpg"; p.write_bytes(b"x")
    with pytest.raises(publish.PublishError):
        publish.publish(_pending([str(p)]), FakeMeta(fail={"fb", "ig"}), tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_publish.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.publish'`.

- [ ] **Step 3: Implement `publish.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from .meta import Meta

log = logging.getLogger("publish")

class PublishError(Exception):
    pass

def _publish_fb(pending: dict, meta: Meta) -> dict:
    message = pending["caption_fb"] + "\n\n" + " ".join(pending["hashtags"])
    fbids = [meta.fb_upload_photo(p) for p in pending["images"]]
    res = meta.fb_create_post(message, fbids)
    return {"ok": True, "post_id": res["id"], "url": res["url"]}

def _publish_ig(pending: dict, meta: Meta) -> dict:
    caption = pending["caption_ig"] + "\n\n" + " ".join(pending["hashtags"])
    child_ids = []
    for p in pending["images"][:10]:
        url = meta.ig_upload_temp(p)
        child_ids.append(meta.ig_create_item(url))
    caro = meta.ig_create_carousel(child_ids, caption)
    res = meta.ig_publish(caro)
    return {"ok": True, "media_id": res["id"]}

def _write_platform_files(pending: dict, outdir: Path) -> tuple[str, str]:
    outdir.mkdir(parents=True, exist_ok=True)
    tags = " ".join(pending["hashtags"])
    yt = outdir / "youtube.txt"
    yt.write_text(
        f"{pending['youtube']['title']}\n\n{pending['youtube']['desc']}\n\n{tags}\n"
        f"\nNguồn: {pending['source']['name']} — {pending['source']['url']}\n",
        encoding="utf-8")
    tt = outdir / "tiktok.txt"
    tt.write_text(f"{pending['tiktok']['caption']}\n\n{tags}\n", encoding="utf-8")
    return str(yt), str(tt)

def publish(pending: dict, meta: Meta, outdir: Path) -> dict:
    outdir = Path(outdir)
    record = {"id": pending["id"], "angle": pending.get("angle"),
              "posted_at": datetime.now(timezone.utc).isoformat()}

    try:
        record["facebook"] = _publish_fb(pending, meta)
    except Exception as e:  # noqa: BLE001
        log.error("facebook publish failed: %s", e)
        record["facebook"] = {"ok": False, "error": str(e)}

    try:
        record["instagram"] = _publish_ig(pending, meta)
    except Exception as e:  # noqa: BLE001
        log.error("instagram publish failed: %s", e)
        record["instagram"] = {"ok": False, "error": str(e)}

    yt, tt = _write_platform_files(pending, outdir)
    record["youtube_file"], record["tiktok_file"] = yt, tt

    if not record["facebook"]["ok"] and not record["instagram"]["ok"]:
        raise PublishError(f"both platforms failed: fb={record['facebook'].get('error')} "
                           f"ig={record['instagram'].get('error')}")
    return record
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_publish.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish.py tests/test_publish.py
git commit -m "feat: publish to Facebook + Instagram, emit YouTube/TikTok copy files"
```

---

## Task 12: `run.py` — build orchestrator

**Files:**
- Create: `src/pipeline/run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `collect`, `score`, `write`, `media`, `review`, `publish`, `state.State`, `telegram.Telegram`, `meta.Meta`.
- Produces:
  - `run.load_configs(root:Path)->tuple[dict,dict,dict]` → `(sources, voice, settings)`.
  - `run.make_id(cand, now)->str` → `f"{now:%Y-%m-%d}-" + slug(cand.title)[:40]`.
  - `run.build(root:Path, now:datetime, dry_run:bool, local:bool)->dict|None` — runs collect→score→write→media, writes `output/<date>/<id>/` (captions, meta.json, images), then:
    - `local` → skip network collect, load candidates from `tests/fixtures/local_candidates.json` if present else run real collect.
    - `dry_run` → do **not** send Telegram, do **not** publish; return the pending dict.
    - else `approval_mode == "telegram"` → `review.send_preview`, `state.pending_add`, return pending.
    - else (`auto`) → `publish.publish`, `state.posted_save`, return record.
    - Always `state.seen_add_many` for every collected candidate hash.
    - Returns `None` when `score.pick` yields no story (after notifying Telegram unless dry_run).
  - `run.main(argv:list[str]|None=None)->int` — argparse `--dry-run`, `--local`, `--data-dir`, `--root`; prints a one-line summary; returns process exit code.

- [ ] **Step 1: Write the failing test**

`tests/test_run.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import run
from pipeline.models import Candidate

NOW = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)

@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path
    (root / "config").mkdir()
    (root / "config/settings.yaml").write_text(
        "approval_mode: telegram\nmin_score: 45\nposts_per_day: 1\n"
        "rsshub_base: http://rss\npending_ttl_hours: 12\n", encoding="utf-8")
    (root / "config/sources.yaml").write_text(
        "rss: []\nsubreddits: []\nhn_min_points: 50\nreddit_min_ups: 100\n"
        "facebook_pages: []\nkeywords: [AI, OpenAI, mô hình]\n", encoding="utf-8")
    (root / "config/voice.yaml").write_text(
        "xung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ngiong: thân thiện\n"
        "cam_ky: [không giật tít sai]\nten_kenh: A Hít Official\n"
        "mo_bai_mau: [Có tin hay nè]\ncta_mau: [Bạn nghĩ sao]\n", encoding="utf-8")
    return root

def _fake_candidate():
    return Candidate(url="https://openai.com/blog/new-model", title="OpenAI ra mô hình AI mới cực mạnh",
                     source="rss:OpenAI Blog", published_at=NOW, raw_score_hint=900,
                     summary="OpenAI ra mô hình AI mới", full_text="Chi tiết mô hình AI mới của OpenAI.")

LLM_JSON = json.dumps({
    "angle": "tin-tuc", "caption_fb": "Bài dài về AI.", "caption_ig": "ngắn",
    "hashtags": ["#AI", "#OpenAI", "#congnghe"], "thumbnail_prompt": "neural core",
    "thumbnail_title": "OPENAI RA MODEL MỚI", "youtube_title": "YT", "youtube_desc": "D",
    "tiktok_caption": "TT"}, ensure_ascii=False)

def test_build_dry_run_produces_output(project, monkeypatch):
    monkeypatch.setattr(run.collect, "collect", lambda *a, **k: [_fake_candidate()])
    monkeypatch.setattr(run.write, "_default_generate", lambda *a, **k: LLM_JSON, raising=False)
    monkeypatch.setattr(run, "_generate", lambda s, u, **k: LLM_JSON, raising=False)
    monkeypatch.setattr(run.write, "write_post",
                        lambda cand, voice, generate=None: run.write.write_post.__wrapped__(cand, voice, generate=lambda s, u, **k: LLM_JSON)
                        if hasattr(run.write.write_post, "__wrapped__") else __import__("pipeline.write", fromlist=["write_post"]).write_post(cand, voice, generate=lambda s, u, **k: LLM_JSON))
    monkeypatch.setattr(run.media, "build_media",
                        lambda cand, post, outdir, channel: ([str(Path(outdir) / "img/01_thumbnail.jpg")], True))
    (project / "output").mkdir(exist_ok=True)
    # ensure the thumbnail path exists so downstream code that stats it is happy
    monkeypatch.setattr(run.media, "build_media",
                        lambda cand, post, outdir, channel: (
                            [_touch(Path(outdir) / "img/01_thumbnail.jpg")], True))
    pending = run.build(project, NOW, dry_run=True, local=False)
    assert pending["id"].startswith("2026-09-03-")
    out_dir = project / "output" / "2026-09-03" / pending["id"]
    assert (out_dir / "caption_fb.txt").exists()
    assert (out_dir / "meta.json").exists()

def _touch(p: Path) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return str(p)

def test_build_no_story_returns_none(project, monkeypatch):
    monkeypatch.setattr(run.collect, "collect", lambda *a, **k: [])
    sent = []
    monkeypatch.setattr(run, "_notify", lambda msg: sent.append(msg))
    assert run.build(project, NOW, dry_run=False, local=False) is None
    assert sent and "không có tin" in sent[0].lower()

def test_make_id_slugifies():
    c = _fake_candidate()
    assert run.make_id(c, NOW) == "2026-09-03-openai-ra-mo-hinh-ai-moi-cuc-manh"[:53]
```

> Note for implementer: `test_build_dry_run_produces_output` only needs `run.build` to (a) call `collect.collect`, (b) call `write.write_post` with an injected generate, (c) call `media.build_media`, (d) write `caption_fb.txt` + `meta.json` + `caption_ig.txt` + `youtube.txt` + `tiktok.txt` under `output/<date>/<id>/`, (e) return the pending dict. Keep `run.build` accepting an optional `generate=` param defaulting to `llm.generate` so tests inject a stub; the monkeypatch mess above collapses to `monkeypatch.setattr(run, "_generate", lambda *a, **k: LLM_JSON)` once `run.build` reads `run._generate`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run.py -v`
Expected: FAIL — `AttributeError` / `ModuleNotFoundError` for `pipeline.run`.

- [ ] **Step 3: Implement `run.py`**

```python
from __future__ import annotations
import argparse, json, logging, re, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import collect, score, write, media, review, publish
from .llm import generate as _generate
from .state import State

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("run")

def load_configs(root: Path) -> tuple[dict, dict, dict]:
    c = root / "config"
    return (yaml.safe_load((c / "sources.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "voice.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "settings.yaml").read_text(encoding="utf-8")))

def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)

def make_id(cand, now: datetime) -> str:
    return f"{now:%Y-%m-%d}-{_slug(cand.title)[:40]}".rstrip("-")

def _notify(msg: str) -> None:
    try:
        from .telegram import Telegram
        Telegram().send_message(msg)
    except Exception as e:  # noqa: BLE001
        log.warning("telegram notify failed: %s", e)

def _load_local_candidates(root: Path) -> list:
    f = root / "tests/fixtures/local_candidates.json"
    if not f.exists():
        return []
    from .models import Candidate
    return [Candidate.from_dict(d) for d in json.loads(f.read_text(encoding="utf-8"))]

def build(root: Path, now: datetime, dry_run: bool, local: bool, generate=None) -> dict | None:
    generate = generate or _generate
    root = Path(root)
    sources, voice, settings = load_configs(root)
    data_dir = root / "data"
    st = State(data_dir)

    if local:
        cands = _load_local_candidates(root) or collect.collect(sources, settings, st, now)
    else:
        cands = collect.collect(sources, settings, st, now)
    log.info("collected %d candidates", len(cands))

    st.seen_add_many([c.url_hash for c in cands])

    best, best_score = score.pick(cands, settings.get("min_score", 45), now,
                                  sources.get("keywords", []))
    if best is None:
        log.info("no story above threshold (best=%.1f)", best_score)
        if not dry_run:
            _notify(f"Hôm nay không có tin AI đủ nóng (điểm cao nhất {best_score:.0f}/{settings.get('min_score',45)}).")
        return None
    log.info("picked: %s (score %.1f)", best.title, best_score)

    post = write.write_post(best, voice, generate=generate)

    pid = make_id(best, now)
    out_dir = root / "output" / f"{now:%Y-%m-%d}" / pid
    (out_dir / "img").mkdir(parents=True, exist_ok=True)

    images, low_media = media.build_media(best, post, out_dir, voice.get("ten_kenh", ""))

    (out_dir / "caption_fb.txt").write_text(post.caption_fb + "\n\n" + " ".join(post.hashtags), encoding="utf-8")
    (out_dir / "caption_ig.txt").write_text(post.caption_ig + "\n\n" + " ".join(post.hashtags), encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(
        {"candidate": best.to_dict(), "post": post.to_dict(), "images": images,
         "low_media": low_media, "score": best_score}, ensure_ascii=False, indent=2), encoding="utf-8")

    pending = review.build_pending(post, images, pid, low_media, now)

    if dry_run:
        log.info("dry-run: wrote %s (no telegram, no publish)", out_dir)
        return pending

    mode = settings.get("approval_mode", "telegram")
    if mode == "telegram":
        from .telegram import Telegram
        review.send_preview(pending, Telegram())
        st.pending_add(pending)
        log.info("sent Telegram preview for %s", pid)
        return pending

    from .meta import Meta
    record = publish.publish(pending, Meta.from_env(), out_dir)
    st.posted_save(record)
    _notify(_summary_line(record))
    return record

def _summary_line(record: dict) -> str:
    fb = "OK" if record.get("facebook", {}).get("ok") else "LỖI"
    ig = "OK" if record.get("instagram", {}).get("ok") else "LỖI"
    return f"Đã đăng {record['id']}: Facebook {fb}, Instagram {ig}."

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI social automation — build stage")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        result = build(Path(args.root), now, dry_run=args.dry_run, local=args.local)
    except (collect.CollectError, write.WriteError, publish.PublishError) as e:
        log.error("pipeline failed: %s", e)
        if not args.dry_run:
            _notify(f"Pipeline lỗi: {e}")
        return 1
    if result is None:
        print("SUMMARY: no post today")
        return 0
    if "posted_at" in result:
        print("SUMMARY: " + _summary_line(result))
    else:
        print(f"SUMMARY: pending {result['id']} awaiting approval"
              if not args.dry_run else f"SUMMARY: dry-run built {result['id']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Simplify the test per the implementer note**

Replace the body of `test_build_dry_run_produces_output` with:
```python
def test_build_dry_run_produces_output(project, monkeypatch):
    monkeypatch.setattr(run.collect, "collect", lambda *a, **k: [_fake_candidate()])
    monkeypatch.setattr(run.media, "build_media",
                        lambda cand, post, outdir, channel: ([_touch(Path(outdir) / "img/01_thumbnail.jpg")], True))
    pending = run.build(project, NOW, dry_run=True, local=False,
                        generate=lambda s, u, **k: LLM_JSON)
    assert pending["id"].startswith("2026-09-03-")
    out_dir = project / "output" / "2026-09-03" / pending["id"]
    assert (out_dir / "caption_fb.txt").exists()
    assert (out_dir / "meta.json").exists()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_run.py -v`
Expected: 3 passed.

- [ ] **Step 6: Full suite green**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/run.py tests/test_run.py
git commit -m "feat: build-stage orchestrator with dry-run and local modes"
```

---

## Task 13: `approve_poll.py` — process Telegram callbacks

**Files:**
- Create: `src/pipeline/approve_poll.py`
- Test: `tests/test_approve_poll.py`

**Interfaces:**
- Consumes: `telegram.Telegram`, `state.State`, `meta.Meta`, `publish.publish`.
- Produces:
  - `approve_poll.handle_update(update:dict, st:State, tg:Telegram, meta:Meta, root:Path, now:datetime)->str|None` — for a `callback_query` with data `approve:<id>` / `edit:<id>` / `reject:<id>`: approve → load pending, `publish.publish`, `posted_save`, `pending_remove`, `answer_callback`, return `"approved:<id>"`; reject → `pending_remove`, return `"rejected:<id>"`; edit → `send_document(meta.json)` + images, keep pending, return `"edit:<id>"`. Unknown → `None`.
  - `approve_poll.expire_stale(st:State, tg:Telegram, ttl_hours:int, now:datetime)->list[str]` — removes pending older than `ttl_hours`, notifies, returns removed ids.
  - `approve_poll.poll(root:Path, now:datetime|None=None)->dict` — loads offset, `get_updates`, processes each, saves `max(update_id)+1`, runs `expire_stale`, returns `{"handled": [...], "expired": [...]}`.

- [ ] **Step 1: Write the failing test**

`tests/test_approve_poll.py`:
```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from pipeline import approve_poll
from pipeline.state import State

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)

class FakeTG:
    def __init__(self): self.msgs = []; self.docs = []; self.acks = []
    def send_message(self, text, buttons=None): self.msgs.append(text)
    def send_document(self, path, caption=""): self.docs.append((path, caption))
    def answer_callback(self, cid, text=""): self.acks.append((cid, text))

class FakeMeta: pass

def _pending(st, pid, created):
    rec = {"id": pid, "created_at": created.isoformat(), "angle": "tin-tuc",
           "caption_fb": "c", "caption_ig": "c", "hashtags": ["#AI"],
           "images": ["a.jpg"], "youtube": {"title": "t", "desc": "d"},
           "tiktok": {"caption": "tk"}, "source": {"url": "u", "name": "n"}, "low_media": False}
    st.pending_add(rec); return rec

def _cbq(data, uid=1):
    return {"update_id": uid, "callback_query": {"id": "cb1", "data": data,
            "message": {"message_id": 10}}}

def test_approve_publishes_and_moves(tmp_path, monkeypatch):
    st = State(tmp_path); _pending(st, "p1", NOW)
    monkeypatch.setattr(approve_poll.publish, "publish",
                        lambda pending, meta, outdir: {"id": "p1", "posted_at": NOW.isoformat(),
                                                       "facebook": {"ok": True}, "instagram": {"ok": True}})
    tg = FakeTG()
    res = approve_poll.handle_update(_cbq("approve:p1"), st, tg, FakeMeta(), tmp_path, NOW)
    assert res == "approved:p1"
    assert st.pending_list() == []
    assert (tmp_path / "data/posted/p1.json").exists()
    assert tg.acks

def test_reject_removes_pending(tmp_path):
    st = State(tmp_path); _pending(st, "p2", NOW)
    tg = FakeTG()
    res = approve_poll.handle_update(_cbq("reject:p2"), st, tg, FakeMeta(), tmp_path, NOW)
    assert res == "rejected:p2" and st.pending_list() == []

def test_edit_keeps_pending_and_sends_doc(tmp_path):
    st = State(tmp_path); _pending(st, "p3", NOW)
    (tmp_path / "output/2026-09-03/p3").mkdir(parents=True)
    (tmp_path / "output/2026-09-03/p3/meta.json").write_text("{}", encoding="utf-8")
    tg = FakeTG()
    res = approve_poll.handle_update(_cbq("edit:p3"), st, tg, FakeMeta(), tmp_path, NOW)
    assert res == "edit:p3"
    assert [r["id"] for r in st.pending_list()] == ["p3"]
    assert tg.docs

def test_expire_stale(tmp_path):
    st = State(tmp_path)
    _pending(st, "old", NOW - timedelta(hours=13))
    _pending(st, "fresh", NOW - timedelta(hours=1))
    tg = FakeTG()
    removed = approve_poll.expire_stale(st, tg, ttl_hours=12, now=NOW)
    assert removed == ["old"]
    assert [r["id"] for r in st.pending_list()] == ["fresh"]

def test_poll_advances_offset(tmp_path, monkeypatch):
    st = State(tmp_path); _pending(st, "p9", NOW)
    monkeypatch.setattr(approve_poll.publish, "publish",
                        lambda *a, **k: {"id": "p9", "posted_at": NOW.isoformat(),
                                         "facebook": {"ok": True}, "instagram": {"ok": True}})
    class TG(FakeTG):
        def get_updates(self, offset, timeout=0):
            return [] if offset else [_cbq("approve:p9", uid=7)]
    monkeypatch.setattr(approve_poll, "Telegram", lambda: TG())
    monkeypatch.setattr(approve_poll, "_meta", lambda: FakeMeta())
    out = approve_poll.poll(tmp_path, NOW)
    assert out["handled"] == ["approved:p9"]
    assert State(tmp_path).offset_load() == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_approve_poll.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.approve_poll'`.

- [ ] **Step 3: Implement `approve_poll.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import publish
from .state import State
from .telegram import Telegram

log = logging.getLogger("approve")

def _meta():
    from .meta import Meta
    return Meta.from_env()

def _find_pending(st: State, pid: str) -> dict | None:
    for rec in st.pending_list():
        if rec["id"] == pid:
            return rec
    return None

def _out_dir(root: Path, pid: str) -> Path:
    date = pid[:10]
    return Path(root) / "output" / date / pid

def handle_update(update: dict, st: State, tg: Telegram, meta, root: Path,
                  now: datetime) -> str | None:
    cbq = update.get("callback_query")
    if not cbq or ":" not in cbq.get("data", ""):
        return None
    action, pid = cbq["data"].split(":", 1)
    pending = _find_pending(st, pid)
    if pending is None:
        tg.answer_callback(cbq["id"], "Bài này không còn nữa.")
        return None

    if action == "approve":
        try:
            record = publish.publish(pending, meta, _out_dir(root, pid))
            st.posted_save(record)
            st.pending_remove(pid)
            fb = "OK" if record["facebook"]["ok"] else "LỖI"
            ig = "OK" if record["instagram"]["ok"] else "LỖI"
            tg.answer_callback(cbq["id"], "Đang đăng…")
            tg.send_message(f"✅ Đã đăng {pid}: Facebook {fb}, Instagram {ig}.")
            return f"approved:{pid}"
        except publish.PublishError as e:
            tg.answer_callback(cbq["id"], "Đăng thất bại.")
            tg.send_message(f"❌ Đăng {pid} thất bại: {e}")
            return f"failed:{pid}"

    if action == "reject":
        st.pending_remove(pid)
        tg.answer_callback(cbq["id"], "Đã bỏ.")
        tg.send_message(f"❌ Đã bỏ {pid}.")
        return f"rejected:{pid}"

    if action == "edit":
        meta_json = _out_dir(root, pid) / "meta.json"
        if meta_json.exists():
            tg.send_document(str(meta_json), caption=f"Sửa {pid}: chỉnh file rồi bấm ✅ lại.")
        for img in pending.get("images", []):
            if Path(img).exists():
                tg.send_document(img)
        tg.answer_callback(cbq["id"], "Đã gửi file để sửa.")
        return f"edit:{pid}"

    return None

def expire_stale(st: State, tg: Telegram, ttl_hours: int, now: datetime) -> list[str]:
    removed = []
    for rec in st.pending_list():
        created = datetime.fromisoformat(rec["created_at"].replace("Z", "+00:00"))
        if now - created > timedelta(hours=ttl_hours):
            st.pending_remove(rec["id"])
            removed.append(rec["id"])
    if removed:
        tg.send_message("⌛ Hết hạn 12h, đã bỏ: " + ", ".join(removed))
    return removed

def poll(root: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    settings = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
    st = State(root / "data")
    tg = Telegram()
    meta = _meta()

    offset = st.offset_load()
    updates = tg.get_updates(offset=offset)
    handled = []
    max_uid = offset - 1
    for up in updates:
        max_uid = max(max_uid, up["update_id"])
        res = handle_update(up, st, tg, meta, root, now)
        if res:
            handled.append(res)
    if updates:
        st.offset_save(max_uid + 1)

    expired = expire_stale(st, tg, settings.get("pending_ttl_hours", 12), now)
    return {"handled": handled, "expired": expired}

if __name__ == "__main__":
    print(poll(Path(".")))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_approve_poll.py -v`
Expected: 6 passed.

- [ ] **Step 5: Full suite green**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/approve_poll.py tests/test_approve_poll.py
git commit -m "feat: Telegram approval poller (approve/edit/reject/expire)"
```

---

## Task 14: GitHub Actions workflows

**Files:**
- Create: `.github/workflows/build.yml`, `.github/workflows/approve.yml`, `.github/workflows/refresh-token.yml`
- Create: `scripts/commit_state.sh`
- Test: `tests/test_workflows.py`

**Interfaces:**
- Consumes: repo secrets `META_PAGE_ID`, `META_PAGE_TOKEN`, `IG_BUSINESS_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CLAUDE_CODE_OAUTH_TOKEN`, `GEMINI_API_KEY`, plus `META_APP_ID`, `META_APP_SECRET` (refresh only).
- Produces: three workflow files that lint as valid YAML and reference `python -m pipeline.run` / `python -m pipeline.approve_poll`.

- [ ] **Step 1: Write the failing test**

`tests/test_workflows.py`:
```python
from pathlib import Path
import yaml

WF = Path(__file__).resolve().parents[1] / ".github/workflows"

def test_all_workflows_valid_yaml():
    for name in ("build.yml", "approve.yml", "refresh-token.yml"):
        data = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
        assert True in data or "on" in data  # 'on' key may parse as bool True
        assert data["jobs"]

def test_build_workflow_runs_pipeline_and_commits():
    text = (WF / "build.yml").read_text(encoding="utf-8")
    assert "python -m pipeline.run" in text
    assert "cron: '0 1 * * *'" in text
    assert "contents: write" in text
    assert "playwright install" in text

def test_approve_workflow_cron_and_module():
    text = (WF / "approve.yml").read_text(encoding="utf-8")
    assert "python -m pipeline.approve_poll" in text
    assert "*/10 * * * *" in text

def test_refresh_workflow_monthly():
    text = (WF / "refresh-token.yml").read_text(encoding="utf-8")
    assert "cron: '0 2 1 * *'" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workflows.py -v`
Expected: FAIL — `FileNotFoundError` for the workflow files.

- [ ] **Step 3: Create `scripts/commit_state.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
git config user.name "ai-social-bot"
git config user.email "bot@users.noreply.github.com"
git add data/ output/ || true
if git diff --cached --quiet; then
  echo "no state changes"
  exit 0
fi
git commit -m "chore(state): update pipeline state [skip ci]"
for i in 1 2 3; do
  if git pull --rebase --autostash && git push; then
    echo "pushed"; exit 0
  fi
  echo "push retry $i"; sleep 5
done
echo "failed to push state" >&2
exit 1
```

- [ ] **Step 4: Create `.github/workflows/build.yml`**

```yaml
name: build
on:
  schedule:
    - cron: '0 1 * * *'   # 08:00 ICT
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: build
  cancel-in-progress: false
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - name: Install deps
        run: |
          pip install -r requirements.txt
          python -m playwright install --with-deps chromium
          npm install -g @anthropic-ai/claude-code
      - name: Run build stage
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          META_PAGE_ID: ${{ secrets.META_PAGE_ID }}
          META_PAGE_TOKEN: ${{ secrets.META_PAGE_TOKEN }}
          IG_BUSINESS_ID: ${{ secrets.IG_BUSINESS_ID }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m pipeline.run
      - name: Commit state
        run: bash scripts/commit_state.sh
```

- [ ] **Step 5: Create `.github/workflows/approve.yml`**

```yaml
name: approve
on:
  schedule:
    - cron: '*/10 * * * *'
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: approve
  cancel-in-progress: false
jobs:
  approve:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Process approvals
        env:
          META_PAGE_ID: ${{ secrets.META_PAGE_ID }}
          META_PAGE_TOKEN: ${{ secrets.META_PAGE_TOKEN }}
          IG_BUSINESS_ID: ${{ secrets.IG_BUSINESS_ID }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m pipeline.approve_poll
      - name: Commit state
        run: bash scripts/commit_state.sh
```

- [ ] **Step 6: Create `.github/workflows/refresh-token.yml`**

```yaml
name: refresh-token
on:
  schedule:
    - cron: '0 2 1 * *'
  workflow_dispatch:
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - name: Mint new long-lived token and notify
        env:
          META_PAGE_ID: ${{ secrets.META_PAGE_ID }}
          META_PAGE_TOKEN: ${{ secrets.META_PAGE_TOKEN }}
          META_APP_ID: ${{ secrets.META_APP_ID }}
          META_APP_SECRET: ${{ secrets.META_APP_SECRET }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m pipeline.refresh_token
```

- [ ] **Step 7: Create `src/pipeline/refresh_token.py`**

```python
from __future__ import annotations
import os
from .meta import Meta
from .telegram import Telegram

def main() -> int:
    m = Meta.from_env()
    res = m.exchange_long_lived_token(os.environ["META_APP_ID"],
                                     os.environ["META_APP_SECRET"],
                                     os.environ["META_PAGE_TOKEN"])
    new_token = res.get("access_token", "")
    masked = new_token[:6] + "…" + new_token[-4:] if new_token else "(none)"
    Telegram().send_message(
        "🔑 Token Meta mới đã được tạo (" + masked + ").\n"
        "Vào GitHub → Settings → Secrets → cập nhật META_PAGE_TOKEN.\n"
        "Giá trị đầy đủ nằm trong log job refresh-token (masked ở Actions UI, "
        "xem trong 'Raw logs' nếu cần).")
    print("::add-mask::" + new_token)
    print("NEW_META_PAGE_TOKEN=" + new_token)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_workflows.py -v`
Expected: 4 passed.

- [ ] **Step 9: Commit**

```bash
git add .github/ scripts/ src/pipeline/refresh_token.py tests/test_workflows.py
git commit -m "ci: build, approve, and monthly token-refresh workflows"
```

---

## Task 15: README + end-to-end dry run

**Files:**
- Create: `README.md`
- Create: `tests/fixtures/local_candidates.json`
- Modify: `.gitignore` (unignore `output/` note — see step)

**Interfaces:**
- Consumes: everything.
- Produces: `README.md` documenting secret setup + `python -m pipeline.run --dry-run --local`; a local-candidates fixture so `--local` works offline.

- [ ] **Step 1: Create `tests/fixtures/local_candidates.json`**

```json
[
  {"url": "https://openai.com/blog/demo-model",
   "title": "OpenAI ra mô hình AI mới nhanh gấp đôi, chi phí giảm một nửa",
   "source": "rss:OpenAI Blog", "published_at": "2026-09-03T00:00:00+00:00",
   "raw_score_hint": 950.0,
   "summary": "OpenAI công bố mô hình mới với tốc độ gấp đôi và giá rẻ hơn.",
   "full_text": "OpenAI vừa công bố một mô hình ngôn ngữ mới. Mô hình này nhanh gấp đôi thế hệ trước, chi phí suy luận giảm khoảng một nửa, và hỗ trợ ngữ cảnh dài hơn. Công ty cho biết mô hình sẽ mở cho lập trình viên qua API trong tuần này.",
   "top_image": null}
]
```

- [ ] **Step 2: Write `README.md`**

````markdown
# AI Social Automation — Phase 1

Tự động mỗi ngày: gom tin AI viral → chọn tin nóng nhất → viết bài tiếng Việt →
tạo 3–4 ảnh → gửi preview Telegram để duyệt → đăng Facebook Page + Instagram.
Chạy miễn phí trên GitHub Actions.

## Chạy thử offline (không đăng, không gọi mạng)

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pipeline.run --dry-run --local
```

Kết quả nằm ở `output/<ngày>/<id>/`: `caption_fb.txt`, `caption_ig.txt`,
`youtube.txt`, `tiktok.txt`, `meta.json`, và `img/`.

## Secrets cần đặt (GitHub → Settings → Secrets and variables → Actions)

| Secret | Lấy ở đâu |
|---|---|
| `META_PAGE_ID` | Graph API Explorer → `GET /me/accounts` |
| `META_PAGE_TOKEN` | Page token, đổi sang long-lived (xem dưới) |
| `IG_BUSINESS_ID` | `GET /{PAGE_ID}?fields=instagram_business_account` |
| `META_APP_ID`, `META_APP_SECRET` | App trong developers.facebook.com (chỉ dùng cho refresh) |
| `TELEGRAM_BOT_TOKEN` | @BotFather |
| `TELEGRAM_CHAT_ID` | Nhắn bot 1 câu, rồi `getUpdates` xem `chat.id` |
| `CLAUDE_CODE_OAUTH_TOKEN` | Máy local: `npm i -g @anthropic-ai/claude-code` rồi `claude setup-token` |
| `GEMINI_API_KEY` | aistudio.google.com/app/apikey (fallback nếu Claude không dùng được) |

### Đổi Page token sang long-lived (60 ngày)

```
GET https://graph.facebook.com/v21.0/oauth/access_token
  ?grant_type=fb_exchange_token&client_id=<APP_ID>
  &client_secret=<APP_SECRET>&fb_exchange_token=<SHORT_PAGE_TOKEN>
```

Workflow `refresh-token` chạy mùng 1 hàng tháng, tạo token mới và nhắn Telegram
để bạn dán lại vào secret `META_PAGE_TOKEN` (thao tác tay ~10 giây).

## Bật/tắt tự động đăng

`config/settings.yaml` → `approval_mode`:
- `telegram` (mặc định): gửi preview, chờ bạn bấm ✅ trong 12h.
- `auto`: đăng thẳng, không hỏi.

## Nguồn nội dung

Sửa `config/sources.yaml` (RSS, subreddit, `facebook_pages`).
Bài Facebook lẻ: dán URL vào `config/facebook_urls.txt`, mỗi dòng một URL.

## Lịch chạy

- `build.yml`: 08:00 ICT hằng ngày (`cron '0 1 * * *'`).
- `approve.yml`: mỗi 10 phút, xử lý nút Telegram.
- `refresh-token.yml`: mùng 1 hàng tháng.
````

- [ ] **Step 3: Run the real dry run**

Run:
```bash
python -m pipeline.run --dry-run --local
```
Expected: exits 0, prints `SUMMARY: dry-run built 2026-...`, and `output/<today>/<id>/caption_fb.txt` exists with the source line, `img/01_thumbnail.jpg` is 1200×630.

- [ ] **Step 4: Full test suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/fixtures/local_candidates.json
git commit -m "docs: setup guide and offline local-candidates fixture"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task(s) |
|---|---|
| §4.1 repo tree | Tasks 1, 14, 15 |
| §4.2 build.yml / approve.yml / refresh-token.yml | Task 14 |
| §5.1 collect (RSS/HN/Reddit/Facebook/manual, dedupe, fulltext top-5) | Task 4 |
| §5.1 seen.json write rule (all read candidates) | Task 12 `build()` → `st.seen_add_many` |
| §5.2 score formula + min_score + "no hot news" notify | Tasks 5, 12 |
| §5.3 write → PostContent, Claude→Gemini, angle validation, source line | Tasks 3, 6 |
| §5.3 voice.yaml default | Task 1 |
| §5.4 media: thumbnail AI+text, source image, screenshot, AI image, <3 → low_media | Task 7 |
| §5.5 review: pending schema + Telegram media group + inline keyboard | Task 10 |
| §5.6 publish: FB photos+feed, IG carousel via tmpfiles, YT/TikTok files, partial-failure handling, seen write | Tasks 9, 11, 12 |
| §5.7 llm/telegram/meta/state helpers | Tasks 2, 3, 8, 9 |
| §6 secrets | Tasks 14, 15 (README) |
| §7 error handling matrix | Tasks 4 (per-source), 3 (LLM fallback), 7 (media fallbacks), 11 (partial), 12 (`main` catches + notify), 14 (git rebase retry), 13 (expire) |
| §8 tests + `--dry-run --local` | every task + Tasks 12, 15 |
| §9 security/legal (source attribution, private repo, no FB login scrape, masked tokens) | Task 6 (source line), 14 (`::add-mask::`), README |
| §10 known limits | README |
| §12 definition of done | Tasks 12–15 |

No uncovered spec requirement.

**2. Placeholder scan**

- No "TBD"/"TODO"/"implement later" in any step.
- Every code step contains complete code.
- `test_run.py` initially contained an over-complex monkeypatch block; Task 12 Step 4 explicitly replaces it with the final version. Acceptable (it's a deliberate refactor step with full code shown), but implementers should write the Step 4 version directly if reading in order.

**3. Type consistency**

- `Candidate` / `PostContent` fields identical across Tasks 2, 4, 5, 6, 7, 10, 12.
- `collect.collect(sources, settings, seen, now, fulltext_top=5)` — same signature in Task 4 def and Task 12 call.
- `score.pick(cands, min_score, now, keywords) -> (Candidate|None, float)` — matches Task 12 usage `best, best_score = score.pick(...)`.
- `write.write_post(cand, voice, generate=...)` — Task 6 def and Task 12 call agree.
- `media.build_media(cand, post, outdir, channel) -> (list[str], bool)` — Task 7 def, Task 12 call agree.
- `review.build_pending(post, images, pid, low_media, now)` and `review.send_preview(pending, tg)` — Tasks 10, 12, 13 agree.
- `publish.publish(pending, meta, outdir) -> dict` with `facebook`/`instagram` sub-dicts carrying `ok` — Tasks 11, 12, 13 agree.
- `state.State` method names (`seen_has`, `seen_add_many`, `pending_add/list/remove`, `posted_save`, `offset_load/save`) identical in Tasks 2, 12, 13.
- `Telegram` methods (`send_message(text, buttons)`, `send_media_group`, `send_document`, `get_updates`, `answer_callback`) identical in Tasks 8, 10, 13.
- `Meta` methods identical in Tasks 9, 11, 14 (`refresh_token.py`).

No mismatches found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-03-ai-social-automation-phase1.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
