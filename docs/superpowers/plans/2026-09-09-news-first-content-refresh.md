# News-First Content Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the article pipeline actually publish AI news reactions/opinion/trend
pieces in the channel's Iman-Gadzhi voice, instead of falling back 100% of the time to
a "top N AI tools" listicle bank.

**Architecture:** `score.py`'s scoring gate structurally rejects every single-source
first-party AI news item (confirmed root cause). Fix the gate, broaden
`write.write_share` beyond "a lab just shipped a product" to four angles
(`tin-nong`/`quan-diem`/`xu-huong`/`chuyen-thuc-chien`), and replace the listicle
fallback bank with evergreen opinion/trend prompts that use the same voice and angle
set. `article_run.draft` wires the angle through to state and nudges the two daily
slots toward different angles.

**Tech Stack:** Python 3.12, existing `pipeline.collect`/`score`/`write`/`topics`/
`article_run` modules, pytest.

## Global Constraints

- Python 3.12. Run from repo root `D:\Automation Social`, interpreter
  `.venv/Scripts/python.exe`.
- `ANGLES = {"tin-nong", "quan-diem", "xu-huong", "chuyen-thuc-chien"}` (in `write.py`)
  is the single source of truth for valid angles; the fallback bank only ever produces
  `quan-diem` or `xu-huong`.
- `_IMAN_VOICE` (already in `write.py`) is used by both `write_share` and the new
  `write_take` — do not weaken or duplicate it.
- Never invent a product `domain` — the existing hard rule in `_STORYBOARD_SPEC` stays;
  only the "must always name a product" framing is relaxed.
- `DailyState.put` semantics and the `posts.<slot>.status` one-way TERMINAL guard are
  unrelated to this plan — do not touch `daily_state.py`.
- Every task must leave `tests --ignore=tests/video -q` and `tests/video -q` green
  (video derives its script from the article's `caption_fb` + `angle` string — both
  keep existing shapes, so `tests/video` is unaffected by this plan and is a pure
  regression check, not something any task edits).
- `config/settings.yaml` `articles.min_score` (read via `settings["articles"]["min_score"]`
  in `article_run.py`) is the only min-score key this plan touches — the unrelated
  top-level `min_score: 45` key in the same file is legacy/unused by this path and is
  left alone.

---

## File Structure

| File | Change |
|---|---|
| `src/pipeline/collect.py` | `MAX_AGE_HOURS` 48→96; `ARTICLE_DEBUG` per-feed logging; `ensure_fulltext` exposed |
| `src/pipeline/score.py` | `_TIER1`/`_TIER2`/`_source_tier`; `_recency` denominator 48→96; `ARTICLE_DEBUG` per-candidate logging |
| `src/pipeline/write.py` | `ANGLES`; `build_share_prompt` + `write_share` rewrite (accepts all AI news, emits/validates `angle`, takes a `sibling_angle` hint); `_STORYBOARD_SPEC` reworded; `write_topic_post`/`build_topic_prompt` replaced by `write_take`/`build_take_prompt` |
| `src/pipeline/topics.py` | `propose_topic` prompt targets `takes`/`shifts`, returns `{topic, angle, why}`, takes a `sibling_angle` hint |
| `src/pipeline/models.py` | `ArticleContent.angle: str = ""` |
| `src/pipeline/article_run.py` | call `collect.ensure_fulltext` on picked candidates before `has_body`; pass `sibling_angle` into both writer calls; take the news angle from `write_share`'s result instead of hard-coding `""` |
| `config/settings.yaml` | `articles.min_score` 45→20 |
| `config/topics.yaml` | replaced: `takes` + `shifts` (drops `formats`/`themes`/`seeds`) |
| `tests/test_score.py`, `tests/test_write.py`, `tests/test_topics.py`, `tests/test_article_run.py`, `tests/test_collect.py` | new/updated tests per task |
| `tests/fixtures/sample_share_response.json` | gains `"angle": "tin-nong"` |

Build order: **Task 1** diagnostic logging (done 2026-09-09 — see below) → **Task 2**
fulltext extraction targeting → **Task 3** scoring gate → **Task 4** `write_share` +
`ANGLES` + `ArticleContent.angle` → **Task 5** fallback rewrite (`topics.yaml` +
`propose_topic` + `write_take`) → **Task 6** `article_run` wiring + full suite.

**Controller note — already actioned 2026-09-09.** Task 1's diagnostic was run live
against real feeds (`ARTICLE_DEBUG=1 .venv/Scripts/python.exe -m pipeline.article_run
--slot morning --root . --fake-llm`). It confirmed the scoring-gate hypothesis (§1) AND
surfaced a second, more immediately-blocking root cause (§1a of the spec): every
candidate `pick_n` selects has `full_text=0` because `collect()` full-text-extracts the
top-8-by-*recency* candidates, not the top-4-by-*score* `pick_n` will actually return —
so `has_body()` zeroes out `picked` before `write_share` is ever called, independent of
the scoring formula. Task 2 fixes this specifically; Task 3 (scoring) still matters for
quiet news days with no cross-posted story to inflate scores. Both are needed together
before the news path will visibly fire in production.

---

## Task 1: Diagnostic logging in `collect` and `score`

**Files:**
- Modify: `src/pipeline/collect.py`
- Modify: `src/pipeline/score.py`
- Test: `tests/test_collect.py`, `tests/test_score.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no new public functions. Behaviour is unchanged; only `logging` calls are
  added, gated on `os.environ.get("ARTICLE_DEBUG") == "1"`. Callers are unaffected.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_score.py` (near the top, after existing imports):

```python
import logging


def test_pick_n_debug_logs_component_breakdown(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_DEBUG", "1")
    cand = _c("OpenAI ships GPT-6", hint=0)
    with caplog.at_level(logging.INFO, logger="score"):
        pick_n([cand], 1, min_score=1000, now=datetime(2026, 9, 5, 8, tzinfo=timezone.utc),
              keywords=["AI", "GPT"])
    text = "\n".join(caplog.messages)
    assert "OpenAI ships GPT-6" in text
    assert "recency=" in text and "total=" in text
    assert "below min_score" in text  # min_score=1000 rejects everything


def test_pick_n_debug_silent_by_default(monkeypatch, caplog):
    monkeypatch.delenv("ARTICLE_DEBUG", raising=False)
    cand = _c("OpenAI ships GPT-6", hint=0)
    with caplog.at_level(logging.INFO, logger="score"):
        pick_n([cand], 1, min_score=1000, now=datetime(2026, 9, 5, 8, tzinfo=timezone.utc),
              keywords=["AI", "GPT"])
    assert not any("recency=" in m for m in caplog.messages)
```

Create `tests/test_collect.py` (new file):

```python
import logging
from datetime import datetime, timezone

import pytest

from pipeline import collect


def _rss_response(entries_xml: str) -> str:
    return (
        "<?xml version='1.0'?><rss version='2.0'><channel>"
        f"{entries_xml}"
        "</channel></rss>"
    )


class _FakeResp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


def test_from_rss_debug_logs_feed_counts(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_DEBUG", "1")
    now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    fresh_pub = "Sat, 05 Sep 2026 10:00:00 GMT"   # 2h old -> kept
    stale_pub = "Mon, 01 Sep 2026 10:00:00 GMT"   # way stale -> dropped
    xml = _rss_response(
        f"<item><title>Fresh item</title><link>https://x/1</link>"
        f"<pubDate>{fresh_pub}</pubDate></item>"
        f"<item><title>Stale item</title><link>https://x/2</link>"
        f"<pubDate>{stale_pub}</pubDate></item>"
    )
    monkeypatch.setattr(collect, "_get", lambda url, params=None: _FakeResp(xml))
    with caplog.at_level(logging.INFO, logger="collect"):
        out = collect.from_rss([{"name": "Test Feed", "url": "https://feed"}], now)
    assert len(out) == 1 and out[0].title == "Fresh item"
    text = "\n".join(caplog.messages)
    assert "Test Feed" in text and "parsed=2" in text and "fresh=1" in text


def test_from_rss_debug_silent_by_default(monkeypatch, caplog):
    monkeypatch.delenv("ARTICLE_DEBUG", raising=False)
    now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    xml = _rss_response(
        "<item><title>Fresh item</title><link>https://x/1</link>"
        "<pubDate>Sat, 05 Sep 2026 10:00:00 GMT</pubDate></item>"
    )
    monkeypatch.setattr(collect, "_get", lambda url, params=None: _FakeResp(xml))
    with caplog.at_level(logging.INFO, logger="collect"):
        collect.from_rss([{"name": "Test Feed", "url": "https://feed"}], now)
    assert not any("parsed=" in m for m in caplog.messages)
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_collect.py tests/test_score.py -k "debug" -q`
Expected: FAIL — the log lines don't exist yet (`AssertionError` on the `text` checks).

- [ ] **Step 3: Implement the logging**

In `src/pipeline/collect.py`, add near the top (after the existing imports, before
`MAX_AGE_HOURS`):

```python
import os

_DEBUG = os.environ.get("ARTICLE_DEBUG") == "1"
```

In `from_rss`, replace the body with:

```python
def from_rss(feeds: list[dict], now: datetime) -> list[Candidate]:
    out: list[Candidate] = []
    for feed in feeds:
        try:
            raw = _get(feed["url"]).text
        except Exception as e:  # noqa: BLE001
            log.warning("rss %s failed: %s", feed["name"], e)
            if _DEBUG:
                log.info("feed=%s status=error error=%s", feed["name"], e)
            continue
        parsed = feedparser.parse(raw)
        fresh_count = 0
        for e in parsed.entries:
            dt = _parse_date(e)
            if not dt or not _fresh(dt, now):
                continue
            fresh_count += 1
            out.append(Candidate(
                url=e.get("link", ""), title=e.get("title", "").strip(),
                source=f"rss:{feed['name']}", published_at=dt,
                summary=(e.get("summary", "") or "")[:500]))
        if _DEBUG:
            log.info("feed=%s parsed=%d fresh=%d", feed["name"],
                     len(parsed.entries), fresh_count)
    return out
```

In `src/pipeline/score.py`, add near the top (after imports):

```python
import os

_DEBUG = os.environ.get("ARTICLE_DEBUG") == "1"
```

In `pick_n`, add debug logging for every candidate considered. The function currently
reads (verify against the real file before editing — this is the body as of this
plan's base commit):

```python
def pick_n(cands, n, min_score, now, keywords, exclude_titles=()):
    scored = [(score_candidate(c, now, cands, keywords), c) for c in cands]
    scored.sort(key=lambda t: t[0], reverse=True)
    picked: list[tuple[float, Candidate]] = []
    for sc, c in scored:
        if not is_ai_relevant(c, keywords):
            log.info("skip non-AI: %s", c.title)
            continue
        if sc < min_score:
            break
        blockers = list(exclude_titles) + [pc.title for _, pc in picked]
        ...
```

Insert a debug block right after computing `scored`, and a per-reject debug line at
each `continue`/`break`:

```python
def pick_n(cands, n, min_score, now, keywords, exclude_titles=()):
    scored = [(score_candidate(c, now, cands, keywords), c) for c in cands]
    scored.sort(key=lambda t: t[0], reverse=True)
    if _DEBUG:
        for sc, c in scored:
            hours = max(0.0, (now - c.published_at).total_seconds() / 3600.0)
            log.info(
                "cand=%r source=%s age_h=%.1f recency=%.1f popularity=%.1f "
                "cross_source=%.1f keyword_fit=%.1f source_spread=%.1f "
                "source_tier=%.1f total=%.1f min_score=%.1f",
                c.title, c.source, hours, _recency(c, now), _popularity(c),
                _cross_source(c, cands), _keyword_fit(c, keywords),
                _source_spread(c), _source_tier(c), sc, min_score)
    picked: list[tuple[float, Candidate]] = []
    for sc, c in scored:
        if not is_ai_relevant(c, keywords):
            log.info("skip non-AI: %s", c.title)
            continue
        if sc < min_score:
            if _DEBUG:
                log.info("reject %r: below min_score (%.1f < %.1f)", c.title, sc, min_score)
            break
        blockers = list(exclude_titles) + [pc.title for _, pc in picked]
        ...  # unchanged below this line
```

(`_source_tier` does not exist yet — Task 3 adds it. For Task 1, replace the
`_source_tier(c)` reference in the f-string args with a literal `0.0` placeholder
computed inline as `0.0` — i.e. drop `source_tier=%.1f` and its arg from this task's
log line entirely; Task 3 adds both the field and the function together. This keeps
Task 1 free of a forward reference to code that doesn't exist yet.)

Corrected log line for Task 1 (no `source_tier` term):

```python
            log.info(
                "cand=%r source=%s age_h=%.1f recency=%.1f popularity=%.1f "
                "cross_source=%.1f keyword_fit=%.1f source_spread=%.1f total=%.1f "
                "min_score=%.1f",
                c.title, c.source, hours, _recency(c, now), _popularity(c),
                _cross_source(c, cands), _keyword_fit(c, keywords),
                _source_spread(c), sc, min_score)
```

Do not modify the existing `for sc, c in scored:` loop body beyond the two additions
shown (the debug block before it, and the one `log.info` line inside the
`if sc < min_score:` branch before `break`). Everything else in `pick_n` stays as-is.

- [ ] **Step 4: Run the tests, verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_collect.py tests/test_score.py -k "debug" -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Full regression**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS (all existing + 4 new = unchanged count + 4).
Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS, unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/collect.py src/pipeline/score.py tests/test_collect.py tests/test_score.py
git commit -m "feat(content): ARTICLE_DEBUG diagnostic logging in collect + score"
```

---

## Task 2: Target fulltext extraction at picked candidates, not recency order

**Context (found live, 2026-09-09):** running Task 1's diagnostic against real feeds
showed `score.pick_n` selects 4 legitimate distinct candidates above the *old*
`min_score=45` — but every one had `full_text` empty and a summary under 400 chars, so
`score.has_body()` filtered all 4 out and `write.write_share` was never called.
Cause: `collect.collect()` only fetches full article text for the top-8-by-*recency*
candidates (`result[:fulltext_top]`), which rarely overlaps with the top-4-by-*score*
`pick_n` actually returns. This task fixes that mismatch; it is a prerequisite for
Task 3 (scoring) to have any visible effect in production.

**Files:**
- Modify: `src/pipeline/collect.py`
- Modify: `src/pipeline/article_run.py`
- Test: `tests/test_collect.py`, `tests/test_article_run.py`

**Interfaces:**
- Consumes: `Candidate` (`pipeline.models`); `collect._extract(url) -> tuple[str, str | None]`
  and `collect._is_google_news_url(url) -> bool` (both already exist, private, unchanged).
- Produces: `collect.ensure_fulltext(c: Candidate) -> None` — fetches and attaches full
  article text to `c` **in place**; no-op if `c.full_text` is already truthy or the URL
  is a Google-News interstitial. `article_run.draft` calls it on every `pick_n`-picked
  candidate that still lacks a body, immediately before the existing `has_body` filter.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_collect.py`:

```python
def test_ensure_fulltext_populates_full_text(monkeypatch):
    from pipeline.models import Candidate
    c = Candidate(url="https://example.com/a", title="t", source="rss:X",
                 published_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(collect, "_extract", lambda url: ("full article text here", "https://img/x.jpg"))
    collect.ensure_fulltext(c)
    assert c.full_text == "full article text here"
    assert c.top_image == "https://img/x.jpg"


def test_ensure_fulltext_skips_when_already_has_text(monkeypatch):
    from pipeline.models import Candidate
    c = Candidate(url="https://example.com/a", title="t", source="rss:X",
                 published_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
                 full_text="already here")
    called = []
    monkeypatch.setattr(collect, "_extract", lambda url: called.append(url) or ("new", None))
    collect.ensure_fulltext(c)
    assert c.full_text == "already here"
    assert called == []


def test_ensure_fulltext_skips_google_news_interstitial(monkeypatch):
    from pipeline.models import Candidate
    c = Candidate(url="https://news.google.com/rss/articles/xyz", title="t",
                 source="rss:Google News (x)",
                 published_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    called = []
    monkeypatch.setattr(collect, "_extract", lambda url: called.append(url) or ("new", None))
    collect.ensure_fulltext(c)
    assert c.full_text == ""
    assert called == []
```

(`datetime`, `timezone` are already imported at the top of `tests/test_collect.py` —
verify before adding; add if missing.)

Add to `tests/test_article_run.py`:

```python
def test_picked_candidates_get_fulltext_before_has_body_filter(tmp_path, monkeypatch):
    from pipeline import article_run
    from pipeline.models import Candidate

    short = Candidate(url="https://a/short", title="Short summary AI news",
                      source="rss:OpenAI Blog",
                      published_at=datetime.now(timezone.utc), summary="s" * 50)
    already_full = Candidate(url="https://a/full", title="Already has body",
                             source="rss:OpenAI Blog",
                             published_at=datetime.now(timezone.utc),
                             full_text="f" * 500)
    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [short, already_full])
    monkeypatch.setattr(article_run.score, "pick_n",
                        lambda *a, **k: [(99.0, short), (98.0, already_full)])

    calls = []
    def fake_ensure_fulltext(c):
        calls.append(c.url)
        if c is short:
            c.full_text = "f" * 500   # simulate a successful fetch
    monkeypatch.setattr(article_run.collect, "ensure_fulltext", fake_ensure_fulltext)

    # collect() failing isn't the point of this test; let the news branch run to
    # completion by making write_share fail so we fall through cleanly, and just
    # assert on the ensure_fulltext call pattern captured above.
    monkeypatch.setattr(article_run.write, "write_share",
                        lambda *a, **k: (_ for _ in ()).throw(article_run.write.WriteError("x")))
    monkeypatch.setattr(article_run.topics, "propose_topic",
                        lambda *a, **k: {"topic": "t", "angle": "quan-diem", "why": "w"})
    from pipeline.models import ArticleContent
    monkeypatch.setattr(
        article_run.write, "write_take",
        lambda topic, angle, why, voice, generate=None: ArticleContent(
            format="share", caption_fb="x", caption_ig="y", hashtags=["#AI"],
            cover_title="t",
            slides=[{"role": "hook", "headline": "h", "body": "b", "tools": []},
                    {"role": "item", "headline": "h", "body": "b " * 45,
                     "tool": None, "bullets": []},
                    {"role": "close", "headline": "h", "body": "b"}],
            sources=[], angle=angle))

    article_run.draft("morning", tmp_path, NOW, generate=lambda *a, **k: "",
                      tg=FakeTelegram(), meta=FakeMeta())
    # ensure_fulltext must be called for the short-summary candidate...
    assert "https://a/short" in calls
    # ...but NOT for the one that already has enough body.
    assert "https://a/full" not in calls
```

(As in Task 6's test guidance below: reuse this file's existing `NOW`/`FakeTelegram`/
`FakeMeta` fixtures and whatever `config`/`data` setup its existing `draft()` tests
already perform — do not invent a different fixture shape. Re-read the file's current
top-of-file fixtures before writing this test.)

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_collect.py tests/test_article_run.py -k "ensure_fulltext or fulltext_before_has_body" -q`
Expected: FAIL — `collect.ensure_fulltext` doesn't exist yet.

- [ ] **Step 3: Implement**

In `src/pipeline/collect.py`, find the `collect()` function's fulltext loop (near the
end of the function):

```python
    for c in result[:fulltext_top]:
        if c.full_text:
            continue
        if _is_google_news_url(c.url):
            log.info("skip fulltext for Google-News interstitial: %s", c.url)
            continue
        text, image = _extract(c.url)
        c.full_text = text
        if image and not c.top_image:
            c.top_image = image
```

Replace it with a call to a new, reusable function:

```python
    for c in result[:fulltext_top]:
        ensure_fulltext(c)
```

And add the function itself (place it just above `collect()`, after `_collapse_similar`
or near the other module-level helpers):

```python
def ensure_fulltext(c: Candidate) -> None:
    """Fetch and attach full article text to ``c`` in place, unless it already
    has some or its URL is a known-unfetchable Google-News interstitial."""
    if c.full_text:
        return
    if _is_google_news_url(c.url):
        log.info("skip fulltext for Google-News interstitial: %s", c.url)
        return
    text, image = _extract(c.url)
    c.full_text = text
    if image and not c.top_image:
        c.top_image = image
```

In `src/pipeline/article_run.py`, find (this already carries Task 1's debug lines):

```python
        cands = collect.collect(sources, settings, State(root / "data"), now)
        picked = score.pick_n(cands, 4, acfg["min_score"], now, keywords,
                              exclude_titles=recent)
        if os.environ.get("ARTICLE_DEBUG") == "1":
            log.info("picked_after_score=%d: %s", len(picked),
                     [(sc, c.title, len(c.full_text or ""), len(c.summary or ""))
                      for sc, c in picked])
        picked = [(sc, c) for sc, c in picked if score.has_body(c)]
        if os.environ.get("ARTICLE_DEBUG") == "1":
            log.info("picked_after_has_body=%d", len(picked))
```

Insert the extraction call between the two debug blocks, right before the `has_body`
filter:

```python
        cands = collect.collect(sources, settings, State(root / "data"), now)
        picked = score.pick_n(cands, 4, acfg["min_score"], now, keywords,
                              exclude_titles=recent)
        if os.environ.get("ARTICLE_DEBUG") == "1":
            log.info("picked_after_score=%d: %s", len(picked),
                     [(sc, c.title, len(c.full_text or ""), len(c.summary or ""))
                      for sc, c in picked])
        for _sc, c in picked:
            if not score.has_body(c):
                collect.ensure_fulltext(c)
        picked = [(sc, c) for sc, c in picked if score.has_body(c)]
        if os.environ.get("ARTICLE_DEBUG") == "1":
            log.info("picked_after_has_body=%d", len(picked))
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_collect.py tests/test_article_run.py -q`
Expected: PASS (all, including the 3 + 1 new tests).

- [ ] **Step 5: Full regression**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS.
Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS, unchanged.

- [ ] **Step 6: Live sanity check (controller, optional but recommended)**

`ARTICLE_DEBUG=1 .venv/Scripts/python.exe -m pipeline.article_run --slot morning --root . --fake-llm`
— confirm `picked_after_has_body` is now > 0 on a normal news day (it was 0 before this
task, per the diagnostic run logged in `.superpowers/sdd/progress.md`). This needs
network and is not part of the automated test suite.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/collect.py src/pipeline/article_run.py tests/test_collect.py tests/test_article_run.py
git commit -m "fix(content): extract fulltext for score-picked candidates, not recency order"
```

---

## Task 3: Fix the scoring gate

**Files:**
- Modify: `src/pipeline/score.py`
- Modify: `src/pipeline/collect.py`
- Modify: `config/settings.yaml`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `Candidate` (`pipeline.models`), unchanged.
- Produces: `score._source_tier(c: Candidate) -> float` (new); `score._TIER1`,
  `score._TIER2` (new module constants, `frozenset[str]`); `score_candidate` now
  includes `_source_tier(c)` in its sum; `collect.MAX_AGE_HOURS == 96`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_score.py`:

```python
def test_source_tier_recognises_tier1_and_tier2():
    assert score._source_tier(mk("x", 0, 0, src="rss:OpenAI Blog")) == 15.0
    assert score._source_tier(mk("x", 0, 0, src="rss:Google DeepMind")) == 15.0
    assert score._source_tier(mk("x", 0, 0, src="rss:Anthropic News")) == 15.0
    assert score._source_tier(mk("x", 0, 0, src="rss:TechCrunch AI")) == 8.0
    assert score._source_tier(mk("x", 0, 0, src="rss:The Verge AI")) == 8.0
    assert score._source_tier(mk("x", 0, 0, src="reddit:artificial")) == 0.0
    assert score._source_tier(mk("x", 0, 0, src="hn")) == 0.0


def test_single_source_tier1_news_clears_new_gate():
    # the exact failure mode from production: one first-party blog post, one
    # source, 30h old, no reddit/HN signal.
    cand = mk("OpenAI ra tính năng mới cho agent", 30, 0, src="rss:OpenAI Blog")
    sc = score.score_candidate(cand, NOW, [cand], KW)
    assert sc >= 20  # config/settings.yaml articles.min_score after this task


def test_breaking_cross_posted_story_still_outranks_single_source():
    breaking = [
        _c("OpenAI ships GPT-6 today", hint=0, sc=1),
        _c("OpenAI ships GPT-6 model today", hint=0, sc=1),
    ]
    single = _c("OpenAI shares a minor blog update", hint=0, sc=1)
    breaking_scores = [score.score_candidate(c, NOW, breaking + [single], KW)
                       for c in breaking]
    single_score = score.score_candidate(single, NOW, breaking + [single], KW)
    assert min(breaking_scores) > single_score
```

Add to `tests/test_collect.py`:

```python
def test_max_age_hours_is_96():
    assert collect.MAX_AGE_HOURS == 96


def test_fresh_keeps_80h_drops_100h():
    now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    from datetime import timedelta
    assert collect._fresh(now - timedelta(hours=80), now) is True
    assert collect._fresh(now - timedelta(hours=100), now) is False
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_score.py tests/test_collect.py -k "tier or clears_new_gate or outranks or max_age or 80h" -q`
Expected: FAIL — `_source_tier` doesn't exist; `MAX_AGE_HOURS` is still 48.

- [ ] **Step 3: Implement**

In `src/pipeline/score.py`, add after `_source_spread`:

```python
_TIER1 = frozenset({"openai", "anthropic", "deepmind", "google research", "meta ai",
                    "nvidia", "mistral", "stability", "hugging face", "xai",
                    "microsoft"})
_TIER2 = frozenset({"techcrunch", "the verge", "venturebeat", "ars technica",
                    "mit tech review", "engadget"})


def _source_tier(c: Candidate) -> float:
    s = (c.source or "").lower()
    if any(t in s for t in _TIER1):
        return 15.0
    if any(t in s for t in _TIER2):
        return 8.0
    return 0.0
```

Change `_recency`:

```python
def _recency(c: Candidate, now: datetime) -> float:
    hours = max(0.0, (now - c.published_at).total_seconds() / 3600.0)
    return max(0.0, 40.0 * (1.0 - hours / 96.0))
```

Change `score_candidate`:

```python
def score_candidate(c: Candidate, now: datetime, cohort: list[Candidate],
                    keywords: list[str]) -> float:
    return round(_recency(c, now) + _popularity(c) + _cross_source(c, cohort)
                 + _keyword_fit(c, keywords) + _source_spread(c) + _source_tier(c), 2)
```

Also update the Task 1 debug log line in `pick_n` to include `source_tier` now that
`_source_tier` exists:

```python
            log.info(
                "cand=%r source=%s age_h=%.1f recency=%.1f popularity=%.1f "
                "cross_source=%.1f keyword_fit=%.1f source_spread=%.1f "
                "source_tier=%.1f total=%.1f min_score=%.1f",
                c.title, c.source, hours, _recency(c, now), _popularity(c),
                _cross_source(c, cands), _keyword_fit(c, keywords),
                _source_spread(c), _source_tier(c), sc, min_score)
```

In `src/pipeline/collect.py`, change:

```python
MAX_AGE_HOURS = 48
```
to
```python
MAX_AGE_HOURS = 96
```

In `config/settings.yaml`, under `articles:`, change:

```yaml
articles:
  slots:
    morning: "11:30"
    evening: "19:45"
  min_score: 45
```
to
```yaml
articles:
  slots:
    morning: "11:30"
    evening: "19:45"
  min_score: 20
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_score.py tests/test_collect.py -q`
Expected: PASS (all, including Task 1's + Task 3's new tests).

- [ ] **Step 5: Full regression**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS. Confirm specifically `test_pick_respects_threshold` and
`test_pick_returns_top` (pre-existing, hardcode their own `min_score=45` argument and
default `src="hn"` which scores `_source_tier == 0`) are unaffected.
Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS, unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/score.py src/pipeline/collect.py config/settings.yaml tests/test_score.py tests/test_collect.py
git commit -m "fix(content): scoring gate no longer rejects single-source first-party AI news"
```

---

## Task 4: Broaden `write_share`, add `ANGLES`, relax the storyboard spec

**Files:**
- Modify: `src/pipeline/write.py`
- Modify: `src/pipeline/models.py`
- Modify: `tests/fixtures/sample_share_response.json`
- Test: `tests/test_write.py`

**Interfaces:**
- Consumes: `Candidate` (`pipeline.models`), `_IMAN_VOICE`, `_ARTICLE_GUARDRAILS`,
  `_STORYBOARD_SPEC`, `_validate_share`, `_SHAPE_NUDGE` (all already in `write.py`,
  unchanged in shape).
- Produces:
  - `write.ANGLES: frozenset[str]` = `{"tin-nong", "quan-diem", "xu-huong",
    "chuyen-thuc-chien"}`.
  - `write.build_share_prompt(cand, voice, sibling_angle="") -> tuple[str, str]` (gains
    the `sibling_angle` parameter; existing 2-arg call sites keep working via the
    default).
  - `write.write_share(cand, voice, sibling_angle="", generate=_default_generate) ->
    ArticleContent` — `ArticleContent.angle` is now populated from the model's `angle`
    key (validated against `ANGLES`); raises `WriteError` on an invalid/missing angle.
  - `models.ArticleContent.angle: str = ""` (new field, last in the dataclass).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_write.py`:

```python
def test_angles_constant():
    assert write.ANGLES == {"tin-nong", "quan-diem", "xu-huong", "chuyen-thuc-chien"}


def test_build_share_prompt_lists_all_four_angles():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE)
    for a in write.ANGLES:
        assert a in sysp


def test_build_share_prompt_accepts_non_launch_framing():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE)
    # must no longer say the source has to be a fresh product launch
    assert "VỪA RA MẮT" not in sysp
    assert "rò rỉ" in sysp or "phân tích" in sysp or "gọi vốn" in sysp


def test_build_share_prompt_includes_sibling_angle_hint():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE, sibling_angle="tin-nong")
    assert "tin-nong" in sysp


def test_build_share_prompt_no_hint_when_sibling_angle_blank():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE, sibling_angle="")
    assert "Slot kia" not in sysp


def test_write_share_returns_validated_angle():
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: _share_payload())
    assert art.angle in write.ANGLES


def test_write_share_rejects_invalid_angle():
    data = json.loads(_share_payload())
    data["angle"] = "linh-tinh"
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_rejects_missing_angle():
    data = json.loads(_share_payload())
    del data["angle"]
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_accepts_a_non_launch_source_via_fixture():
    # same fixture, just prove the writer path doesn't special-case "launch"
    # wording anywhere in validation — angle-driven acceptance only.
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: _share_payload())
    assert art.format == "share"


def test_storyboard_spec_allows_toolless_slides():
    assert "hook.tools = []" in write._STORYBOARD_SPEC or "BÌNH THƯỜNG" in write._STORYBOARD_SPEC
```

Update `tests/fixtures/sample_share_response.json`: add a top-level key
`"angle": "tin-nong"` (as a sibling of `"caption_fb"`, `"cover_title"`, etc. — the file
is a single JSON object; insert `"angle": "tin-nong",` right after the opening `{`).

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write.py -k "angle or storyboard_spec_allows" -q`
Expected: FAIL — `write.ANGLES` doesn't exist; `build_share_prompt` doesn't accept
`sibling_angle`; the fixture has no `angle` key so `write_share` (once it requires one)
would fail even the "returns_validated_angle" test until the fixture is updated (which
this step already did) — confirm the failure is about the missing `ANGLES`/parameter,
not the fixture.

- [ ] **Step 3: Implement**

In `src/pipeline/write.py`, add near `ALLOWED_ANGLES` (do not remove
`ALLOWED_ANGLES` — it belongs to the unrelated legacy `write_post`):

```python
ANGLES = frozenset({"tin-nong", "quan-diem", "xu-huong", "chuyen-thuc-chien"})
```

Replace `build_share_prompt` in full:

```python
def build_share_prompt(cand: Candidate, voice: dict, sibling_angle: str = "") -> tuple[str, str]:
    """System + user prompt for the launch-analysis writer.

    The piece is ONE person analysing ONE noteworthy AI-world event — in the
    channel's sharing voice, NOT a reporter, NOT a numbered news round-up. The
    source no longer has to be a fresh product launch: rumor, analysis, funding,
    research, benchmark, controversy, or policy all qualify.
    """
    sibling_line = (
        f"Slot kia hôm nay đã dùng góc \"{sibling_angle}\" — nếu hợp lý, chọn góc "
        "khác cho đa dạng. " if sibling_angle else ""
    )
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        f"{_IMAN_VOICE} "
        "NHIỆM VỤ: bài nguồn nói về MỘT chuyện đáng chú ý trong giới AI — có thể là "
        "ra mắt sản phẩm, rò rỉ/tin đồn, phân tích, gọi vốn, kết quả nghiên cứu, "
        "benchmark, tranh cãi, hay chính sách. Viết một bài PHÂN TÍCH/CHIA SẺ về "
        "chuyện đó, bằng giọng CHIA SẺ của kênh — KHÔNG phải phóng viên, KHÔNG phải "
        "một bản tin, KHÔNG đánh số danh sách tin. "
        f"{sibling_line}"
        "Chọn 'angle' HỢP NHẤT với tin, một trong bốn: "
        "tin-nong (chuyện vừa xảy ra — 'tin này dạy mình điều gì'), "
        "quan-diem (phản biện cách hiểu số đông về chuyện này), "
        "xu-huong (tin này nằm trong một cú dịch chuyển lớn hơn — nêu cú dịch "
        "chuyển đó và nó ảnh hưởng tới người đọc thế nào), "
        "chuyen-thuc-chien (rút ra được cách áp dụng thật, kể như trải nghiệm). "
        "Mở bằng câu hook gây tò mò — KHÔNG mở bằng \"Công ty X vừa công bố...\". "
        "Nếu angle là tin-nong/xu-huong, các slide item bám mạch: (a) chuyện gì "
        "→ (b) nó thực sự nghĩa là gì, dùng chi tiết THẬT trong bài nguồn → "
        "(c) khác gì trước đây → (d) ảnh hưởng tới bạn thế nào → (e) nên làm gì. "
        "Nếu angle là quan-diem: nêu cách hiểu phổ biến → vì sao nó thiếu/sai → "
        "góc đúng hơn → hệ quả. "
        "Nếu angle là chuyen-thuc-chien: bối cảnh → thử thế nào → vướng gì → "
        "bài học rút ra. "
        "Mỗi item body 40-70 từ, cụ thể, dùng chi tiết THẬT trong bài nguồn — "
        "KHÔNG bịa số liệu. "
        "caption_fb: 200-350 từ, VIẾT THÀNH ĐOẠN VĂN MẠCH LẠC (xuống dòng giữa các "
        "ý), TUYỆT ĐỐI KHÔNG đánh số \"1. 2. 3.\", không phải danh sách tin, KHÔNG "
        "chèn URL. Giọng dứt khoát, chia sẻ, \"mình\"/\"bạn\", có chính kiến, không "
        "PR sáo rỗng, không hàn lâm. Kết bằng một câu hỏi. "
        "caption_ig: <=50 từ, cùng tinh thần. "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "angle (một trong bốn mã ở trên), "
        "caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "cover_title (<=9 từ, chính là câu hook), "
        f"{_STORYBOARD_SPEC}, "
        "risk (bool). Toàn bộ tiếng Việt. "
        "Nếu bài nguồn KHÔNG liên quan AI, hoặc không có đủ dữ kiện cụ thể để viết, "
        "trả về ĐÚNG JSON {\"skip\": true, \"reason\": \"...\"} và không gì khác."
    )
    article = (cand.full_text or cand.summary or cand.title)[:6000]
    user = (
        f"TIÊU ĐỀ: {cand.title}\n"
        f"NGUỒN: {cand.source}\n"
        f"URL: {cand.url}\n\n"
        f"NỘI DUNG BÀI GỐC:\n{article}\n"
    )
    return system, user
```

Replace `write_share` in full:

```python
def write_share(cand: Candidate, voice: dict, sibling_angle: str = "",
                generate=_default_generate):
    """Turn one candidate into a single-topic knowledge-share article
    (``format="share"``) with a 4-to-9-slide hook / item... / close storyboard
    and a validated ``angle`` (see ``ANGLES``).

    The LLM often returns a wrong-shaped payload (slide count out of range,
    hook/close not at the ends, invalid angle). Mirror ``video/script.py``:
    validate, and on failure retry once with a correction nudge. A dead backend
    (``LLMError`` from the ``generate`` call itself) is *not* retried; a
    JSON-parse or validation failure — a model-output problem — is.
    """
    system, user = build_share_prompt(cand, voice, sibling_angle)

    for attempt in (1, 2):
        log.info("write_share attempt %d", attempt)
        try:
            raw = generate(system, user, provider="auto")
        except LLMError as e:  # backend down — retrying won't help
            raise WriteError(f"LLM failed: {e}") from e
        try:
            data = parse_json_response(raw)
            if isinstance(data, dict) and data.get("skip"):
                raise _Decline(
                    f"nguồn không phù hợp: {str(data.get('reason', ''))[:200]}")
            angle = str(data.get("angle", "")).strip()
            if angle not in ANGLES:
                raise WriteError(f"angle không hợp lệ: {angle!r}")
            slides = _validate_share(data)
        except _Decline:  # a legitimate, machine-readable refusal — do NOT retry
            raise
        except (LLMError, WriteError) as e:  # bad model output — retryable
            if attempt == 2:
                raise e if isinstance(e, WriteError) else WriteError(f"LLM failed: {e}")
            log.warning("write_share attempt %d rejected: %s", attempt, e)
            user = user + f"\n\n[SỬA] Bản vừa rồi sai định dạng: {e}. " + _SHAPE_NUDGE
            continue

        name = _source_name(cand)
        line = f"Nguồn: {name}"
        cap = _strip_urls(data["caption_fb"])
        if line not in cap:
            cap = f"{cap}\n\n{line}"
        cap_ig = _strip_urls(data["caption_ig"])

        from .models import ArticleContent
        return ArticleContent(
            format="share", caption_fb=cap, caption_ig=cap_ig,
            hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
            cover_title=str(data["cover_title"]).strip(),
            slides=slides,
            sources=[{"name": name, "url": cand.url}],
            risk=bool(data.get("risk", False)),
            angle=angle)
    raise WriteError("unreachable")  # for type-checkers
```

In `_STORYBOARD_SPEC` (the module-level string constant, currently used by both
`write_share` and `write_topic_post`), find this sentence:

```
"Các slide 'item' phải bám ĐÚNG mạch của hook. "
```

Insert immediately after it:

```
"Nhiều bài (quan-diem / xu-huong / tin-nong không xoay quanh một sản phẩm cụ thể) "
"sẽ có hook.tools = [] và mọi item.tool = null — đó là BÌNH THƯỜNG, không phải "
"thiếu sót. "
```

In `src/pipeline/models.py`, change `ArticleContent`'s last field from:

```python
    slides: list[dict]
    sources: list[dict]
    risk: bool = False
```
to
```python
    slides: list[dict]
    sources: list[dict]
    risk: bool = False
    angle: str = ""
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_write.py -q`
Expected: PASS (all existing `write_share`/`write_post` tests + the new ones — note
`test_write_topic_post_*` tests still reference the untouched `write_topic_post`, which
this task does not remove; Task 5 removes/renames them).

- [ ] **Step 5: Full regression**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS.
Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS, unchanged (video's `script.generate_from_article` takes `angle: str`
positionally/by-keyword already — an `ArticleContent.angle` default of `""` does not
change any existing call site outside `write.py`).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/write.py src/pipeline/models.py tests/test_write.py tests/fixtures/sample_share_response.json
git commit -m "feat(content): write_share accepts all AI news, emits a validated angle"
```

---

## Task 5: Replace the listicle fallback bank

**Files:**
- Modify: `config/topics.yaml` (full replace)
- Modify: `src/pipeline/topics.py`
- Modify: `src/pipeline/write.py`
- Test: `tests/test_topics.py`, `tests/test_write.py`

**Interfaces:**
- Consumes: `write.ANGLES`, `write._IMAN_VOICE`, `write._ARTICLE_GUARDRAILS`,
  `write._STORYBOARD_SPEC`, `write._validate_share`, `write._SHAPE_NUDGE` (Task 4).
- Produces:
  - `topics.propose_topic(topics: dict, recent: list[str], voice: dict, generate, sibling_angle: str = "") -> dict`
    — now returns `{"topic": str, "angle": str, "why": str}` with
    `angle ∈ {"quan-diem", "xu-huong"}` (defaults to `"quan-diem"` on an
    invalid/missing angle from the model, with a logged warning).
  - `write.write_take(topic: str, angle: str, why: str, voice: dict, generate=_default_generate) -> ArticleContent`
    — replaces `write.write_topic_post`. `build_take_prompt(topic, angle, why, voice) -> tuple[str, str]`
    replaces `build_topic_prompt`.
  - `write.write_topic_post` and `write.build_topic_prompt` are **removed**.

- [ ] **Step 1: Write the failing tests**

Replace `config/topics.yaml` in full:

```yaml
# Ngân hàng chủ đề fall-back — CHỈ dùng khi không có tin AI nào đáng viết.
# Giọng: sắc, có chính kiến (xem write._IMAN_VOICE). KHÔNG listicle "top công cụ".

# angle = quan-diem
takes:
  - "Đa số người học prompt sai chỗ — thứ thực sự quyết định kết quả"
  - "Đừng vội thay người bằng AI: việc AI vẫn làm tệ hơn bạn"
  - "'Người biết AI sẽ thay người không biết' — câu này đang bỏ sót điều gì"
  - "Học thêm 10 công cụ AI nữa không làm bạn giỏi hơn"
  - "Vì sao 'AI viết giúp' đang làm nhiều người viết dở đi"
  - "Miễn phí không phải lý do để dùng một công cụ AI"
  - "Bạn không cần 'prompt hoàn hảo', bạn cần biết mình muốn gì"
  - "AI làm được 80% việc — và vì sao 20% còn lại mới là nghề của bạn"
  - "Tự động hoá sai việc còn tệ hơn làm tay"
  - "Đo lường sai: vì sao 'tiết kiệm thời gian' không phải thước đo tốt"
  - "Chạy theo mọi model mới là cách chắc chắn không đi tới đâu"
  - "Kỹ năng dùng AI đáng giá nhất không nằm ở phần mềm nào cả"

# angle = xu-huong
shifts:
  - "Cú dịch chuyển từ 'chatbot trả lời' sang 'agent tự làm' — nghĩa là gì với bạn"
  - "Vì sao 12 tháng tới nghề dựng nội dung sẽ tách làm hai nhóm"
  - "Giá token rớt hàng trăm lần — điều đó mở ra cái gì"
  - "Khi ai cũng có cùng công cụ AI, thứ gì trở nên đắt giá"
  - "Nội dung AI tạo tràn lan — người xem sẽ trả tiền cho cái gì"
  - "Từ 'biết code' sang 'biết mô tả điều mình muốn' — nghề lập trình đang đổi"
  - "Vì sao các đội nhỏ giờ làm được việc trước đây cần cả công ty"
  - "AI cá nhân hoá tới mức nào thì thói quen mua hàng thay đổi"
  - "Lớp công việc mới xuất hiện quanh việc 'kiểm định đầu ra của AI'"
  - "Khoảng cách không còn là 'có AI hay không' mà là 'dùng vào đâu'"

recent_window_days: 45
```

In `tests/test_topics.py`, add:

```python
def test_load_topics_has_takes_and_shifts(tmp_path):
    (tmp_path / "config").mkdir()
    import shutil
    shutil.copy("config/topics.yaml", tmp_path / "config" / "topics.yaml")
    t = topics.load_topics(tmp_path)
    assert "takes" in t and "shifts" in t
    assert "formats" not in t and "seeds" not in t


def test_propose_topic_returns_angle_and_why():
    spec = topics.propose_topic(
        {"takes": ["A"], "shifts": ["B"]}, [], VOICE,
        generate=lambda s, u, **k: json.dumps(
            {"topic": "Một chủ đề", "angle": "xu-huong", "why": "vì lý do X"}))
    assert spec == {"topic": "Một chủ đề", "angle": "xu-huong", "why": "vì lý do X"}


def test_propose_topic_defaults_bad_angle_to_quan_diem(caplog):
    spec = topics.propose_topic(
        {"takes": ["A"], "shifts": ["B"]}, [], VOICE,
        generate=lambda s, u, **k: json.dumps(
            {"topic": "Một chủ đề", "angle": "linh-tinh", "why": "x"}))
    assert spec["angle"] == "quan-diem"


def test_propose_topic_prompt_includes_sibling_angle_hint():
    sysp, _usr = topics._build_prompt({"takes": [], "shifts": []}, [], VOICE,
                                      sibling_angle="tin-nong")
    assert "tin-nong" in sysp
```

(Add `import json` at the top of `tests/test_topics.py` if not already present, and a
module-level `VOICE = {"ten_kenh": "A Hít Official", "xung_ho": {"nguoi_noi": "mình",
"nguoi_nghe": "bạn"}}` if the file's existing `VOICE` constant lacks any key these
tests need — reuse it if already defined near the top of the file.)

In `tests/test_write.py`, **replace** every `test_write_topic_post_*` and
`test_build_topic_prompt*` test (there are several — search the file for
`write_topic_post` and `build_topic_prompt` and remove all matches) with:

```python
def _take_payload() -> str:
    data = json.loads(_topic_payload())
    return json.dumps(data)


def test_build_take_prompt_uses_iman_voice_and_angle():
    sysp, usr = write.build_take_prompt(
        "Đa số người học prompt sai chỗ", "quan-diem", "vì họ tối ưu sai thứ", VOICE)
    assert "Đa số người học prompt sai chỗ" in usr
    assert "quan-diem" in usr
    assert "chia sẻ" in sysp or "chính kiến" in sysp


def test_write_take_builds_storyboard_arc():
    art = write.write_take(
        "5 công cụ AI viết content", "quan-diem", "vì hầu hết dùng sai cách",
        VOICE, generate=lambda s, u, **k: _take_payload())
    assert art.format == "share"
    assert art.angle == "quan-diem"
    roles = [s["role"] for s in art.slides]
    assert roles[0] == "hook" and roles[-1] == "close"
    assert all(r == "item" for r in roles[1:-1])
    _assert_v4_slide_shape(art.slides)
    assert art.sources == []
    assert "Nguồn:" not in art.caption_fb
    assert "http" not in art.caption_fb


def test_write_take_accepts_toolless_hook():
    data = json.loads(_topic_payload())
    data["slides"][0]["tools"] = []
    for s in data["slides"][1:-1]:
        s["tool"] = None
    art = write.write_take("Chủ đề không sản phẩm", "xu-huong", "vì...", VOICE,
                           generate=lambda s, u, **k: json.dumps(data))
    assert art.slides[0]["tools"] == []
    assert all(s.get("tool") is None for s in art.slides[1:-1])


def test_write_topic_post_removed():
    assert not hasattr(write, "write_topic_post")
    assert not hasattr(write, "build_topic_prompt")
```

Delete the now-superseded `_topic_payload`-based `write_topic_post` tests you replaced
above (do not leave both old and new tests referencing a removed function — the old
ones would fail with `AttributeError`).

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_topics.py tests/test_write.py -k "take or topic" -q`
Expected: FAIL — `write.write_take`/`build_take_prompt` don't exist yet;
`propose_topic` doesn't return `why` or accept `sibling_angle`; `topics.yaml` load
still returns `formats`/`seeds` until this step's file replace lands (it already did
above, so this should already show "takes"/"shifts" present but the code-side tests
fail on the missing functions).

- [ ] **Step 3: Implement**

In `src/pipeline/topics.py`, replace `_build_prompt`:

```python
def _build_prompt(topics: dict, recent: list[str], voice: dict,
                  sibling_angle: str = "") -> tuple[str, str]:
    ten_kenh = voice.get("ten_kenh", "")
    sibling_line = (
        f"Slot kia hôm nay đã dùng góc \"{sibling_angle}\" — nếu hợp lý, chọn góc "
        "khác cho đa dạng. " if sibling_angle else ""
    )
    system = (
        f"Bạn là người lên chủ đề nội dung cho kênh \"{ten_kenh}\" về AI, năng suất "
        "và kiếm tiền online cho khán giả Việt Nam. Chọn ĐÚNG MỘT mục từ 'takes' "
        "hoặc 'shifts' trong ngân hàng bên dưới (hoặc tự nghĩ một câu cùng tinh "
        "thần), KHÔNG được trùng hay xào lại bất cứ mục nào trong danh sách 'đã "
        f"đăng gần đây'. {sibling_line}"
        "CHỈ trả về JSON: {\"topic\": chuỗi <=16 từ, "
        "\"angle\": \"quan-diem\" nếu lấy cảm hứng từ 'takes' hoặc \"xu-huong\" nếu "
        "từ 'shifts', "
        "\"why\": một câu nêu góc nhìn/lý do chủ đề này đáng nói}."
    )
    recent_block = "\n".join(f"- {t}" for t in recent[:30]) or "(chưa có)"
    user = (
        "ĐÃ ĐĂNG GẦN ĐÂY (tránh lặp lại):\n"
        f"{recent_block}\n\n"
        "NGÂN HÀNG CHỦ ĐỀ (config/topics.yaml):\n"
        f"{yaml.safe_dump(topics, allow_unicode=True, sort_keys=False)}"
    )
    return system, user
```

Replace `propose_topic`:

```python
def propose_topic(topics: dict, recent: list[str], voice: dict, generate,
                  sibling_angle: str = "") -> dict:
    """One LLM call: propose a single specific, non-repeated topic + angle + why."""
    system, user = _build_prompt(topics, recent, voice, sibling_angle)
    raw = generate(system, user, provider="auto")
    try:
        data = parse_json_response(raw)
    except Exception as e:  # noqa: BLE001 - normalise to TopicError
        raise TopicError(f"topic proposal not JSON: {e}") from e
    if not isinstance(data, dict):
        raise TopicError(f"topic proposal wrong shape: {type(data).__name__}")
    topic = str(data.get("topic", "")).strip()
    if not topic:
        raise TopicError(f"topic proposal missing 'topic': {data!r}")
    angle = str(data.get("angle", "")).strip()
    if angle not in ("quan-diem", "xu-huong"):
        log.warning("propose_topic got invalid angle %r, defaulting to quan-diem", angle)
        angle = "quan-diem"
    why = str(data.get("why", "")).strip()
    log.info("proposed topic: %s | angle: %s | why: %s", topic, angle, why)
    return {"topic": topic, "angle": angle, "why": why}
```

In `src/pipeline/write.py`, **delete** `build_topic_prompt` and `write_topic_post` in
their entirety, and add in their place:

```python
def build_take_prompt(topic: str, angle: str, why: str, voice: dict) -> tuple[str, str]:
    """System + user prompt for the knowledge-sourced (fallback) writer.

    No source article — the model writes ``topic`` from its own knowledge, in the
    same Iman-Gadzhi sharing voice and 4-9-slide storyboard as ``write_share``.
    Only ever called with angle 'quan-diem' or 'xu-huong' (see topics.propose_topic).
    """
    system = (
        f"Bạn là người viết tiếng Việt cho kênh \"{voice.get('ten_kenh','')}\" về AI. "
        f"Xưng \"{voice['xung_ho']['nguoi_noi']}\", "
        f"gọi khán giả \"{voice['xung_ho']['nguoi_nghe']}\". "
        f"Điều cấm kỵ: {', '.join(voice.get('cam_ky', []))}. {_ARTICLE_GUARDRAILS} "
        f"{_IMAN_VOICE} "
        f"Đây là bài KHÔNG có bài nguồn — viết từ hiểu biết chung, góc \"{angle}\". "
        "KHÔNG bịa số liệu cụ thể; nếu cần ví dụ, dùng ví dụ chung/định tính thay vì "
        "một con số bạn không chắc. "
        "hook.tools PHẢI là [] và mọi item.tool PHẢI là null — bài này không xoay "
        "quanh một sản phẩm cụ thể. "
        "caption_fb: 200-350 từ, VIẾT THÀNH ĐOẠN VĂN MẠCH LẠC, TUYỆT ĐỐI KHÔNG đánh "
        "số \"1. 2. 3.\", KHÔNG chèn URL. Kết bằng một câu hỏi. "
        "caption_ig: <=50 từ, cùng tinh thần. "
        "CHỈ trả về một object JSON hợp lệ với đúng các khoá: "
        "caption_fb, caption_ig, hashtags (mảng 8-15 chuỗi bắt đầu bằng #), "
        "cover_title (<=9 từ, chính là câu hook), "
        f"{_STORYBOARD_SPEC}, "
        "risk (bool). Toàn bộ tiếng Việt. "
        "Nếu bạn không đủ hiểu biết chắc chắn để viết chủ đề này, trả về ĐÚNG JSON "
        "{\"skip\": true, \"reason\": \"...\"} và không gì khác."
    )
    user = f"CHỦ ĐỀ: {topic}\nGÓC: {angle}\nÝ: {why}\n"
    return system, user


def write_take(topic: str, angle: str, why: str, voice: dict,
               generate=_default_generate):
    """Write a single-topic opinion/trend article (``format="share"``) from the
    model's own knowledge — the fallback bank's writer. Same 2-attempt
    retry-with-``[SỬA]``-nudge loop and 4-9-slide validation as ``write_share``.
    ``sources`` is empty, ``angle`` is the caller-supplied value (not re-derived
    from the model), and no ``Nguồn:`` line is appended.
    """
    system, user = build_take_prompt(topic, angle, why, voice)

    for attempt in (1, 2):
        log.info("write_take attempt %d", attempt)
        try:
            raw = generate(system, user, provider="auto")
        except LLMError as e:  # backend down — retrying won't help
            raise WriteError(f"LLM failed: {e}") from e
        try:
            data = parse_json_response(raw)
            if isinstance(data, dict) and data.get("skip"):
                raise _Decline(
                    f"chủ đề không viết được: {str(data.get('reason', ''))[:200]}")
            slides = _validate_share(data)
        except _Decline:  # a legitimate, machine-readable refusal — do NOT retry
            raise
        except (LLMError, WriteError) as e:  # bad model output — retryable
            if attempt == 2:
                raise e if isinstance(e, WriteError) else WriteError(f"LLM failed: {e}")
            log.warning("write_take attempt %d rejected: %s", attempt, e)
            user = user + f"\n\n[SỬA] Bản vừa rồi sai định dạng: {e}. " + _SHAPE_NUDGE
            continue

        cap = _strip_urls(data["caption_fb"])
        cap_ig = _strip_urls(data["caption_ig"])

        from .models import ArticleContent
        return ArticleContent(
            format="share", caption_fb=cap, caption_ig=cap_ig,
            hashtags=[h if h.startswith("#") else f"#{h}" for h in data["hashtags"]],
            cover_title=str(data["cover_title"]).strip(),
            slides=slides,
            sources=[],
            risk=bool(data.get("risk", False)),
            angle=angle)
    raise WriteError("unreachable")  # for type-checkers
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_topics.py tests/test_write.py -q`
Expected: PASS.

- [ ] **Step 5: Full regression**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS — grep the test suite for any remaining reference to
`write_topic_post`/`build_topic_prompt` outside `test_write.py` first
(`grep -rn "write_topic_post\|build_topic_prompt" tests/ src/`) and update any hit
this task's Step 3 missed.
Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS, unchanged.

- [ ] **Step 6: Commit**

```bash
git add config/topics.yaml src/pipeline/topics.py src/pipeline/write.py tests/test_topics.py tests/test_write.py
git commit -m "feat(content): replace listicle fallback bank with opinion/trend write_take"
```

---

## Task 6: Wire angles through `article_run.draft`

**Files:**
- Modify: `src/pipeline/article_run.py`
- Test: `tests/test_article_run.py`

**Interfaces:**
- Consumes: `write.write_share(cand, voice, sibling_angle, generate=...)`,
  `write.write_take(topic, angle, why, voice, generate=...)`,
  `topics.propose_topic(topics_cfg, recent, voice, generate, sibling_angle=...)` (all
  from Tasks 3-4). `ArticleContent.angle`.
- Produces: no new public function — `draft()`'s external contract (return shape,
  `ds.put` fields) is unchanged except that `posts.<slot>.angle` now holds a real value
  on the news path too (previously always `""` there).

- [ ] **Step 1: Write the failing tests**

First, read the current `draft()` body from `src/pipeline/article_run.py` to get the
exact surrounding lines (it was captured while writing this plan; re-read the file
before editing, since Tasks 1-4 do not touch this file and it should be unchanged from
what's shown below — if it differs, adapt the edit to the real text, not this plan).

Add to `tests/test_article_run.py` (create the fixtures/fakes this file already uses
for `draft()` — check the file's existing `_fake_generate`/`FakeTelegram`/monkeypatch
patterns for `collect`/`write`/`topics` and follow them; the tests below assume a
`monkeypatch.setattr(article_run.collect, "collect", ...)` style already used
elsewhere in the file):

```python
def test_news_path_uses_write_share_angle(tmp_path, monkeypatch):
    from pipeline import article_run, write
    from pipeline.models import Candidate, ArticleContent

    cand = Candidate(url="https://openai.com/x", title="OpenAI tin mới",
                     source="rss:OpenAI Blog",
                     published_at=datetime.now(timezone.utc), summary="s" * 500,
                     full_text="f" * 500)
    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [cand])
    monkeypatch.setattr(article_run.score, "pick_n",
                        lambda *a, **k: [(99.0, cand)])
    monkeypatch.setattr(article_run.score, "has_body", lambda c: True)

    captured = {}
    def fake_write_share(c, voice, sibling_angle="", generate=None):
        captured["sibling_angle"] = sibling_angle
        return ArticleContent(format="share", caption_fb="x", caption_ig="y",
                              hashtags=["#AI"], cover_title="t",
                              slides=[{"role": "hook", "headline": "h", "body": "b",
                                       "tools": []},
                                      {"role": "item", "headline": "h",
                                       "body": "b " * 45, "tool": None, "bullets": []},
                                      {"role": "close", "headline": "h", "body": "b"}],
                              sources=[{"name": "OpenAI", "url": cand.url}],
                              angle="tin-nong")
    monkeypatch.setattr(article_run.write, "write_share", fake_write_share)

    # ... build the same tg/meta/settings fixtures the file's existing draft()
    # tests use, then call article_run.draft("morning", tmp_path, NOW, generate=...,
    # tg=FakeTelegram(), meta=FakeMeta())
    result = article_run.draft("morning", tmp_path, NOW, generate=lambda *a, **k: "",
                               tg=FakeTelegram(), meta=FakeMeta())
    assert result["angle"] == "tin-nong"
    assert result["sources"]
    assert captured["sibling_angle"] == ""  # no sibling slot drafted yet today


def test_fallback_path_uses_write_take_and_angle(tmp_path, monkeypatch):
    from pipeline import article_run

    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [])
    monkeypatch.setattr(article_run.topics, "propose_topic",
                        lambda *a, **k: {"topic": "Một chủ đề", "angle": "xu-huong",
                                        "why": "vì lý do X"})
    from pipeline.models import ArticleContent
    monkeypatch.setattr(
        article_run.write, "write_take",
        lambda topic, angle, why, voice, generate=None: ArticleContent(
            format="share", caption_fb="x", caption_ig="y", hashtags=["#AI"],
            cover_title="t",
            slides=[{"role": "hook", "headline": "h", "body": "b", "tools": []},
                    {"role": "item", "headline": "h", "body": "b " * 45,
                     "tool": None, "bullets": []},
                    {"role": "close", "headline": "h", "body": "b"}],
            sources=[], angle=angle))

    result = article_run.draft("morning", tmp_path, NOW, generate=lambda *a, **k: "",
                               tg=FakeTelegram(), meta=FakeMeta())
    assert result["angle"] == "xu-huong"
    assert result["sources"] == []


def test_evening_gets_morning_angle_as_sibling_hint(tmp_path, monkeypatch):
    from pipeline import article_run
    from pipeline.daily_state import DailyState
    from datetime import datetime as dt

    date = NOW.strftime("%Y-%m-%d")
    ds = DailyState(tmp_path / "data")
    ds.put(date, "morning", status="scheduled", title="Bài sáng", angle="tin-nong")

    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [])
    captured = {}
    def fake_propose(topics_cfg, recent, voice, generate, sibling_angle=""):
        captured["sibling_angle"] = sibling_angle
        return {"topic": "Chủ đề tối", "angle": "quan-diem", "why": "vì..."}
    monkeypatch.setattr(article_run.topics, "propose_topic", fake_propose)
    from pipeline.models import ArticleContent
    monkeypatch.setattr(
        article_run.write, "write_take",
        lambda topic, angle, why, voice, generate=None: ArticleContent(
            format="share", caption_fb="x", caption_ig="y", hashtags=["#AI"],
            cover_title="t",
            slides=[{"role": "hook", "headline": "h", "body": "b", "tools": []},
                    {"role": "item", "headline": "h", "body": "b " * 45,
                     "tool": None, "bullets": []},
                    {"role": "close", "headline": "h", "body": "b"}],
            sources=[], angle=angle))

    article_run.draft("evening", tmp_path, NOW, generate=lambda *a, **k: "",
                      tg=FakeTelegram(), meta=FakeMeta())
    assert captured["sibling_angle"] == "tin-nong"
```

(These three tests assume `NOW`, `FakeTelegram`, `FakeMeta` fixtures already exist in
`tests/test_article_run.py` — reuse them exactly as the file's existing tests do rather
than redefining. If `article_run.draft` also needs `settings`/`voice`/`sources.yaml` on
disk in `tmp_path / "config"`, copy whatever setup the file's existing `draft()` tests
already perform — do not invent a different fixture shape.)

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -k "angle or sibling" -q`
Expected: FAIL — `write_share`/`write_take`/`propose_topic` aren't called with a
`sibling_angle`, and the news-path `angle` is hard-coded `""`.

- [ ] **Step 3: Implement**

In `src/pipeline/article_run.py`, find:

```python
    other = ds.get_safe(date, _OTHER[slot]) or {}
    if other.get("title"):
        recent = [other["title"]] + recent
```

Add immediately after:

```python
    sibling_angle = (other.get("angle") or "").strip()
```

Find:

```python
    for sc, cand in picked:
        attempted.append(cand.url_hash)
        try:
            article = write.write_share(cand, voice, generate=generate)
        except write.WriteError as e:
```

Change the `write_share` call to:

```python
            article = write.write_share(cand, voice, sibling_angle, generate=generate)
```

Find:

```python
    if article is None:
        try:
            spec = topics.propose_topic(topics_cfg, recent, voice, generate)
        except Exception as e:  # noqa: BLE001 - any proposal failure is non-fatal
            tg.send_message(f"⚠️ Không đề xuất được chủ đề {slot}: {e}")
            return {"slot": slot, "status": "error"}
        try:
            article = write.write_topic_post(
                spec["topic"], spec.get("angle", ""), voice, generate=generate)
        except write.WriteError as e:
            tg.send_message(
                f"⚠️ Không viết được bài {slot} (chủ đề: {spec['topic']}): {e}")
            return {"slot": slot, "status": "error"}
        title = spec["topic"]
        angle = spec.get("angle", "")
        state_sources: list[dict] = []
    else:
        title = news_title
        angle = ""
        state_sources = news_sources
```

Replace with:

```python
    if article is None:
        try:
            spec = topics.propose_topic(topics_cfg, recent, voice, generate,
                                        sibling_angle=sibling_angle)
        except Exception as e:  # noqa: BLE001 - any proposal failure is non-fatal
            tg.send_message(f"⚠️ Không đề xuất được chủ đề {slot}: {e}")
            return {"slot": slot, "status": "error"}
        try:
            article = write.write_take(
                spec["topic"], spec["angle"], spec.get("why", ""), voice,
                generate=generate)
        except write.WriteError as e:
            tg.send_message(
                f"⚠️ Không viết được bài {slot} (chủ đề: {spec['topic']}): {e}")
            return {"slot": slot, "status": "error"}
        title = spec["topic"]
        angle = spec["angle"]
        state_sources: list[dict] = []
    else:
        title = news_title
        angle = article.angle
        state_sources = news_sources
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -q`
Expected: PASS (all existing `draft()` tests + the 3 new ones).

- [ ] **Step 5: Full regression**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS, all green.
Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS, unchanged.
Sanity smoke: `.venv/Scripts/python.exe -m pipeline.article_run --slot morning --root . --fake-llm`
Expected: exits cleanly (offline smoke mode, no Telegram token needed), proving the
wiring doesn't crash on a cold run.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/article_run.py tests/test_article_run.py
git commit -m "feat(content): article_run wires angle through both writers + sibling-angle hint"
```

---

## Self-Review

**Spec coverage:**
- §1 root cause / §2 goals 1-2 (gate fix, `write_share` broadening) → Task 3, Task 4.
- §1a second root cause (fulltext extraction targets recency, not score) → Task 2.
- §2 goal 3 (four angles) → `ANGLES` in Task 4, used by Task 4's `write_share` and
  Task 5's `propose_topic`/`write_take`.
- §2 goal 4 (evergreen fallback, no listicles) → Task 5 (`topics.yaml` replace,
  `write_take`).
- §2 goal 5 (daily variety) → Task 6 (`sibling_angle` threaded through both writers).
- §2 goal 6 (diagnostic first) → Task 1, whose live run (2026-09-09) directly produced
  Task 2 and confirmed Task 3's premise — the controller gate described for Task 1→3
  has already fired and is recorded in `.superpowers/sdd/progress.md`.
- §3 angle table → verbatim in Task 4's `build_share_prompt` and Task 5's
  `build_take_prompt`/`_build_prompt`.
- §4.1 diagnostic → Task 1. §4.2a fulltext extraction targeting → Task 2. §4.2 scoring
  gate → Task 3. §4.3 `write_share` → Task 4. §4.4 fallback (`topics.yaml`,
  `propose_topic`, `write_take`) → Task 5. §4.5 `article_run` wiring incl.
  sibling-angle hint → Task 6. §4.6 storyboard relaxation → Task 4.
- §5 file table → matches the plan's File Structure table.
- §6 test list → each task's Step 1 covers its corresponding bullet (collect/
  extraction-targeting tests in Task 2, score tests in Task 3, write tests in Task 4,
  topics tests in Task 5, article_run tests in Task 6, full-suite green checks in every
  task's Step 5).
- §7 build order → Task 1→6 order matches.
- §8 out of scope → no task touches `write_post`/`build_prompt`/`ALLOWED_ANGLES`, the
  video pipeline, `styles`, or `images`; no LLM web search is introduced; the fallback
  never recycles stale news.

**Placeholder scan:** no "TBD"/"handle appropriately"/"similar to Task N" language.
Task 6's Step 1 explicitly instructs re-reading the live file before editing (since it
depends on exact surrounding text Tasks 1-5 don't touch) rather than assuming stale
line numbers — this is a deliberate hedge against drift, not a placeholder, and the
Step 3 old/new text blocks are given in full either way. Task 2's Step 3 old-text block
for `article_run.py` was written against the file's *actual* current state (it already
carries Task 1's debug lines, added by the controller directly and committed as
`1c0ba48`) rather than the pre-Task-1 state — verified by reading the file before
writing this section.

**Type consistency:** `write.ANGLES` (Task 4) is the same set referenced by
`build_share_prompt`'s angle list (Task 4) and `topics.propose_topic`'s
`{"quan-diem","xu-huong"}` subset (Task 5) and `write_take`'s accepted `angle` param
(Task 5, not re-validated against `ANGLES` since the caller — `propose_topic` — already
constrains it). `write_share(cand, voice, sibling_angle="", generate=...)` (Task 4) and
its Task 6 call site `write.write_share(cand, voice, sibling_angle, generate=generate)`
match positionally. `write_take(topic, angle, why, voice, generate=...)` (Task 5) and
its Task 6 call site `write.write_take(spec["topic"], spec["angle"], spec.get("why",""), voice, generate=generate)`
match. `topics.propose_topic(topics, recent, voice, generate, sibling_angle="")`
(Task 5) and its Task 6 call site
`topics.propose_topic(topics_cfg, recent, voice, generate, sibling_angle=sibling_angle)`
match. `ArticleContent.angle: str = ""` (Task 4) is set by both `write_share` (from the
validated model output) and `write_take` (from the caller argument) and read by
`article_run.draft`'s `angle = article.angle` (Task 6) — consistent end to end.
