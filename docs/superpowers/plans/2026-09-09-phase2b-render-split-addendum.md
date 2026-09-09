# Phase 2B addendum — split video render into its own workflow + final-review fixes

Base: `ca6d88f` (branch `feature/p2b-video-render`, after Tasks 1–11).
Origin: the whole-branch review `.superpowers/sdd/final-review.md` found C1 (every video renders a
stale committed `cards.mjs`), C2 (`failed` is a dead end), C3 (uncaught `FileNotFoundError`), and
I1–I5 (rendered MP4 discarded; video deps gate + un-cached on the 5-min poller; render blocks the
15-min article-undo window; killed job replays audio forever; null `video:` key crash).

User decision (2026-09-09): **split rendering into its own `video-render.yml` workflow**; the
article-approve poller only *records* that audio arrived.

## Global Constraints (bind every task)

- Python 3.12. Run from `D:\Automation Social`, interpreter `.venv/Scripts/python.exe`.
- Revised `video.status` machine:
  `awaiting_audio` → (poller) `audio_received` → (render wf) `rendering` → `rendered`
  · render failure → back to `awaiting_audio` (never a terminal `failed`; reason in `render_err`)
  · `awaiting_audio | audio_received | rendering | rendered` → `discarded` via `vid:{d}:{s}:undo`
- `DailyState.put(date, slot, video={...})` does `cur.update` → every write spreads the prior
  `video` dict (`{**v, ...}`) and the post-step writes re-read state first.
- The Remotion script/layout must be regenerated **at render time from `video.script`** in state —
  never trust `video/tools/*.mjs` in the checkout (they are throwaway, git-checkout'd on the drafting
  runner and not committed).
- `article-approve.yml` must carry **no Node / npm / Remotion** steps after this addendum. All video
  deps live only in `video-render.yml`.
- `video-render.yml` shares `concurrency.group: pipeline-state` with the article workflows (no
  concurrent writers to `data/` → no git-rebase races in `commit_state.sh`). A render in progress
  therefore delays an article-approve tick by up to its runtime; `UNDO_GRACE_MIN` is raised to 45 to
  keep article-undo usable across that window.
- `video-render.yml` gates its heavy steps behind a zero-dependency bash check for a pending slot, so
  the ~144 no-op runs/day cost only checkout+setup-python.
- ICT = UTC+7. `settings["video"]["enabled"]` still gates the whole branch.
- No platform publishing (2C). No blocking approval gate. No TTS.

---

## Task 12 — `render.py`: split `record_audio` (poller) from `render_pending` (workflow); land C1/C2/C3/I1/I5

**Files:** modify `src/pipeline/video/render.py`; rewrite the `receive_audio` tests in
`tests/video/test_render.py` (keep the Task-8 helper tests and the `handle_undo` tests unchanged).

### Step 1 — `draft_script.py` writes the Script + an audio slot into state

`src/pipeline/video/draft_script.py`, in the `video = {…}` dict (currently ~line 78):
- add `"script": s.to_dict(),`
- add `"audio_file_id": None,`
- keep every existing key.

(`Script.to_dict` / `Script.from_dict` already exist in `models.py`.)

### Step 2 — `record_audio` (called by the poller)

Replace `receive_audio` with:

```python
def _cfg(root: Path) -> dict:
    data = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")) or {}
    return data.get("video") or {}          # null `video:` key -> {}  (I5)


def is_audio(msg: dict) -> bool:
    return _audio_file_id(msg) is not None


def record_audio(msg: dict, ds, tg, root: Path, now: datetime) -> str | None:
    """Poller side: attach the uploaded audio to a waiting slot and mark it
    `audio_received`. The heavy render happens later in `render_pending`."""
    fid = _audio_file_id(msg)
    if fid is None:
        return None
    root = Path(root)
    if not _cfg(root).get("enabled"):
        return None                         # branch dormant (M9)
    date, slot, v = _find_slot(ds, msg, now)
    if date is None:
        tg.send_message("⚠️ Nhận được audio nhưng không có video nào đang chờ.")
        return None
    ds.put(date, slot, video={**v, "status": "audio_received",
                              "audio_file_id": fid,
                              "audio_msg_id": msg.get("message_id"),
                              "render_err": None})
    tg.send_message(f"🎧 Đã nhận audio cho video {slot} ({date}). "
                    "Đang dựng, vài phút nữa có kết quả.")
    return f"audio_received:{date}:{slot}"
```

`_find_slot` keeps matching only `status == "awaiting_audio"` (a re-upload after a failure works
because `render_pending`'s failure path resets the slot to `awaiting_audio`). Also apply the two
cheap `_find_slot` fixes:
- iterate the slots of each date newest-first by `slot_ict` (`sorted(doc["posts"].items(),
  key=lambda kv: kv[1].get("slot_ict", ""), reverse=True)`) so a same-day tie prefers the later slot
  (M6);
- once a date is older than the 3-day cutoff, `break` the outer loop instead of `continue` (files are
  already iterated newest-first) (M7).

### Step 3 — `render_pending` (called by `video-render.yml`)

```python
def render_pending(ds, tg, root: Path, now: datetime, *, limit: int = 1) -> list[str]:
    """Workflow side: render up to `limit` slots sitting at `audio_received`
    (oldest first). Regenerates the Remotion project from `video.script` in
    state; on any failure the slot returns to `awaiting_audio`."""
    from . import codegen as _codegen
    from .models import Script

    root = Path(root)
    cfg = _cfg(root)
    comp = cfg.get("render_composition", "CodexShort")
    video_dir = root / "video"
    out: list[str] = []

    pending: list[tuple[str, str, dict]] = []
    for f in sorted(ds.all_files()):                     # oldest date first
        doc = ds.load_safe(f.stem)
        if doc is None:
            continue
        for slot, row in doc["posts"].items():
            v = row.get("video") or {}
            if v.get("status") == "audio_received":
                pending.append((f.stem, slot, v))

    for date, slot, v in pending[:limit]:
        ds.put(date, slot, video={**v, "status": "rendering",
                                  "started_at": now.isoformat()})

        def _fail(exc: Exception) -> str:
            cur = (ds.get_safe(date, slot) or {}).get("video") or v
            ds.put(date, slot, video={**cur, "status": "awaiting_audio",
                                      "render_err": f"{type(exc).__name__}: {exc}"[-500:]})
            tg.send_message(f"❌ Render video {slot} ({date}) lỗi: {exc}\n"
                            "Gửi lại audio để thử lại.")
            return f"failed:{date}:{slot}"

        try:
            script_rel = v["script_path"]
            out_dir = root / Path(script_rel).parent
            pid = out_dir.parent.name                    # real story id, not "video" (M2)
            out_mp4 = out_dir / f"{pid}.mp4"

            _codegen.write(Script.from_dict(v["script"]), video_dir)   # C1

            raw = tg.download_file(v["audio_file_id"], str(video_dir / "public" / "voice_in"))
            _to_mp3(Path(raw), video_dir / "public" / "voice.mp3", video_dir)
            dur = _align.make_silence_txt(video_dir / "public" / "voice.mp3",
                                         video_dir / "ref" / "silence.txt", video_dir)
            tl_path = _align.run_aligner(video_dir, dur)
            tl = json.loads(tl_path.read_text(encoding="utf-8"))
            seconds = float(tl.get("duration", 0) or 0)

            out_dir.mkdir(parents=True, exist_ok=True)
            for name in ("tools/cards.mjs", "tools/variants.mjs"):
                src = video_dir / name
                if src.exists():
                    shutil.copy(src, out_dir / Path(name).name)
            shutil.copy(tl_path, out_dir / "timeline.json")
            vmp3 = video_dir / "public" / "voice.mp3"
            if vmp3.exists():
                shutil.copy(vmp3, out_dir / "voice.mp3")

            r = _remotion_render(video_dir, comp, out_mp4)
            if r.returncode != 0 or not out_mp4.exists():
                raise RuntimeError(f"remotion exit {r.returncode}: {(r.stderr or '')[-300:]}")
        except Exception as e:  # noqa: BLE001 - any failure => slot back to awaiting_audio (C2/C3)
            log.exception("render_pending %s:%s failed", date, slot)
            out.append(_fail(e))
            continue

        slot_ict = (ds.get_safe(date, slot) or {}).get("slot_ict", "11:30")
        due = max(now, datetime.fromtimestamp(slot_unix(date, slot_ict), tz=timezone.utc))
        cap = (f"🎬 Video {slot} — {(v.get('meta') or {}).get('title', '')}\n"
               f"{round(seconds, 1)}s. Tự lên lịch đăng {slot_ict}.")
        resp = tg.send_video(str(out_mp4), caption=cap,
                             buttons=[("🗑 Gỡ", f"vid:{date}:{slot}:undo")])
        tg_file_id = (((resp or {}).get("result") or {}).get("video") or {}).get("file_id")   # I1

        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        ds.put(date, slot, video={**cur, "status": "rendered",
                                  "mp4_path": str(out_mp4.relative_to(root)).replace("\\", "/"),
                                  "tg_file_id": tg_file_id,
                                  "seconds": round(seconds, 1), "render_err": None,
                                  "publish_due": due.isoformat()})
        target = cfg.get("target_seconds", 40)
        if not (target * 0.6 <= seconds <= target * 1.4):                                     # nit
            tg.send_message(f"⚠️ Timeline lệch ({seconds:.0f}s), xem kỹ trước khi đăng.")
        out.append(f"rendered:{date}:{slot}")

    return out
```

Notes: the `tg.send_video` + final `ds.put` sit **outside** the try on purpose — a Telegram upload
failure must not bounce a good render back to `awaiting_audio`; it raises out of `render_pending`,
the job's `Commit state: if: always()` still flushes the `rendering`→? state… actually keep it
simple: leave send_video outside the try (a raise here is logged by the workflow, slot stays
`rendering`, `expire_stale` recovers it after 40 min). Do **not** wrap it.

Keep `_audio_file_id`, `_to_mp3`, `_remotion_render`, `_find_slot`, `handle_undo` as they are, except
`handle_undo`'s allowed set becomes `{"awaiting_audio", "audio_received", "rendering", "rendered"}`.

### Step 4 — tests (`tests/video/test_render.py`)

Drop `test_receive_audio_*`. Add, using the existing `FakeTG` / `_seed` / `_mock_pipeline` style
(extend `FakeTG` with `download_file` already present; add `send_video` returning
`{"result": {"video": {"file_id": "TGVID"}}}`):

1. `test_record_audio_attaches_and_marks` — `awaiting_audio` slot + `settings.yaml` `video.enabled:
   true`; `record_audio({"message_id": 9, "voice": {"file_id": "V"}}, …)` → returns
   `"audio_received:{d}:{s}"`, slot `video.status == "audio_received"`, `video.audio_file_id == "V"`,
   a `🎧` Telegram message sent.
2. `test_record_audio_disabled_is_silent` — `video.enabled: false` → returns `None`, no Telegram
   message.
3. `test_record_audio_no_slot_warns` — no `awaiting_audio` slot → `None` + the `⚠️ … không có video
   nào đang chờ` message.
4. `test_render_pending_regenerates_script_and_renders` — seed a slot at `audio_received` with
   `video.script` = a real `Script.to_dict()` (build a tiny `Script` with 1 card), `video.audio_file_id
   = "V"`, `video.script_path = "output/2026-09-08/2026-09-08-story/video/script.json"`; write
   `video/tools/cards.mjs` containing the marker `STALE`; `_mock_pipeline`; monkeypatch
   `render._codegen.write`? no — let the real `codegen.write` run and assert `video/tools/cards.mjs`
   no longer contains `STALE` and contains a token from the seeded card. Assert result
   `["rendered:2026-09-08:morning"]`, `video.status == "rendered"`, `video.tg_file_id == "TGVID"`,
   `video.mp4_path` endswith `.mp4`, `video.seconds` set, a `send_video` recorded.
5. `test_render_pending_failure_resets_to_awaiting` — `_mock_pipeline(render_rc=1)` → result
   `["failed:2026-09-08:morning"]`, `video.status == "awaiting_audio"`, `video.render_err`
   contains `remotion exit 1`, a `❌ Render video … lỗi` message sent.
6. `test_render_pending_limit_one` — two slots at `audio_received`; `render_pending(..., limit=1)`
   renders only the oldest-date one; the other stays `audio_received`.

Adjust `_mock_pipeline` so `render._remotion_render` writes `out_mp4` (as today) and
`_align.run_aligner` writes a `timeline.json` with `{"duration": 41.0}`; the real `codegen.write`
must be able to run, so give the seeded `Script` whatever shape `codegen.write` needs (check
`codegen.py`).

### Step 5 — run + commit

`.venv/Scripts/python.exe -m pytest tests/video/test_render.py -q` → green.
`.venv/Scripts/python.exe -m pytest tests/video -q` and `… tests --ignore=tests/video -q` — the
non-video suite will FAIL here (`article_approve` still calls `render.receive_audio`) — that is
expected and fixed in Task 13; note it in the report, do not "fix" it by keeping `receive_audio`.

Commit: `feat(p2b): split render — record_audio (poller) + render_pending (workflow); fix C1/C2/C3`

---

## Task 13 — poller routing, `video-render.yml`, `render_run` entrypoint, `expire_stale`, `article-approve.yml`

**Files:** `src/pipeline/article_approve.py`, new `src/pipeline/video/render_run.py`,
new `.github/workflows/video-render.yml`, `.github/workflows/article-approve.yml`,
`tests/test_article_approve.py`, `tests/test_workflows.py`.

### Step 1 — `article_approve.py`

- The audio branch calls `render.record_audio` (not `receive_audio`) and uses `render.is_audio(msg)`
  for the guard.
- `handle_undo` routing (`vid:` prefix) unchanged.
- `UNDO_GRACE_MIN = 15` → `45`.
- `expire_stale` video sweep: a slot with `video.status == "rendering"` whose `started_at` is more
  than `40 * 60` s old → `ds.put(date, slot_name, video={**v, "status": "awaiting_audio",
  "render_err": "render timed out (>40 min)"})` (M8) and append `f"{date}:{slot_name} (video)"` to
  `stuck`. Parse guard: `except (ValueError, TypeError)` (M4). The `(video)` notify line becomes
  `f"⚠️ {s} kẹt khi render — đã trả lại, gửi lại audio."`

### Step 2 — `src/pipeline/video/render_run.py`

```python
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..daily_state import DailyState
from ..telegram import Telegram
from . import render


def run(root: Path, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    ds = DailyState(root / "data")
    tg = Telegram()
    return render.render_pending(ds, tg, root, now)


def main() -> None:
    print(run(Path(".")))


if __name__ == "__main__":
    main()
```

### Step 3 — `.github/workflows/video-render.yml`

```yaml
name: video-render
on:
  schedule:
    - cron: '3-59/10 * * * *'   # every 10 min, offset from article-approve (*/5)
  workflow_dispatch:
permissions:
  contents: write
concurrency:
  group: pipeline-state
  cancel-in-progress: false
jobs:
  render:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Any pending audio?
        id: g
        run: |
          if grep -lR '"audio_received"' data/daily/ 2>/dev/null | grep -q .; then
            echo "go=1" >> "$GITHUB_OUTPUT"
          else
            echo "go=0" >> "$GITHUB_OUTPUT"
          fi
      - uses: actions/setup-node@v4
        if: steps.g.outputs.go == '1'
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: video/package-lock.json
      - name: Cache Remotion browser
        if: steps.g.outputs.go == '1'
        uses: actions/cache@v4
        with:
          path: ~/.cache/remotion
          key: remotion-browser-${{ runner.os }}
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
      - name: Render pending videos
        if: steps.g.outputs.go == '1'
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m pipeline.video.render_run
      - name: Commit state
        if: always()
        run: bash scripts/commit_state.sh
```

### Step 4 — `.github/workflows/article-approve.yml`

- Remove the `actions/setup-node@v4` step and the `Video render deps` step.
- `timeout-minutes: 25` → `15`.
- `Commit state` step → add `if: always()` (I4).
- Everything else (cron `*/5`, `concurrency: pipeline-state`, env block, `python -m
  pipeline.article_approve`) unchanged.

### Step 5 — tests

`tests/test_article_approve.py`:
- update `test_poll_routes_video_audio_and_undo` to monkeypatch `render.record_audio` (not
  `receive_audio`); assert a plain text message update does **not** reach it.
- `test_expire_stale_fails_stuck_video_render` → rename intent: assert stuck `rendering` →
  `awaiting_audio`, `render_err` set, message contains `kẹt khi render`.

`tests/test_workflows.py`:
- add `video-render.yml` to the valid-YAML list and the boilerplate list where it applies
  (it has `workflow_dispatch:`, `concurrency:`, `group: pipeline-state`, `fetch-depth: 0`,
  `contents: write`, `python-version: '3.12'`, `bash scripts/commit_state.sh`).
- `test_approve_and_ig_crons_and_modules`: drop the `"npm ci"` / `"remotion browser ensure"`
  asserts on `a`; add `assert "setup-node" not in a` and `assert "timeout-minutes: 15" in a`.
- new `test_video_render_workflow`: `v = (WF/"video-render.yml").read_text()`; assert
  `"3-59/10 * * * *" in v`, `"pipeline.video.render_run" in v`, `"npm ci" in v`,
  `"remotion browser ensure" in v`, `"cache: npm" in v`, `"if: always()" in v`,
  `"steps.g.outputs.go" in v`.

### Step 6 — run + commit

Both suites green: `… tests --ignore=tests/video -q` and `… tests/video -q`.
Commit: `feat(p2b): dedicated video-render workflow; poller only records audio`

---

## Task 14 — cleanup, README, whole-suite, delta re-review

**Files:** `src/pipeline/video/draft_script.py`, `README.md`, `git rm` of dead assets,
`.superpowers/sdd/progress.md`.

- **M1** `draft_script._make_id` — fold the slot in: `f"{now:%Y-%m-%d}-{slot}-{_slug(title)[:40]}"`
  (thread `slot` into `_make_id`; it is already a parameter of `draft`). Update the Task-5 test that
  asserts the id shape.
- **N1** `git rm "video/public/From Klickpin.com-"*.mp4` (5 files, ~16 MB, unused — the pool was
  retired in Task 2). Confirm nothing in `video/src` references them (`grep -rn "Klickpin" video/`).
- **N2** `README.md` Phase 2A section — drop the `assets/voice/sample.wav` / `sample.txt`
  voice-clone prep bullets (TTS is gone).
- **N-nit** `render.py` — drop the now-unused `from ..daily_state import DailyState` line **only if**
  `render_run.py` is the sole `DailyState` user (it is) — i.e. `render.py` itself never references it.
  Keep `import logging` / `log` (used).
- README: under "Luồng video (Phase 2B)" add one line — *"Render chạy ở workflow riêng
  `video-render` (mỗi 10 phút), không nằm trong poller bài viết."*
- Full suite: `.venv/Scripts/python.exe -m pytest tests -q` (both halves) — all green.
- Commit: `chore(p2b): render-split cleanup + README`
- Then: `scripts/review-package ca6d88f <head>` and dispatch a delta whole-branch review (opus)
  scoped to the addendum diff + confirmation that C1/C2/C3/I1–I5 from `final-review.md` are closed.
- Then `superpowers:finishing-a-development-branch`.
