# Phase 2B — Video: kịch bản → audio người dùng → render → xem trên Telegram

**Ngày:** 2026-09-08
**Trạng thái:** đã duyệt thiết kế, chờ review spec → writing-plans
**Nhánh dự kiến:** `feature/p2b-video-render`
**Base:** `ce92f8a` (Plan 1 + Plan 2 đã merge + push)

## 1. Mục tiêu

Nối tiếp Phase 1: mỗi lần `article_run.draft(slot)` chọn được một tin, ngoài carousel bài viết, sinh thêm **kịch bản video kinetic-typography** cho cùng câu chuyện đó, gửi lên Telegram để người dùng **tự thu âm đọc** và gửi file audio lại. Poller nhận audio → căn giờ → **render MP4 đầy đủ** (Remotion, dọc 1080×1920, ~40s) → gửi MP4 lên Telegram cho người dùng xem → **tự lên lịch** để Phase 2C đăng lên YouTube / FB Reel / IG Reel / TikTok.

**"Xong" của 2B:** với một `data/daily/<date>.json` có `posts.<slot>.video.status == "awaiting_audio"`, gửi một file audio hợp lệ vào bot → trong ≤2 vòng poll, `video.status` chuyển `"rendered"`, có `mp4_path` trỏ tới một MP4 render thật, và MP4 đó đã được `sendVideo` lên Telegram.

**Ngoài phạm vi 2B:** đăng lên bất kỳ nền tảng nào (→ 2C). TTS / voice clone (đã bỏ hẳn). Pool nền / lịch nền. Nhiều hơn 1 video/slot. Video ngang YouTube dài. Cổng duyệt "✅ Đăng" chặn (render xong tự lên lịch, chỉ có nút Gỡ).

## 2. Bối cảnh & quyết định đã chốt

| Vấn đề | Quyết định (2026-09-08) |
|---|---|
| Nguồn giọng | **Người dùng tự thu, gửi file audio qua Telegram.** Bỏ hẳn TTS. |
| Chủ đề video | **Dùng chung tin đã chọn cho bài viết.** 2 video/ngày (slot sáng + tối). |
| Sau khi render | Gửi MP4 lên Telegram cho người dùng xem, **rồi tự lên lịch đăng** (không chặn chờ bấm). Nút `🗑 Gỡ` làm lưới an toàn. |
| Thiếu audio trước giờ slot | **Không bỏ.** Khi nào người dùng gửi audio (kể cả sau giờ slot) thì render + đăng lúc đó. |
| Nền video | **Một file cố định** `video/public/bg.mp4` (từ `adsbot-vox.mp4` người dùng cung cấp). Không pool, không lịch. |
| Metadata đăng | Bước sinh kịch bản đẻ luôn **tiêu đề giật tít + mô tả + hashtag + từ khoá**, lưu vào `video` record để 2C dùng. |
| Nơi render | GitHub Actions `ubuntu-latest` + Node 20 + `npx remotion render` (Chrome headless). |

### Đã có sẵn từ Phase 2A (giữ, tái dùng)

- `src/pipeline/video/models.py` — `Card`, `SectionMark`, `Script` (`.spoken_text`, `.word_count`).
- `src/pipeline/video/script.py` — `generate(cand, post, voice, cfg, llm) -> Script` (LLM, schema, dải từ, retry `[SỬA]`).
- `src/pipeline/video/variants.py` — `normalize(script)` (heuristic hậu kiểm layout).
- `src/pipeline/video/codegen.py` — `write(script, video_dir)` → `video/tools/cards.mjs` + `video/tools/variants.mjs`; `node_check(video_dir)`.
- `src/pipeline/video/align.py` — `make_silence_txt(voice_mp3, out_txt, video_dir) -> float`; `run_aligner(video_dir, sil_dur) -> Path` (→ `video/src/timeline.json`).
- `video/` — dự án Remotion. `Root.tsx` có `<Composition id="CodexShort" .../>` 1080×1920@30. `BgVideo.tsx` layer nền + scrim.
- `tests/video/` — 42 test đang xanh.

### Bỏ

- `src/pipeline/video/tts.py` + `tests/video/test_tts.py` — xoá.
- `build_video.py`: nhánh `_tts.synthesize`, `--tts-check`, `--fake` (nghĩa TTS).
- `config/settings.yaml` `video.tts_provider` — xoá.
- `docs/superpowers/notes/2026-09-03-tts-spike.md` — **giữ** (lịch sử), không sửa.
- `requirements-video.txt` — bỏ các gói chỉ phục vụ TTS (`f5-tts`, `gradio-client`, `faster-whisper` nếu không dùng chỗ khác); giữ những gì `align`/`codegen` cần.

---

## 3. Kiến trúc

### 3.1 `src/pipeline/video/script.py` — thêm hai thứ

**(a) Adapter cho `ArticleContent`.** Article track không còn `Candidate`/`PostContent` ở `draft()`. Thêm:

```python
def generate_from_article(title: str, source_url: str, body_text: str,
                          caption_fb: str, angle: str, voice: dict, cfg: dict,
                          llm=None) -> tuple[Script, VideoMeta]:
    """Dựng shim Candidate+PostContent tối thiểu từ dữ liệu bài viết rồi gọi
    generate(). body_text = article.caption_fb (bản chia sẻ) khi không có
    fulltext. Trả (Script, VideoMeta)."""
```

**(b) Metadata đăng.** Prompt của `build_prompt` mở rộng để LLM trả thêm một khối `publish`:

```
"publish": {
  "title": str,        # <=70 ký tự, giật tít, có yếu tố tò mò/con số
  "description": str,   # 2-4 câu + 1 CTA (theo dõi kênh); không chèn URL trần
  "hashtags": [str],    # 8-12, mỗi cái bắt đầu bằng '#', không dấu cách
  "keywords": [str],    # 5-10 từ khoá cho YouTube tags (không '#')
  "tiktok_caption": str # <=150 ký tự, kèm 3-5 hashtag inline
}
```

`VideoMeta` (dataclass trong `models.py`): `title, description, hashtags: list[str], keywords: list[str], tiktok_caption`. Validate: `title` 10..70 ký tự; `8 <= len(hashtags) <= 12` và mọi phần tử khớp `^#\S+$`; `5 <= len(keywords) <= 10`; `tiktok_caption` ≤ 150. Thiếu/sai → `VideoScriptError` (giống schema kịch bản, một lần retry `[SỬA]`).

`_validate` cũ tách phần kịch bản; hàm mới `_validate_meta(data["publish"], ...)`. `Script.from_dict` không đổi.

### 3.2 `src/pipeline/video/draft_script.py` (mới)

```python
def draft(slot: str, root: Path, *, title: str, source_url: str, body_text: str,
          caption_fb: str, angle: str, now: datetime, generate=None, tg=None) -> dict:
    """Sinh kịch bản + metadata cho slot, codegen ra cards.mjs/variants.mjs,
    ghi posts.<slot>.video vào daily-state với status='awaiting_audio', gửi tin
    kịch bản lên Telegram. Trả bản ghi video, hoặc {'status':'error'} nếu gen lỗi
    (bài viết đã tự lên lịch nên KHÔNG raise ra ngoài)."""
```

Luồng:
1. `cfg = settings["video"]`; nếu `not cfg.get("enabled")` → `{"skipped": True}`.
2. `voice = yaml.safe_load(config/voice.yaml)`.
3. `try: s, meta = script.generate_from_article(...); s = variants.normalize(s)` — `except VideoScriptError as e:` → `tg.send_message(f"⚠️ Kịch bản video {slot} lỗi: {e}")`, return `{"status": "error"}`.
4. `codegen.write(s, root/"video")`; `try: codegen.node_check(root/"video") except FileNotFoundError: log.warning(...)`.
5. `date = now.astimezone(utc).strftime("%Y-%m-%d")`; `pid = _make_id(title, now)` (dùng `_slug` sẵn có trong `build_video`).
6. `out_dir = root/"output"/date/pid/"video"`; `script.write_script_json(s, out_dir)`.
7. `ds.put(date, slot, video={...})` — bản ghi §4, `status="awaiting_audio"`, kèm `meta`.
8. Telegram:
   ```
   🎬 Kịch bản video {slot} ({date})

   {s.spoken_text}

   ▶️ Thu âm đọc đúng đoạn trên (~{cfg['target_seconds']}s), gửi file audio lại cho bot.
   ```
   (nếu `spoken_text` > 3500 ký tự thì chia 2 tin — hiếm.)

### 3.3 Nối vào `src/pipeline/article_run.py`

Trong `draft()`, **sau** khi `publish.schedule_slot(...)` xong (nhánh thành công), trước `return ds.get(...)`:

```python
    try:
        video.draft_script.draft(
            slot, root, title=title, source_url=(state_sources[0]["url"] if state_sources else ""),
            body_text=article.caption_fb, caption_fb=article.caption_fb, angle=angle,
            now=now, generate=generate, tg=tg)
    except Exception as e:  # noqa: BLE001 - video là phụ; bài viết đã lên lịch
        log.warning("video draft_script failed: %s", e)
        try: tg.send_message(f"⚠️ Kịch bản video {slot} lỗi: {e}")
        except Exception: pass
```

Import lười: `from .video import draft_script as _video_draft` (tránh kéo Remotion deps vào path bài viết — `draft_script` chỉ import `script`/`variants`/`codegen`, đều thuần Python).

Không chạy nếu `settings["video"]["enabled"]` false (giữ `draft()` không đổi hành vi khi tắt video).

### 3.4 `src/pipeline/video/render.py` (mới)

```python
def receive_audio(msg: dict, ds, tg, root: Path, now: datetime) -> str | None:
    """msg = một Telegram message. Nếu có voice/audio/document(mp3|m4a|wav|ogg):
    tải về, khớp slot video 'awaiting_audio' mới nhất (hoặc slot mà tin kịch bản
    của nó là reply_to_message), chuyển mp3, align, render, sendVideo, cập nhật
    state. Trả 'rendered:{date}:{slot}' / 'failed:{date}:{slot}' / None."""
```

- `_audio_file_id(msg) -> str | None` — ưu tiên `voice.file_id`, rồi `audio.file_id`, rồi `document.file_id` nếu `mime_type` ∈ {audio/mpeg, audio/mp4, audio/x-wav, audio/ogg} hoặc đuôi hợp lệ. Không có → `None` (poller bỏ qua).
- Khớp slot: nếu `msg.reply_to_message.message_id` == một `video.script_msg_id` đã lưu → dùng slot đó; nếu không → slot `video.status=="awaiting_audio"` có `date` mới nhất (trong cửa sổ 3 ngày). Không có slot chờ nào → `tg.send_message("⚠️ Nhận được audio nhưng không có video nào đang chờ.")`, return `None`.
- `ds.put(date, slot, video={**v, "status": "rendering", "audio_msg_id": msg["message_id"]})` — đặt TRƯỚC khi tải/render (chống double khi poll lại).
- `tg.download_file(file_id, root/"video/public/voice_in")` → `_to_mp3(src, root/"video/public/voice.mp3", root/"video")` (subprocess `ffmpeg -i … -ac 1 -ar 44100 -b:a 128k voice.mp3`; ffmpeg = `video/node_modules/ffmpeg-static/ffmpeg` hoặc `ffmpeg` trên PATH).
- `sil = align.make_silence_txt(voice_mp3, root/"video/ref/silence.txt", root/"video")`; `tl_path = align.run_aligner(root/"video", sil)`; `tl = json.loads(...)`; `timeline_off = not (25 <= tl["duration"] <= 55)`.
- Copy `cards.mjs, variants.mjs, timeline.json, voice.mp3` → `out_dir` (đường dẫn từ `video.script_path`'s cha).
- `_remotion_render(video_dir, composition, out_mp4) -> subprocess.CompletedProcess` — `npx remotion render {composition} {out_mp4}` trong `video_dir`, `capture_output`, `encoding="utf-8"`, `errors="replace"`. **Hàm riêng để test mock.**
  - exit ≠ 0 → `ds.put(video.status="failed", render_err=stderr[-500:])`; `tg.send_message(f"❌ Render video {slot} lỗi:\n{stderr[-500:]}\nGửi lại audio để thử lại.")`; return `failed:...`.
- exit 0 → `dur = tl["duration"]`; `ds.put(video={..., "status":"rendered", "mp4_path": rel(out_mp4), "seconds": round(dur,1), "publish_due": max(now, slot_unix(date, slot_ict)) iso, "result": {"yt":None,"fb":None,"ig":None,"tiktok":None}})`.
  - `tg.send_video(out_mp4, caption=f"🎬 Video {slot} — {meta['title']}\n{round(dur,1)}s. Tự lên lịch đăng {slot_ict}." )` + nút `[🗑 Gỡ]` data `vid:{date}:{slot}:undo`.
  - `timeline_off` → thêm tin `⚠️ Timeline lệch ({dur:.0f}s), xem kỹ trước khi đăng.`
  - return `rendered:...`.

`telegram.Telegram` cần method mới `send_video(path, caption="", buttons=None)` — `sendVideo` multipart (giống `send_document`). Thêm.

### 3.5 Route trong `src/pipeline/article_approve.py` (KHÔNG có poller video riêng)

`article_approve.poll` là poller Telegram **duy nhất** đọc `getUpdates` (một offset `data/telegram_offset.json`). Không tạo `video_approve.py`, không tạo `video-approve.yml`, không có offset thứ hai (hai offset trên cùng một bot chắc chắn lệch → update bị xử 2 lần hoặc bỏ sót).

`poll` route mỗi update:
- `callback_query.data` bắt đầu `art:` → `handle_callback` (như cũ).
- `callback_query.data` bắt đầu `vid:` → `render.handle_undo(cbq, ds, tg, root, now)` — 2B chỉ set `video.status="discarded"` + `tg.send_message("🗑 Đã huỷ video {slot}.")` (chưa có post thật để xoá; 2C mở rộng xoá 4 nền tảng).
- `update.message` có audio (theo `render._audio_file_id`) → `render.receive_audio(msg, ds, tg, root, now)`.
- mỗi update bọc `try/except` riêng (poison update không làm treo poll); `offset_save(max_uid + 1)` như cũ.

`receive_audio` render mất ~5-8', chạy đồng bộ trong `poll` → chặn poll bài viết trong lúc đó. Chấp nhận: nâng `article-approve.yml` `timeout-minutes` 15 → **25**; giữ `concurrency.group: pipeline-state`. Render chỉ xảy ra 2 lần/ngày, và bài viết đã lên lịch native FB nên poll trễ 8' không mất bài.

`expire_stale` (đã có trong `article_approve`) mở rộng: quét `posts.*.video.status == "rendering"` mà `now - video.started_at > 40 phút` → set `"failed"` + `tg.send_message("⚠️ video {slot} kẹt khi render, gửi lại audio để thử.")`.

`article-approve.yml` cần Node 20 + `npx remotion` sẵn (Chrome headless) vì render chạy trong poll: thêm `actions/setup-node@v4` + bước `cd video && npm ci` + `npx remotion browser ensure` vào workflow (hiện chỉ có Python).

### 3.6 `config/settings.yaml`

```yaml
video:
  enabled: true              # 2B bật; đặt lại false để tắt cả nhánh video
  target_seconds: 40
  words_min: 110
  words_max: 140
  render_composition: CodexShort
```
(bỏ `tts_provider`.)

### 3.7 Nền video `video/public/bg.mp4`

- Người dùng cung cấp `adsbot-vox.mp4` → copy vào `video/public/bg.mp4` (commit — file ~vài MB; nếu > 40MB thì để `.gitignore` và người dùng đặt tay + ghi trong README).
- `BgVideo.tsx` hiện dùng gì làm nền cần kiểm khi implement (Task đầu của plan): nếu nó đọc một mảng `BG` schedule → 2B ghi `video/src/BgVideo.tsx` (hoặc một `bg.json`) tối thiểu `[{src:"bg.mp4", from:0, durationInFrames: <all>}]` trong `codegen.write` hoặc `render.receive_audio`. Nếu nó đã mặc định một file → không cần gì.

---

## 4. `data/daily/<date>.json` — khối `video`

```json
"posts": {
  "morning": {
    "status": "scheduled",
    "video": {
      "status": "awaiting_audio",
      "meta": {
        "title": "…", "description": "…",
        "hashtags": ["#AI", "…"], "keywords": ["…"],
        "tiktok_caption": "…"
      },
      "spoken_text": "…",
      "script_path": "output/2026-09-08/2026-09-08-openai-…/video/script.json",
      "script_msg_id": 811,
      "audio_msg_id": 842,
      "mp4_path": "output/2026-09-08/2026-09-08-openai-…/video/2026-09-08-openai-….mp4",
      "seconds": 41.2,
      "render_err": null,
      "started_at": "2026-09-08T02:31:00+00:00",
      "publish_due": "2026-09-08T04:45:00+00:00",
      "result": { "yt": null, "fb": null, "ig": null, "tiktok": null }
    }
  }
}
```

Trạng thái một chiều: `awaiting_audio → rendering → rendered → discarded` (nút Gỡ) / `failed` (render/align lỗi; gửi lại audio đưa về `awaiting_audio`). `rendered` là đầu vào của 2C.

## 5. Xử lý lỗi (tổng hợp)

| Tình huống | Hành vi |
|---|---|
| `script.generate` / `generate_from_article` lỗi | `draft_script.draft` trả `{"status":"error"}`, Telegram `⚠️`, **không** raise; bài viết vẫn đăng. |
| `codegen.node_check` không có node | log warning, tiếp tục (CI có node; máy user có thể không). |
| Update Telegram không phải audio / không khớp slot nào | bỏ qua (không phải audio) hoặc `⚠️ không có video đang chờ` (là audio nhưng không slot). Poller không crash. |
| `_to_mp3` (ffmpeg) exit ≠ 0 | `video.status="failed"`, Telegram `❌ chuyển audio lỗi`, gửi lại để thử. |
| `align` raise `AlignError` | `video.status="failed"` + Telegram. |
| `remotion render` exit ≠ 0 | `video.status="failed"`, `render_err`=stderr[-500:], Telegram kèm stderr, "gửi lại audio". |
| `timeline_off` (dur < 25 hoặc > 55) | vẫn render, Telegram cảnh báo. |
| Poller kill giữa render | slot kẹt `"rendering"`; `expire_stale` >40' → `"failed"` + cảnh báo. |
| Nhận audio khi slot `video` đã `rendered`/`discarded` | `⚠️ video slot này đã xử lý` — không render lại. |

## 6. Test

| File | Nội dung |
|---|---|
| `tests/video/test_script.py` (mở rộng) | `generate_from_article` dựng shim đúng, trả `(Script, VideoMeta)`; `_validate_meta` bắt title quá dài / hashtag thiếu / keyword thừa; retry `[SỬA]` một lần khi meta sai. |
| `tests/video/test_draft_script.py` (mới) | `draft` ghi `posts.<slot>.video` `awaiting_audio` + `meta` + `spoken_text`; gửi tin kịch bản; `generate` raise → `{"status":"error"}` + Telegram `⚠️`, không ghi record. `enabled=false` → `{"skipped":True}`, không gọi LLM. |
| `tests/video/test_render.py` (mới) | `receive_audio`: message `voice` → `download_file` (mock) → khớp slot mới nhất → `_to_mp3` (mock subprocess) → `align` (mock) → `_remotion_render` (mock, exit 0) → `send_video` (mock) → state `rendered` + `mp4_path` + `publish_due` + `result` khung. message không audio → `None`, state không đổi. `_remotion_render` exit 1 → `failed` + `render_err` + stderr tail tới Telegram. message audio nhưng không slot chờ → `⚠️` + `None`. reply vào `script_msg_id` → khớp đúng slot đó (không phải slot mới nhất). |
| `tests/test_article_approve.py` (mở rộng) | `poll` route: callback `vid:D:S:undo` → `video_render.handle_undo` (xóa? — 2B chỉ set `discarded` + báo; 2C mới có post thật để xóa); message audio → `receive_audio` gọi; `expire_stale` `video.status="rendering"` > 40' → `failed`. |
| `tests/test_article_run.py` (mở rộng) | `draft()` gọi `video.draft_script.draft` sau `schedule_slot` khi `video.enabled`; `draft_script` raise → chỉ log + Telegram `⚠️`, `draft()` vẫn trả `scheduled`. `video.enabled=false` → không gọi. |
| `tests/video/test_telegram_send_video.py` hoặc `tests/test_telegram.py` (mở rộng) | `Telegram.send_video` multipart đúng field (`chat_id`, `video`, `caption`, `reply_markup`). |
| `tests/video/test_workflows_video.py` (sửa) | bỏ assert `video-smoke` nếu đổi; `article-approve.yml` `timeout-minutes: 25`. |
| `tests/video/test_tts.py` | **xoá.** |
| toàn bộ | `.venv/Scripts/python.exe -m pytest tests --ignore-glob='*video*' -q` VÀ `pytest tests/video -q` đều xanh. CI (`article-test`) xanh. |

## 7. Không làm (YAGNI)

TTS. Pool/lịch nền. Đăng nền tảng (2C). >1 video/slot. Video ngang dài. Cổng "✅ Đăng" chặn. Whisper align (dùng `align.mjs` silence-based sẵn có). Sửa dự án Remotion (chỉ "nạp liệu" + render).

## 8. Rủi ro / lưu ý

- **Render trên runner**: `npx remotion render` cần Chrome headless (`npx remotion browser ensure` hoặc `--chrome-mode=chrome-for-testing`). ~40s@30fps = 1200 frame; runner 2 core ~4-8'. Timeout job 25'. Lần đầu tải Chrome ~1-2'.
- **Chặn `article-approve`**: một render đang chạy giữ `concurrency: pipeline-state` ~8', hoãn poll bài viết. Chấp nhận (bài viết đã lịch native FB). Nếu thành vấn đề → tách workflow + tách offset (đã cân nhắc, để lại follow-up).
- **`bg.mp4` kích thước**: nếu > ~40MB, không commit — `.gitignore` + README hướng dẫn người dùng đặt tay vào `video/public/`.
- **Một chiều nhận audio**: người dùng gửi nhầm audio khác → khớp nhầm slot mới nhất. Giảm thiểu: chỉ khớp slot trong 3 ngày, ưu tiên `reply_to` tin kịch bản. Nút Gỡ + gửi lại audio là cách sửa.
- **`article_approve` giờ đa nhiệm** (callback bài viết + callback video + audio). Giữ `handle_callback` route rõ theo prefix `art:` / `vid:`; message audio là nhánh riêng trước phần callback.
- **2C phụ thuộc**: đọc `video.status=="rendered"` + `video.meta` + `video.mp4_path` + `video.publish_due`; ghi `video.result.{yt,fb,ig,tiktok}`; mở rộng nút Gỡ để xóa post thật.
