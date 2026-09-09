# AI Social Automation — Phase 1

Tự động mỗi ngày: chọn một chủ đề AI/năng suất từ ngân hàng chủ đề
(`config/topics.yaml`) tránh trùng lịch sử → viết bài tiếng Việt từ kiến thức
model → tạo 5 ảnh slide → lập lịch đăng Facebook + Instagram. Chạy miễn phí
trên GitHub Actions.

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

## Luồng bài viết

- `article-morning` (07:00 ICT) và `article-evening` (17:00 ICT) dựng bản nháp
  rồi tự động lập lịch: Facebook đăng lúc 11:30 / 19:45 ICT (native
  `scheduled_publish_time`), Instagram chuẩn bị sẵn.
- Telegram gửi thông báo `🗓 Đã lên lịch` với nút `🗑 Gỡ bài` (xóa cả bài
  Facebook + media Instagram nếu bấm trước giờ slot, hoặc trong vòng 15 phút
  sau đó).
- Khi lập lịch thất bại: bài ở trạng thái `draft`, `article-approve` thử lại
  mỗi 5 phút cho tới giờ slot, rồi đánh dấu `expired` với cảnh báo.

## Luồng video (Phase 2B)

- `article_run.draft` (07:00 / 17:00 ICT), sau khi lên lịch bài viết, sinh **kịch bản
  video** + tiêu đề/mô tả/hashtag/từ khoá cho cùng câu chuyện, gửi kịch bản lên Telegram.
- Bạn thu âm đọc kịch bản, gửi file audio vào bot (bất cứ lúc nào). `article-approve`
  chỉ ghi nhận "đã nhận audio" (`video.status = "audio_received"`) rồi thoát ngay.
- Workflow riêng `video-render` (cron mỗi 10 phút, KHÔNG nằm trong poller bài viết) quét
  slot có audio → dựng lại project Remotion từ `video.script` trong state → căn giờ
  (`align.mjs`) → `npx remotion render CodexShort` → gửi MP4 lên Telegram →
  `video.status = "rendered"` + nút `🗑 Gỡ`. Render lỗi → slot quay lại `awaiting_audio`,
  gửi lại audio để thử.
- Nền video cố định: `video/public/bg.mp4` (đặt một lần).
- Tắt cả nhánh video: `config/settings.yaml` → `video.enabled: false`.

## Đăng video (Phase 2C)

- Sau khi render, `video-render` cũng chạy `publish_pending`: đưa MP4 lên một
  GitHub Release ẩn (`video-assets`) lấy URL công khai, rồi đăng lần lượt YouTube
  Shorts → FB Reel → IG Reel → TikTok (nháp). Bật từng nền tảng ở
  `config/settings.yaml` → `video.publish.<platform>: true`.
- Đăng xong đủ các nền tảng đang bật → `video.status = "published"`, xoá asset,
  Telegram gửi tổng kết + nút `🗑 Gỡ tất cả` (60 phút, xoá YT/FB/IG; TikTok tự xoá
  nháp trong app).
- Lỗi một nền tảng → thử lại tick sau, tối đa 5 lần rồi bỏ cuộc + cảnh báo.
- Secrets: `YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN` (chạy
  `python scripts/mint_youtube_token.py` một lần để lấy); FB/IG Reel dùng lại
  `META_PAGE_TOKEN`.
- TikTok: đăng vào hộp nháp (app chưa audit). Secrets `TIKTOK_CLIENT_KEY/SECRET/
  REFRESH_TOKEN` + `GH_PAT` (fine-grained PAT repo này, quyền Secrets: read/write —
  để workflow tự ghi lại refresh token TikTok mỗi lần xoay vòng). Không có `GH_PAT`
  thì bot Telegram token mới cho bạn dán tay.

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
  auto-lập lịch đăng 11:30 ICT.
- `article-evening`: 17:00 ICT (`cron '0 10 * * *'`) → như trên cho bài #2
  (tránh trùng chủ đề bài sáng) → auto-lập lịch đăng 19:45 ICT.
- `article-approve`: mỗi 5 phút (`cron '*/5 * * * *'`) → thử lại bài ở trạng
  thái `draft`, đánh dấu slot `expired` nếu quá giờ.
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

## Phase 2A — video (kịch bản + timeline)

Bật `config/settings.yaml` → `video.enabled: true`. Audio là do bạn tự thu và gửi
qua Telegram (xem "Luồng video (Phase 2B)" ở trên) — không còn TTS/clone giọng.

Thử offline (không cần audio thật):

    python -m pipeline.video.build_video --fake-llm --voice tests/fixtures/video/voice_fixture.wav --story tests/fixtures/video/story.json

Sau khi chạy build_video ở máy local, hoàn nguyên file sinh ra: `git checkout -- video/tools video/src/timeline.json video/public/voice.mp3`.

## Kiến trúc

`src/pipeline/`: `topics → write → images` (đường dựng bản nháp hiện tại;
`collect → score` vẫn còn nhưng đã tách khỏi đường này), cộng `llm`
(Claude CLI → Gemini fallback), `telegram`, `meta`, `daily_state`, `state`,
`models`. Ba entrypoint:
- `article_run --slot <morning|evening>` — dựng bản nháp cho slot, xem trước carousel qua Telegram rồi tự lập lịch đăng.
- `article_approve` — thử lại bài ở trạng thái `draft`, xử lý nút `Gỡ bài`.
- `article_publish_ig` — đăng carousel Instagram khi tới giờ slot đã lên lịch.

State: `data/daily/<YYYY-MM-DD>.json`, một file mỗi ngày, hai slot
`morning`/`evening`, status một chiều `draft → scheduled | posted | discarded |
expired`. `data/seen.json` chống trùng tin. Tất cả commit ngược repo.

Escape hatch quota Gemini: `config/settings.yaml` → `images.provider: legacy`
để bỏ qua Gemini, dựng ảnh bằng đường `media` cũ.

Spec và plan đầy đủ: `docs/superpowers/`.  
  
