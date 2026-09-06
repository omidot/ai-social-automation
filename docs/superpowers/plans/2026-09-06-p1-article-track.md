# P1 Article Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish two approved Vietnamese AI-news posts per day to Facebook Page + Instagram — post #1 at 11:30 ICT, post #2 at 19:45 ICT — each gathered, drafted, and image-generated automatically, then Telegram-previewed and human-approved before going live.

**Architecture:** Four new GitHub Actions workflows (`article-morning`, `article-evening`, `article-approve`, `article-publish-ig`) drive new modules layered on the existing `pipeline` package. Morning/evening jobs gather → dedup → rank → pick one distinct topic → let the LLM choose a "deep" or "roundup" format → generate images with Gemini (fallback to the legacy image path) → write a per-day state file → send a Telegram preview with `[Đăng ngay] [Lên lịch] [Bỏ]` buttons. A 10-minute poll handles the button callbacks: "now" publishes immediately, "sched" schedules Facebook natively via `scheduled_publish_time` and records an `ig_due` time; a separate 15-minute poll publishes the Instagram carousel when `ig_due` passes.

**Tech Stack:** Python 3.12, httpx, feedparser, Pillow, google-genai (Gemini text + image), PyYAML, pytest. GitHub Actions cron. Facebook Graph API v21.0, Instagram Content Publishing API.

## Global Constraints

- Runtime target: Python 3.12 (CI); pins verified on 3.14. Do not add dependencies beyond those already in `requirements.txt` (httpx, feedparser, trafilatura, PyYAML, Pillow, playwright, google-genai, python-dateutil, pytest).
- All new source files under `src/pipeline/`; all tests under `tests/`; `pythonpath = src`.
- TDD: every task writes the failing test first, watches it fail, implements minimally, watches it pass, commits.
- Timezone: all cron expressions are UTC. ICT = UTC+7, no DST. Slot times in config are ICT strings (`"11:30"`).
- Voice: speaker says "mình", audience "bạn"; tone from `config/voice.yaml`; obey `cam_ky` (no false clickbait, no unrealistic money promises, no personal attacks). Content must not distort history, fabricate numbers, or contain unlawful/defamatory/politically-sensitive claims.
- LLM calls go through `pipeline.llm.generate(system, user, provider="auto")`. Image model id from `os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.6-flash")`.
- Never publish without a human button tap. If a post is not approved by its slot time it stays `draft` and is not published.
- One-way status transitions: `draft → scheduled | posted | discarded | expired`. A callback for an already-terminal post is acknowledged and ignored.
- Frequent-running workflows (`article-approve`, `article-publish-ig`) must not run `playwright install`.

---

### Task 1: Config blocks + `Candidate.source_count` + Google News source

**Files:**
- Modify: `config/settings.yaml`
- Modify: `config/sources.yaml`
- Modify: `src/pipeline/models.py:17-25` (the `Candidate` dataclass fields)
- Modify: `src/pipeline/collect.py` (add `from_google_news`)
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `Candidate.source_count: int = 1` (new dataclass field, after `top_image`).
  - `collect.from_google_news(queries: list[str], langs: list[str], now: datetime) -> list[Candidate]`.
  - `config/settings.yaml` key `articles` (dict: `slots.morning`, `slots.evening`, `min_score`, `format_deep_margin`, `roundup_min`, `roundup_max`) and key `images` (dict: `provider`, `style_prompt`, `size`, `raw_base`).
  - `config/sources.yaml` key `google_news` (dict: `queries` list, `langs` list).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_collect.py`:

```python
from pipeline import collect as _collect_mod

_GNEWS_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>OpenAI ra mắt mô hình mới - VnExpress</title>
<link>https://news.google.com/rss/articles/abc?oc=5</link>
<pubDate>Fri, 05 Sep 2026 06:00:00 GMT</pubDate>
<description>OpenAI công bố...</description></item>
</channel></rss>"""

def test_from_google_news_parses(monkeypatch):
    class R:
        text = _GNEWS_RSS
        def raise_for_status(self): pass
    monkeypatch.setattr(_collect_mod, "_get", lambda url, params=None: R())
    now = datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)
    cands = _collect_mod.from_google_news(["AI"], ["vi"], now)
    assert len(cands) == 1
    assert cands[0].source.startswith("rss:Google News")
    assert "OpenAI" in cands[0].title
    assert cands[0].source_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collect.py::test_from_google_news_parses -v`
Expected: FAIL — `AttributeError: module 'pipeline.collect' has no attribute 'from_google_news'`

- [ ] **Step 3: Add the `source_count` field**

In `src/pipeline/models.py`, add to `Candidate` after `top_image`:

```python
    top_image: str | None = None
    source_count: int = 1
```

- [ ] **Step 4: Implement `from_google_news`**

In `src/pipeline/collect.py`, after `from_rss`:

```python
def from_google_news(queries: list[str], langs: list[str], now: datetime) -> list[Candidate]:
    out: list[Candidate] = []
    for lang in langs:
        for q in queries:
            hl = "vi" if lang == "vi" else "en-US"
            url = "https://news.google.com/rss/search"
            try:
                raw = _get(url, params={"q": q, "hl": hl,
                                        "gl": "VN" if lang == "vi" else "US"}).text
            except Exception as e:  # noqa: BLE001
                log.warning("google news %r/%s failed: %s", q, lang, e)
                continue
            parsed = feedparser.parse(raw)
            for e in parsed.entries:
                dt = _parse_date(e)
                if not dt or not _fresh(dt, now):
                    continue
                title = e.get("title", "").strip()
                out.append(Candidate(
                    url=e.get("link", ""), title=title,
                    source=f"rss:Google News ({q})", published_at=dt,
                    summary=(e.get("summary", "") or "")[:500]))
    return out
```

- [ ] **Step 5: Wire it into `collect()` and add config**

In `src/pipeline/collect.py` `collect()`, add to the `jobs` list after the `from_rss` lambda:

```python
        lambda: from_google_news(
            sources.get("google_news", {}).get("queries", []),
            sources.get("google_news", {}).get("langs", []), now),
```

Append to `config/sources.yaml`:

```yaml
google_news:
  queries: ["artificial intelligence", "AI model", "trí tuệ nhân tạo", "AI Việt Nam"]
  langs: ["en", "vi"]
```

Append to `config/settings.yaml`:

```yaml
articles:
  slots:
    morning: "11:30"
    evening: "19:45"
  min_score: 45
  format_deep_margin: 12
  roundup_min: 3
  roundup_max: 5
images:
  provider: gemini
  style_prompt: "digital art, glowing neural and tech motifs, blue and violet, cinematic, no text"
  size: "1080x1350"
  raw_base: "https://raw.githubusercontent.com/omidot/ai-social-automation/master"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_collect.py -v`
Expected: PASS (all, including the new test).

- [ ] **Step 7: Commit**

```bash
git add config/settings.yaml config/sources.yaml src/pipeline/models.py src/pipeline/collect.py tests/test_collect.py
git commit -m "feat(p1): google news source + Candidate.source_count + article/image config"
```

---

### Task 2: Collapse near-duplicate stories with a `source_count`

**Files:**
- Modify: `src/pipeline/collect.py` (add `_collapse_similar`, call it in `collect()`)
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `Candidate.source_count` (Task 1).
- Produces: `collect._collapse_similar(cands: list[Candidate]) -> list[Candidate]` — groups by title similarity ≥ 0.72 (`difflib.SequenceMatcher`), keeps the earliest-`published_at` member of each group as representative, sets its `source_count` to the group size, keeps its `full_text`/`top_image` if any member had them.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_collect.py`:

```python
from pipeline.collect import _collapse_similar

def test_collapse_similar_merges_and_counts():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    a = Candidate(url="https://a.com/x", title="OpenAI launches GPT-6 today",
                  source="rss:A", published_at=now)
    b = Candidate(url="https://b.com/y", title="OpenAI launches GPT-6 today, sources say",
                  source="rss:B", published_at=now)
    c = Candidate(url="https://c.com/z", title="Nvidia announces new GPU",
                  source="rss:C", published_at=now)
    out = _collapse_similar([a, b, c])
    assert len(out) == 2
    merged = [x for x in out if "OpenAI" in x.title][0]
    assert merged.source_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collect.py::test_collapse_similar_merges_and_counts -v`
Expected: FAIL — `ImportError: cannot import name '_collapse_similar'`

- [ ] **Step 3: Implement `_collapse_similar`**

In `src/pipeline/collect.py` (add `from difflib import SequenceMatcher` to imports):

```python
def _collapse_similar(cands: list[Candidate]) -> list[Candidate]:
    groups: list[list[Candidate]] = []
    for c in cands:
        placed = False
        for g in groups:
            if SequenceMatcher(None, c.title.lower(), g[0].title.lower()).ratio() >= 0.72:
                g.append(c)
                placed = True
                break
        if not placed:
            groups.append([c])
    out: list[Candidate] = []
    for g in groups:
        rep = min(g, key=lambda x: x.published_at)
        rep.source_count = len(g)
        for m in g:
            if not rep.full_text and m.full_text:
                rep.full_text = m.full_text
            if not rep.top_image and m.top_image:
                rep.top_image = m.top_image
        out.append(rep)
    return out
```

- [ ] **Step 4: Call it in `collect()`**

In `src/pipeline/collect.py` `collect()`, replace the line
`result = sorted(dedup.values(), key=lambda c: c.published_at, reverse=True)` with:

```python
    collapsed = _collapse_similar(list(dedup.values()))
    result = sorted(collapsed, key=lambda c: c.published_at, reverse=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_collect.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/collect.py tests/test_collect.py
git commit -m "feat(p1): collapse near-duplicate stories, count covering sources"
```

---

### Task 3: `score.pick_n` — N distinct topics, with exclusions

**Files:**
- Modify: `src/pipeline/score.py` (add `_source_spread`, `pick_n`)
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `Candidate.source_count` (Task 1).
- Produces:
  - `score.score_candidate` gains `+ _source_spread(c)` in its sum, where `_source_spread(c) -> float` returns `min(c.source_count - 1, 4) * 5.0` (0–20).
  - `score.pick_n(cands, n, min_score, now, keywords, exclude_titles=()) -> list[tuple[float, Candidate]]` — highest score first, at most `n`, each above `min_score`, each not near-matching (SequenceMatcher ratio ≥ 0.5) any string in `exclude_titles` **or** any already-picked candidate's title.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_score.py`:

```python
from pipeline.score import pick_n

def _c(title, hint=0.0, sc=1):
    return Candidate(url=f"https://x/{title[:8]}", title=title, source="rss:X",
                     published_at=datetime(2026, 9, 5, 6, tzinfo=timezone.utc),
                     raw_score_hint=hint, summary=title, source_count=sc)

def test_pick_n_returns_distinct_topics():
    now = datetime(2026, 9, 5, 8, tzinfo=timezone.utc)
    cands = [_c("OpenAI ships GPT-6", hint=800, sc=3),
             _c("OpenAI ships GPT-6 model", hint=200, sc=1),
             _c("Nvidia reveals Rubin GPU", hint=500, sc=2),
             _c("Google DeepMind protein news", hint=120)]
    picked = pick_n(cands, 2, min_score=20, now=now, keywords=["AI", "GPT", "GPU"])
    assert len(picked) == 2
    titles = [c.title for _, c in picked]
    assert "OpenAI ships GPT-6" in titles[0]
    assert "Nvidia" in titles[1]  # 2nd pick skips the near-duplicate OpenAI item

def test_pick_n_respects_exclude_titles():
    now = datetime(2026, 9, 5, 8, tzinfo=timezone.utc)
    cands = [_c("OpenAI ships GPT-6", hint=800, sc=3),
             _c("Nvidia reveals Rubin GPU", hint=500, sc=2)]
    picked = pick_n(cands, 1, min_score=20, now=now, keywords=["AI"],
                    exclude_titles=["OpenAI ships GPT-6 today"])
    assert len(picked) == 1
    assert "Nvidia" in picked[0][1].title
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_score.py -k pick_n -v`
Expected: FAIL — `ImportError: cannot import name 'pick_n'`

- [ ] **Step 3: Implement**

In `src/pipeline/score.py`:

```python
def _source_spread(c: Candidate) -> float:
    return min(max(c.source_count - 1, 0), 4) * 5.0
```

Add `+ _source_spread(c)` inside the `round(...)` in `score_candidate`.

```python
def pick_n(cands, n, min_score, now, keywords, exclude_titles=()):
    scored = [(score_candidate(c, now, cands, keywords), c) for c in cands]
    scored.sort(key=lambda t: t[0], reverse=True)
    picked: list[tuple[float, Candidate]] = []
    for sc, c in scored:
        if sc < min_score:
            break
        blockers = list(exclude_titles) + [pc.title for _, pc in picked]
        if any(SequenceMatcher(None, c.title.lower(), b.lower()).ratio() >= 0.5
               for b in blockers):
            continue
        picked.append((sc, c))
        if len(picked) == n:
            break
    return picked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_score.py -v`
Expected: PASS (existing `pick` tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/score.py tests/test_score.py
git commit -m "feat(p1): pick_n selects N distinct topics with title exclusions"
```

---

### Task 4: `ArticleContent` model

**Files:**
- Modify: `src/pipeline/models.py` (add `ArticleContent`)
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Produces: `models.ArticleContent` dataclass with fields:
  `format: str` (`"deep"|"roundup"`), `caption_fb: str`, `caption_ig: str`,
  `hashtags: list[str]`, `cover_title: str`, `cover_brief: str`,
  `image_briefs: list[str]`, `sources: list[dict]` (`{"name": str, "url": str}`),
  `risk: bool = False`. Plus `to_dict()` and `from_dict(d)` (ignores unknown keys),
  mirroring `PostContent`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scaffold.py`:

```python
def test_article_content_roundtrip():
    from pipeline.models import ArticleContent
    a = ArticleContent(format="deep", caption_fb="x", caption_ig="y", hashtags=["#AI"],
                       cover_title="TIÊU ĐỀ", cover_brief="neural core",
                       image_briefs=["a", "b"], sources=[{"name": "hn", "url": "http://h"}])
    b = ArticleContent.from_dict({**a.to_dict(), "junk": 1})
    assert b == a
    assert b.risk is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scaffold.py::test_article_content_roundtrip -v`
Expected: FAIL — `ImportError: cannot import name 'ArticleContent'`

- [ ] **Step 3: Implement**

In `src/pipeline/models.py`:

```python
@dataclass
class ArticleContent:
    format: str
    caption_fb: str
    caption_ig: str
    hashtags: list[str]
    cover_title: str
    cover_brief: str
    image_briefs: list[str]
    sources: list[dict]
    risk: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ArticleContent":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scaffold.py::test_article_content_roundtrip -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/models.py tests/test_scaffold.py
git commit -m "feat(p1): ArticleContent model"
```

---

### Task 5: `write.decide_format`

**Files:**
- Modify: `src/pipeline/write.py` (add `decide_format`)
- Test: `tests/test_write.py`

**Interfaces:**
- Consumes: output shape of `score.pick_n` — `list[tuple[float, Candidate]]`.
- Produces: `write.decide_format(scored: list[tuple[float, Candidate]], margin: float) -> str`
  returns `"deep"` if `len(scored) == 1` or `scored[0][0] - scored[1][0] >= margin`,
  else `"roundup"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_write.py`:

```python
def test_decide_format():
    from pipeline.write import decide_format
    assert decide_format([(90.0, None)], margin=12) == "deep"
    assert decide_format([(90.0, None), (70.0, None)], margin=12) == "deep"
    assert decide_format([(90.0, None), (85.0, None)], margin=12) == "roundup"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_write.py::test_decide_format -v`
Expected: FAIL — `ImportError: cannot import name 'decide_format'`

- [ ] **Step 3: Implement**

In `src/pipeline/write.py`:

```python
def decide_format(scored, margin):
    if len(scored) <= 1:
        return "deep"
    return "deep" if (scored[0][0] - scored[1][0]) >= margin else "roundup"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_write.py::test_decide_format -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/write.py tests/test_write.py
git commit -m "feat(p1): decide_format picks deep vs roundup by score margin"
```

---

### Task 6: `write.write_deep`

**Files:**
- Modify: `src/pipeline/write.py` (add `_ARTICLE_GUARDRAILS`, `build_deep_prompt`, `write_deep`)
- Create: `tests/fixtures/sample_deep_response.json`
- Test: `tests/test_write.py`

**Interfaces:**
- Consumes: `models.ArticleContent` (Task 4); `pipeline.llm.generate`.
- Produces:
  - `write._ARTICLE_GUARDRAILS: str` — a reusable prompt clause: "Không xuyên tạc lịch sử, không bịa số liệu, không nội dung vi phạm pháp luật / phỉ báng / chính trị nhạy cảm. Nếu bài chạm vùng nhạy cảm, đặt \"risk\": true."
  - `write.build_deep_prompt(cand: Candidate, voice: dict) -> tuple[str, str]`.
  - `write.write_deep(cand: Candidate, voice: dict, generate=_default_generate) -> ArticleContent`
    (`format="deep"`). Raises `WriteError` on missing keys / bad JSON.
    Appends `Nguồn: <name> — <url>` to `caption_fb` if absent (reuse `_source_name`).
    `image_briefs` length clamped to 3–4; `cover_title` upper-cased; `sources` = one entry.

- [ ] **Step 1: Write the failing test + fixture**

Create `tests/fixtures/sample_deep_response.json`:

```json
{
  "caption_fb": "Bạn thấy sao về chuyện này? Mình nghĩ đây là bước ngoặt.",
  "caption_ig": "AI lại có biến. Bạn nghĩ sao?",
  "hashtags": ["#AI", "#trituenhantao", "#congnghe", "#ahitofficial"],
  "cover_title": "openai ra mắt mô hình mới",
  "cover_brief": "futuristic neural core, blue violet, cinematic, no text",
  "image_briefs": ["glowing data center", "abstract circuit brain", "researcher silhouette"],
  "risk": false
}
```

Add to `tests/test_write.py`:

```python
def test_write_deep_builds_article(monkeypatch):
    from pipeline.write import write_deep
    payload = (FIXTURES / "sample_deep_response.json").read_text(encoding="utf-8")
    art = write_deep(_cand(), VOICE, generate=lambda s, u, **k: payload)
    assert art.format == "deep"
    assert art.cover_title == "OPENAI RA MẮT MÔ HÌNH MỚI"
    assert 3 <= len(art.image_briefs) <= 4
    assert art.sources == [{"name": "OpenAI Blog", "url": "https://openai.com/blog/new"}]
    assert art.caption_fb.rstrip().endswith("Nguồn: OpenAI Blog — https://openai.com/blog/new")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_write.py::test_write_deep_builds_article -v`
Expected: FAIL — `ImportError: cannot import name 'write_deep'`

- [ ] **Step 3: Implement**

In `src/pipeline/write.py`:

```python
_ARTICLE_GUARDRAILS = (
    "Không xuyên tạc lịch sử, không bịa số liệu, không nội dung vi phạm pháp luật, "
    "phỉ báng, hay chính trị nhạy cảm. Nếu bài chạm vùng nhạy cảm, đặt \"risk\": true."
)
_DEEP_KEYS = ("caption_fb", "caption_ig", "hashtags", "cover_title", "cover_brief",
              "image_briefs")

def build_deep_prompt(cand, voice):
    system = (
        f"Bạn là biên tập viên tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Giọng: {voice.get('giong','')}. Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        "Viết bài CHUYÊN SÂU về MỘT tin. CHỈ trả về JSON với khoá: "
        "caption_fb (200-350 từ, xuống dòng, kết bằng CTA), caption_ig (<=60 từ), "
        "hashtags (8-15 chuỗi #), cover_title (4-10 từ tiếng Việt), "
        "cover_brief (tiếng Anh, tả ảnh, không chữ), "
        "image_briefs (3-4 chuỗi tiếng Anh tả ảnh minh hoạ, không chữ), risk (bool)."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = f"TIÊU ĐỀ: {cand.title}\nNGUỒN: {cand.source}\nURL: {cand.url}\n\n{article}\n"
    return system, user

def write_deep(cand, voice, generate=_default_generate):
    try:
        data = parse_json_response(generate(*build_deep_prompt(cand, voice), provider="auto"))
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e
    missing = [k for k in _DEEP_KEYS if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"deep response missing keys: {missing}")
    name = _source_name(cand)
    line = f"Nguồn: {name} — {cand.url}"
    cap = data["caption_fb"].rstrip()
    if line not in cap:
        cap = f"{cap}\n\n{line}"
    briefs = [b.strip() for b in data["image_briefs"] if b.strip()][:4]
    if len(briefs) < 3:
        briefs = (briefs + [data["cover_brief"]] * 3)[:3]
    from .models import ArticleContent
    return ArticleContent(
        format="deep", caption_fb=cap, caption_ig=data["caption_ig"].strip(),
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        cover_title=data["cover_title"].strip().upper(),
        cover_brief=data["cover_brief"].strip(), image_briefs=briefs,
        sources=[{"name": name, "url": cand.url}], risk=bool(data.get("risk", False)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/write.py tests/test_write.py tests/fixtures/sample_deep_response.json
git commit -m "feat(p1): write_deep produces a deep-dive ArticleContent"
```

---

### Task 7: `write.write_roundup`

**Files:**
- Modify: `src/pipeline/write.py` (add `build_roundup_prompt`, `write_roundup`)
- Create: `tests/fixtures/sample_roundup_response.json`
- Test: `tests/test_write.py`

**Interfaces:**
- Consumes: `models.ArticleContent`; `_ARTICLE_GUARDRAILS` (Task 6).
- Produces: `write.write_roundup(cands: list[Candidate], voice: dict, generate=_default_generate) -> ArticleContent`
  (`format="roundup"`). `image_briefs` has exactly `len(cands)` entries (one per item, order matches).
  `sources` has one `{name,url}` per candidate. Raises `WriteError` on missing keys or on
  `len(data["image_briefs"]) != len(cands)`.

- [ ] **Step 1: Write the failing test + fixture**

Create `tests/fixtures/sample_roundup_response.json`:

```json
{
  "caption_fb": "3 tin AI đáng chú ý hôm nay:\n\n1. ...\n2. ...\n3. ...\n\nBạn quan tâm tin nào nhất?",
  "caption_ig": "3 tin AI hôm nay 👇",
  "hashtags": ["#AI", "#tinAI", "#congnghe", "#ahitofficial"],
  "cover_title": "3 tin AI nóng hôm nay",
  "cover_brief": "collage of tech headlines, blue violet, cinematic, no text",
  "image_briefs": ["chip macro shot", "robot arm in lab", "phone with chatbot ui"],
  "risk": false
}
```

Add to `tests/test_write.py`:

```python
def test_write_roundup_one_brief_per_item():
    from pipeline.write import write_roundup
    payload = (FIXTURES / "sample_roundup_response.json").read_text(encoding="utf-8")
    cands = [_cand(),
             Candidate(url="https://b/1", title="Nvidia GPU", source="rss:B",
                       published_at=datetime(2026, 9, 3, tzinfo=timezone.utc), summary="x"),
             Candidate(url="https://c/2", title="Google model", source="rss:C",
                       published_at=datetime(2026, 9, 3, tzinfo=timezone.utc), summary="y")]
    art = write_roundup(cands, VOICE, generate=lambda s, u, **k: payload)
    assert art.format == "roundup"
    assert len(art.image_briefs) == 3
    assert len(art.sources) == 3
    assert art.sources[1] == {"name": "B", "url": "https://b/1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_write.py::test_write_roundup_one_brief_per_item -v`
Expected: FAIL — `ImportError: cannot import name 'write_roundup'`

- [ ] **Step 3: Implement**

In `src/pipeline/write.py`:

```python
def build_roundup_prompt(cands, voice):
    items = "\n\n".join(
        f"[{i+1}] {c.title}\nNGUỒN: {_source_name(c)} — {c.url}\n"
        f"{(c.full_text or c.summary or '')[:1500]}"
        for i, c in enumerate(cands))
    system = (
        f"Bạn là biên tập viên tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Giọng: {voice.get('giong','')}. Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". {_ARTICLE_GUARDRAILS} "
        f"Viết bài GOM {len(cands)} tin, đánh số 1..{len(cands)}, mỗi tin 2-4 câu + link nguồn. "
        "CHỈ trả về JSON với khoá: caption_fb (đánh số, kết bằng câu hỏi tương tác), "
        "caption_ig (<=40 từ), hashtags (8-15 chuỗi #), cover_title (4-10 từ tiếng Việt), "
        "cover_brief (tiếng Anh, tả ảnh, không chữ), "
        f"image_briefs (ĐÚNG {len(cands)} chuỗi tiếng Anh, thứ tự khớp tin 1..{len(cands)}, "
        "tả ảnh, không chữ), risk (bool)."
    )
    return system, f"CÁC TIN:\n\n{items}\n"

def write_roundup(cands, voice, generate=_default_generate):
    try:
        data = parse_json_response(generate(*build_roundup_prompt(cands, voice), provider="auto"))
    except LLMError as e:
        raise WriteError(f"LLM failed: {e}") from e
    missing = [k for k in _DEEP_KEYS if k not in data or data[k] in (None, "", [])]
    if missing:
        raise WriteError(f"roundup response missing keys: {missing}")
    briefs = [b.strip() for b in data["image_briefs"] if b.strip()]
    if len(briefs) != len(cands):
        raise WriteError(f"roundup image_briefs {len(briefs)} != items {len(cands)}")
    from .models import ArticleContent
    return ArticleContent(
        format="roundup", caption_fb=data["caption_fb"].rstrip(),
        caption_ig=data["caption_ig"].strip(),
        hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
        cover_title=data["cover_title"].strip().upper(),
        cover_brief=data["cover_brief"].strip(), image_briefs=briefs,
        sources=[{"name": _source_name(c), "url": c.url} for c in cands],
        risk=bool(data.get("risk", False)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/write.py tests/test_write.py tests/fixtures/sample_roundup_response.json
git commit -m "feat(p1): write_roundup produces a numbered multi-story ArticleContent"
```

---

### Task 8: `images.py` — Gemini image generation with legacy fallback

**Files:**
- Create: `src/pipeline/images.py`
- Test: `tests/test_images.py`

**Interfaces:**
- Consumes: `models.ArticleContent`; `media._wrap`, `media._save_jpeg`, `media._gradient`,
  `media.FONT_PATH` (reused for the cover text overlay); `media.build_media` (legacy fallback).
- Produces:
  - `images._gemini_image(prompt: str, size: tuple[int, int]) -> bytes` — calls
    `google.genai` with model `os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.6-flash")`,
    `response_modalities=["IMAGE"]`; returns the first inline image's raw bytes; raises on
    no image.
  - `images._overlay_title(img_bytes: bytes, title: str, size: tuple[int,int]) -> PIL.Image.Image`
    — dark scrim + wrapped upper-case title, bottom-anchored (same look as
    `media.make_thumbnail`).
  - `images.build_images(article, out_dir, *, style_prompt, size, gen=None) -> list[str]`
    — image 1 = cover (`_gemini_image(cover_brief+style)` → `_overlay_title`), images
    2..N = clean `_gemini_image(brief+style)` per `image_briefs`. `gen` overrides
    `_gemini_image` for tests. On ANY exception from the Gemini path, log and return
    `_legacy_fallback(article, out_dir)`.
  - `images._legacy_fallback(article, out_dir) -> list[str]` — builds a
    `PostContent`-shaped object from `article` and calls `media.build_media`; returns its
    path list.
  - Files written to `out_dir` as `01_cover.jpg`, `02.jpg`, … (JPEG, resized to `size`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_images.py`:

```python
from pathlib import Path
import pytest
from PIL import Image
import io
from pipeline import images
from pipeline.models import ArticleContent

def _art():
    return ArticleContent(format="deep", caption_fb="x", caption_ig="y", hashtags=["#AI"],
                          cover_title="TIN AI HÔM NAY", cover_brief="neural core",
                          image_briefs=["a", "b"], sources=[{"name": "hn", "url": "http://h"}])

def _png_bytes(color=(20, 40, 120)):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()

def test_build_images_gemini_path(tmp_path):
    calls = []
    def fake_gen(prompt, size):
        calls.append(prompt)
        return _png_bytes()
    out = images.build_images(_art(), tmp_path, style_prompt="cinematic",
                              size=(1080, 1350), gen=fake_gen)
    assert len(out) == 3                      # cover + 2 briefs
    assert Path(out[0]).name == "01_cover.jpg"
    assert all(Path(p).exists() for p in out)
    assert Image.open(out[0]).size == (1080, 1350)
    assert "cinematic" in calls[0]

def test_build_images_falls_back_on_error(tmp_path, monkeypatch):
    def boom(prompt, size):
        raise RuntimeError("quota")
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda art, od: [str(tmp_path / "legacy.jpg")])
    out = images.build_images(_art(), tmp_path, style_prompt="x", size=(1080, 1350), gen=boom)
    assert out == [str(tmp_path / "legacy.jpg")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_images.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.images'`

- [ ] **Step 3: Implement `src/pipeline/images.py`**

```python
from __future__ import annotations
import io, logging, os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import media
from .models import ArticleContent, PostContent

log = logging.getLogger("images")


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


def _overlay_title(img_bytes: bytes, title: str, size: tuple[int, int]) -> Image.Image:
    W, H = size
    bg = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((W, H))
    bg = Image.alpha_composite(bg.convert("RGBA"),
                               Image.new("RGBA", (W, H), (0, 0, 0, 90))).convert("RGB")
    draw = ImageDraw.Draw(bg)
    font = ImageFont.truetype(str(media.FONT_PATH), 78)
    lines = media._wrap(draw, title.upper(), font, W - 140)
    line_h = 92
    y = H - 110 - line_h * len(lines)
    for ln in lines:
        x = (W - draw.textlength(ln, font=font)) / 2
        draw.text((x, y), ln, font=font, fill="white", stroke_width=4,
                  stroke_fill=(10, 10, 30))
        y += line_h
    return bg


def _legacy_fallback(article: ArticleContent, out_dir: Path) -> list[str]:
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
    return paths


def build_images(article: ArticleContent, out_dir, *, style_prompt: str,
                 size: tuple[int, int], gen=None) -> list[str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    gen = gen or _gemini_image
    try:
        cover_bytes = gen(f"{article.cover_brief}, {style_prompt}", size)
        cover = _overlay_title(cover_bytes, article.cover_title, size)
        paths = [str(media._save_jpeg(cover, out_dir / "01_cover.jpg"))]
        for i, brief in enumerate(article.image_briefs, start=2):
            b = gen(f"{brief}, {style_prompt}", size)
            im = Image.open(io.BytesIO(b)).convert("RGB").resize(size)
            paths.append(str(media._save_jpeg(im, out_dir / f"{i:02d}.jpg")))
        return paths
    except Exception as e:  # noqa: BLE001 - any Gemini failure -> legacy path
        log.warning("gemini image path failed (%s); using legacy media", e)
        return _legacy_fallback(article, out_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_images.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/images.py tests/test_images.py
git commit -m "feat(p1): images.build_images via Gemini with legacy fallback"
```

---

### Task 9: `daily_state.py` — per-day two-slot state

**Files:**
- Create: `src/pipeline/daily_state.py`
- Test: `tests/test_daily_state.py`

**Interfaces:**
- Consumes: `state._atomic_write`, `state._read_json`.
- Produces: `daily_state.DailyState(data_dir: Path)` with:
  - `path(date: str) -> Path` → `<data_dir>/daily/<date>.json`
  - `load(date: str) -> dict` → existing doc or `{"date": date, "posts": {}}`
  - `get(date: str, slot: str) -> dict | None`
  - `put(date: str, slot: str, **fields) -> dict` — merges `fields` into the slot dict,
    creating it if absent, writes the file, returns the slot dict.
  - `set_status(date: str, slot: str, status: str) -> bool` — applies the one-way
    transition guard: returns `False` (no write) if the current status is terminal
    (`posted`/`discarded`/`expired`); otherwise sets it and returns `True`.
  - `TERMINAL = frozenset({"posted", "discarded", "expired"})`
  - `all_files() -> list[Path]` → sorted `<data_dir>/daily/*.json`

- [ ] **Step 1: Write the failing test**

Create `tests/test_daily_state.py`:

```python
from pipeline.daily_state import DailyState

def test_put_and_get(tmp_path):
    ds = DailyState(tmp_path)
    ds.put("2026-09-06", "morning", status="draft", format="deep", text_fb="hi")
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "draft" and slot["text_fb"] == "hi"
    ds.put("2026-09-06", "morning", fb_post_id="123")
    assert ds.get("2026-09-06", "morning")["fb_post_id"] == "123"
    assert ds.get("2026-09-06", "evening") is None

def test_one_way_status(tmp_path):
    ds = DailyState(tmp_path)
    ds.put("2026-09-06", "morning", status="draft")
    assert ds.set_status("2026-09-06", "morning", "scheduled") is True
    assert ds.set_status("2026-09-06", "morning", "posted") is True
    assert ds.set_status("2026-09-06", "morning", "discarded") is False
    assert ds.get("2026-09-06", "morning")["status"] == "posted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_daily_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.daily_state'`

- [ ] **Step 3: Implement `src/pipeline/daily_state.py`**

```python
from __future__ import annotations
import json
from pathlib import Path

from .state import _atomic_write, _read_json

TERMINAL = frozenset({"posted", "discarded", "expired"})


class DailyState:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "daily"

    def path(self, date: str) -> Path:
        return self.dir / f"{date}.json"

    def load(self, date: str) -> dict:
        return _read_json(self.path(date), {"date": date, "posts": {}})

    def _save(self, date: str, doc: dict) -> None:
        _atomic_write(self.path(date), json.dumps(doc, ensure_ascii=False, indent=2))

    def get(self, date: str, slot: str) -> dict | None:
        return self.load(date)["posts"].get(slot)

    def put(self, date: str, slot: str, **fields) -> dict:
        doc = self.load(date)
        cur = doc["posts"].setdefault(slot, {})
        cur.update(fields)
        self._save(date, doc)
        return cur

    def set_status(self, date: str, slot: str, status: str) -> bool:
        doc = self.load(date)
        cur = doc["posts"].get(slot, {})
        if cur.get("status") in TERMINAL:
            return False
        cur["status"] = status
        doc["posts"][slot] = cur
        self._save(date, doc)
        return True

    def all_files(self) -> list[Path]:
        if not self.dir.exists():
            return []
        return sorted(self.dir.glob("*.json"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_daily_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/daily_state.py tests/test_daily_state.py
git commit -m "feat(p1): DailyState per-day two-slot store with one-way status"
```

---

### Task 10: `meta.py` — Facebook scheduled multi-photo post

**Files:**
- Modify: `src/pipeline/meta.py` (`fb_create_post` gains `scheduled_publish_time`)
- Test: `tests/test_meta.py`

**Interfaces:**
- Consumes: existing `Meta.fb_upload_photo`.
- Produces: `Meta.fb_create_post(self, message: str, media_fbids: list[str], scheduled_publish_time: int | None = None, now_unix: int | None = None) -> dict`
  returns `{"id", "url", "scheduled": bool}`.
  - If `scheduled_publish_time` is `None` → `published=true`, `scheduled=False` (current behavior).
  - If set and `scheduled_publish_time - (now_unix or time.time()) >= 600` → add
    `published=false` + `scheduled_publish_time`; `scheduled=True`.
  - If set but `< 600` seconds ahead → publish immediately (`published=true`),
    `scheduled=False`, and `log.warning`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_meta.py`:

```python
def test_fb_create_post_scheduled(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    sent = {}
    monkeypatch.setattr(m, "_post", lambda url, data=None, files=None:
                        (sent.update(data=data), {"id": "PID_9"})[1])
    r = m.fb_create_post("hello", ["1", "2"],
                         scheduled_publish_time=2000, now_unix=1000)
    assert r["scheduled"] is True
    assert sent["data"]["published"] == "false"
    assert sent["data"]["scheduled_publish_time"] == 2000

def test_fb_create_post_schedule_too_soon_publishes_now(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK")
    sent = {}
    monkeypatch.setattr(m, "_post", lambda url, data=None, files=None:
                        (sent.update(data=data), {"id": "PID_9"})[1])
    r = m.fb_create_post("hi", ["1"], scheduled_publish_time=1100, now_unix=1000)
    assert r["scheduled"] is False
    assert "published" not in sent["data"] or sent["data"]["published"] == "true"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_meta.py -k fb_create_post -v`
Expected: FAIL — `TypeError: fb_create_post() got an unexpected keyword argument 'scheduled_publish_time'`

- [ ] **Step 3: Implement**

In `src/pipeline/meta.py` (add `import time` at top), replace `fb_create_post`:

```python
    def fb_create_post(self, message, media_fbids, scheduled_publish_time=None,
                       now_unix=None):
        data = {"message": message, "access_token": self.token}
        for i, fbid in enumerate(media_fbids):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": str(fbid)},
                                                      separators=(",", ":"))
        scheduled = False
        if scheduled_publish_time is not None:
            lead = scheduled_publish_time - int(now_unix if now_unix is not None else time.time())
            if lead >= 600:
                data["published"] = "false"
                data["scheduled_publish_time"] = scheduled_publish_time
                scheduled = True
            else:
                import logging
                logging.getLogger("meta").warning(
                    "scheduled_publish_time only %ss ahead; publishing now", lead)
        res = self._post(f"{BASE}/{self.page_id}/feed", data=data)
        pid = str(res["id"])
        return {"id": pid, "url": f"https://facebook.com/{pid}", "scheduled": scheduled}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_meta.py -v`
Expected: PASS (existing meta tests still green — the new kwarg is optional).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/meta.py tests/test_meta.py
git commit -m "feat(p1): fb_create_post supports native scheduled_publish_time"
```

---

### Task 11: `meta.py` — Instagram publish from public URLs

**Files:**
- Modify: `src/pipeline/meta.py` (add `ig_publish_images`)
- Test: `tests/test_meta.py`

**Interfaces:**
- Consumes: existing `Meta.ig_create_item`, `ig_create_carousel`, `ig_publish`.
- Produces: `Meta.ig_publish_images(self, image_urls: list[str], caption: str) -> dict`
  → `{"ok": True, "media_id": ...}`.
  - 1 URL → single-image container (`{"image_url": url, "caption": caption}`) → `ig_publish`.
  - 2+ URLs → `ig_create_item` per URL → `ig_create_carousel` → `ig_publish`.
  Public image URLs are passed in by the caller (raw GitHub URLs); this method never
  touches tmpfiles.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_meta.py`:

```python
def test_ig_publish_images_single(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    calls = []
    monkeypatch.setattr(m, "_post", lambda url, data=None, files=None:
                        (calls.append((url, data)), {"id": "cid"})[1])
    r = m.ig_publish_images(["https://raw/x.jpg"], "cap")
    assert r == {"ok": True, "media_id": "cid"}
    assert any("media_publish" in u for u, _ in calls)

def test_ig_publish_images_carousel(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    seq = iter(["a", "b", "carousel", "published"])
    monkeypatch.setattr(m, "_post",
                        lambda url, data=None, files=None: {"id": next(seq)})
    r = m.ig_publish_images(["u1", "u2"], "cap")
    assert r["media_id"] == "published"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_meta.py -k ig_publish_images -v`
Expected: FAIL — `AttributeError: 'Meta' object has no attribute 'ig_publish_images'`

- [ ] **Step 3: Implement**

In `src/pipeline/meta.py`, in the Instagram section:

```python
    def ig_publish_images(self, image_urls, caption):
        if len(image_urls) == 1:
            res = self._post(f"{BASE}/{self.ig_id}/media",
                             data={"image_url": image_urls[0], "caption": caption,
                                   "access_token": self.token})
            pub = self.ig_publish(str(res["id"]))
            return {"ok": True, "media_id": str(pub["id"])}
        child_ids = [self.ig_create_item(u) for u in image_urls[:10]]
        caro = self.ig_create_carousel(child_ids, caption)
        pub = self.ig_publish(caro)
        return {"ok": True, "media_id": str(pub["id"])}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_meta.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/meta.py tests/test_meta.py
git commit -m "feat(p1): ig_publish_images publishes single or carousel from public URLs"
```

---

### Task 12: `article_run.py` — draft orchestrator + Telegram preview

**Files:**
- Create: `src/pipeline/article_run.py`
- Test: `tests/test_article_run.py`

**Interfaces:**
- Consumes: `collect.collect`, `score.pick_n`, `write.decide_format/write_deep/write_roundup`,
  `images.build_images`, `daily_state.DailyState`, `telegram.Telegram`, `state.State`
  (for `seen_add_many`), `run.load_configs` (reads `sources.yaml`/`voice.yaml`/`settings.yaml`).
- Produces:
  - `article_run.raw_base_url(settings, rel_path: str) -> str` → `f"{settings['images']['raw_base']}/{rel_path}"` with `\\`→`/`.
  - `article_run.send_preview(article, image_paths: list[str], slot: str, date: str, tg) -> None`
    — `tg.send_media_group(image_paths)` then `tg.send_message(text, buttons=[...])` with
    callbacks `art:{date}:{slot}:now`, `art:{date}:{slot}:sched`, `art:{date}:{slot}:drop`;
    button labels `✅ Đăng ngay`, `🕓 Lên lịch {slot_ict}`, `🗑 Bỏ`. Text: meta line
    (`[{format}] {source names} · điểm {score}` + ` ⚠️ nhạy cảm` if `article.risk`),
    blank line, `caption_fb` (truncated to 900 chars + ` …`), blank line, hashtags.
  - `article_run.draft(slot: str, root: Path, now: datetime, *, generate=None, tg=None) -> dict`
    — full pipeline: load configs → `collect` → `pick_n(1, min_score, exclude_titles=<other slot's stored title or []>)`
    → if empty: `tg.send_message("Không có tin AI đủ nóng…")` and return `{"slot": slot, "status": "none"}`
    → gather up to `roundup_max` candidates for format decision → `decide_format` →
    `write_deep`/`write_roundup` → `build_images` into
    `assets/posts/{date}/{slot}/` → `seen.seen_add_many` → `DailyState.put(date, slot, status="draft", format=…, title=<picked title>, topic_key=<slug>, text_fb=…, text_ig=…, hashtags=…, images=[rel paths], image_urls=[raw urls], risk=…, slot_ict=…, sources=…)` →
    `send_preview` → return the slot dict.
  - `article_run.main(argv=None) -> int` — argparse `--slot morning|evening --root . [--fake-llm]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_article_run.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import article_run
from pipeline.models import Candidate, ArticleContent
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.media = []; self.msgs = []
    def send_media_group(self, paths, caption=""): self.media.append(list(paths))
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))


@pytest.fixture
def wired(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text("google_news: {queries: [], langs: []}\nkeywords: [AI]\n", encoding="utf-8")
    (tmp_path / "config" / "voice.yaml").write_text(
        "xung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ngiong: vui\ncam_ky: []\nten_kenh: A Hít\n", encoding="utf-8")
    (tmp_path / "config" / "settings.yaml").write_text(
        "articles:\n  slots: {morning: '11:30', evening: '19:45'}\n  min_score: 10\n"
        "  format_deep_margin: 12\n  roundup_min: 3\n  roundup_max: 5\n"
        "images:\n  style_prompt: x\n  size: '1080x1350'\n  raw_base: https://raw/base\n", encoding="utf-8")
    cand = Candidate(url="https://o/x", title="OpenAI ships GPT-6", source="rss:OpenAI",
                     published_at=datetime(2026, 9, 6, 6, tzinfo=timezone.utc),
                     summary="big", full_text="big news", raw_score_hint=900, source_count=3)
    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [cand])
    art = ArticleContent(format="deep", caption_fb="body\n\nCTA", caption_ig="ig",
                         hashtags=["#AI"], cover_title="GPT-6", cover_brief="core",
                         image_briefs=["a", "b"], sources=[{"name": "OpenAI", "url": "https://o/x"}])
    monkeypatch.setattr(article_run.write, "write_deep", lambda *a, **k: art)
    monkeypatch.setattr(article_run.write, "write_roundup", lambda *a, **k: art)
    monkeypatch.setattr(article_run.images, "build_images",
                        lambda *a, **k: [str(tmp_path / "01_cover.jpg"), str(tmp_path / "02.jpg")])
    return tmp_path, cand


def test_draft_writes_state_and_preview(wired):
    root, _ = wired
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    slot = article_run.draft("morning", root, now, tg=tg)
    assert slot["status"] == "draft"
    assert slot["format"] == "deep"
    ds = DailyState(root / "data")
    assert ds.get("2026-09-06", "morning")["title"] == "OpenAI ships GPT-6"
    assert tg.media and tg.msgs
    _, buttons = tg.msgs[-1]
    assert [b[1] for b in buttons] == ["art:2026-09-06:morning:now",
                                       "art:2026-09-06:morning:sched",
                                       "art:2026-09-06:morning:drop"]


def test_draft_evening_excludes_morning_title(wired, monkeypatch):
    root, cand = wired
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", title="OpenAI ships GPT-6 today")
    seen = {}
    monkeypatch.setattr(article_run.score, "pick_n",
                        lambda *a, **k: seen.setdefault("ex", k.get("exclude_titles")) and [])
    tg = FakeTG()
    now = datetime(2026, 9, 6, 10, 5, tzinfo=timezone.utc)
    out = article_run.draft("evening", root, now, tg=tg)
    assert out["status"] == "none"
    assert "OpenAI ships GPT-6 today" in seen["ex"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_article_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.article_run'`

- [ ] **Step 3: Implement `src/pipeline/article_run.py`**

```python
from __future__ import annotations
import argparse, logging, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import collect, score, write, images
from .daily_state import DailyState
from .state import State
from .telegram import Telegram
from .llm import generate as _default_generate

log = logging.getLogger("article_run")
_OTHER = {"morning": "evening", "evening": "morning"}


def _configs(root: Path):
    c = Path(root) / "config"
    return (yaml.safe_load((c / "sources.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "voice.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "settings.yaml").read_text(encoding="utf-8")))


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-zA-Z0-9]+", "-", t)).strip("-").lower()[:50]


def _parse_size(s: str) -> tuple[int, int]:
    w, h = s.lower().split("x")
    return int(w), int(h)


def raw_base_url(settings: dict, rel_path: str) -> str:
    return f"{settings['images']['raw_base']}/{rel_path}".replace("\\", "/")


def send_preview(article, image_paths, slot, date, tg, slot_ict, score_val):
    tg.send_media_group(image_paths)
    src = ", ".join(s["name"] for s in article.sources)
    meta = f"[{article.format}] {src} · điểm {score_val:.0f}"
    if article.risk:
        meta += " ⚠️ nhạy cảm"
    cap = article.caption_fb
    body = cap if len(cap) <= 900 else cap[:900] + " …"
    text = f"{meta}\n\n{body}\n\n{' '.join(article.hashtags)}"
    tg.send_message(text, buttons=[
        ("✅ Đăng ngay", f"art:{date}:{slot}:now"),
        (f"🕓 Lên lịch {slot_ict}", f"art:{date}:{slot}:sched"),
        ("🗑 Bỏ", f"art:{date}:{slot}:drop")])


def draft(slot, root, now, *, generate=None, tg=None):
    root = Path(root)
    generate = generate or _default_generate
    tg = tg or Telegram()
    sources, voice, settings = _configs(root)
    acfg = settings["articles"]
    date = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    ds = DailyState(root / "data")
    st = State(root / "data")

    other = ds.get(date, _OTHER[slot]) or {}
    exclude = [other["title"]] if other.get("title") else []

    cands = collect.collect(sources, settings, st, now)
    picked = score.pick_n(cands, acfg["roundup_max"], acfg["min_score"], now,
                          sources.get("keywords", []), exclude_titles=exclude)
    if not picked:
        tg.send_message("Không có tin AI đủ nóng cho slot " + slot + " hôm nay.")
        return {"slot": slot, "status": "none"}

    fmt = write.decide_format(picked, acfg["format_deep_margin"])
    top_score, top = picked[0]
    if fmt == "deep":
        article = write.write_deep(top, voice, generate=generate)
    else:
        n = min(max(len(picked), acfg["roundup_min"]), acfg["roundup_max"])
        article = write.write_roundup([c for _, c in picked[:n]], voice, generate=generate)

    rel_dir = f"assets/posts/{date}/{slot}"
    paths = images.build_images(article, root / rel_dir,
                               style_prompt=settings["images"]["style_prompt"],
                               size=_parse_size(settings["images"]["size"]))
    rel_paths = [str(Path(p).relative_to(root)).replace("\\", "/") for p in paths]
    image_urls = [raw_base_url(settings, rp) for rp in rel_paths]

    st.seen_add_many([top.url_hash])
    slot_ict = acfg["slots"][slot]
    ds.put(date, slot, status="draft", format=fmt, title=top.title,
           topic_key=_slug(top.title), text_fb=article.caption_fb,
           text_ig=article.caption_ig, hashtags=article.hashtags,
           images=rel_paths, image_urls=image_urls, risk=article.risk,
           slot_ict=slot_ict, sources=article.sources, score=round(top_score, 1))
    send_preview(article, paths, slot, date, tg, slot_ict, top_score)
    return ds.get(date, slot)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=("morning", "evening"), required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--fake-llm", action="store_true")
    args = ap.parse_args(argv)
    gen = None
    if args.fake_llm:
        from .run import _fake_generate as gen  # reuse the existing canned generator
    out = draft(args.slot, Path(args.root), datetime.now(timezone.utc), generate=gen)
    print("SUMMARY:", out.get("status"), out.get("slot", args.slot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: `write_deep`/`write_roundup`/`build_images` are looked up as module attributes
(`article_run.write.write_deep`, `article_run.images.build_images`) so the tests'
`monkeypatch.setattr` works.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_article_run.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/article_run.py tests/test_article_run.py
git commit -m "feat(p1): article_run.draft gathers, writes, images, previews one slot"
```

---

### Task 13: `article_approve.py` — Telegram button callbacks

**Files:**
- Create: `src/pipeline/article_approve.py`
- Test: `tests/test_article_approve.py`

**Interfaces:**
- Consumes: `daily_state.DailyState`, `telegram.Telegram` (`get_updates`, `answer_callback`,
  `send_message`), `meta.Meta` (`fb_upload_photo`, `fb_create_post`, `ig_publish_images`),
  `state.State` (`offset_load`/`offset_save`).
- Produces:
  - `article_approve.slot_unix(date: str, slot_ict: str) -> int` — UTC unix timestamp for
    `date` + `slot_ict` interpreted as ICT (UTC+7). `date` is `YYYY-MM-DD`,
    `slot_ict` is `HH:MM`.
  - `article_approve.handle_callback(cbq: dict, ds, tg, meta, root: Path, now: datetime) -> str | None`
    — parses `art:{date}:{slot}:{action}`. Loads the slot; if missing or its status is in
    `daily_state.TERMINAL` → `answer_callback("Bài này đã xử lý.")`, return `None`.
    - `now`: upload `images` (as repo-relative paths under `root`) → `fb_create_post(...)`
      (no schedule) → `ig_publish_images(image_urls, ig_caption)` →
      `set_status("posted")`, `put(result=…)`, `send_message("✅ Đã đăng … <fb url>")`.
    - `sched`: `fb_create_post(..., scheduled_publish_time=slot_unix, now_unix=int(now.timestamp()))`
      → `put(fb_post_id=…, ig_due=<iso slot_unix>)`, `set_status("scheduled")`,
      `send_message("🕓 Đã lên lịch, đăng lúc {slot_ict}.")`.
    - `drop`: `set_status("discarded")`, `send_message("🗑 Đã bỏ …")`.
    - `ig_caption` = `text_ig + "\\n\\n" + " ".join(hashtags)`; FB message =
      `text_fb + "\\n\\n" + " ".join(hashtags)`.
  - `article_approve.expire_stale(ds, tg, now: datetime) -> list[str]` — for every daily
    file, any slot with status `draft` whose `slot` time (`slot_unix`) is > 24h before
    `now` → `set_status("expired")`, collect `"{date}:{slot}"`; if any, `send_message`.
  - `article_approve.poll(root: Path, now: datetime | None = None) -> dict` — mirrors
    `approve_poll.poll`: load offset, `get_updates`, route `callback_query`s through
    `handle_callback`, advance offset, then `expire_stale`. Returns
    `{"handled": [...], "expired": [...]}`.
  - `article_approve.main()` → `print(poll(Path(".")))`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_article_approve.py`:

```python
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from pipeline import article_approve
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []; self.acks = []
    def answer_callback(self, cid, text=""): self.acks.append(text)
    def send_message(self, text, buttons=None): self.msgs.append(text)


class FakeMeta:
    def __init__(self): self.scheduled = None; self.ig = None
    def fb_upload_photo(self, p): return "fb:" + Path(p).name
    def fb_create_post(self, msg, ids, scheduled_publish_time=None, now_unix=None):
        self.scheduled = scheduled_publish_time
        return {"id": "P_1", "url": "https://facebook.com/P_1",
                "scheduled": scheduled_publish_time is not None}
    def ig_publish_images(self, urls, caption):
        self.ig = (urls, caption); return {"ok": True, "media_id": "IG_1"}


def _seed(root, status="draft"):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status=status, format="deep",
           text_fb="body", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01_cover.jpg"],
           image_urls=["https://raw/base/assets/posts/2026-09-06/morning/01_cover.jpg"],
           slot_ict="11:30", sources=[{"name": "OpenAI", "url": "https://o/x"}])
    return ds


def _cbq(action):
    return {"id": "cb1", "data": f"art:2026-09-06:morning:{action}"}


def test_now_publishes_both(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert res == "posted:2026-09-06:morning"
    assert meta.scheduled is None and meta.ig is not None
    assert ds.get("2026-09-06", "morning")["status"] == "posted"


def test_sched_uses_native_schedule(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)     # 07:40 ICT
    article_approve.handle_callback(_cbq("sched"), ds, tg, meta, tmp_path, now)
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "scheduled"
    assert meta.scheduled == article_approve.slot_unix("2026-09-06", "11:30")
    assert slot["ig_due"]


def test_late_callback_on_posted_is_ignored(tmp_path):
    ds = _seed(tmp_path, status="posted")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert res is None
    assert tg.acks == ["Bài này đã xử lý."]


def test_expire_stale_marks_old_drafts(tmp_path):
    ds = _seed(tmp_path)
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)     # >24h after 11:30 ICT slot
    tg = FakeTG()
    out = article_approve.expire_stale(ds, tg, now)
    assert out == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["status"] == "expired"


def test_slot_unix_is_ict():
    # 2026-09-06 11:30 ICT == 2026-09-06 04:30 UTC
    assert article_approve.slot_unix("2026-09-06", "11:30") == int(
        datetime(2026, 9, 6, 4, 30, tzinfo=timezone.utc).timestamp())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_article_approve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.article_approve'`

- [ ] **Step 3: Implement `src/pipeline/article_approve.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .daily_state import DailyState, TERMINAL
from .state import State
from .telegram import Telegram

log = logging.getLogger("article_approve")
_ICT = timezone(timedelta(hours=7))


def slot_unix(date: str, slot_ict: str) -> int:
    y, m, d = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in slot_ict.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=_ICT).timestamp())


def _meta():
    from .meta import Meta
    return Meta.from_env()


def _fb_message(slot: dict) -> str:
    return slot["text_fb"] + "\n\n" + " ".join(slot["hashtags"])


def _ig_caption(slot: dict) -> str:
    return slot["text_ig"] + "\n\n" + " ".join(slot["hashtags"])


def handle_callback(cbq, ds, tg, meta, root, now):
    data = cbq.get("data", "")
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "art":
        return None
    _, date, slot_name, action = parts
    slot = ds.get(date, slot_name)
    if slot is None or slot.get("status") in TERMINAL:
        tg.answer_callback(cbq["id"], "Bài này đã xử lý.")
        return None

    if action == "now":
        fbids = [meta.fb_upload_photo(str(Path(root) / p)) for p in slot["images"]]
        fb = meta.fb_create_post(_fb_message(slot), fbids)
        try:
            ig = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
        except Exception as e:  # noqa: BLE001
            ig = {"ok": False, "error": str(e)}
        ds.put(date, slot_name, result={"fb": fb, "ig": ig})
        ds.set_status(date, slot_name, "posted")
        tg.answer_callback(cbq["id"], "Đang đăng…")
        tail = "" if ig.get("ok") else " (IG lỗi, thử lại sau)"
        tg.send_message(f"✅ Đã đăng {date}:{slot_name}: {fb['url']}{tail}")
        return f"posted:{date}:{slot_name}"

    if action == "sched":
        when = slot_unix(date, slot["slot_ict"])
        fbids = [meta.fb_upload_photo(str(Path(root) / p)) for p in slot["images"]]
        fb = meta.fb_create_post(_fb_message(slot), fbids,
                                 scheduled_publish_time=when,
                                 now_unix=int(now.timestamp()))
        ds.put(date, slot_name, fb_post_id=fb["id"],
               ig_due=datetime.fromtimestamp(when, tz=timezone.utc).isoformat(),
               result={"fb": fb, "ig": None})
        ds.set_status(date, slot_name, "scheduled")
        tg.answer_callback(cbq["id"], "Đã lên lịch.")
        tg.send_message(f"🕓 Đã lên lịch {date}:{slot_name}, đăng lúc {slot['slot_ict']}.")
        return f"scheduled:{date}:{slot_name}"

    if action == "drop":
        ds.set_status(date, slot_name, "discarded")
        tg.answer_callback(cbq["id"], "Đã bỏ.")
        tg.send_message(f"🗑 Đã bỏ {date}:{slot_name}.")
        return f"discarded:{date}:{slot_name}"
    return None


def expire_stale(ds, tg, now):
    out = []
    for f in ds.all_files():
        date = f.stem
        for slot_name, slot in ds.load(date)["posts"].items():
            if slot.get("status") != "draft":
                continue
            due = slot_unix(date, slot.get("slot_ict", "11:30"))
            if now.timestamp() - due > 24 * 3600:
                ds.set_status(date, slot_name, "expired")
                out.append(f"{date}:{slot_name}")
    if out:
        tg.send_message("⌛ Quá 24h chưa duyệt, đã bỏ: " + ", ".join(out))
    return out


def poll(root, now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    st = State(root / "data")
    ds = DailyState(root / "data")
    tg = Telegram()
    meta = _meta()
    offset = st.offset_load()
    updates = tg.get_updates(offset=offset)
    handled, max_uid = [], offset - 1
    for up in updates:
        max_uid = max(max_uid, up["update_id"])
        cbq = up.get("callback_query")
        if cbq:
            r = handle_callback(cbq, ds, tg, meta, root, now)
            if r:
                handled.append(r)
    if updates:
        st.offset_save(max_uid + 1)
    return {"handled": handled, "expired": expire_stale(ds, tg, now)}


if __name__ == "__main__":
    print(poll(Path(".")))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_article_approve.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_approve.py tests/test_article_approve.py
git commit -m "feat(p1): article_approve handles now/sched/drop callbacks + expiry"
```

---

### Task 14: `article_publish_ig.py` — Instagram slot poller

**Files:**
- Create: `src/pipeline/article_publish_ig.py`
- Test: `tests/test_article_publish_ig.py`

**Interfaces:**
- Consumes: `daily_state.DailyState`, `telegram.Telegram`, `meta.Meta.ig_publish_images`,
  `article_approve._ig_caption`.
- Produces:
  - `article_publish_ig.due_slots(ds, now: datetime) -> list[tuple[str, str, dict]]` —
    `(date, slot_name, slot)` for every slot with `status == "scheduled"`, a non-null
    `ig_due` whose parsed time `<= now`, and `result.ig` falsy.
  - `article_publish_ig.run(root: Path, now: datetime | None = None, *, tg=None, meta=None) -> dict`
    — for each due slot: `ig_publish_images(image_urls, _ig_caption(slot))`; on success
    `put(result={... , "ig": res})` and `send_message("📸 Đã đăng IG …")`; on failure
    `send_message("❌ IG lỗi …")` and leave `result.ig` null (retried next tick). If both
    `result.fb.scheduled` is done and `result.ig` now set → `set_status("posted")`.
    Returns `{"published": [...], "failed": [...]}`.
  - `article_publish_ig.main()` → `print(run(Path(".")))`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_article_publish_ig.py`:

```python
from datetime import datetime, timezone
import pytest
from pipeline import article_publish_ig
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None): self.msgs.append(text)


class FakeMeta:
    def __init__(self, ok=True): self.ok = ok; self.calls = []
    def ig_publish_images(self, urls, caption):
        self.calls.append(urls)
        if not self.ok:
            raise RuntimeError("ig down")
        return {"ok": True, "media_id": "IG_9"}


def _seed(root, ig_due, ig_result=None):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", text_ig="ig", hashtags=["#AI"],
           image_urls=["https://raw/x.jpg"], slot_ict="11:30",
           ig_due=ig_due, result={"fb": {"scheduled": True}, "ig": ig_result})
    return ds


def test_due_slot_gets_published(tmp_path):
    ds = _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 46, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["published"] == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["result"]["ig"]["media_id"] == "IG_9"
    assert ds.get("2026-09-06", "morning")["status"] == "posted"


def test_not_due_is_skipped(tmp_path):
    _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 10, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["published"] == [] and meta.calls == []


def test_already_published_is_skipped(tmp_path):
    _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00", ig_result={"ok": True, "media_id": "old"})
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["published"] == [] and meta.calls == []


def test_failure_is_reported_and_retryable(tmp_path):
    ds = _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta(ok=False)
    now = datetime(2026, 9, 6, 4, 46, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["failed"] == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["result"]["ig"] in (None, {"ok": False})
    assert any("IG lỗi" in m for m in tg.msgs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_article_publish_ig.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.article_publish_ig'`

- [ ] **Step 3: Implement `src/pipeline/article_publish_ig.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from .daily_state import DailyState
from .telegram import Telegram
from .article_approve import _ig_caption

log = logging.getLogger("article_publish_ig")


def _meta():
    from .meta import Meta
    return Meta.from_env()


def due_slots(ds, now):
    out = []
    for f in ds.all_files():
        date = f.stem
        for slot_name, slot in ds.load(date)["posts"].items():
            if slot.get("status") != "scheduled":
                continue
            if not slot.get("ig_due"):
                continue
            due = datetime.fromisoformat(slot["ig_due"])
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due <= now and not (slot.get("result", {}) or {}).get("ig"):
                out.append((date, slot_name, slot))
    return out


def run(root, now=None, *, tg=None, meta=None):
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    ds = DailyState(root / "data")
    tg = tg or Telegram()
    meta = meta or _meta()
    published, failed = [], []
    for date, slot_name, slot in due_slots(ds, now):
        result = dict(slot.get("result") or {})
        try:
            res = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
            result["ig"] = res
            ds.put(date, slot_name, result=result)
            if (result.get("fb") or {}).get("scheduled"):
                ds.set_status(date, slot_name, "posted")
            tg.send_message(f"📸 Đã đăng IG {date}:{slot_name}.")
            published.append(f"{date}:{slot_name}")
        except Exception as e:  # noqa: BLE001
            log.error("ig publish %s:%s failed: %s", date, slot_name, e)
            tg.send_message(f"❌ IG lỗi {date}:{slot_name}: {e}")
            failed.append(f"{date}:{slot_name}")
    return {"published": published, "failed": failed}


if __name__ == "__main__":
    print(run(Path(".")))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_article_publish_ig.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_publish_ig.py tests/test_article_publish_ig.py
git commit -m "feat(p1): article_publish_ig publishes IG carousels at their slot time"
```

---

### Task 15: Workflows, `commit_state.sh`, retire `build.yml`/`approve.yml`

**Files:**
- Create: `.github/workflows/article-morning.yml`, `.github/workflows/article-evening.yml`,
  `.github/workflows/article-approve.yml`, `.github/workflows/article-publish-ig.yml`
- Delete: `.github/workflows/build.yml`, `.github/workflows/approve.yml`
- Modify: `scripts/commit_state.sh` (also stage `assets/`)
- Modify: `tests/test_workflows.py` (retarget assertions to the new workflows)
- Test: `tests/test_workflows.py`

**Interfaces:**
- Consumes: `article_run.main` (`--slot`), `article_approve.poll` (`python -m pipeline.article_approve`),
  `article_publish_ig.run` (`python -m pipeline.article_publish_ig`).
- Produces: four workflow files; `commit_state.sh` stages `data/ output/ assets/`.

- [ ] **Step 1: Rewrite the workflow tests**

Replace `tests/test_workflows.py` with:

```python
from pathlib import Path
import yaml

WF = Path(__file__).resolve().parents[1] / ".github/workflows"


def test_all_workflows_valid_yaml():
    for name in ("article-morning.yml", "article-evening.yml", "article-approve.yml",
                 "article-publish-ig.yml", "refresh-token.yml"):
        data = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
        assert True in data or "on" in data
        assert data["jobs"]


def test_old_workflows_removed():
    assert not (WF / "build.yml").exists()
    assert not (WF / "approve.yml").exists()


def test_morning_and_evening_crons_and_module():
    m = (WF / "article-morning.yml").read_text(encoding="utf-8")
    e = (WF / "article-evening.yml").read_text(encoding="utf-8")
    assert "cron: '0 0 * * *'" in m and "--slot morning" in m
    assert "cron: '0 10 * * *'" in e and "--slot evening" in e
    assert "playwright install" in m and "playwright install" in e
    assert "contents: write" in m


def test_approve_and_ig_crons_and_modules():
    a = (WF / "article-approve.yml").read_text(encoding="utf-8")
    g = (WF / "article-publish-ig.yml").read_text(encoding="utf-8")
    assert "python -m pipeline.article_approve" in a
    assert "*/10 * * * *" in a
    assert "playwright install" not in a
    assert "python -m pipeline.article_publish_ig" in g
    assert "0,15,30,45 4,5,12,13 * * *" in g
    assert "playwright install" not in g


def test_refresh_workflow_monthly():
    assert "cron: '0 2 1 * *'" in (WF / "refresh-token.yml").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workflows.py -v`
Expected: FAIL — new workflow files don't exist yet.

- [ ] **Step 3: Create `.github/workflows/article-morning.yml`**

```yaml
name: article-morning
on:
  schedule:
    - cron: '0 0 * * *'   # 07:00 ICT
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: article-morning
  cancel-in-progress: false
jobs:
  draft:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Install deps
        run: |
          pip install -r requirements.txt
          pip install -e .
          python -m playwright install --with-deps chromium
      - name: Draft morning article
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m pipeline.article_run --slot morning
      - name: Commit state
        run: bash scripts/commit_state.sh
```

- [ ] **Step 4: Create `.github/workflows/article-evening.yml`**

Same as `article-morning.yml` with: `name: article-evening`, `cron: '0 10 * * *'`,
`concurrency.group: article-evening`, step name `Draft evening article`, and
`run: python -m pipeline.article_run --slot evening`.

- [ ] **Step 5: Create `.github/workflows/article-approve.yml`**

```yaml
name: article-approve
on:
  schedule:
    - cron: '*/10 * * * *'
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: article-approve
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
        run: |
          pip install -r requirements.txt
          pip install -e .
      - name: Process approvals
        env:
          META_PAGE_ID: ${{ secrets.META_PAGE_ID }}
          META_PAGE_TOKEN: ${{ secrets.META_PAGE_TOKEN }}
          IG_BUSINESS_ID: ${{ secrets.IG_BUSINESS_ID }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m pipeline.article_approve
      - name: Commit state
        run: bash scripts/commit_state.sh
```

- [ ] **Step 6: Create `.github/workflows/article-publish-ig.yml`**

Same skeleton as `article-approve.yml` with: `name: article-publish-ig`,
`cron: '0,15,30,45 4,5,12,13 * * *'`, `concurrency.group: article-publish-ig`,
step name `Publish due Instagram posts`, `run: python -m pipeline.article_publish_ig`.

- [ ] **Step 7: Delete the old workflows and update `commit_state.sh`**

```bash
git rm .github/workflows/build.yml .github/workflows/approve.yml
```

In `scripts/commit_state.sh`, change the add line to:

```bash
git add data/ output/ assets/ || true
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_workflows.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add .github/workflows/ scripts/commit_state.sh tests/test_workflows.py
git commit -m "feat(p1): article workflows (morning/evening/approve/publish-ig); retire build+approve"
```

---

### Task 16: Retire the old single-story path; full-suite green; CI

**Files:**
- Modify: `src/pipeline/run.py` (drop the article publish path; keep video helpers)
- Modify: `tests/test_run.py` (drop/adjust tests for the removed path)
- Modify: `.github/workflows/video-smoke.yml` — no change expected; confirm it still passes
- Test: whole suite

**Interfaces:**
- Consumes: everything above.
- Produces: `run.py` no longer imports `review`/`publish` for an article flow; `run.build()`
  either removed or reduced to the video-only helper it still needs. `pipeline.run` is no
  longer referenced by any workflow (verified in Task 15 tests).

- [ ] **Step 1: Inventory what still uses `run.py`**

Run: `grep -rn "pipeline.run\|from .run\|from pipeline.run\|import run" src tests .github`
Expected: `article_run.main` imports `run._fake_generate`; `tests/test_run.py` exists;
`video/` code may import `run`. Note every hit.

- [ ] **Step 2: Move `_fake_generate` / `_FAKE_LLM_JSON` into a neutral home**

If `run.build()` is being removed, move `_fake_generate` and `_FAKE_LLM_JSON` from
`run.py` into `src/pipeline/llm.py` (append), and update the import in
`article_run.main` to `from .llm import _fake_generate as gen`. Keep the JSON exactly as
it is in `run.py` today.

- [ ] **Step 3: Reduce `run.py`**

Delete `build()`, `make_id`, `_slug`, `_notify`, `_summary_line`, `_load_local_candidates`,
`load_configs`, and `main()` from `run.py` **only if** Step 1 showed nothing else imports
them. If the video pipeline (`src/pipeline/video/*`) imports any of them, leave those
symbols in place and only delete the article-publish branch inside `build()`. Record the
decision in the commit message.

- [ ] **Step 4: Update `tests/test_run.py`**

Delete tests that exercised the removed article path (`test_build_*`, dry-run publish
tests). Keep any test still relevant to retained helpers. If the whole file is obsolete,
`git rm tests/test_run.py`.

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS, 0 failures. Fix any fallout (imports, fixtures) until green.

- [ ] **Step 6: Confirm the smoke path**

Run: `python -m pipeline.article_run --slot morning --root . --fake-llm` in a checkout
with no credentials.
Expected: it reaches `collect` and then either sends a preview (if network gave stories)
or prints `SUMMARY: none morning` — it must not raise. If `Telegram()` construction fails
without env vars, guard `main()` to build a no-op stand-in when `TELEGRAM_BOT_TOKEN` is
unset and print `SUMMARY: dry` instead.

- [ ] **Step 7: Add CI for the article suite**

If `video-smoke.yml` is the only test workflow, add `.github/workflows/article-test.yml`:

```yaml
name: article-test
on:
  push: { branches: [master] }
  pull_request:
  workflow_dispatch:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt && pip install -e .
      - run: python -m pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(p1): retire single-story run.py path; article-test CI; suite green"
```

---

## Self-Review

**1. Spec coverage**

| Spec item | Task |
|-----------|------|
| 4 workflows at 07:00 / 17:00 / */10 / IG-window | Task 15 |
| Google News RSS source | Task 1 |
| Dedup + `source_count` viral signal | Task 2 |
| `pick_n`, distinct topics, `exclude_titles` | Task 3 |
| `topic_key` slug stored | Task 12 (`_slug`) |
| LLM chooses deep vs roundup (`format_deep_margin`) | Tasks 5, 12 |
| Deep: long caption, 3–4 image briefs, cover title | Task 6 |
| Roundup: numbered items, 1 brief/item | Task 7 |
| Gemini 3.6 image gen, `GEMINI_IMAGE_MODEL` override | Task 8 |
| Cover = Gemini bg + Pillow VN headline overlay; others clean | Task 8 |
| Legacy fallback on Gemini failure | Task 8 |
| Images committed to repo, raw URLs for IG | Tasks 12 (`image_urls`), 15 (`commit_state.sh` adds `assets/`) |
| `data/daily/<date>.json` schema, one-way status | Task 9 |
| Telegram preview: media group + text + `[Đăng ngay][Lên lịch][Bỏ]` | Task 12 |
| Callback: now → publish both immediately | Task 13 |
| Callback: sched → FB `scheduled_publish_time`, set `ig_due` | Tasks 10, 13 |
| Callback: drop → discarded | Task 13 |
| Not approved by slot → stays draft, no publish, 24h → expired | Task 13 (`expire_stale`) |
| `<10 min` ahead → publish immediately, warn | Task 10 |
| FB multi-photo post | Tasks 10, 13 |
| IG carousel / single from public URLs (no tmpfiles) | Tasks 11, 13, 14 |
| IG poller publishes at `ig_due` | Task 14 |
| FB ok / IG fail reporting + retry | Tasks 13, 14 |
| Content guardrails in prompt + `risk` flag surfaced | Tasks 6, 7, 12 |
| `< 2` stories AM → still #1; `0` → skip slot + Telegram note | Task 12 |
| All-sources-fail → Telegram error, no post | Task 12 (propagates `collect.CollectError`) → **gap: `draft()` should catch it and message.** |
| Retire `build.yml` / `approve.yml` / old `run.py` path | Tasks 15, 16 |
| TDD unit + fakes + offline smoke + CI | every task + Task 16 |

**Gap found & fixed inline:** Task 12 `draft()` must catch `collect.CollectError` and send
a Telegram "gom tin lỗi hết nguồn" message instead of raising. Add to Task 12 Step 3,
wrapping the `collect.collect(...)` call:

```python
    try:
        cands = collect.collect(sources, settings, st, now)
    except collect.CollectError as e:
        tg.send_message(f"⚠️ Gom tin lỗi hết nguồn cho slot {slot}: {e}")
        return {"slot": slot, "status": "error"}
```

And add a test to `tests/test_article_run.py`:

```python
def test_draft_reports_collect_failure(wired, monkeypatch):
    root, _ = wired
    def boom(*a, **k):
        raise article_run.collect.CollectError("all sources down")
    monkeypatch.setattr(article_run.collect, "collect", boom)
    tg = FakeTG()
    out = article_run.draft("morning", root, datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc), tg=tg)
    assert out["status"] == "error"
    assert any("Gom tin lỗi" in m for m, _ in tg.msgs)
```

**2. Placeholder scan:** no "TBD"/"handle errors"/"similar to". Task 16 Steps 3–4 are
conditional ("only if nothing else imports them") but give the exact grep and the exact
fallback action, which is appropriate for a cleanup whose blast radius depends on the
video code's imports.

**3. Type consistency:** `pick_n` returns `list[tuple[float, Candidate]]` — consumed that
way in `decide_format` (Task 5), `write_roundup` (`[c for _, c in picked[:n]]`, Task 12),
and `send_preview` (`top_score`, Task 12). `ArticleContent` fields
(`caption_fb/caption_ig/hashtags/cover_title/cover_brief/image_briefs/sources/risk/format`)
are produced in Tasks 6–7 and read in Tasks 8, 12. `DailyState.put/get/set_status/all_files`
signatures match across Tasks 12–14. `Meta.fb_create_post(..., scheduled_publish_time,
now_unix)` and `Meta.ig_publish_images(image_urls, caption)` match between Tasks 10–11 and
their callers in Tasks 13–14. Slot callback string `art:{date}:{slot}:{action}` is emitted
in Task 12 and parsed in Task 13 with the same 4-part shape.
