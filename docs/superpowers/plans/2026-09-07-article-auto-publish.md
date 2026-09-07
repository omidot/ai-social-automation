# Article Auto-Publish (remove Telegram approval gate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The daily article pipeline schedules each post to Facebook + Instagram automatically the moment it is drafted; Telegram becomes a notification with a single 15-minute "Gỡ bài" (undo) button instead of an approval gate.

**Architecture:** A new `src/pipeline/publish.py` owns the "upload photos → `fb_create_post(scheduled)` → arm IG poller" sequence (lifted from `article_approve.handle_callback`). `article_run.draft()` calls it right after building images. `article_approve` loses the `now`/`sched`/`drop` branches, keeps only `undo`, gains a `retry_unscheduled` sweep in `poll()` that re-attempts any slot left at `draft` by a transient publish failure, and expires a `draft` slot the instant its slot time passes.

**Tech Stack:** Python 3.12, `httpx`, Facebook Graph API v21.0, Telegram Bot API, `pytest`.

## Global Constraints

- Python 3.12 (CI floor). Local runs: `.venv/Scripts/python.exe` with `PYTHONUTF8=1`.
- Run tests with: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q` (from repo root `D:\Automation Social`).
- ICT = UTC+7, no DST.
- State is persisted by `scripts/commit_state.sh` staging `data/` + `assets/`. Do not add new top-level state dirs.
- All 4 article workflows share `concurrency.group: pipeline-state`. Do not change that.
- `daily_state.TERMINAL = frozenset({"posted", "discarded", "expired"})`; `set_status` refuses to move a slot out of a TERMINAL status. `scheduled` and `publishing` are NOT terminal.
- Telegram callback_data is `art:{date}:{slot}:{action}` — exactly 4 colon-separated parts.
- User copy is Vietnamese. Match the existing tone of `article_approve.py` messages.
- Never introduce a code path that can publish the same slot twice. Once `fb_create_post` has returned, the slot must never fall back to a status a fresh trigger could act on.

---

### Task 1: `meta.py` — delete a Facebook post and an Instagram media

**Files:**
- Modify: `src/pipeline/meta.py` (add two methods to class `Meta`, after `ig_publish_images`, before the `# ---------- tokens ----------` block)
- Test: `tests/test_meta.py` (append)

**Interfaces:**
- Consumes: `Meta._client` (an `httpx.Client`), `Meta.token`, module fn `_raise_for_graph(r)`, module const `BASE` (`"https://graph.facebook.com/v21.0"`).
- Produces:
  - `Meta.fb_delete_post(self, post_id: str) -> dict`
  - `Meta.ig_delete_media(self, media_id: str) -> dict`
  - Both issue `DELETE {BASE}/{id}?access_token=...`, call `_raise_for_graph`, return `r.json()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_meta.py`:

```python
def test_fb_delete_post_calls_delete(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")
    seen = {}

    class _DR:
        status_code = 200
        is_success = True
        def json(self): return {"success": True}
        @property
        def text(self): return "{}"

    def fake_delete(url, params=None):
        seen["url"] = url
        seen["params"] = params
        return _DR()

    monkeypatch.setattr(m._client, "delete", fake_delete, raising=False)
    assert m.fb_delete_post("P_1") == {"success": True}
    assert seen["url"].endswith("/P_1")
    assert seen["params"]["access_token"] == "TOK"


def test_ig_delete_media_calls_delete(monkeypatch):
    from pipeline.meta import Meta
    m = Meta("PID", "TOK", "IGID")

    class _DR:
        status_code = 200
        is_success = True
        def json(self): return {"success": True}
        @property
        def text(self): return "{}"

    calls = []
    monkeypatch.setattr(m._client, "delete",
                        lambda url, params=None: (calls.append(url), _DR())[1],
                        raising=False)
    assert m.ig_delete_media("IG_9") == {"success": True}
    assert calls[0].endswith("/IG_9")


def test_fb_delete_post_raises_on_graph_error(monkeypatch):
    from pipeline.meta import Meta, MetaError
    m = Meta("PID", "TOK")

    class _ER:
        status_code = 400
        is_success = False
        def json(self): return {"error": {"code": 100, "message": "no such post"}}
        @property
        def text(self): return '{"error":{"code":100}}'
        class request:  # noqa: N801 - stub for _raise_for_graph's f-string
            method = "DELETE"
            class url:  # noqa: N801
                path = "/v21.0/P_1"

    monkeypatch.setattr(m._client, "delete",
                        lambda url, params=None: _ER(), raising=False)
    import pytest
    with pytest.raises(MetaError):
        m.fb_delete_post("P_1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_meta.py -q`
Expected: FAIL — `AttributeError: 'Meta' object has no attribute 'fb_delete_post'`.

- [ ] **Step 3: Add the methods**

In `src/pipeline/meta.py`, immediately after the `ig_publish_images` method:

```python
    def fb_delete_post(self, post_id: str) -> dict:
        r = self._client.delete(f"{BASE}/{post_id}",
                                params={"access_token": self.token})
        _raise_for_graph(r)
        return r.json()

    def ig_delete_media(self, media_id: str) -> dict:
        r = self._client.delete(f"{BASE}/{media_id}",
                                params={"access_token": self.token})
        _raise_for_graph(r)
        return r.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_meta.py -q`
Expected: PASS (all, including the 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/meta.py tests/test_meta.py
git commit -m "feat(meta): fb_delete_post + ig_delete_media for the undo button"
```

---

### Task 2: `publish.py` — the schedule-or-publish sequence

**Files:**
- Create: `src/pipeline/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `daily_state.DailyState` (`.get`, `.put`, `.set_status`), a `Meta`-shaped object with `fb_upload_photo(path)->str`, `fb_create_post(msg, ids, scheduled_publish_time=, now_unix=)->{"id","url","scheduled":bool}`, `ig_publish_images(urls, caption)->{"ok":bool,"media_id":str}`. A `tg` with `send_message(text, buttons=None)`.
- Produces:
  - `slot_unix(date: str, slot_ict: str) -> int` — ICT (UTC+7) wall time → unix seconds.
  - `_fb_message(slot: dict) -> str` — `slot["text_fb"] + "\n\n" + " ".join(slot["hashtags"])`.
  - `_ig_caption(slot: dict) -> str` — same with `slot["text_ig"]`.
  - `schedule_slot(ds, meta, root, date: str, slot_name: str, now: datetime, tg) -> str` — returns `"scheduled:{date}:{slot_name}"` or `"posted:{date}:{slot_name}"`. Raises if `fb_upload_photo`/`fb_create_post` raise (nothing published). Once `fb_create_post` returns, never raises for an IG/state/telegram error — marks `posted` and returns.
  - Precondition: caller has already `ds.put(...)` the content fields AND `ds.set_status(date, slot_name, "publishing")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_publish.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import publish
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))


class FakeMeta:
    def __init__(self): self.sched_arg = None; self.ig = None
    def fb_upload_photo(self, p): return "fb:" + Path(p).name
    def fb_create_post(self, msg, ids, scheduled_publish_time=None, now_unix=None):
        self.sched_arg = scheduled_publish_time
        sched = (scheduled_publish_time is not None and now_unix is not None
                 and (scheduled_publish_time - now_unix) >= 600)
        return {"id": "P_1", "url": "https://facebook.com/P_1", "scheduled": sched}
    def ig_publish_images(self, urls, caption):
        self.ig = (urls, caption); return {"ok": True, "media_id": "IG_1"}


def _seed(root):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="publishing", format="share",
           title="Chủ đề X", text_fb="thân bài", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01.jpg"],
           image_urls=["https://raw/base/assets/posts/2026-09-06/morning/01.jpg"],
           slot_ict="11:30", sources=[])
    return ds


def test_slot_unix_is_ict():
    assert publish.slot_unix("2026-09-06", "11:30") == int(
        datetime(2026, 9, 6, 4, 30, tzinfo=timezone.utc).timestamp())


def test_schedule_slot_uses_native_schedule(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)      # 07:05 ICT, lead ~4h
    res = publish.schedule_slot(ds, meta, tmp_path, "2026-09-06", "morning", now, tg)
    assert res == "scheduled:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "scheduled"
    assert slot["fb_post_id"] == "P_1"
    assert slot["ig_due"]
    assert meta.sched_arg == publish.slot_unix("2026-09-06", "11:30")
    text, buttons = tg.msgs[-1]
    assert "lên lịch" in text.lower()
    assert buttons == [("🗑 Gỡ bài", "art:2026-09-06:morning:undo")]


def test_schedule_slot_too_close_publishes_now(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 25, tzinfo=timezone.utc)     # 5 min before slot
    res = publish.schedule_slot(ds, meta, tmp_path, "2026-09-06", "morning", now, tg)
    assert res == "posted:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "posted"
    assert meta.ig is not None
    assert slot["result"]["ig"]["media_id"] == "IG_1"


def test_schedule_slot_ig_failure_still_posts(tmp_path):
    ds = _seed(tmp_path)
    tg = FakeTG()

    class IGBoom(FakeMeta):
        def ig_publish_images(self, urls, caption):
            raise RuntimeError("IG 400")

    meta = IGBoom()
    now = datetime(2026, 9, 6, 4, 25, tzinfo=timezone.utc)
    res = publish.schedule_slot(ds, meta, tmp_path, "2026-09-06", "morning", now, tg)
    assert res == "posted:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "posted"
    assert slot["result"]["ig"]["ok"] is False
    assert any("IG lỗi" in t for t, _ in tg.msgs)


def test_schedule_slot_raises_when_upload_fails(tmp_path):
    ds = _seed(tmp_path)
    tg = FakeTG()

    class UploadBoom(FakeMeta):
        def fb_upload_photo(self, p):
            raise RuntimeError("(190) Session has expired")

    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError):
        publish.schedule_slot(ds, UploadBoom(), tmp_path, "2026-09-06", "morning", now, tg)
    # nothing published, status untouched by schedule_slot itself
    assert ds.get("2026-09-06", "morning")["status"] == "publishing"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_publish.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.publish'`.

- [ ] **Step 3: Create `src/pipeline/publish.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("publish")
_ICT = timezone(timedelta(hours=7))


def slot_unix(date: str, slot_ict: str) -> int:
    y, m, d = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in slot_ict.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=_ICT).timestamp())


def _fb_message(slot: dict) -> str:
    return slot["text_fb"] + "\n\n" + " ".join(slot["hashtags"])


def _ig_caption(slot: dict) -> str:
    return slot["text_ig"] + "\n\n" + " ".join(slot["hashtags"])


def schedule_slot(ds, meta, root, date: str, slot_name: str,
                  now: datetime, tg) -> str:
    """Upload the carousel and schedule it on Facebook for the slot's ICT time;
    arm the IG poller via ``ig_due``. If the slot is < 600s away, Facebook
    publishes immediately and this also publishes Instagram now.

    Caller MUST have written the content fields and set status "publishing"
    first. Raises on any failure BEFORE ``fb_create_post`` returns (nothing was
    published — the caller makes the slot retryable). After that point never
    raises: an IG/state/telegram error still ends "posted".
    """
    root = Path(root)
    slot = ds.get(date, slot_name)
    when = slot_unix(date, slot["slot_ict"])

    fbids = [meta.fb_upload_photo(str(root / p)) for p in slot["images"]]
    fb = meta.fb_create_post(_fb_message(slot), fbids,
                             scheduled_publish_time=when,
                             now_unix=int(now.timestamp()))
    # --- point of no return: the FB post/creation call has returned ----------
    undo = [("🗑 Gỡ bài", f"art:{date}:{slot_name}:undo")]
    title = slot.get("title", "")

    if fb.get("scheduled"):
        ds.put(date, slot_name, fb_post_id=fb["id"],
               ig_due=datetime.fromtimestamp(when, tz=timezone.utc).isoformat(),
               result={"fb": fb, "ig": None})
        ds.set_status(date, slot_name, "scheduled")
        log.info("scheduled %s:%s for %s", date, slot_name, slot["slot_ict"])
        tg.send_message(
            f"🗓 Đã lên lịch {slot['slot_ict']}: {title}\n{fb['url']}", buttons=undo)
        return f"scheduled:{date}:{slot_name}"

    try:
        ig = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
    except Exception as e:  # noqa: BLE001 - FB already out; IG retry is the poller's job
        ig = {"ok": False, "error": str(e)}
    ds.put(date, slot_name, fb_post_id=fb["id"], result={"fb": fb, "ig": ig})
    ds.set_status(date, slot_name, "posted")
    tail = "" if ig.get("ok") else " (IG lỗi, thử lại sau)"
    tg.send_message(
        f"✅ Đã đăng {slot['slot_ict']}: {title}\n{fb['url']}{tail}", buttons=undo)
    return f"posted:{date}:{slot_name}"
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_publish.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish.py tests/test_publish.py
git commit -m "feat(publish): schedule_slot — FB native schedule + IG arm, extracted from approve"
```

---

### Task 3: point `article_approve` + `article_publish_ig` at `publish.py` helpers

**Files:**
- Modify: `src/pipeline/article_approve.py` (imports + drop the local `slot_unix`/`_fb_message`/`_ig_caption` defs, re-export from publish)
- Modify: `src/pipeline/article_publish_ig.py:8` (`from .article_approve import _ig_caption` → `from .publish import _ig_caption`)
- Test: existing `tests/test_article_approve.py::test_slot_unix_is_ict`, `tests/test_article_publish_ig.py` must still pass unchanged.

**Interfaces:**
- Consumes: Task 2's `publish.slot_unix`, `publish._fb_message`, `publish._ig_caption`.
- Produces: `article_approve.slot_unix` / `._fb_message` / `._ig_caption` remain importable (re-export) so no other test churns.

- [ ] **Step 1: Edit `article_approve.py`**

Replace the top-of-file `_ICT`, `slot_unix`, `_fb_message`, `_ig_caption` definitions with a re-export. The new header (keep everything else in the file for now — later tasks gut `handle_callback`):

```python
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .daily_state import DailyState
from .state import State
from .telegram import Telegram
from .publish import slot_unix, _fb_message, _ig_caption  # noqa: F401 - re-export

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("article_approve")

ACTIONABLE = frozenset({"draft"})
```

Delete the now-duplicated `_ICT = timezone(...)`, `def slot_unix`, `def _fb_message`, `def _ig_caption` bodies.

- [ ] **Step 2: Edit `article_publish_ig.py:8`**

```python
from .publish import _ig_caption
```

- [ ] **Step 3: Run the affected suites**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py tests/test_article_publish_ig.py -q`
Expected: PASS (unchanged — the re-export keeps every symbol reachable).

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/article_approve.py src/pipeline/article_publish_ig.py
git commit -m "refactor: source slot_unix/_fb_message/_ig_caption from publish.py"
```

---

### Task 4: `article_run.draft()` — schedule instead of preview

**Files:**
- Modify: `src/pipeline/article_run.py` — `draft()` signature + tail; delete `send_preview`; drop the `send_preview` import usage.
- Test: `tests/test_article_run.py` (rewrite the preview-centric assertions)

**Interfaces:**
- Consumes: `publish.schedule_slot(ds, meta, root, date, slot, now, tg)` (Task 2).
- Produces: `draft(slot, root, now, *, generate=None, tg=None, meta=None) -> dict`.
  - On success: slot row ends `status="scheduled"` (or `"posted"` if near slot); return `ds.get(date, slot)`.
  - On `schedule_slot` raising: `ds.set_status(date, slot, "draft")`, `_notify_failure(slot, e)`, return `{"slot": slot, "status": "error"}`.
  - The committed-slot guard now also treats `"scheduled"`/`"posted"`/`"publishing"` as untouchable (unchanged) — plus `draft` rows are re-attempted by `article_approve` (Task 6), so a same-day rerun that finds `draft` proceeds and overwrites, which is fine.

- [ ] **Step 1: Update `tests/test_article_run.py`**

In the `wired` fixture, add a fake schedule so existing flow tests don't hit Meta. After the `build_images` monkeypatch line add:

```python
    monkeypatch.setattr(article_run.publish, "schedule_slot",
                        lambda ds, meta, root, date, slot, now, tg:
                            (ds.set_status(date, slot, "scheduled"),
                             f"scheduled:{date}:{slot}")[1])
```

Replace `test_draft_writes_state_and_preview` with:

```python
def test_draft_writes_state_and_schedules(wired):
    root, _ = wired
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    slot = article_run.draft("morning", root, now, tg=tg, meta=object())
    assert slot["status"] == "scheduled"
    assert slot["format"] == "share"
    ds = DailyState(root / "data")
    saved = ds.get("2026-09-06", "morning")
    assert saved["title"] == "5 công cụ AI dựng video"
    assert saved["sources"] == []
    assert saved["angle"] == "giúp bạn ra video nhanh hơn"
    # media still previewed to Telegram before scheduling
    assert tg.media
```

Delete `test_send_preview_sends_full_caption_in_one_message` and
`test_send_preview_splits_when_over_telegram_limit` (function `send_preview` is gone).

In `test_draft_prefers_news_candidate`, `test_draft_falls_back_to_topic_bank`,
`test_draft_falls_back_when_collect_fails`, `test_draft_excludes_recent_and_other_slot`:
change `assert out["status"] == "draft"` → `"scheduled"`, and every
`tg.msgs[-1][0]` assertion about `📰`/`💡` — move those to check the media caption
or drop them (the news/topic marker now rides the media-group caption; see Step 3).
For the two that assert `"📰"`/`"💡"` in `tg.msgs[-1][0]`, replace with:

```python
    assert any("📰" in c for c in tg.captions)   # news marker
```

and add to `FakeTG`:

```python
    def send_media_group(self, paths, caption=""):
        self.media.append(list(paths)); self.captions.append(caption)
```

plus `self.captions = []` in `FakeTG.__init__`.

Add a new test:

```python
def test_draft_schedule_failure_marks_draft_and_notifies(wired, monkeypatch):
    root, _ = wired

    def boom(*a, **k):
        raise RuntimeError("(190) token expired")

    monkeypatch.setattr(article_run.publish, "schedule_slot", boom)
    notes = []
    monkeypatch.setattr(article_run, "_notify_failure",
                        lambda slot, e: notes.append((slot, str(e))))
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg, meta=object())
    assert out == {"slot": "morning", "status": "error"}
    assert DailyState(root / "data").get("2026-09-06", "morning")["status"] == "draft"
    assert notes and "token expired" in notes[0][1]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -q`
Expected: FAIL — `AttributeError: module 'pipeline.article_run' has no attribute 'publish'` and status assertions.

- [ ] **Step 3: Edit `src/pipeline/article_run.py`**

Add import (top, with the other `from . import`):

```python
from . import write, images, topics, collect, score, publish
```

Add a lazy Meta helper near `_parse_size`:

```python
def _meta():
    from .meta import Meta
    return Meta.from_env()
```

Delete the entire `send_preview` function.

Replace the tail of `draft()` — everything from `rel_dir = ...` to `return ds.get(date, slot)` — with:

```python
    rel_dir = f"assets/posts/{date}/{slot}"
    paths = images.build_images(article, root / rel_dir,
                                size=_parse_size(settings["images"]["size"]),
                                brand=settings["images"].get("brand", {}),
                                root=root)
    rel_paths = [str(Path(p).relative_to(root)).replace("\\", "/") for p in paths]
    image_urls = [raw_base_url(settings, rp) for rp in rel_paths]
    slot_ict = acfg["slots"][slot]

    # preview the carousel to Telegram (informational only — no buttons)
    marker = "📰" if is_news else "💡"
    try:
        tg.send_media_group(paths, caption=f"{marker} {title}")
    except Exception as e:  # noqa: BLE001 - a preview failure must not stop publishing
        log.warning("preview send failed: %s", e)

    ds.put(date, slot, status="publishing", format="share", title=title,
           topic_key=_slug(title), text_fb=article.caption_fb,
           text_ig=article.caption_ig, hashtags=article.hashtags,
           images=rel_paths, image_urls=image_urls, risk=article.risk,
           slot_ict=slot_ict, sources=state_sources, angle=angle)
    try:
        publish.schedule_slot(ds, meta or _meta(), root, date, slot, now, tg)
    except Exception as e:  # noqa: BLE001 - transient publish failure -> retryable
        ds.set_status(date, slot, "draft")
        _notify_failure(slot, e)
        return {"slot": slot, "status": "error"}
    if article.risk:
        tg.send_message(f"⚠️ {date}:{slot} — bài này gắn cờ nhạy cảm, kiểm tra nhanh.")
    return ds.get(date, slot)
```

Change the `draft` signature line to:

```python
def draft(slot: str, root: Path, now: datetime, *, generate=None, tg=None, meta=None) -> dict:
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_run.py tests/test_article_run.py
git commit -m "feat(article_run): auto-schedule on draft; drop the Telegram approval preview"
```

---

### Task 5: `article_approve.handle_callback` — undo only

**Files:**
- Modify: `src/pipeline/article_approve.py` — replace `handle_callback` body; drop `ACTIONABLE`, `_ack` stays.
- Test: `tests/test_article_approve.py` — replace all `now`/`sched`/`drop`/late-callback tests with `undo` tests.

**Interfaces:**
- Consumes: Task 1 `meta.fb_delete_post`, `meta.ig_delete_media`; `publish.slot_unix`.
- Produces: `handle_callback(cbq, ds, tg, meta, root, now) -> str | None`. Only `action == "undo"` does work. Returns `"discarded:{date}:{slot}"` on success, `"undo-expired:{date}:{slot}"` past the grace window, `None` otherwise.
- Module const: `UNDO_GRACE_MIN = 15`.

- [ ] **Step 1: Replace the `now`/`sched`/`drop` tests**

In `tests/test_article_approve.py`: delete `test_now_publishes_both`,
`test_sched_uses_native_schedule`, `test_sched_too_close_publishes_now`,
`test_late_callback_on_posted_is_ignored`, `test_second_callback_on_scheduled_is_ignored`,
`test_inflight_status_set_before_meta_call`,
`test_exception_after_publish_marks_posted_not_draft`,
`test_prepublish_failure_leaves_slot_retryable`, `test_drop_marks_discarded_no_publish`,
`test_missing_slot_reports_desync`, `test_handle_callback_corrupt_daily_file_reports_desync`.

Extend `FakeMeta` with:

```python
    def __init__(self):
        self.scheduled = None; self.ig = None
        self.fb_deleted = []; self.ig_deleted = []
    def fb_delete_post(self, pid): self.fb_deleted.append(pid); return {"success": True}
    def ig_delete_media(self, mid): self.ig_deleted.append(mid); return {"success": True}
```

Add:

```python
def _seed_scheduled(root):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", format="share",
           text_fb="body", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01.jpg"],
           image_urls=["https://raw/x/01.jpg"], slot_ict="11:30", sources=[],
           fb_post_id="P_1", result={"fb": {"id": "P_1"}, "ig": {"media_id": "IG_1"}})
    return ds


def test_undo_deletes_fb_and_ig_within_grace(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)     # 5 min after slot
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now)
    assert res == "discarded:2026-09-06:morning"
    assert meta.fb_deleted == ["P_1"] and meta.ig_deleted == ["IG_1"]
    assert ds.get("2026-09-06", "morning")["status"] == "discarded"


def test_undo_past_grace_is_refused(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)      # 30 min after slot
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now)
    assert res == "undo-expired:2026-09-06:morning"
    assert meta.fb_deleted == [] and meta.ig_deleted == []
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"
    assert any("gỡ thủ công" in m for m in tg.msgs)


def test_undo_missing_slot_is_noop(tmp_path):
    ds = DailyState(tmp_path / "data")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)
    assert article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now) is None
    assert meta.fb_deleted == []


def test_legacy_now_button_is_inert(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)
    assert article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now) is None
    assert meta.fb_deleted == [] and meta.scheduled is None
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"


def test_undo_fb_delete_error_still_marks_discarded(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg = FakeTG()

    class DelBoom(FakeMeta):
        def fb_delete_post(self, pid): raise RuntimeError("Graph 100")

    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, DelBoom(), tmp_path, now)
    assert res == "discarded:2026-09-06:morning"
    assert ds.get("2026-09-06", "morning")["status"] == "discarded"
    assert any("Lỗi" in m for m in tg.msgs)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py -q`
Expected: FAIL (undo path not implemented; legacy `now` still tries to publish).

- [ ] **Step 3: Replace `handle_callback` in `article_approve.py`**

Delete the whole current `handle_callback`. Delete `ACTIONABLE`. Add:

```python
UNDO_GRACE_MIN = 15


def handle_callback(cbq: dict, ds, tg, meta, root: Path, now: datetime) -> str | None:
    parts = cbq.get("data", "").split(":")
    if len(parts) != 4 or parts[0] != "art":
        return None
    _, date, slot_name, action = parts
    if action != "undo":
        # now/sched/drop retired — the pipeline schedules itself
        _ack(tg, cbq["id"], "Nút này không còn dùng.")
        return None

    slot = ds.get_safe(date, slot_name)
    if slot is None or slot.get("status") in ("discarded", "expired"):
        _ack(tg, cbq["id"], "Không có gì để gỡ.")
        return None

    when = slot_unix(date, slot.get("slot_ict", "11:30"))
    if now.timestamp() - when > UNDO_GRACE_MIN * 60:
        _ack(tg, cbq["id"], "Đăng lâu rồi — gỡ tay trên trang.")
        tg.send_message(
            f"⚠️ {date}:{slot_name} đã đăng quá {UNDO_GRACE_MIN} phút, "
            "gỡ thủ công trên Facebook/Instagram.")
        return f"undo-expired:{date}:{slot_name}"

    res = slot.get("result") or {}
    fb_id = (res.get("fb") or {}).get("id") or slot.get("fb_post_id")
    ig_id = (res.get("ig") or {}).get("media_id")
    errs: list[str] = []
    if fb_id:
        try:
            meta.fb_delete_post(fb_id)
        except Exception as e:  # noqa: BLE001
            errs.append(f"FB: {e}")
    if ig_id:
        try:
            meta.ig_delete_media(ig_id)
        except Exception as e:  # noqa: BLE001
            errs.append(f"IG: {e}")
    ds.put(date, slot_name, result={**res, "undone": True})
    ds.set_status(date, slot_name, "discarded")
    _ack(tg, cbq["id"], "Đã gỡ.")
    msg = f"🗑 Đã gỡ {date}:{slot_name} khỏi FB/IG."
    if errs:
        msg += " Lỗi: " + "; ".join(errs)
    tg.send_message(msg)
    return f"discarded:{date}:{slot_name}"
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py -q`
Expected: PASS (undo tests + the still-valid `expire_stale`/`poll` tests; `test_slot_unix_is_ict` passes via the re-export).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_approve.py tests/test_article_approve.py
git commit -m "feat(approve): replace publish gate with a 15-min undo button"
```

---

### Task 6: retry sweep + immediate expiry in `poll()`

**Files:**
- Modify: `src/pipeline/article_approve.py` — new `retry_unscheduled(...)`, call it in `poll()`, tighten `expire_stale`'s `draft` rule.
- Test: `tests/test_article_approve.py` (append)

**Interfaces:**
- Consumes: `publish.schedule_slot` (Task 2).
- Produces:
  - `retry_unscheduled(ds, meta, root, tg, now) -> list[str]` — for every `status=="draft"` slot with `images` and `text_fb` and `now < slot time`: set `"publishing"`, call `schedule_slot`; on failure reset to `"draft"`. Returns the schedule-result tags.
  - `expire_stale` change: a `draft` slot is expired the instant `now >= slot time` (was `> 24h after`). Message unchanged batch, wording `⚠️ ... không lên lịch được, đã bỏ`.
  - `poll()` runs `retry_unscheduled` before `expire_stale`.

- [ ] **Step 1: Append tests**

```python
def _seed_draft_ready(root, slot_ict="11:30"):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="draft", format="share",
           title="X", text_fb="body", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01.jpg"],
           image_urls=["https://raw/x/01.jpg"], slot_ict=slot_ict, sources=[])
    return ds


def test_retry_unscheduled_schedules_ready_draft(tmp_path, monkeypatch):
    ds = _seed_draft_ready(tmp_path)
    tg = FakeTG()
    calls = []
    monkeypatch.setattr(article_approve.publish, "schedule_slot",
                        lambda ds, meta, root, date, slot, now, tg:
                            (calls.append((date, slot)),
                             ds.set_status(date, slot, "scheduled"),
                             f"scheduled:{date}:{slot}")[-1])
    now = datetime(2026, 9, 6, 0, 30, tzinfo=timezone.utc)     # before 11:30 ICT
    out = article_approve.retry_unscheduled(ds, FakeMeta(), tmp_path, tg, now)
    assert out == ["scheduled:2026-09-06:morning"]
    assert calls == [("2026-09-06", "morning")]
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"


def test_retry_unscheduled_resets_to_draft_on_failure(tmp_path, monkeypatch):
    ds = _seed_draft_ready(tmp_path)
    monkeypatch.setattr(article_approve.publish, "schedule_slot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("token")))
    now = datetime(2026, 9, 6, 0, 30, tzinfo=timezone.utc)
    out = article_approve.retry_unscheduled(ds, FakeMeta(), tmp_path, FakeTG(), now)
    assert out == []
    assert ds.get("2026-09-06", "morning")["status"] == "draft"


def test_retry_unscheduled_skips_past_slot(tmp_path, monkeypatch):
    ds = _seed_draft_ready(tmp_path)
    monkeypatch.setattr(article_approve.publish, "schedule_slot",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not schedule a past slot")))
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)      # after 11:30 ICT
    assert article_approve.retry_unscheduled(ds, FakeMeta(), tmp_path, FakeTG(), now) == []


def test_expire_stale_expires_draft_the_moment_slot_passes(tmp_path):
    ds = _seed_draft_ready(tmp_path)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 4, 31, tzinfo=timezone.utc)     # 1 min past 04:30 UTC
    out = article_approve.expire_stale(ds, tg, now)
    assert out == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["status"] == "expired"
    assert any("không lên lịch được" in m for m in tg.msgs)
```

The existing `test_expire_stale_marks_old_drafts` still holds (a 24h-late draft is
also `>= slot time`). Keep it.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py -q`
Expected: FAIL — `retry_unscheduled` missing; `expire_stale` still on the 24h rule.

- [ ] **Step 3: Edit `article_approve.py`**

Add import at top: change the publish import line to also expose the module:

```python
from . import publish
from .publish import slot_unix, _fb_message, _ig_caption  # noqa: F401 - re-export
```

Add the function (after `handle_callback`, before `expire_stale`):

```python
def retry_unscheduled(ds, meta, root: Path, tg, now: datetime) -> list[str]:
    """Re-attempt any slot a transient publish failure left at 'draft'. Only
    slots that already have rendered images + caption and whose slot time is
    still in the future. On failure the slot goes back to 'draft' for the next
    tick; expire_stale sweeps it once the slot time passes."""
    out: list[str] = []
    for f in ds.all_files():
        date = f.stem
        doc = ds.load_safe(date)
        if doc is None:
            continue
        for slot_name, slot in doc["posts"].items():
            if slot.get("status") != "draft":
                continue
            if not (slot.get("images") and slot.get("text_fb")):
                continue
            if now.timestamp() >= slot_unix(date, slot.get("slot_ict", "11:30")):
                continue
            try:
                ds.set_status(date, slot_name, "publishing")
                out.append(publish.schedule_slot(ds, meta, root, date, slot_name, now, tg))
            except Exception as e:  # noqa: BLE001
                ds.set_status(date, slot_name, "draft")
                log.warning("retry schedule %s:%s failed: %s", date, slot_name, e)
    return out
```

In `expire_stale`, replace the `draft` branch:

```python
            if status == "draft":
                if now.timestamp() >= due:
                    ds.set_status(date, slot_name, "expired")
                    out.append(f"{date}:{slot_name}")
```

and the summary line:

```python
    if out:
        tg.send_message("⚠️ Không lên lịch được, đã bỏ: " + ", ".join(out))
```

In `poll()`, add before `expired = expire_stale(...)`:

```python
    retried = retry_unscheduled(ds, meta, root, tg, now)
    if retried:
        log.info("poll: retried=%s", retried)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_approve.py tests/test_article_approve.py
git commit -m "feat(approve): poll retries stuck drafts; draft expires at slot time"
```

---

### Task 7: full-suite green + README/workflow copy

**Files:**
- Modify: `README.md` (the "Lịch chạy" / "Kiến trúc" bullets that still say "duyệt trên Telegram")
- Verify: `.github/workflows/article-approve.yml` unchanged (still `*/5`, still `concurrency.group: pipeline-state`).
- Test: whole suite.

- [ ] **Step 1: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS. If `tests/test_workflows.py` asserts anything about approval buttons, update it to the new reality (only `undo`).

- [ ] **Step 2: Update README**

Find the section describing the Telegram approval flow (search `Đăng ngay`, `Lên lịch`, `duyệt`). Replace with 2-3 lines: pipeline drafts at 07:00 / 17:00 ICT, auto-schedules to 11:30 / 19:45, Telegram posts a `🗓 Đã lên lịch` notice with a 15-minute `🗑 Gỡ bài` undo; a transient failure retries every 5 min until the slot time, then expires.

- [ ] **Step 3: Run CI-parity**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q -p no:cacheprovider`
Expected: PASS (same as Step 1; this just mirrors `article-test.yml`).

- [ ] **Step 4: Commit**

```bash
git add README.md tests/test_workflows.py
git commit -m "docs(p1.5): README describes the auto-schedule flow"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-09-07-article-style-variety-auto-publish-design.md` §1):
- §1.1 auto-schedule in `draft()` → Task 4. `schedule_slot` → Task 2.
- §1.2 failure → `status="draft"` + notify; `fb` set → `posted` → Task 2 (post-`fb_create_post` never raises) + Task 4 (pre-return raise → draft).
- §1.3 `undo` branch, 15-min window from slot time, delete FB+IG, retire `now`/`sched`/`drop` → Task 5.
- §1.4 `retry_unscheduled` before `expire_stale`; draft expires at slot time → Task 6.
- §1.5 `fb_delete_post` / `ig_delete_media` → Task 1.
- §5 risk note: `risk` still stored + surfaced to Telegram → Task 4 (the `⚠️ ... nhạy cảm` message).

**Placeholder scan:** none — every step has concrete code or an exact command.

**Type consistency:** `schedule_slot(ds, meta, root, date, slot_name, now, tg)` — same 7-arg order in Task 2 definition, Task 4 call, Task 6 call. `handle_callback(cbq, ds, tg, meta, root, now)` unchanged from the current signature. `slot_unix(date, slot_ict)` unchanged. `fb_delete_post(post_id)` / `ig_delete_media(media_id)` — same names in Task 1 def, Task 5 calls, Task 5 `FakeMeta`.

**Note for executor:** this plan does NOT add the `style=` field to `ds.put` — that belongs to the style-variety plan (`2026-09-07-article-style-variety.md`), which rebases on top of this branch.
