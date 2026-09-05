# AI Social Automation — Phase 1

Tự động mỗi ngày: gom tin AI viral → chọn tin nóng nhất → viết bài tiếng Việt →
tạo 3–4 ảnh → gửi preview Telegram để duyệt → đăng Facebook Page + Instagram.
Chạy miễn phí trên GitHub Actions.

## Chạy thử offline (không đăng, không gọi API bài đăng)

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
python -m playwright install chromium
python -m pipeline.run --dry-run --local --fake-llm   # không cần key nào
```

Bỏ `--fake-llm` khi đã đặt `CLAUDE_CODE_OAUTH_TOKEN` hoặc `GEMINI_API_KEY`
để xem nội dung thật do LLM viết.

Kết quả nằm ở `output/<ngày>/<id>/`: `caption_fb.txt`, `caption_ig.txt`,
`youtube.txt`, `tiktok.txt`, `meta.json`, và `img/`.

> `--local` đọc `tests/fixtures/local_candidates.json` thay cho việc gọi mạng
> thu thập tin. `--dry-run` không gửi Telegram và không đăng. `--fake-llm`
> dùng nội dung mẫu có sẵn thay cho gọi LLM (kiểm tra luồng khi chưa có key).

## Secrets cần đặt (GitHub → Settings → Secrets and variables → Actions)

| Secret | Lấy ở đâu |
|---|---|
| `META_PAGE_ID` | Graph API Explorer → `GET /me/accounts` |
| `META_PAGE_TOKEN` | Page token, đổi sang long-lived (xem dưới) |
| `IG_BUSINESS_ID` | `GET /{PAGE_ID}?fields=instagram_business_account` |
| `META_APP_ID`, `META_APP_SECRET` | App trong developers.facebook.com (chỉ dùng cho refresh) |
| `TELEGRAM_BOT_TOKEN` | @BotFather |
| `TELEGRAM_CHAT_ID` | Nhắn bot 1 câu, rồi mở `https://api.telegram.org/bot<token>/getUpdates` xem `chat.id` |
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

## Môi trường dev (máy này)

Ổ C: đầy → dùng venv trên ổ D:. Interpreter: `D:\python.exe` (Python 3.12.3).

```
D:\Automation Social\.venv\Scripts\python.exe -m pytest -q
```

Cache đã trỏ về D: qua biến môi trường user (`PIP_CACHE_DIR`, `HF_HOME`,
`TORCH_HOME`, `UV_CACHE_DIR` → `D:\cache\*`). Cài lại deps:
`.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-video.txt -e .`

## Phase 2A — video (kịch bản + giọng + timeline)

Bật `config/settings.yaml` → `video.enabled: true`. Chuẩn bị:
- `assets/voice/sample.wav` — 3–10 phút giọng kể (WAV mono 44.1kHz)
- `assets/voice/sample.txt` — lời thoại của mẫu (không có thì pipeline tự transcribe)
- `video/public/bg-*.mp4` — pool nền (2B dùng)

Thử offline (không gọi TTS thật):

    python -m pipeline.video.build_video --fake --fake-llm --story tests/fixtures/video/story.json

Sau khi chạy build_video ở máy local, hoàn nguyên file sinh ra: `git checkout -- video/tools video/src/timeline.json video/public/voice.mp3`.

Kiểm tra giọng clone thật:

    python -m pipeline.video.build_video --tts-check

TTS engine do spike chọn (xem docs/superpowers/specs/2026-09-03-phase2a-script-voice-timeline-design.md (mục 4 — spike TTS)).
F5-TTS checkpoint tiếng Việt có ràng buộc license — chỉ dùng làm fallback.

## Kiến trúc

`src/pipeline/`: `collect → score → write → media → review → publish`, cộng
`llm` (Claude CLI → Gemini fallback), `telegram`, `meta`, `state`, `models`.
`run.py` chạy giai đoạn dựng bài; `approve_poll.py` xử lý nút Telegram.
State (`data/seen.json`, `data/pending/`, `data/posted/`) được commit ngược repo.

Spec và plan đầy đủ: `docs/superpowers/`. 
 
