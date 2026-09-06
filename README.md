# AI Social Automation — Phase 1

Tự động mỗi ngày: chọn một chủ đề AI/năng suất từ ngân hàng chủ đề
(`config/topics.yaml`) tránh trùng lịch sử → viết bài tiếng Việt từ kiến thức
model → tạo 5 ảnh slide → gửi preview Telegram để duyệt → đăng Facebook Page +
Instagram. Chạy miễn phí trên GitHub Actions.

## Chạy thử offline (không đăng, không gọi API bài đăng)

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
python -m playwright install chromium
python -m pipeline.article_run --slot morning --root . --fake-llm   # không cần key nào
```

Bỏ `--fake-llm` khi đã đặt `CLAUDE_CODE_OAUTH_TOKEN` hoặc `GEMINI_API_KEY`
để xem nội dung thật do LLM viết.

Kết quả nằm ở `data/daily/<ngày>.json` (bản nháp cho slot) và ảnh ở
`assets/posts/<ngày>/<slot>/`.

> `--fake-llm` dùng nội dung mẫu có sẵn thay cho gọi LLM (kiểm tra luồng khi
> chưa có key). Khi chưa đặt `TELEGRAM_BOT_TOKEN`, lệnh chạy ở chế độ smoke
> ngoại tuyến: không gửi Telegram, in `SUMMARY: dry`.

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

Bài morning/evening **không cào tin** nữa. Mỗi lần chạy, pipeline nạp ngân hàng
chủ đề `config/topics.yaml` (formats × themes + seeds) và danh sách tiêu đề đã
đăng gần đây (`data/daily/*.json`, cửa sổ `recent_window_days`), rồi gọi LLM một
lần để chọn **một chủ đề cụ thể, không trùng lịch sử**. Bài được viết từ kiến
thức sẵn có của model (`write.write_topic_post`), không có `Nguồn:`. Chỉnh chủ đề
bằng cách sửa `config/topics.yaml`.

`config/sources.yaml` (RSS, subreddit) và `collect`/`score` vẫn còn trong repo và
vẫn được test, nhưng không nằm trên đường dựng bản nháp nữa.

## Lịch chạy

- `article-morning`: 07:00 ICT (`cron '0 0 * * *'`) → chọn chủ đề từ
  `config/topics.yaml` + lịch sử gần đây → viết bài #1 từ kiến thức model →
  gửi preview Telegram.
- `article-evening`: 17:00 ICT (`cron '0 10 * * *'`) → như trên cho bài #2
  (tránh trùng chủ đề bài sáng).
- `article-approve`: mỗi 10 phút (`cron '*/10 * * * *'`) → xử lý nút Telegram
  Đăng ngay / Lên lịch / Bỏ.
- `article-publish-ig`: poll trong khung giờ đăng
  (`cron '0,15,30,45 4,5,12,13 * * *'`) → đăng carousel Instagram khi tới đúng
  giờ slot đã lên lịch.
- `refresh-token.yml`: mùng 1 hàng tháng.

Facebook: bài #1 đăng 11:30, bài #2 đăng 19:45 ICT bằng `scheduled_publish_time`
native của Meta (Meta tự đăng đúng giờ). Instagram do `article-publish-ig` đăng.

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

`src/pipeline/`: `topics → write → images` (đường dựng bản nháp hiện tại;
`collect → score` vẫn còn nhưng đã tách khỏi đường này), cộng `llm`
(Claude CLI → Gemini fallback), `telegram`, `meta`, `daily_state`, `state`,
`models`. Ba entrypoint:
- `article_run --slot <morning|evening>` — dựng bản nháp cho slot, gửi preview.
- `article_approve` — xử lý callback nút Telegram (Đăng ngay / Lên lịch / Bỏ).
- `article_publish_ig` — đăng carousel Instagram khi tới giờ slot đã lên lịch.

State: `data/daily/<YYYY-MM-DD>.json`, một file mỗi ngày, hai slot
`morning`/`evening`, status một chiều `draft → scheduled | posted | discarded |
expired`. `data/seen.json` chống trùng tin. Tất cả commit ngược repo.

Escape hatch quota Gemini: `config/settings.yaml` → `images.provider: legacy`
để bỏ qua Gemini, dựng ảnh bằng đường `media` cũ.

Spec và plan đầy đủ: `docs/superpowers/`.  
  
