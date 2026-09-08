# Phase 2B — Video Render & Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After `article_run.draft(slot)` schedules the article, generate a kinetic-typography video script + publish metadata for the same story, send the script to Telegram; when the user uploads their recorded audio, the Telegram poller renders a full MP4 with Remotion and sends it back — leaving `posts.<slot>.video.status == "rendered"` for Phase 2C to publish.

**Architecture:** Reuse the built Phase 2A chain (`script` → `variants` → `codegen` → `align` → `video/` Remotion project). Drop the entire TTS subsystem — audio now comes from the user via Telegram. `article_approve.poll` stays the single Telegram poller and gains two routes: `vid:` callbacks and audio messages. Video state is a nested `video` dict inside the existing `posts.<slot>` daily-state row.

**Tech Stack:** Python 3.12, `httpx`, Telegram Bot API, Remotion 4 (`npx remotion render`, Node 20, Chrome Headless Shell), ffmpeg (`video/node_modules/ffmpeg-static`), `pytest`.

## Global Constraints

- Python 3.12. Local runs: `.venv/Scripts/python.exe` with `PYTHONUTF8=1`. Run from repo root `D:\Automation Social`.
- Non-video suite: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`. Video suite: `.venv/Scripts/python.exe -m pytest tests/video -q`. Both must pass.
- Video output: **1080×1920, 30fps**, composition id **`CodexShort`**, ~35–45s (~110–140 displayed Vietnamese words). One MP4 per slot.
- Displayed-word band: `words_min: 110`, `words_max: 140`; `_NUDGE = 15` slack (in `script.py`).
- No TTS anywhere. No background pool/schedule — one fixed `video/public/bg.mp4`. No platform publishing (that is 2C). No blocking "✅ Đăng" gate — render → auto-schedule → `🗑 Gỡ` button only.
- State: `data/daily/<YYYY-MM-DD>.json`, `posts.<slot>.video` is a nested dict. One-way status: `awaiting_audio → rendering → rendered → discarded | failed`. `DailyState.put(date, slot, video=X)` REPLACES the whole `video` dict — always write `video={**existing, ...}`.
- Telegram callback_data prefixes: `art:` (article, existing), `vid:` (video, new). `vid:{date}:{slot}:undo` — exactly 4 colon parts.
- ICT = UTC+7. `publish.slot_unix(date, slot_ict)` converts an ICT slot time to unix seconds. Article slots: morning `11:30`, evening `19:45`.
- All 4 article workflows share `concurrency.group: pipeline-state`. `article-approve.yml` cron is `*/5 * * * *`.
- Vietnamese operator copy — match the tone of existing `article_approve.py` / `article_run.py` messages.
- `settings["video"]["enabled"]` gates the whole video branch: when false, `article_run.draft()` behaves exactly as today.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pipeline/video/tts.py` | **DELETE** — TTS retired |
| `tests/video/test_tts.py` | **DELETE** |
| `src/pipeline/video/__init__.py` | remove `TTSError` (unused after tts.py goes) |
| `src/pipeline/video/build_video.py` | drop `_tts` import + `synthesize` call + `--tts-check`/`--fake`; add `--voice <path>` for manual runs |
| `src/pipeline/video/models.py` | add `VideoMeta` dataclass |
| `src/pipeline/video/script.py` | `build_prompt(..., with_meta=False)`; `_validate_meta`; `generate_from_article(...) -> (Script, VideoMeta)` |
| `src/pipeline/video/draft_script.py` | **NEW** — `draft(slot, root, *, title, source_url, body_text, caption_fb, angle, now, generate, tg) -> dict` |
| `src/pipeline/video/render.py` | **NEW** — `_audio_file_id`, `_to_mp3`, `_remotion_render`, `receive_audio`, `handle_undo` |
| `src/pipeline/article_run.py` | call `video.draft_script.draft(...)` after `schedule_slot` when `video.enabled` |
| `src/pipeline/article_approve.py` | `poll` routes `vid:` callbacks + audio messages; `expire_stale` sweeps `video.status=="rendering"` |
| `src/pipeline/telegram.py` | add `Telegram.send_video(path, caption="", buttons=None)` |
| `video/src/BgVideo.tsx` | `BG` → single `{from:0, file:'bg.mp4', pal:DARK, rate:1}` |
| `video/public/bg.mp4` | the user's fixed background (see Task 2 for the gitignore decision) |
| `config/settings.yaml` | `video.enabled: true`; drop `tts_provider`; add `render_composition: CodexShort` |
| `.github/workflows/article-approve.yml` | add Node 20 + `npm ci` in `video/` + `npx remotion browser ensure`; `timeout-minutes: 25` |
| `requirements-video.txt` | drop TTS-only packages |
| `README.md` | short "Luồng video" section |

---

## Task 1: Retire TTS + config

**Files:**
- Delete: `src/pipeline/video/tts.py`, `tests/video/test_tts.py`
- Modify: `src/pipeline/video/__init__.py`, `src/pipeline/video/build_video.py`, `config/settings.yaml`, `requirements-video.txt`
- Test: `tests/video/test_build_video.py` (adjust)

**Interfaces:**
- Produces: `build_video.build(root, cand, post, now, cfg, *, voice_wav: Path, render_smoke=False, llm=None) -> dict` — `voice_wav` (a local wav/mp3) replaces the removed TTS synthesis; copied to `video/public/voice.mp3` (via ffmpeg if not already mp3). CLI: `--voice <path>` required (with `--story`), `--tts-check`/`--fake` removed.
- `config/settings.yaml` `video:` block is `{enabled: true, target_seconds: 40, words_min: 110, words_max: 140, render_composition: CodexShort}`.

- [ ] **Step 1: Delete the TTS module + its test**

```bash
git rm src/pipeline/video/tts.py tests/video/test_tts.py
```

- [ ] **Step 2: Remove `TTSError`**

In `src/pipeline/video/__init__.py` delete the `class TTSError(VideoError): pass` block (grep the repo first — `grep -rn TTSError src tests` — nothing else should reference it after Step 1).

- [ ] **Step 3: Rewire `build_video.py`**

In `src/pipeline/video/build_video.py`:
- Remove `from . import tts as _tts` and the `_FAKE_SCRIPT_JSON` / `_fake_llm` block **only if** `--fake-llm` is also being removed — KEEP `_FAKE_SCRIPT_JSON` + `_fake_llm` (still useful for `--fake-llm` offline script smoke). Remove only the TTS pieces.
- In `build(...)`: replace the signature `... cfg: dict, fake: bool = False, render_smoke: bool = False, llm=None)` with `... cfg: dict, *, voice_wav: Path, render_smoke: bool = False, llm=None)`.
- Replace the block:
  ```python
      voice_mp3 = video_dir / "public" / "voice.mp3"
      seconds = _tts.synthesize(s.spoken_text, voice_mp3, cfg, video_dir, fake=fake)
      backend = "fake" if fake else cfg.get("tts_provider", "auto")
  ```
  with:
  ```python
      voice_mp3 = video_dir / "public" / "voice.mp3"
      _copy_as_mp3(Path(voice_wav), voice_mp3, video_dir)
      backend = "user-audio"
  ```
- Add near the top (after `_load_story`):
  ```python
  def _copy_as_mp3(src: Path, dst: Path, video_dir: Path) -> None:
      """Put ``src`` audio at ``dst`` as mp3. If already .mp3, copy; else ffmpeg."""
      dst.parent.mkdir(parents=True, exist_ok=True)
      if src.suffix.lower() == ".mp3":
          shutil.copy(src, dst)
          return
      ff = _align._ffmpeg_bin(video_dir)
      r = subprocess.run([ff, "-y", "-hide_banner", "-i", str(src),
                          "-ac", "1", "-ar", "44100", "-b:a", "128k", str(dst)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
      if r.returncode != 0:
          raise VideoError(f"ffmpeg mp3 convert failed: {r.stderr[-300:]}")
  ```
  (add `from . import align as _align` to imports; `VideoError` already imported.)
- In `main()`: delete the `if args.tts_check:` branch and the `--tts-check` / `--fake` argparse lines. Add `ap.add_argument("--voice", required=False)`. After `if not args.story: ap.error(...)` add `if not args.voice: ap.error("--voice is required with --story")`. Change the `build(...)` call to pass `voice_wav=Path(args.voice)` and drop `fake=args.fake`.
- `manifest["tts_backend"]` key: rename to `"audio_source"` with value `backend` — grep tests for `tts_backend` and update.

- [ ] **Step 4: Config + requirements**

`config/settings.yaml` — replace the whole `video:` block with:
```yaml
video:
  enabled: true
  target_seconds: 40
  words_min: 110
  words_max: 140
  render_composition: CodexShort
```

`requirements-video.txt` — remove any line for `f5-tts`, `gradio-client`, `faster-whisper` (TTS-only). Keep anything `codegen`/`align` needs (they only shell out to `node`/`ffmpeg`, so likely nothing video-specific remains except maybe `pyyaml` which is already in the base). If the file becomes empty, leave a comment line `# (video stage shells out to node + ffmpeg; no extra python deps)`.

- [ ] **Step 5: Fix `tests/video/test_build_video.py`**

Open it. Any test calling `build(..., fake=True)` → change to `build(..., voice_wav=<a tmp wav/mp3 fixture>)`. Any `--tts-check` / `--fake` CLI test → delete. Any assertion on `manifest["tts_backend"]` → `manifest["audio_source"] == "user-audio"`. For the voice fixture, write a tiny silent mp3 with ffmpeg in the test, or `monkeypatch` `_copy_as_mp3` to just `shutil.copy` a `tmp_path` file.

- [ ] **Step 6: Run video suite**

Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS (test_tts gone; test_build_video adjusted). If `node` is absent locally, `needs_node`-marked tests skip — that's fine.

- [ ] **Step 7: Run the non-video suite (nothing should break)**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS (202) — `settings.yaml` `video` block change shouldn't touch article tests; grep `tests/` for `tts_provider` first and fix if any.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(p2b): retire TTS — video audio now comes from the user"
```

---

## Task 2: Single fixed background

**Files:**
- Modify: `video/src/BgVideo.tsx`
- Add: `video/public/bg.mp4` (or gitignore + README note — see Step 2)
- Delete: `video/public/bg-topo.mp4`, `bg-navy.mp4`, `bg-purple.mp4`, `bg-red.mp4`, `bg-grid.mp4` (the per-chapter pool)
- Test: `tests/video/test_remotion_project.py` (adjust)

**Interfaces:**
- Produces: `BgVideo.BG` is a one-element array `[{ from: 0, file: 'bg.mp4', pal: DARK, rate: 1 }]`. Every render uses `video/public/bg.mp4`. `palAt(t)` still resolves (always `DARK`).

- [ ] **Step 1: Edit `video/src/BgVideo.tsx`**

Replace the `export const BG = [ ... ];` array (5 entries) with:
```ts
/** Nền cố định — một video xuyên suốt mọi clip của kênh. */
export const BG = [
  { from: 0.0, file: 'bg.mp4', pal: DARK, rate: 1 },
];
```
Leave the rest of the file (the `BgVideo` component, `palAt`, `FADE`) untouched — with one entry, `prev` is always `null` and the component just renders `bg.mp4` full-bleed with the scrim.

- [ ] **Step 2: Place `bg.mp4`**

The user's background is `D:\video ahitofficial short\out\adsbot-vox.mp4` (or wherever they point). Two paths:
- **If ≤ 40 MB:** `cp "<user bg path>" video/public/bg.mp4` and commit it.
- **If > 40 MB:** add `video/public/bg.mp4` to `.gitignore`, and add to README under "Luồng video": *"Đặt file nền vào `video/public/bg.mp4` (một lần). CI cần file này — nếu chưa commit được vì nặng, dùng Git LFS hoặc tải trong workflow."* — then for CI, the `article-approve.yml` job (Task 11) gets a step to fetch it (e.g. from a release asset). **Recommendation:** re-encode to ≤ 40 MB (`ffmpeg -i in.mp4 -vf scale=1080:1920 -c:v libx264 -crf 28 -an -t 60 video/public/bg.mp4`) and commit — simplest, no CI fetch. Do this and commit the file.

- [ ] **Step 3: Remove the pool files**

```bash
git rm video/public/bg-topo.mp4 video/public/bg-navy.mp4 video/public/bg-purple.mp4 video/public/bg-red.mp4 video/public/bg-grid.mp4
```
(grep `video/src` for each name — only `BgVideo.tsx`'s old array referenced them.)

- [ ] **Step 4: Fix `tests/video/test_remotion_project.py`**

Open it. If it asserts the `BG` array length or the `bg-*.mp4` filenames, update: assert `BG` has 1 entry and `BG[0].file === 'bg.mp4'`, and that `video/public/bg.mp4` exists. If it only `node --check`s the `.tsx`/`.mjs` files, add a check that `video/public/bg.mp4` exists.

- [ ] **Step 5: Verify**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_remotion_project.py -q`
Expected: PASS (or skip if `needs_node` and no node). Also: `cd video && node --check src/BgVideo.tsx 2>/dev/null || npx tsc --noEmit -p . ` is optional — the `test_remotion_project` node check covers it.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(p2b): one fixed background video (video/public/bg.mp4)"
```

---

## Task 3: `VideoMeta` model + `_validate_meta`

**Files:**
- Modify: `src/pipeline/video/models.py`
- Modify: `src/pipeline/video/script.py`
- Test: `tests/video/test_models.py`, `tests/video/test_script.py`

**Interfaces:**
- Produces:
  - `models.VideoMeta` — `@dataclass` with `title: str`, `description: str`, `hashtags: list[str]`, `keywords: list[str]`, `tiktok_caption: str`; `.to_dict()` / `.from_dict(d)`.
  - `script._validate_meta(data: dict) -> VideoMeta` — raises `VideoScriptError` on: `title` length outside 10..70; `len(hashtags)` outside 8..12 or any element not matching `^#\S+$`; `len(keywords)` outside 5..10; `len(tiktok_caption) > 150`; missing key.

- [ ] **Step 1: Write failing tests**

Append to `tests/video/test_models.py`:
```python
from pipeline.video.models import VideoMeta

def test_videometa_roundtrip():
    m = VideoMeta(title="Tiêu đề giật tít về AI", description="Mô tả. CTA.",
                  hashtags=["#AI", "#congnghe", "#tudonghoa", "#ainews",
                            "#chatgpt", "#automation", "#ahit", "#vn"],
                  keywords=["ai", "tự động hoá", "công nghệ", "chatgpt", "n8n"],
                  tiktok_caption="AI vừa có bước nhảy lớn #AI #congnghe #fyp")
    assert VideoMeta.from_dict(m.to_dict()) == m
```

Append to `tests/video/test_script.py`:
```python
import pytest
from pipeline.video import script as vscript
from pipeline.video import VideoScriptError

_GOOD_META = {
    "title": "AI vừa có một bước nhảy lớn hôm nay",
    "description": "Một mô hình mới vừa ra mắt. Theo dõi kênh để không bỏ lỡ.",
    "hashtags": ["#AI", "#congnghe", "#tudonghoa", "#ainews", "#chatgpt",
                 "#automation", "#ahitofficial", "#vietnam"],
    "keywords": ["ai", "tự động hoá", "công nghệ", "mô hình ngôn ngữ", "n8n", "chatgpt"],
    "tiktok_caption": "AI vừa nhảy vọt, bạn theo kịp chưa? #AI #congnghe #fyp",
}

def test_validate_meta_ok():
    m = vscript._validate_meta(dict(_GOOD_META))
    assert m.title.startswith("AI vừa")
    assert len(m.hashtags) == 8

@pytest.mark.parametrize("mutate", [
    lambda d: d.update(title="Ngắn"),                                   # < 10 chars
    lambda d: d.update(title="x" * 71),                                 # > 70
    lambda d: d.update(hashtags=d["hashtags"][:5]),                     # < 8
    lambda d: d.update(hashtags=d["hashtags"] + ["#a"] * 6),            # > 12
    lambda d: d.update(hashtags=["no-hash"] + d["hashtags"][1:]),       # bad element
    lambda d: d.update(keywords=d["keywords"][:3]),                     # < 5
    lambda d: d.update(tiktok_caption="x" * 151),                       # > 150
    lambda d: d.pop("description"),                                     # missing
])
def test_validate_meta_rejects(mutate):
    d = dict(_GOOD_META)
    mutate(d)
    with pytest.raises(VideoScriptError):
        vscript._validate_meta(d)
```

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_models.py tests/video/test_script.py -q`
Expected: FAIL — `AttributeError: module 'pipeline.video.models' has no attribute 'VideoMeta'` / `script` has no `_validate_meta`.

- [ ] **Step 3: Add `VideoMeta` to `models.py`**

After the `Script` dataclass:
```python
@dataclass
class VideoMeta:
    title: str
    description: str
    hashtags: list[str]
    keywords: list[str]
    tiktok_caption: str

    def to_dict(self) -> dict:
        return {"title": self.title, "description": self.description,
                "hashtags": list(self.hashtags), "keywords": list(self.keywords),
                "tiktok_caption": self.tiktok_caption}

    @classmethod
    def from_dict(cls, d: dict) -> "VideoMeta":
        return cls(title=d["title"], description=d["description"],
                   hashtags=list(d["hashtags"]), keywords=list(d["keywords"]),
                   tiktok_caption=d["tiktok_caption"])
```

- [ ] **Step 4: Add `_validate_meta` to `script.py`**

Add `import re` at top if absent. Add after `_validate`:
```python
_HASHTAG = re.compile(r"^#\S+$")


def _validate_meta(data: dict) -> "VideoMeta":
    from .models import VideoMeta
    try:
        title = str(data["title"]).strip()
        desc = str(data["description"]).strip()
        tags = [str(h).strip() for h in data["hashtags"]]
        kws = [str(k).strip() for k in data["keywords"]]
        tk = str(data["tiktok_caption"]).strip()
    except (KeyError, TypeError) as e:
        raise VideoScriptError(f"bad publish meta: {e}") from e
    if not (10 <= len(title) <= 70):
        raise VideoScriptError(f"meta title length {len(title)} outside 10..70")
    if not (8 <= len(tags) <= 12) or not all(_HASHTAG.match(h) for h in tags):
        raise VideoScriptError(f"meta hashtags invalid: {tags}")
    if not (5 <= len(kws) <= 10):
        raise VideoScriptError(f"meta keywords count {len(kws)} outside 5..10")
    if len(tk) > 150:
        raise VideoScriptError(f"tiktok_caption {len(tk)} > 150 chars")
    return VideoMeta(title=title, description=desc, hashtags=tags,
                     keywords=kws, tiktok_caption=tk)
```

- [ ] **Step 5: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_models.py tests/video/test_script.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/video/models.py src/pipeline/video/script.py tests/video/test_models.py tests/video/test_script.py
git commit -m "feat(p2b): VideoMeta model + publish-metadata validation"
```

---

## Task 4: `script.generate_from_article`

**Files:**
- Modify: `src/pipeline/video/script.py`
- Test: `tests/video/test_script.py`

**Interfaces:**
- Consumes: `_validate` + `_validate_meta` (Task 3), `models.Script`, `models.VideoMeta`, `Candidate` / `PostContent` (`from ..models import Candidate, PostContent`).
- Produces:
  - `script.build_prompt(cand, post, voice, cfg, *, with_meta: bool = False) -> tuple[str, str]` — when `with_meta`, the system prompt also asks for a `"publish"` object (title ≤70 giật tít; description 2-4 câu + 1 CTA, no raw URL; hashtags 8-12 each `#...`; keywords 5-10 no `#`; tiktok_caption ≤150 with 3-5 inline hashtags), and the required JSON shape becomes `{sections, cards, publish}`.
  - `script.generate_from_article(title: str, source_url: str, body_text: str, caption_fb: str, angle: str, voice: dict, cfg: dict, llm=None) -> tuple[Script, VideoMeta]` — builds a minimal `Candidate` (`url=source_url or "", title=title, source="", published_at=now, full_text=body_text, summary=""`) and `PostContent` (`angle=angle, caption_fb=caption_fb`, other fields `""` / `[]`), calls the LLM with `with_meta=True`, validates both the script (existing `_validate`) and `data["publish"]` (`_validate_meta`), applies the same word-band retry as `generate`.
  - `script.generate(cand, post, voice, cfg, llm=None) -> Script` — UNCHANGED signature and behaviour (calls `build_prompt(..., with_meta=False)`).

- [ ] **Step 1: Write failing tests**

Append to `tests/video/test_script.py`:
```python
from pipeline.video.models import Script, VideoMeta

_VOICE = {"ten_kenh": "A Hít Official", "giong": "gãy gọn",
          "xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "cam_ky": []}
_CFG = {"target_seconds": 40, "words_min": 110, "words_max": 140}

def _fake_full_reply():
    import json
    cards = [{"lines": [f"Dòng số {i}", "thêm vài từ nữa cho đủ"], "variant": "stack",
              "anchor": "mid", "motion_in": "rise", "motion_out": "up"} for i in range(12)]
    return json.dumps({
        "sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 6}],
        "cards": cards,
        "publish": dict(_GOOD_META),
    }, ensure_ascii=False)

def test_generate_from_article_returns_script_and_meta():
    calls = []
    def llm(system, user, provider="auto"):
        calls.append((system, user)); return _fake_full_reply()
    s, m = vscript.generate_from_article(
        title="OpenAI ra mắt mô hình video", source_url="https://openai.com/x",
        body_text="Nội dung bài viết dài...", caption_fb="Caption tham khảo.",
        angle="chia sẻ", voice=_VOICE, cfg=_CFG, llm=llm)
    assert isinstance(s, Script) and isinstance(m, VideoMeta)
    assert "publish" in calls[0][0]                 # with_meta prompt used
    assert m.title.startswith("AI vừa")

def test_generate_from_article_bad_meta_raises():
    import json
    def llm(system, user, provider="auto"):
        d = json.loads(_fake_full_reply()); d["publish"]["hashtags"] = ["#a", "#b"]
        return json.dumps(d, ensure_ascii=False)
    with pytest.raises(VideoScriptError):
        vscript.generate_from_article(title="x" * 20, source_url="", body_text="b",
                                      caption_fb="c", angle="a", voice=_VOICE, cfg=_CFG, llm=llm)

def test_generate_still_returns_bare_script():
    from pipeline.video.models import Candidate  # noqa - see note below
```
(For `test_generate_still_returns_bare_script`, reuse whatever existing `test_script.py` fixture already exercises `generate` — do not rewrite it; just assert it still returns a `Script` and that `build_prompt(..., with_meta=False)` output has no `"publish"` substring. If the existing file already covers `generate`, skip adding this one.)

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_script.py -q`
Expected: FAIL — `generate_from_article` undefined.

- [ ] **Step 3: Refactor `build_prompt` + add `generate_from_article`**

In `script.py`:

- Change `build_prompt` signature to `def build_prompt(cand, post, voice, cfg, *, with_meta: bool = False) -> tuple[str, str]:`. In the system string, change the JSON-shape sentence and append the meta ask when `with_meta`:
  ```python
      shape = ("{sections:[{label,card_start}], "
               "cards:[{lines,variant,anchor,motion_in,motion_out,num?}]"
               + (", publish:{title,description,hashtags,keywords,tiktok_caption}}" if with_meta else "}"))
      system = (
          f"Bạn viết kịch bản video dọc ~{cfg['target_seconds']} giây cho kênh "
          f"\"{voice.get('ten_kenh', '')}\" về AI, phong cách kinetic typography. "
          # ... (unchanged middle) ...
          f"CHỈ trả về một object JSON: {shape} "
          # ... (unchanged card rules) ...
      )
      if with_meta:
          system += (
              " Khối 'publish': title <=70 ký tự, giật tít, có yếu tố tò mò hoặc con số. "
              "description 2-4 câu + 1 lời kêu gọi theo dõi kênh, KHÔNG chèn URL. "
              "hashtags 8-12, mỗi cái bắt đầu '#', không dấu cách. "
              "keywords 5-10 từ khoá cho YouTube (không '#'). "
              "tiktok_caption <=150 ký tự kèm 3-5 hashtag inline. Tất cả tiếng Việt."
          )
  ```
  (Keep the existing `user` construction. Return `(system, user)` as before.)

- Add:
  ```python
  def generate_from_article(title: str, source_url: str, body_text: str,
                            caption_fb: str, angle: str, voice: dict, cfg: dict,
                            llm=None):
      from datetime import datetime, timezone
      from ..models import Candidate, PostContent
      cand = Candidate(url=source_url or "", title=title, source="",
                       published_at=datetime.now(timezone.utc),
                       summary="", full_text=body_text or caption_fb or title)
      post = PostContent(angle=angle, caption_fb=caption_fb, caption_ig="",
                         hashtags=[], thumbnail_prompt="", thumbnail_title="",
                         youtube_title="", youtube_desc="", tiktok_caption="",
                         source_url=source_url or "", source_name="")
      llm = llm or _default_generate
      system, user = build_prompt(cand, post, voice, cfg, with_meta=True)
      wmin, wmax = cfg["words_min"], cfg["words_max"]
      for attempt in (1, 2):
          try:
              raw = llm(system, user, provider="auto")
              data = parse_json_response(raw)
              s = _validate(data, cfg)
              meta = _validate_meta(data.get("publish", {}))
          except LLMError as e:
              raise VideoScriptError(f"LLM failed: {e}") from e
          wc = s.word_count
          if wmin - _NUDGE <= wc <= wmax + _NUDGE:
              return s, meta
          if attempt == 2:
              raise VideoScriptError(f"word count {wc} outside {wmin}-{wmax} after retry")
          user = (user + f"\n\n[SỬA] Bản vừa rồi có {wc} từ hiển thị. "
                  f"Viết lại cho đủ {wmin}-{wmax} từ, giữ nguyên cấu trúc JSON kể cả 'publish'.")
      raise VideoScriptError("unreachable")
  ```
  Confirm `Candidate` / `PostContent` field names against `src/pipeline/models.py` — adjust the kwargs to match exactly (Candidate has `raw_score_hint`, `top_image`, `source_count` with defaults; PostContent's 11 fields are all required — pass `""`/`[]` for the unused ones as above).

- `generate` itself: no change (it already calls `build_prompt(cand, post, voice, cfg)` → `with_meta` defaults False).

- [ ] **Step 4: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_script.py -q`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/script.py tests/video/test_script.py
git commit -m "feat(p2b): script.generate_from_article — script + publish metadata from an article"
```

---

## Task 5: `video/draft_script.py`

**Files:**
- Create: `src/pipeline/video/draft_script.py`
- Test: `tests/video/test_draft_script.py`

**Interfaces:**
- Consumes: `script.generate_from_article` (Task 4), `variants.normalize`, `codegen.write` + `codegen.node_check`, `script.write_script_json`, `DailyState.put` / `.get_safe`, a `tg` with `send_message(text, buttons=None) -> dict` (the returned dict has `result.message_id`).
- Produces: `draft_script.draft(slot: str, root: Path, *, title: str, source_url: str, body_text: str, caption_fb: str, angle: str, now: datetime, generate=None, tg=None) -> dict`. Returns one of: `{"skipped": True}` (video disabled), `{"status": "error"}` (script gen failed — Telegram warned, no state written), or the written `video` dict (`status="awaiting_audio"`).
- Side effects: writes `output/<date>/<pid>/video/script.json` + `video/tools/cards.mjs` + `video/tools/variants.mjs`; sets `posts.<slot>.video` in `data/daily/<date>.json`.

- [ ] **Step 1: Write failing tests**

Create `tests/video/test_draft_script.py`:
```python
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.video import draft_script
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None):
        self.msgs.append(text)
        return {"result": {"message_id": 900 + len(self.msgs)}}


def _wire(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "video:\n  enabled: true\n  target_seconds: 40\n  words_min: 110\n"
        "  words_max: 140\n  render_composition: CodexShort\n", encoding="utf-8")
    (tmp_path / "config" / "voice.yaml").write_text(
        "ten_kenh: A Hít\ngiong: vui\nxung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ncam_ky: []\n",
        encoding="utf-8")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    return tmp_path


def _fake_gen_ok(system, user, provider="auto"):
    import json
    cards = [{"lines": [f"Câu {i}", "vài từ nữa cho đủ chữ"], "variant": "stack",
              "anchor": "mid", "motion_in": "rise", "motion_out": "up"} for i in range(12)]
    return json.dumps({
        "sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 6}],
        "cards": cards,
        "publish": {"title": "AI vừa có một bước nhảy lớn hôm nay",
                    "description": "Mô hình mới ra mắt. Theo dõi kênh nhé.",
                    "hashtags": ["#AI", "#congnghe", "#tudonghoa", "#ainews", "#chatgpt",
                                 "#automation", "#ahitofficial", "#vietnam"],
                    "keywords": ["ai", "tự động hoá", "công nghệ", "mô hình", "chatgpt"],
                    "tiktok_caption": "AI vừa nhảy vọt #AI #congnghe #fyp"},
    }, ensure_ascii=False)


def test_draft_writes_video_record_and_sends_script(tmp_path):
    root = _wire(tmp_path)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 0, 5, tzinfo=timezone.utc)
    v = draft_script.draft("morning", root, title="OpenAI ra mắt mô hình video",
                           source_url="https://openai.com/x", body_text="Bài gốc dài",
                           caption_fb="Caption.", angle="chia sẻ", now=now,
                           generate=_fake_gen_ok, tg=tg)
    assert v["status"] == "awaiting_audio"
    assert v["meta"]["title"].startswith("AI vừa")
    assert v["spoken_text"]
    assert v["script_msg_id"] == 901
    saved = DailyState(root / "data").get_safe("2026-09-08", "morning")
    assert saved["video"]["status"] == "awaiting_audio"
    assert (root / "video" / "tools" / "cards.mjs").exists()
    assert any("Kịch bản video morning" in m for m in tg.msgs)


def test_draft_gen_failure_warns_no_state(tmp_path):
    root = _wire(tmp_path)
    tg = FakeTG()
    def boom(system, user, provider="auto"):
        return '{"cards": [], "sections": []}'          # fails _validate (card count)
    out = draft_script.draft("evening", root, title="x" * 20, source_url="", body_text="b",
                             caption_fb="c", angle="a", now=datetime(2026, 9, 8, tzinfo=timezone.utc),
                             generate=boom, tg=tg)
    assert out == {"status": "error"}
    assert any("Kịch bản video evening lỗi" in m for m in tg.msgs)
    assert DailyState(root / "data").get_safe("2026-09-08", "evening") is None


def test_draft_skipped_when_video_disabled(tmp_path):
    root = _wire(tmp_path)
    (root / "config" / "settings.yaml").write_text(
        "video:\n  enabled: false\n", encoding="utf-8")
    calls = []
    out = draft_script.draft("morning", root, title="t" * 20, source_url="", body_text="b",
                             caption_fb="c", angle="a",
                             now=datetime(2026, 9, 8, tzinfo=timezone.utc),
                             generate=lambda *a, **k: calls.append(1) or "{}", tg=FakeTG())
    assert out == {"skipped": True}
    assert calls == []
```

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_draft_script.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.video.draft_script'`.

- [ ] **Step 3: Create `src/pipeline/video/draft_script.py`**

```python
from __future__ import annotations
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..daily_state import DailyState
from . import VideoScriptError
from . import script as _script
from . import variants as _variants
from . import codegen as _codegen

log = logging.getLogger("video.draft_script")


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)


def _make_id(title: str, now: datetime) -> str:
    return f"{now:%Y-%m-%d}-{_slug(title)[:40]}".rstrip("-")


def draft(slot: str, root: Path, *, title: str, source_url: str, body_text: str,
          caption_fb: str, angle: str, now: datetime, generate=None, tg=None) -> dict:
    root = Path(root)
    cfg = (yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
           or {}).get("video", {})
    if not cfg.get("enabled"):
        return {"skipped": True}

    voice = yaml.safe_load((root / "config/voice.yaml").read_text(encoding="utf-8"))
    date = now.astimezone(timezone.utc).strftime("%Y-%m-%d")

    try:
        s, meta = _script.generate_from_article(
            title=title, source_url=source_url, body_text=body_text,
            caption_fb=caption_fb, angle=angle, voice=voice, cfg=cfg, llm=generate)
        s = _variants.normalize(s)
    except VideoScriptError as e:
        if tg is not None:
            try:
                tg.send_message(f"⚠️ Kịch bản video {slot} lỗi: {e}")
            except Exception:  # noqa: BLE001
                log.exception("warn send failed")
        return {"status": "error"}

    video_dir = root / "video"
    _codegen.write(s, video_dir)
    try:
        _codegen.node_check(video_dir)
    except FileNotFoundError:
        log.warning("node not available, skipping tools/*.mjs --check")

    pid = _make_id(title, now)
    out_dir = root / "output" / date / pid / "video"
    _script.write_script_json(s, out_dir)

    spoken = s.spoken_text
    msg = (f"🎬 Kịch bản video {slot} ({date})\n\n{spoken}\n\n"
           f"▶️ Thu âm đọc đúng đoạn trên (~{cfg.get('target_seconds', 40)}s), "
           "gửi file audio lại cho bot.")
    script_msg_id = None
    if tg is not None:
        try:
            r = tg.send_message(msg)
            script_msg_id = (r or {}).get("result", {}).get("message_id")
        except Exception:  # noqa: BLE001 - a preview failure must not lose the record
            log.exception("script msg send failed")

    ds = DailyState(root / "data")
    video = {
        "status": "awaiting_audio",
        "meta": meta.to_dict(),
        "spoken_text": spoken,
        "script_path": str((out_dir / "script.json").relative_to(root)).replace("\\", "/"),
        "script_msg_id": script_msg_id,
        "audio_msg_id": None,
        "mp4_path": None,
        "seconds": None,
        "render_err": None,
        "started_at": None,
        "publish_due": None,
        "result": {"yt": None, "fb": None, "ig": None, "tiktok": None},
    }
    existing = ds.get_safe(date, slot) or {}
    ds.put(date, slot, video={**(existing.get("video") or {}), **video})
    return video
```

- [ ] **Step 4: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_draft_script.py -q`
Expected: PASS (3). `node_check` FileNotFoundError path exercised when node absent — fine.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/draft_script.py tests/video/test_draft_script.py
git commit -m "feat(p2b): video.draft_script — script + Telegram + awaiting_audio state"
```

---

## Task 6: Wire `draft_script` into `article_run.draft()`

**Files:**
- Modify: `src/pipeline/article_run.py`
- Test: `tests/test_article_run.py`

**Interfaces:**
- Consumes: `video.draft_script.draft(slot, root, *, title, source_url, body_text, caption_fb, angle, now, generate, tg)` (Task 5).
- Produces: no signature change to `draft()`. After a successful `publish.schedule_slot`, if `settings["video"]["enabled"]`, calls `draft_script.draft(...)` in a `try/except` that only logs + sends a `⚠️` Telegram line on failure (the article is already scheduled — video must never break it).

- [ ] **Step 1: Extend `tests/test_article_run.py`**

In the `wired` fixture, after the `styles.pick_style` monkeypatch, add:
```python
    vcalls = {}
    monkeypatch.setattr(article_run, "_video_draft",
                        type("M", (), {"draft": staticmethod(
                            lambda *a, **k: vcalls.update(k) or {"status": "awaiting_audio"})}))
```
(If `article_run` imports the module lazily inside `draft()`, instead monkeypatch `article_run.video` / the import target — see Step 3 for the exact name; align the test to it.)

Add:
```python
def test_draft_triggers_video_when_enabled(wired, monkeypatch):
    root, _ = wired
    (root / "config" / "settings.yaml").write_text(
        (root / "config" / "settings.yaml").read_text(encoding="utf-8")
        + "video:\n  enabled: true\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(article_run._video_draft, "draft",
                        lambda slot, r, **k: seen.update(slot=slot, **k) or {"status": "awaiting_audio"})
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=FakeTG(), meta=object())
    assert out["status"] == "scheduled"
    assert seen["slot"] == "morning"
    assert "title" in seen and "caption_fb" in seen


def test_draft_video_failure_does_not_break_article(wired, monkeypatch):
    root, _ = wired
    (root / "config" / "settings.yaml").write_text(
        (root / "config" / "settings.yaml").read_text(encoding="utf-8")
        + "video:\n  enabled: true\n", encoding="utf-8")
    monkeypatch.setattr(article_run._video_draft, "draft",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    tg = FakeTG()
    out = article_run.draft("morning", root, datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc),
                            tg=tg, meta=object())
    assert out["status"] == "scheduled"
    assert any("Kịch bản video morning lỗi" in m[0] for m in tg.msgs)


def test_draft_no_video_when_disabled(wired, monkeypatch):
    root, _ = wired   # fixture settings.yaml has no video block -> disabled
    called = []
    monkeypatch.setattr(article_run._video_draft, "draft",
                        lambda *a, **k: called.append(1))
    article_run.draft("morning", root, datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc),
                      tg=FakeTG(), meta=object())
    assert called == []
```
(The `wired` fixture's `FakeTG` already records `msgs` as `(text, buttons)` tuples — match `m[0]`.)

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -q -k video`
Expected: FAIL — `article_run` has no `_video_draft`.

- [ ] **Step 3: Edit `article_run.py`**

Near the other imports add:
```python
from .video import draft_script as _video_draft
```
(It only pulls `script`/`variants`/`codegen` — pure Python, no Remotion. Confirm `import pipeline.article_run` still works: `.venv/Scripts/python.exe -c "import pipeline.article_run"`.)

In `draft()`, replace `return ds.get(date, slot)` (the last line of the success path, after the `publish.schedule_slot` try/except) with:
```python
    if settings.get("video", {}).get("enabled"):
        try:
            _video_draft.draft(
                slot, root, title=title,
                source_url=(state_sources[0]["url"] if state_sources else ""),
                body_text=article.caption_fb, caption_fb=article.caption_fb,
                angle=angle, now=now, generate=generate, tg=tg)
        except Exception as e:  # noqa: BLE001 - video is secondary; the article is already scheduled
            log.warning("video draft_script failed: %s", e)
            try:
                tg.send_message(f"⚠️ Kịch bản video {slot} lỗi: {e}")
            except Exception:  # noqa: BLE001
                pass
    return ds.get(date, slot)
```
`settings` is already loaded in `draft()` (from `_configs(root)`); confirm the local name — it's `settings`.

- [ ] **Step 4: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_run.py -q`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_run.py tests/test_article_run.py
git commit -m "feat(p2b): article_run.draft() spawns the video script when video.enabled"
```

---

## Task 7: `Telegram.send_video`

**Files:**
- Modify: `src/pipeline/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Produces: `Telegram.send_video(self, path: str, caption: str = "", buttons: list[tuple[str, str]] | None = None) -> dict` — `POST sendVideo` multipart: `chat_id`, `video` file, `caption`, optional `reply_markup` (same inline-keyboard shape as `send_message`).

- [ ] **Step 1: Write failing test**

Append to `tests/test_telegram.py` (match the file's existing fake-httpx pattern — read it first):
```python
def test_send_video_multipart(monkeypatch, tmp_path):
    from pipeline.telegram import Telegram
    vid = tmp_path / "v.mp4"; vid.write_bytes(b"\x00\x00fakemp4")
    seen = {}

    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True, "result": {"message_id": 5}}

    def fake_post(url, data=None, files=None):
        seen["url"] = url; seen["data"] = data; seen["files"] = files
        return R()

    t = Telegram(token="T", chat_id="C")
    monkeypatch.setattr(t._client, "post", fake_post)
    out = t.send_video(str(vid), caption="hi", buttons=[("🗑 Gỡ", "vid:2026-09-08:morning:undo")])
    assert out["result"]["message_id"] == 5
    assert seen["url"].endswith("/sendVideo")
    assert seen["data"]["chat_id"] == "C"
    assert seen["data"]["caption"] == "hi"
    assert "reply_markup" in seen["data"]
    assert "video" in seen["files"]
```

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_telegram.py -q -k send_video`
Expected: FAIL — `Telegram` has no `send_video`.

- [ ] **Step 3: Add `send_video` to `telegram.py`**

After `send_document`:
```python
    def send_video(self, path: str, caption: str = "",
                   buttons: list[tuple[str, str]] | None = None) -> dict:
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption
        if buttons:
            data["reply_markup"] = {"inline_keyboard": [
                [{"text": lbl, "callback_data": cb} for lbl, cb in buttons]]}
        with open(path, "rb") as fh:
            return self._post("sendVideo", data=data,
                              files={"video": (Path(path).name, fh, "video/mp4")})
```
(`self._post` already JSON-encodes dict/list values in `data` — the `reply_markup` dict is handled. `Path` is already imported.)

- [ ] **Step 4: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_telegram.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/telegram.py tests/test_telegram.py
git commit -m "feat(p2b): Telegram.send_video"
```

---

## Task 8: `render.py` helpers

**Files:**
- Create: `src/pipeline/video/render.py`
- Test: `tests/video/test_render.py`

**Interfaces:**
- Produces:
  - `render._audio_file_id(msg: dict) -> str | None` — returns `msg["voice"]["file_id"]`, else `msg["audio"]["file_id"]`, else `msg["document"]["file_id"]` when the document's `mime_type` starts with `audio/` or its `file_name` ends `.mp3/.m4a/.wav/.ogg`; else `None`.
  - `render._to_mp3(src: Path, dst: Path, video_dir: Path) -> None` — mp3 → copy; else ffmpeg (`_align._ffmpeg_bin`) `-ac 1 -ar 44100 -b:a 128k`; raises `AlignError` (reuse) on ffmpeg failure.
  - `render._remotion_render(video_dir: Path, composition: str, out_mp4: Path) -> subprocess.CompletedProcess` — runs `npx remotion render {composition} {out_mp4}` in `video_dir`, `capture_output=True, text=True, encoding="utf-8", errors="replace"`. Never raises for a non-zero exit — the caller inspects `.returncode` / `.stderr`.

- [ ] **Step 1: Write failing tests**

Create `tests/video/test_render.py`:
```python
from pathlib import Path
import subprocess
import pytest
from pipeline.video import render


def test_audio_file_id_variants():
    assert render._audio_file_id({"voice": {"file_id": "V"}}) == "V"
    assert render._audio_file_id({"audio": {"file_id": "A"}}) == "A"
    assert render._audio_file_id(
        {"document": {"file_id": "D", "mime_type": "audio/mpeg"}}) == "D"
    assert render._audio_file_id(
        {"document": {"file_id": "D", "file_name": "take.m4a"}}) == "D"
    assert render._audio_file_id({"document": {"file_id": "D", "mime_type": "image/png"}}) is None
    assert render._audio_file_id({"text": "hello"}) is None


def test_to_mp3_copies_mp3(tmp_path):
    src = tmp_path / "a.mp3"; src.write_bytes(b"ID3xx")
    dst = tmp_path / "out" / "voice.mp3"
    render._to_mp3(src, dst, tmp_path)
    assert dst.read_bytes() == b"ID3xx"


def test_to_mp3_converts_with_ffmpeg(tmp_path, monkeypatch):
    src = tmp_path / "a.ogg"; src.write_bytes(b"OggS")
    dst = tmp_path / "voice.mp3"
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd); dst.write_bytes(b"mp3")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    render._to_mp3(src, dst, tmp_path)
    assert dst.exists() and calls and "-ar" in calls[0]


def test_to_mp3_ffmpeg_failure_raises(tmp_path, monkeypatch):
    src = tmp_path / "a.wav"; src.write_bytes(b"RIFF")
    monkeypatch.setattr(render.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    from pipeline.video import AlignError
    with pytest.raises(AlignError):
        render._to_mp3(src, tmp_path / "v.mp3", tmp_path)


def test_remotion_render_shells_out(tmp_path, monkeypatch):
    seen = {}
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd; seen["cwd"] = kw.get("cwd")
        return subprocess.CompletedProcess(cmd, 0, "done", "")
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    r = render._remotion_render(tmp_path / "video", "CodexShort", tmp_path / "o.mp4")
    assert r.returncode == 0
    assert "remotion" in seen["cmd"] and "CodexShort" in seen["cmd"]
    assert seen["cwd"] == str(tmp_path / "video")
```

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_render.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.video.render'`.

- [ ] **Step 3: Create `src/pipeline/video/render.py` (helpers only for this task)**

```python
from __future__ import annotations
import logging
import shutil
import subprocess
from pathlib import Path

from . import AlignError
from . import align as _align

log = logging.getLogger("video.render")

_AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".oga")


def _audio_file_id(msg: dict) -> str | None:
    if isinstance(msg.get("voice"), dict) and msg["voice"].get("file_id"):
        return msg["voice"]["file_id"]
    if isinstance(msg.get("audio"), dict) and msg["audio"].get("file_id"):
        return msg["audio"]["file_id"]
    doc = msg.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        mime = str(doc.get("mime_type", ""))
        name = str(doc.get("file_name", "")).lower()
        if mime.startswith("audio/") or name.endswith(_AUDIO_EXT):
            return doc["file_id"]
    return None


def _to_mp3(src: Path, dst: Path, video_dir: Path) -> None:
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".mp3":
        shutil.copy(src, dst)
        return
    ff = _align._ffmpeg_bin(video_dir)
    r = subprocess.run([ff, "-y", "-hide_banner", "-i", str(src),
                        "-ac", "1", "-ar", "44100", "-b:a", "128k", str(dst)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise AlignError(f"ffmpeg mp3 convert failed: {(r.stderr or '')[-300:]}")


def _remotion_render(video_dir: Path, composition: str,
                     out_mp4: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["npx", "remotion", "render", composition, str(out_mp4)],
        cwd=str(video_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
```

- [ ] **Step 4: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_render.py -q`
Expected: PASS (5).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/render.py tests/video/test_render.py
git commit -m "feat(p2b): render helpers — audio detect, mp3 convert, remotion render"
```

---

## Task 9: `render.receive_audio` + `render.handle_undo`

**Files:**
- Modify: `src/pipeline/video/render.py`
- Test: `tests/video/test_render.py`

**Interfaces:**
- Consumes: `_audio_file_id`, `_to_mp3`, `_remotion_render` (Task 8); `align.make_silence_txt` / `align.run_aligner`; `publish.slot_unix`; a `tg` with `download_file(file_id, dest) -> str`, `send_message(text, buttons=None)`, `send_video(path, caption, buttons=None)`; `DailyState` `.get_safe` / `.put` / `.all_files` / `.load_safe`.
- Produces:
  - `render.receive_audio(msg: dict, ds, tg, root: Path, now: datetime) -> str | None` — returns `"rendered:{date}:{slot}"`, `"failed:{date}:{slot}"`, or `None` (not audio / no waiting slot / already handled).
  - `render.handle_undo(cbq: dict, ds, tg, root: Path, now: datetime) -> str | None` — parses `vid:{date}:{slot}:undo`; if `video.status` in `("awaiting_audio","rendering","rendered")` set it `"discarded"` + ack + `tg.send_message("🗑 Đã huỷ video {date}:{slot}.")`; return `"discarded:{date}:{slot}"`. (2B has no live post to delete — 2C extends this.)
- Slot matching in `receive_audio`: if `msg["reply_to_message"]["message_id"]` equals some slot's `video.script_msg_id`, use that slot. Else pick the `video.status == "awaiting_audio"` slot with the most recent `date` within the last 3 days. No candidate → `tg.send_message("⚠️ Nhận được audio nhưng không có video nào đang chờ.")` + return `None`.
- Composition id: read `config/settings.yaml` `video.render_composition` (default `"CodexShort"`).
- `out_mp4`: sibling of `video.script_path` → `<script_path parent>/<pid>.mp4` where `pid` = that parent dir's name.

- [ ] **Step 1: Write failing tests**

Append to `tests/video/test_render.py`:
```python
from datetime import datetime, timezone
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []; self.videos = []
    def download_file(self, fid, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"audio"); return str(dest)
    def send_message(self, text, buttons=None): self.msgs.append(text)
    def send_video(self, path, caption="", buttons=None):
        self.videos.append((path, caption)); return {"result": {"message_id": 7}}


def _seed(root, slot="morning", date="2026-09-08", **extra):
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "video:\n  render_composition: CodexShort\n", encoding="utf-8")
    ds = DailyState(root / "data")
    sp = f"output/{date}/{date}-openai-x/video/script.json"
    v = {"status": "awaiting_audio", "meta": {"title": "Tiêu đề video AI dài hơn mười ký tự"},
         "spoken_text": "một hai ba", "script_path": sp, "script_msg_id": 901,
         "result": {"yt": None, "fb": None, "ig": None, "tiktok": None}, **extra}
    ds.put(date, slot, status="scheduled", slot_ict="11:30", video=v)
    return ds


def _mock_pipeline(monkeypatch, render_rc=0):
    monkeypatch.setattr(render, "_to_mp3", lambda *a, **k: None)
    monkeypatch.setattr(render._align, "make_silence_txt", lambda *a, **k: 41.0)
    def fake_aligner(video_dir, dur):
        p = Path(video_dir) / "src" / "timeline.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"duration": 41.0, "cards": [1]}', encoding="utf-8")
        return p
    monkeypatch.setattr(render._align, "run_aligner", fake_aligner)
    import subprocess
    monkeypatch.setattr(render, "_remotion_render",
                        lambda vd, comp, out: (Path(out).parent.mkdir(parents=True, exist_ok=True),
                                               Path(out).write_bytes(b"MP4"),
                                               subprocess.CompletedProcess([], render_rc, "", "err tail"))[-1])


def test_receive_audio_renders_and_sends(tmp_path, monkeypatch):
    ds = _seed(tmp_path)
    (tmp_path / "video" / "tools").mkdir(parents=True)
    for f in ("cards.mjs", "variants.mjs"):
        (tmp_path / "video" / "tools" / f).write_text("//", encoding="utf-8")
    (tmp_path / "video" / "public").mkdir(parents=True)
    _mock_pipeline(monkeypatch)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    r = render.receive_audio({"message_id": 950, "voice": {"file_id": "V"}},
                             ds, tg, tmp_path, now)
    assert r == "rendered:2026-09-08:morning"
    v = ds.get_safe("2026-09-08", "morning")["video"]
    assert v["status"] == "rendered" and v["mp4_path"].endswith(".mp4")
    assert v["seconds"] == 41.0 and v["publish_due"]
    assert tg.videos and "Video morning" in tg.videos[0][1]


def test_receive_audio_render_failure(tmp_path, monkeypatch):
    ds = _seed(tmp_path)
    (tmp_path / "video" / "tools").mkdir(parents=True)
    for f in ("cards.mjs", "variants.mjs"):
        (tmp_path / "video" / "tools" / f).write_text("//", encoding="utf-8")
    _mock_pipeline(monkeypatch, render_rc=1)
    tg = FakeTG()
    r = render.receive_audio({"message_id": 950, "audio": {"file_id": "A"}},
                             ds, tg, tmp_path, datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc))
    assert r == "failed:2026-09-08:morning"
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "failed"
    assert any("Render video morning lỗi" in m for m in tg.msgs)


def test_receive_audio_not_audio_returns_none(tmp_path):
    ds = _seed(tmp_path)
    assert render.receive_audio({"message_id": 1, "text": "hi"}, ds, FakeTG(),
                                tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc)) is None


def test_receive_audio_no_waiting_slot(tmp_path):
    ds = DailyState(tmp_path / "data")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text("video: {}\n", encoding="utf-8")
    tg = FakeTG()
    assert render.receive_audio({"message_id": 1, "voice": {"file_id": "V"}}, ds, tg,
                                tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc)) is None
    assert any("không có video nào đang chờ" in m for m in tg.msgs)


def test_receive_audio_matches_by_reply(tmp_path, monkeypatch):
    ds = _seed(tmp_path, slot="evening", date="2026-09-07")   # older, but replied-to
    _seed(tmp_path, slot="morning", date="2026-09-08")        # newer, not replied-to
    (tmp_path / "video" / "tools").mkdir(parents=True)
    for f in ("cards.mjs", "variants.mjs"):
        (tmp_path / "video" / "tools" / f).write_text("//", encoding="utf-8")
    _mock_pipeline(monkeypatch)
    r = render.receive_audio(
        {"message_id": 960, "voice": {"file_id": "V"},
         "reply_to_message": {"message_id": 901}}, ds, FakeTG(), tmp_path,
        datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc))
    # both seeds use script_msg_id 901; reply picks the one whose slot has it —
    # tie broken by most-recent date, so this still resolves to 2026-09-08:morning.
    assert r == "rendered:2026-09-08:morning"


def test_handle_undo(tmp_path):
    ds = _seed(tmp_path, extra_status="rendered")
    class CB:  # noqa
        pass
    tg = FakeTG()
    out = render.handle_undo({"id": "c1", "data": "vid:2026-09-08:morning:undo"},
                             ds, tg, tmp_path, datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc))
    assert out == "discarded:2026-09-08:morning"
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "discarded"
```
(Note: `_seed`'s `**extra` lets a test pass `extra_status="rendered"` — adjust `_seed` so `status` inside `v` can be overridden: change `"status": "awaiting_audio"` to `"status": extra.pop("extra_status", "awaiting_audio")`.)

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_render.py -q -k "receive_audio or handle_undo"`
Expected: FAIL — `render` has no `receive_audio` / `handle_undo`.

- [ ] **Step 3: Implement in `render.py`**

Add imports at top: `import json`, `from datetime import datetime, timezone`, `import yaml`, `from ..daily_state import DailyState`, `from ..publish import slot_unix`. Then:

```python
def _find_slot(ds, msg: dict, now: datetime):
    """(date, slot, videodict) of the awaiting_audio slot this audio belongs to,
    or (None, None, None). Prefer a reply to a known script_msg_id; else newest
    awaiting_audio within 3 days."""
    reply_id = (msg.get("reply_to_message") or {}).get("message_id")
    best = None
    cutoff = now.timestamp() - 3 * 86400
    for f in sorted(ds.all_files(), reverse=True):
        date = f.stem
        doc = ds.load_safe(date)
        if doc is None:
            continue
        for slot, row in doc["posts"].items():
            v = row.get("video") or {}
            if v.get("status") != "awaiting_audio":
                continue
            try:
                if slot_unix(date, "00:00") < cutoff:
                    continue
            except Exception:  # noqa: BLE001
                continue
            if reply_id is not None and v.get("script_msg_id") == reply_id:
                return date, slot, v
            if best is None:
                best = (date, slot, v)
    return best if best else (None, None, None)


def receive_audio(msg: dict, ds, tg, root: Path, now: datetime) -> str | None:
    if _audio_file_id(msg) is None:
        return None
    date, slot, v = _find_slot(ds, msg, now)
    if date is None:
        tg.send_message("⚠️ Nhận được audio nhưng không có video nào đang chờ.")
        return None

    root = Path(root)
    cfg = (yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
           or {}).get("video", {})
    comp = cfg.get("render_composition", "CodexShort")
    video_dir = root / "video"
    script_rel = v["script_path"]
    out_dir = root / Path(script_rel).parent
    pid = out_dir.name
    out_mp4 = out_dir / f"{pid}.mp4"

    ds.put(date, slot, video={**v, "status": "rendering",
                              "audio_msg_id": msg.get("message_id"),
                              "started_at": now.isoformat()})

    def _fail(reason: str, err_tail: str = "") -> str:
        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        ds.put(date, slot, video={**cur, "status": "failed", "render_err": err_tail[-500:]})
        tg.send_message(f"❌ Render video {slot} lỗi: {reason}\n{err_tail[-500:]}\n"
                        "Gửi lại audio để thử lại.")
        return f"failed:{date}:{slot}"

    try:
        raw = tg.download_file(_audio_file_id(msg), str(video_dir / "public" / "voice_in"))
        _to_mp3(Path(raw), video_dir / "public" / "voice.mp3", video_dir)
        sil = _align.make_silence_txt(video_dir / "public" / "voice.mp3",
                                      video_dir / "ref" / "silence.txt", video_dir)
        tl_path = _align.run_aligner(video_dir, sil)
        tl = json.loads(tl_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.exception("prep failed")
        return _fail(f"{type(e).__name__}: {e}")

    dur = float(tl.get("duration", 0) or 0)
    timeline_off = not (25.0 <= dur <= 55.0)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("tools/cards.mjs", "tools/variants.mjs"):
        src = video_dir / name
        if src.exists():
            shutil.copy(src, out_dir / Path(name).name)
    shutil.copy(tl_path, out_dir / "timeline.json")
    shutil.copy(video_dir / "public" / "voice.mp3", out_dir / "voice.mp3")

    r = _remotion_render(video_dir, comp, out_mp4)
    if r.returncode != 0 or not out_mp4.exists():
        return _fail(f"remotion exit {r.returncode}", r.stderr or "")

    slot_ict = (ds.get_safe(date, slot) or {}).get("slot_ict", "11:30")
    due = max(now, datetime.fromtimestamp(slot_unix(date, slot_ict), tz=timezone.utc))
    cur = (ds.get_safe(date, slot) or {}).get("video") or v
    ds.put(date, slot, video={**cur, "status": "rendered",
                              "mp4_path": str(out_mp4.relative_to(root)).replace("\\", "/"),
                              "seconds": round(dur, 1), "render_err": None,
                              "publish_due": due.isoformat()})
    title = (v.get("meta") or {}).get("title", "")
    cap = f"🎬 Video {slot} — {title}\n{round(dur, 1)}s. Tự lên lịch đăng {slot_ict}."
    tg.send_video(str(out_mp4), caption=cap,
                  buttons=[("🗑 Gỡ", f"vid:{date}:{slot}:undo")])
    if timeline_off:
        tg.send_message(f"⚠️ Timeline lệch ({dur:.0f}s), xem kỹ trước khi đăng.")
    return f"rendered:{date}:{slot}"


def handle_undo(cbq: dict, ds, tg, root: Path, now: datetime) -> str | None:
    parts = cbq.get("data", "").split(":")
    if len(parts) != 4 or parts[0] != "vid" or parts[3] != "undo":
        return None
    _, date, slot, _ = parts
    row = ds.get_safe(date, slot) or {}
    v = row.get("video") or {}
    if v.get("status") not in ("awaiting_audio", "rendering", "rendered"):
        try:
            tg.answer_callback(cbq["id"], "Video này đã xử lý.")
        except Exception:  # noqa: BLE001
            pass
        return None
    ds.put(date, slot, video={**v, "status": "discarded"})
    try:
        tg.answer_callback(cbq["id"], "Đã huỷ.")
    except Exception:  # noqa: BLE001
        pass
    tg.send_message(f"🗑 Đã huỷ video {date}:{slot}.")
    return f"discarded:{date}:{slot}"
```

- [ ] **Step 4: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_render.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/video/render.py tests/video/test_render.py
git commit -m "feat(p2b): render.receive_audio + handle_undo — audio -> align -> render -> Telegram"
```

---

## Task 10: `article_approve.poll` routing + `expire_stale` video sweep

**Files:**
- Modify: `src/pipeline/article_approve.py`
- Test: `tests/test_article_approve.py`

**Interfaces:**
- Consumes: `video.render.receive_audio(msg, ds, tg, root, now)`, `video.render.handle_undo(cbq, ds, tg, root, now)` (Task 9).
- Produces: `poll()` routes each update — `callback_query.data` `art:*` → `handle_callback` (unchanged); `vid:*` → `render.handle_undo`; `update.message` with audio (via `render._audio_file_id`) → `render.receive_audio`. `expire_stale` also sweeps `posts.*.video.status == "rendering"` where `now - fromiso(video.started_at) > 40*60` → `video.status = "failed"` + a Telegram warning.

- [ ] **Step 1: Extend `tests/test_article_approve.py`**

```python
def test_poll_routes_video_audio_and_undo(tmp_path, monkeypatch):
    from pipeline import article_approve
    from pipeline.state import State
    seen = {"audio": 0, "undo": 0}
    monkeypatch.setattr(article_approve.render, "receive_audio",
                        lambda msg, ds, tg, root, now: seen.__setitem__("audio", seen["audio"] + 1) or "rendered:x:y")
    monkeypatch.setattr(article_approve.render, "handle_undo",
                        lambda cbq, ds, tg, root, now: seen.__setitem__("undo", seen["undo"] + 1) or "discarded:x:y")
    updates = [
        {"update_id": 20, "message": {"message_id": 1, "voice": {"file_id": "V"}}},
        {"update_id": 21, "callback_query": {"id": "c", "data": "vid:2026-09-08:morning:undo"}},
        {"update_id": 22, "callback_query": {"id": "c2", "data": "art:2026-09-08:morning:undo"}},
    ]

    class FakeTelegram:
        def __init__(self, *a, **k): pass
        def get_updates(self, offset, timeout=0): return updates
        def send_message(self, *a, **k): pass
        def answer_callback(self, *a, **k): pass
    monkeypatch.setattr(article_approve, "Telegram", FakeTelegram)
    monkeypatch.setattr(article_approve, "_meta", lambda: object())
    monkeypatch.setattr(article_approve, "handle_callback", lambda *a, **k: "art-handled")
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    res = article_approve.poll(tmp_path, now=now)
    assert seen == {"audio": 1, "undo": 1}
    assert State(tmp_path / "data").offset_load() == 23


def test_expire_stale_fails_stuck_video_render(tmp_path):
    from pipeline import article_approve
    ds = DailyState(tmp_path / "data")
    ds.put("2026-09-08", "morning", status="scheduled", slot_ict="11:30",
           video={"status": "rendering",
                  "started_at": datetime(2026, 9, 8, 2, 0, tzinfo=timezone.utc).isoformat()})
    tg = FakeTG()
    article_approve.expire_stale(ds, tg, datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc))
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "failed"
    assert any("kẹt khi render" in m for m in tg.msgs)
```
(Use the file's existing `FakeTG` / `DailyState` imports.)

- [ ] **Step 2: Run — verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py -q -k "video"`
Expected: FAIL — `article_approve` has no `render`.

- [ ] **Step 3: Edit `article_approve.py`**

Add import: `from .video import render`.

In `poll()`, replace the update loop body:
```python
    for up in updates:
        try:
            max_uid = max(max_uid, up.get("update_id", max_uid))
            cbq = up.get("callback_query")
            msg = up.get("message")
            if cbq:
                data = cbq.get("data", "")
                if data.startswith("vid:"):
                    r = render.handle_undo(cbq, ds, tg, root, now)
                else:
                    r = handle_callback(cbq, ds, tg, meta, root, now)
                if r:
                    handled.append(r)
            elif msg and render._audio_file_id(msg):
                r = render.receive_audio(msg, ds, tg, root, now)
                if r:
                    handled.append(r)
        except Exception as e:  # noqa: BLE001 - a poison update must not stall the poller
            log.exception("update %s failed: %s", up.get("update_id"), e)
```

In `expire_stale`, inside the `for slot_name, slot in doc["posts"].items():` loop, after the existing `status`/`due` block, add:
```python
            v = slot.get("video") or {}
            if v.get("status") == "rendering" and v.get("started_at"):
                try:
                    started = datetime.fromisoformat(v["started_at"])
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                except ValueError:
                    started = now
                if (now - started).total_seconds() > 40 * 60:
                    ds.put(date, slot_name, video={**v, "status": "failed"})
                    stuck.append(f"{date}:{slot_name} (video)")
```
And change the stuck-notify loop to distinguish:
```python
    for s in stuck:
        if s.endswith("(video)"):
            tg.send_message(f"⚠️ {s} kẹt khi render, gửi lại audio để thử.")
        else:
            tg.send_message(f"⚠️ {s} kẹt ở 'publishing' — đã đánh dấu posted, kiểm tra Page.")
```

- [ ] **Step 4: Run — verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/article_approve.py tests/test_article_approve.py
git commit -m "feat(p2b): poll routes video audio + vid: undo; expire_stale fails stuck renders"
```

---

## Task 11: `article-approve.yml` + full suite + README

**Files:**
- Modify: `.github/workflows/article-approve.yml`
- Modify: `README.md`
- Test: `tests/test_workflows.py` (adjust) + whole suite

**Interfaces:** none — infra + docs.

- [ ] **Step 1: Edit `.github/workflows/article-approve.yml`**

- `jobs.approve.timeout-minutes: 15` → `25`.
- After the `setup-python` step add:
  ```yaml
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - name: Video render deps
        run: |
          cd video && npm ci
          npx remotion browser ensure
  ```
- Keep cron `*/5 * * * *`, `concurrency.group: pipeline-state`, the `env:` block (already has `TELEGRAM_*` + `META_*`), and the `Commit state` step.

- [ ] **Step 2: Adjust `tests/test_workflows.py`**

If it asserts `article-approve.yml` `timeout-minutes: 15` → change to `25`. If it has a "no node in article-approve" style assertion → remove it. Add: `assert "npm ci" in approve_text` and `assert "remotion browser ensure" in approve_text`.

- [ ] **Step 3: README — add "Luồng video (Phase 2B)"**

Under the article-flow section:
```markdown
## Luồng video (Phase 2B)

- `article_run.draft` (07:00 / 17:00 ICT), sau khi lên lịch bài viết, sinh **kịch bản
  video** + tiêu đề/mô tả/hashtag/từ khoá cho cùng câu chuyện, gửi kịch bản lên Telegram.
- Bạn thu âm đọc kịch bản, gửi file audio vào bot (bất cứ lúc nào).
- `article-approve` (mỗi 5 phút) nhận audio → căn giờ (`align.mjs`) → `npx remotion
  render CodexShort` → gửi MP4 lên Telegram → `video.status = "rendered"` + nút `🗑 Gỡ`.
- Nền video cố định: `video/public/bg.mp4` (đặt một lần).
- Đăng YouTube / FB Reel / IG Reel / TikTok = Phase 2C (chưa làm).
- Tắt cả nhánh video: `config/settings.yaml` → `video.enabled: false`.
```

- [ ] **Step 4: Whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q`
Expected: PASS.
Run: `.venv/Scripts/python.exe -m pytest tests/video -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/article-approve.yml README.md tests/test_workflows.py
git commit -m "docs(p2b): article-approve runs remotion; README video flow"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-09-08-phase2b-video-render-review-design.md`):
- §2 "Bỏ": `tts.py` + `test_tts.py` + `--tts-check`/`--fake` + `tts_provider` → Task 1. `tts-spike.md` kept (untouched). `requirements-video.txt` trim → Task 1.
- §3.1(a) `generate_from_article` → Task 4. §3.1(b) `VideoMeta` + `_validate_meta` + `publish` block → Task 3 + Task 4.
- §3.2 `draft_script.draft` → Task 5.
- §3.3 `article_run.draft()` wiring, lazy import, `video.enabled` gate → Task 6.
- §3.4 `render.py` (`_audio_file_id`, `_to_mp3`, `_remotion_render`) → Task 8; (`receive_audio`, `handle_undo`) → Task 9.
- §3.5 `article_approve.poll` routing + `expire_stale` video sweep + `article-approve.yml` node/timeout → Task 10 + Task 11. No separate poller/offset/workflow — confirmed (Tasks 10/11 only touch `article_approve`/`article-approve.yml`).
- §3.6 `settings.yaml` → Task 1.
- §3.7 `bg.mp4` + `BgVideo.tsx` → Task 2.
- §4 `video` record shape → Task 5 (initial write) + Task 9 (transitions). All keys present.
- §5 error table → Task 5 (gen fail), Task 8 (`_to_mp3` fail → `AlignError`), Task 9 (align fail, remotion fail, timeline_off, already-handled), Task 10 (stuck-rendering sweep).
- §6 test list → each task's Step 1. `test_tts.py` deleted (Task 1). Both suites green (Task 11).
- §7 YAGNI: no TTS, no bg pool, no publishing, no ✅-gate — nothing in the plan adds them.
- `Telegram.send_video` (§3.4 "cần method mới") → Task 7.

**Placeholder scan:** Task 1 Step 3/5 and Task 2 Step 2/4 and Task 11 Step 2 say "open it / grep / adjust to match" rather than giving literal final code — deliberate: those touch pre-existing test/YAML files this plan can't see verbatim, and each gives the exact assertion to end at. Everything creating NEW code (Tasks 3,4,5,7,8,9 + the `article_run`/`article_approve` edits) carries complete code.

**Type consistency:**
- `generate_from_article(title, source_url, body_text, caption_fb, angle, voice, cfg, llm=None) -> (Script, VideoMeta)` — Task 4 def, Task 5 call (kwargs match), spec §3.1.
- `draft_script.draft(slot, root, *, title, source_url, body_text, caption_fb, angle, now, generate=None, tg=None) -> dict` — Task 5 def, Task 6 call (`_video_draft.draft(slot, root, title=…, source_url=…, body_text=…, caption_fb=…, angle=…, now=…, generate=…, tg=…)`), spec §3.2/§3.3.
- `render.receive_audio(msg, ds, tg, root, now)` / `render.handle_undo(cbq, ds, tg, root, now)` — Task 9 def, Task 10 call. `render._audio_file_id(msg)` — Task 8 def, Task 10 + Task 9 use.
- `render._remotion_render(video_dir, composition, out_mp4) -> CompletedProcess` — Task 8 def, Task 9 call.
- `Telegram.send_video(path, caption="", buttons=None) -> dict` — Task 7 def, Task 9 call.
- `video` state keys (`status, meta, spoken_text, script_path, script_msg_id, audio_msg_id, mp4_path, seconds, render_err, started_at, publish_due, result`) — Task 5 writes all; Task 9 reads `script_path`/`meta`/`script_msg_id` and writes `status`/`audio_msg_id`/`started_at`/`mp4_path`/`seconds`/`render_err`/`publish_due`; Task 10 reads `status`/`started_at`. Consistent.
- `_align._ffmpeg_bin(video_dir)` — real fn in `align.py` (verified). `_align.make_silence_txt(voice, out_txt, video_dir) -> float`, `_align.run_aligner(video_dir, duration) -> Path` — real signatures (verified).
- `daily_state.DailyState.put(date, slot, **fields)` does `cur.update(fields)` — so `put(date, slot, video={...})` replaces the whole `video` sub-dict; every writer in Tasks 5/9/10 passes `video={**existing, ...}`. Consistent with the Global Constraint.
