# AI Social Automation — Giai đoạn 1 (Spec thiết kế)

**Ngày:** 2026-09-03
**Trạng thái:** Đã duyệt thiết kế, chờ viết plan
**Chủ sở hữu:** ahitofficial (kênh "A Hít Official")

---

## 1. Mục tiêu

Xây một pipeline **tự động hoàn toàn** (chạy trên GitHub Actions, miễn phí) làm việc sau mỗi ngày:

1. Thu thập bài viết/tin về AI đang viral từ web chính thống + cộng đồng + Facebook.
2. Phân tích, chấm điểm, chọn ra **1 tin nóng nhất**.
3. Dùng LLM viết **bài đăng tiếng Việt** cho Facebook + Instagram (caption, hashtag), kèm nội dung soạn sẵn cho YouTube + TikTok.
4. Tạo **3–4 ảnh**: thumbnail AI + chữ tiếng Việt, ảnh từ bài gốc, screenshot trang nguồn, ảnh AI free.
5. Gửi **preview qua Telegram** để duyệt (1–2 tuần đầu), sau đó chuyển sang đăng thẳng.
6. **Tự đăng** lên Facebook Page + Instagram; ghi file nội dung YouTube/TikTok cho giai đoạn 2.

**Ngoài phạm vi giai đoạn 1:** dựng video, cắt ghép, thêm nhạc, clone giọng, đăng video YouTube/TikTok. Đó là spec riêng cho giai đoạn 2.

---

## 2. Bối cảnh & ràng buộc

| Ràng buộc | Quyết định |
|---|---|
| Chi phí | Bằng 0. Mọi dịch vụ dùng bậc miễn phí. |
| Nơi chạy | GitHub Actions, repo **private**, cron. Không có VM luôn bật. Mỗi job ≤ 6 giờ. |
| Ngôn ngữ output | 100% tiếng Việt (caption, hashtag, chữ trên thumbnail). |
| Kênh | Mới tạo, gần như chưa có nội dung → giọng văn khởi đầu bằng config mặc định. |
| Nền tảng đăng (GĐ1) | Facebook Page + Instagram Business (đăng tự động qua Graph API). |
| YouTube/TikTok (GĐ1) | Không có API đăng text/community → chỉ ghi file nội dung soạn sẵn. |
| Nguồn Facebook đầu vào | Không có API đọc page người khác. Dùng RSS-bridge miễn phí (best-effort) + fallback dán link tay. |
| LLM | Ưu tiên Claude qua OAuth token gói Pro (`CLAUDE_CODE_OAUTH_TOKEN`); fallback Gemini free. |
| Duyệt bài | `APPROVAL_MODE=telegram` lúc đầu → `auto` sau 1–2 tuần (chỉ đổi config). |
| Tần suất | 1 bài/ngày lúc 08:00 ICT. Có thể tăng lên 3–4 lần/ngày qua config. |

### Tài khoản người dùng đã có
- Facebook Page: `https://www.facebook.com/profile.php?id=61585365795062`
- YouTube: `https://www.youtube.com/@ahitofficials`
- TikTok: `https://www.tiktok.com/@ahitofficial`
- Instagram: `https://www.instagram.com/ahitofficial` (cần chuyển sang Business/Creator + liên kết Page)
- Tài khoản Meta for Developers (để tạo app lấy token).

---

## 3. Cách tiếp cận đã chọn

**Gói Python module hoá** (Approach B). Chia pipeline thành 6 tầng độc lập, mỗi tầng là một module có interface rõ ràng, test riêng được. Một thin runner ghép các tầng. State lưu trong file JSON commit ngược về repo. Không dùng database, không dùng n8n.

Lý do: dễ test, dễ sửa từng phần mà không vỡ phần khác, hợp với ràng buộc "free + đơn giản".

---

## 4. Kiến trúc

### 4.1 Cây thư mục repo

```
ai-social-automation/            (repo private trên GitHub)
├── .github/workflows/
│   ├── build.yml                # cron 08:00 ICT — chạy pipeline dựng bài
│   ├── approve.yml              # cron mỗi 10 phút — đọc nút Telegram, đăng bài đã duyệt
│   └── refresh-token.yml        # cron mùng 1 hàng tháng — gia hạn token Meta
│
├── src/pipeline/
│   ├── __init__.py
│   ├── run.py                   # runner: gọi collect→score→write→media→review
│   ├── collect.py              # thu thập ứng viên từ mọi nguồn
│   ├── score.py               # chấm điểm viral, chọn 1 tin
│   ├── write.py               # LLM sinh caption + text các nền tảng
│   ├── media.py               # tạo 3–4 ảnh
│   ├── review.py              # đóng gói pending + gửi Telegram
│   ├── publish.py             # đăng FB + IG, ghi file YT/TikTok
│   ├── llm.py                 # abstraction: ClaudeBackend / GeminiBackend
│   ├── telegram.py            # wrapper Telegram Bot API
│   ├── meta.py                # wrapper Facebook/Instagram Graph API
│   └── state.py               # đọc/ghi data/*.json, khử trùng
│
├── config/
│   ├── sources.yaml            # RSS feeds, subreddits, facebook pages
│   ├── voice.yaml             # hồ sơ giọng văn tiếng Việt
│   ├── settings.yaml          # APPROVAL_MODE, posts_per_day, run_hour, ngưỡng điểm
│   └── facebook_urls.txt       # fallback: link bài FB dán tay (1 URL/dòng)
│
├── assets/fonts/
│   └── BeVietnamPro-Bold.ttf   # font có dấu tiếng Việt cho thumbnail
│
├── data/                       # state, commit ngược về repo
│   ├── seen.json              # {url_hash: iso_date} — chống xử lý trùng
│   ├── pending/<id>.json       # bài chờ duyệt (kèm đường dẫn ảnh)
│   └── posted/<id>.json        # lịch sử đã đăng + kết quả từng nền tảng
│
├── output/<YYYY-MM-DD>/<id>/    # sản phẩm mỗi bài
│   ├── caption_fb.txt
│   ├── caption_ig.txt
│   ├── youtube.txt            # tiêu đề + mô tả + hashtag
│   ├── tiktok.txt
│   ├── meta.json             # toàn bộ dữ liệu bài
│   └── img/01_thumbnail.jpg … 04_*.jpg
│
├── tests/
│   ├── fixtures/               # rss mẫu, html bài mẫu, response LLM mẫu
│   ├── test_collect.py
│   ├── test_score.py
│   ├── test_write.py
│   ├── test_media.py
│   └── test_publish.py         # dry-run, không gọi API thật
│
├── requirements.txt
├── README.md                   # hướng dẫn setup secrets + bật workflow
└── .gitignore
```

### 4.2 Ba workflow

**`build.yml`** — `schedule: cron` (08:00 ICT = 01:00 UTC), cho phép `workflow_dispatch` để chạy tay.
Các bước:
1. `checkout` (fetch full để commit ngược).
2. `setup-python` 3.12, `pip install -r requirements.txt`, `playwright install --with-deps chromium`.
3. `python -m pipeline.run` → thực hiện collect→score→write→media→review.
4. Nếu `APPROVAL_MODE=auto`: `run.py` gọi luôn `publish.py`.
5. `git add data/ output/ && git commit && git pull --rebase && git push` (retry 3 lần nếu xung đột).
Permissions: `contents: write`.
Concurrency group `build` để không chạy chồng.

**`approve.yml`** — `schedule: cron '*/10 * * * *'` (mỗi 10 phút). Chỉ hoạt động khi `APPROVAL_MODE=telegram`.
Các bước:
1. `checkout`.
2. `python -m pipeline.approve_poll`:
   - Gọi Telegram `getUpdates` với `offset` lưu trong `data/telegram_offset.json`.
   - Với mỗi `callback_query` dạng `approve:<id>` / `edit:<id>` / `reject:<id>`:
     - `approve` → load `data/pending/<id>.json`, gọi `publish.py`, chuyển sang `data/posted/`, trả lời Telegram "Đã đăng ✅ + link".
     - `edit` → gửi kèm `output/.../meta.json` + ảnh dưới dạng file, giữ pending (người dùng sửa tay rồi bấm approve lại, hoặc chỉnh trong repo).
     - `reject` → xoá pending, trả lời "Đã bỏ ❌".
   - Pending quá 12h (so `created_at`) mà chưa xử lý → xoá, báo Telegram "Hết hạn, đã bỏ".
3. Commit `data/` nếu có thay đổi.
Concurrency group `approve`.

**`refresh-token.yml`** — `schedule: cron '0 2 1 * *'` (mùng 1 hàng tháng).
Gọi Graph API đổi `META_PAGE_TOKEN` hiện tại lấy token long-lived mới, in ra **giá trị mới** vào log job (masked) và gửi Telegram nhắc người dùng cập nhật lại secret. (GitHub Actions không tự ghi được secret của chính nó → cần bước thủ công cập nhật; workflow chỉ tạo token mới + nhắc.)
> Ghi chú: nếu sau này muốn tự động hẳn, chuyển token store sang một Gist private và đọc từ đó. Giai đoạn 1 giữ đơn giản: nhắc thủ công mỗi tháng.

---

## 5. Thiết kế từng tầng

### 5.1 `collect.py`

**Input:** `config/sources.yaml`, `config/facebook_urls.txt`, `data/seen.json`
**Output:** `list[Candidate]` — đã lọc bỏ URL từng xử lý.

```python
@dataclass
class Candidate:
    url: str
    title: str
    source: str          # "rss:openai" | "hn" | "reddit:LocalLLaMA" | "facebook:<page>" | "manual"
    published_at: datetime
    raw_score_hint: float # điểm HN/upvote nếu có, else 0
    summary: str          # tóm tắt ngắn từ feed
    full_text: str        # nội dung bài đã trích (rỗng nếu chưa lấy được)
    top_image: str | None # og:image hoặc ảnh đầu bài
```

Nguồn:
- **RSS** (`feedparser`): danh sách trong `sources.yaml` — blog OpenAI, Anthropic, Google DeepMind, Meta AI, TechCrunch (tag AI), The Verge (AI), VentureBeat, MIT Technology Review, Ars Technica. Lọc bài trong 48h.
- **Hacker News** (Algolia API `http://hn.algolia.com/api/v1/search_by_date?tags=story&query=AI`): lọc `points >= 50`, 48h.
- **Reddit** (JSON công khai `https://www.reddit.com/r/<sub>/top.json?t=day`, User-Agent tuỳ chỉnh): `r/artificial`, `r/LocalLLaMA`, `r/OpenAI`, `r/singularity`. Lọc `ups >= 100`. Nếu Reddit trả 429 → bỏ qua, log cảnh báo.
- **Facebook**: với mỗi page trong `sources.yaml.facebook_pages`, gọi RSS-bridge (`RSSHUB_BASE` env, mặc định instance công khai; route `/facebook/page/<id>`), parse như RSS. Lỗi/timeout → bỏ qua. Sau đó đọc `config/facebook_urls.txt`, mỗi URL trích bằng `trafilatura` → Candidate `source="manual"`.
- **Trích nội dung bài**: với các Candidate lọt vòng score, `write.py` mới cần `full_text` đầy đủ → `collect.py` chỉ trích full text cho top ~5 ứng viên (tiết kiệm thời gian) bằng `trafilatura.fetch_url` + `extract`.

Khử trùng: `hash = sha1(normalized_url)`. Bỏ Candidate nếu hash có trong `seen.json`.
**Quy tắc ghi `seen.json`:** ghi hash của **mọi Candidate đã đọc** ngay trong lần chạy này (không chỉ tin được chọn). Đánh đổi: một tin hôm nay trượt ngưỡng sẽ không được xét lại ngày mai, nhưng tránh được vòng lặp xử lý đi xử lý lại cùng một tin. Chấp nhận được ở giai đoạn 1.

**Lỗi:** mỗi nguồn bọc `try/except`, lỗi → `log.warning`, tiếp nguồn khác. Nếu **tất cả** nguồn fail → raise `CollectError` (job dừng, báo Telegram).

### 5.2 `score.py`

**Input:** `list[Candidate]`, `config/settings.yaml`
**Output:** `Candidate` được chọn, hoặc `None`.

Công thức điểm (0–100):
- `recency`: 40 điểm, giảm tuyến tính theo giờ (0h → 40, 48h → 0).
- `popularity`: 30 điểm, log-scale theo `raw_score_hint` (HN points / Reddit ups).
- `cross_source`: 20 điểm nếu cùng chủ đề xuất hiện ≥ 2 nguồn (so khớp bằng fuzzy title / trùng domain bài gốc).
- `keyword_fit`: 10 điểm theo mật độ từ khoá AI (`AI, LLM, GPT, model, mô hình, OpenAI, Anthropic, Gemini, agent, ...`).

Chọn Candidate điểm cao nhất. Nếu `max_score < settings.min_score` (mặc định 45) → trả `None`; runner báo Telegram "Hôm nay không có tin đủ nóng" và kết thúc sạch (exit 0).

### 5.3 `write.py`

**Input:** `Candidate` được chọn, `config/voice.yaml`
**Output:** `PostContent`

```python
@dataclass
class PostContent:
    angle: str            # "tin-tuc" | "ung-dung-mmo" | "phan-tich" | "giat-gan"
    caption_fb: str       # 150–400 từ, có xuống dòng, CTA, nguồn ở cuối
    caption_ig: str       # 80–150 từ, cô đọng hơn
    hashtags: list[str]   # 8–15 hashtag tiếng Việt + tiếng Anh phổ biến
    thumbnail_prompt: str # prompt tiếng Anh cho model ảnh (KHÔNG chứa chữ)
    thumbnail_title: str  # 4–10 từ tiếng Việt, in lên thumbnail
    youtube_title: str
    youtube_desc: str
    tiktok_caption: str
    source_url: str
    source_name: str
```

`llm.py` cung cấp `generate(system: str, user: str) -> str` (kỳ vọng trả JSON). Backend:
- **ClaudeBackend**: shell `claude -p --output-format json --model claude-sonnet-4-x` với env `CLAUDE_CODE_OAUTH_TOKEN`. Parse `result`.
- **GeminiBackend**: `google-genai`, model `gemini-2.0-flash`, `response_mime_type=application/json`.
- `llm.generate` thử Claude trước; bắt lỗi (exit code ≠ 0, token bị từ chối, timeout 90s) → tự chuyển Gemini. Cả hai fail → `LLMError`.

Prompt nhồi: `voice.yaml` (cách xưng hô "mình/bạn", độ dài câu, mức emoji, 2–3 câu mở bài mẫu, điều cấm kỵ), toàn văn bài gốc (cắt ≤ 6000 token), yêu cầu **tự chọn `angle`** theo loại tin, luôn ghi nguồn cuối `caption_fb`, không bịa số liệu, không dịch máy cứng.

`voice.yaml` khởi đầu (mặc định):
```yaml
xung_ho: { nguoi_noi: "mình", nguoi_nghe: "bạn" }
giong: "thân thiện, dễ hiểu, có chút hài, không hàn lâm"
do_dai_cau: "ngắn–vừa, tránh câu lê thê"
emoji: "vừa phải, 2–5 cái mỗi bài, không lạm dụng"
mo_bai_mau:
  - "Có tin này hay nè:"
  - "AI tuần này lại có biến:"
  - "Nghe thử cái này xem:"
cam_ky:
  - "không giật tít sai sự thật"
  - "không hứa hẹn kiếm tiền phi thực tế"
  - "không dùng từ ngữ tiêu cực/chê bai cá nhân"
cta_mau:
  - "Bạn nghĩ sao? Comment cho mình biết nhé."
  - "Lưu lại để dùng dần nha."
```

### 5.4 `media.py`

**Input:** `Candidate`, `PostContent`, thư mục `output/<date>/<id>/img/`
**Output:** `list[str]` đường dẫn ảnh (3–4 file), ảnh `01` luôn là thumbnail.

1. **Thumbnail** (`01_thumbnail.jpg`, 1200×630):
   - Nền: `GET https://image.pollinations.ai/prompt/<url-encoded thumbnail_prompt>?width=1200&height=630&nologo=true`. Timeout 60s, retry 2. Lỗi → nền gradient tạo bằng Pillow.
   - Phủ lớp tối 35% để chữ nổi.
   - Ghi `thumbnail_title` bằng Pillow: font `BeVietnamPro-Bold`, tự wrap, canh giữa-dưới, có stroke (viền) 3px màu tương phản. Thêm dải nhỏ ghi tên kênh "A Hít Official" góc dưới.
2. **Ảnh bài gốc** (`02_source.jpg`): tải `Candidate.top_image`. Bỏ nếu < 500px cạnh dài hoặc tải lỗi.
3. **Screenshot trang nguồn** (`03_screenshot.jpg`): Playwright Chromium, `viewport 1280×800`, mở `Candidate.url`, chờ `networkidle` (timeout 30s), chụp `full_page=False` phần đầu. Cắt còn 1280×720.
4. **Ảnh AI phụ** (`04_ai.jpg`): Pollinations với prompt = `thumbnail_prompt + ", alternate composition, editorial illustration"`.

Sau khi gom: loại file trùng (hash), loại < 500px. Nếu còn < 3 → vẫn tiếp tục, đánh dấu `low_media=true` trong pending để preview cảnh báo. Luôn giữ tối đa 4.

### 5.5 `review.py`

**Input:** `PostContent`, danh sách ảnh, `id`
**Output:** `data/pending/<id>.json`

```json
{
  "id": "2026-09-03-openai-xyz",
  "created_at": "2026-09-03T01:05:00Z",
  "angle": "tin-tuc",
  "caption_fb": "...",
  "caption_ig": "...",
  "hashtags": ["#AI", "..."],
  "images": ["output/2026-09-03/<id>/img/01_thumbnail.jpg", "..."],
  "youtube": {"title": "...", "desc": "..."},
  "tiktok": {"caption": "..."},
  "source": {"url": "...", "name": "OpenAI Blog"},
  "low_media": false
}
```

Nếu `APPROVAL_MODE=telegram`:
- `sendMediaGroup` 3–4 ảnh.
- `sendMessage`: caption_fb (rút gọn ≤ 900 ký tự cho preview) + cảnh báo `low_media` nếu có + inline keyboard:
  `[✅ Đăng](approve:<id>)  [✏️ Sửa](edit:<id>)  [❌ Bỏ](reject:<id>)`

Nếu `APPROVAL_MODE=auto`: runner gọi thẳng `publish.publish(pending)`.

### 5.6 `publish.py`

**Input:** `pending` dict
**Output:** `data/posted/<id>.json` + ghi `output/<date>/<id>/{youtube,tiktok}.txt`

- **Facebook Page** (`meta.py`):
  1. Với mỗi ảnh: `POST /{PAGE_ID}/photos` body `{source: <file>, published: false}` → thu `media_fbid`.
  2. `POST /{PAGE_ID}/feed` body `{message: caption_fb + "\n\n" + hashtags, attached_media: [{media_fbid}, ...]}` → thu `post_id`.
- **Instagram** (`meta.py`, cần `IG_BUSINESS_ID`):
  1. Ảnh phải có URL công khai → upload ảnh lên **GitHub raw** của chính repo (đã commit trong `output/`) và dùng link `raw.githubusercontent.com`. (Repo private → raw cần token; **thay bằng**: upload ảnh lên [0x0.st](https://0x0.st) hoặc `tmpfiles.org` free, lấy URL tạm 1h — đủ để IG fetch.) → quyết định: dùng `tmpfiles.org`.
  2. Mỗi ảnh: `POST /{IG_ID}/media` `{image_url, is_carousel_item: true}` → `creation_id`.
  3. `POST /{IG_ID}/media` `{media_type: CAROUSEL, children: [ids], caption: caption_ig + hashtags}` → `carousel_id`.
  4. `POST /{IG_ID}/media_publish` `{creation_id: carousel_id}`.
- **YouTube/TikTok**: ghi `youtube.txt` (title + desc + hashtag) và `tiktok.txt` (caption). Không gọi API.
- Ghi `posted/<id>.json`:
  ```json
  {"id": "...", "posted_at": "...", "facebook": {"ok": true, "post_id": "...", "url": "..."},
   "instagram": {"ok": false, "error": "..."}, "youtube_file": "output/.../youtube.txt"}
  ```
- FB ok nhưng IG fail (hoặc ngược lại) → không raise; ghi rõ, `review`/`approve` báo Telegram phần fail để đăng tay.
- Ghi `seen.json` cho URL tin đã đăng.

### 5.7 `llm.py`, `telegram.py`, `meta.py`, `state.py`

- `llm.py`: như 5.3. Config `LLM_PROVIDER=claude|gemini|auto` (mặc định `auto`).
- `telegram.py`: `send_message`, `send_media_group`, `send_document`, `get_updates(offset)`, `answer_callback`. Dùng `httpx`, token từ env.
- `meta.py`: `fb_upload_photo`, `fb_create_post`, `ig_create_item`, `ig_create_carousel`, `ig_publish`, `debug_token`, `exchange_long_lived_token`. Base `https://graph.facebook.com/v21.0`.
- `state.py`: `load_seen/save_seen`, `add_pending/load_pending/list_pending/remove_pending`, `save_posted`, `load_offset/save_offset`. Tất cả là file JSON trong `data/`, có khoá ghi bằng `os.replace` (atomic).

---

## 6. Secrets (GitHub Actions → Settings → Secrets)

| Tên | Dùng để | Lấy ở đâu |
|---|---|---|
| `META_PAGE_ID` | ID Facebook Page | Graph API Explorer |
| `META_PAGE_TOKEN` | Token long-lived đăng FB + IG | Graph API Explorer → exchange long-lived |
| `IG_BUSINESS_ID` | ID tài khoản IG Business | `GET /{PAGE_ID}?fields=instagram_business_account` |
| `TELEGRAM_BOT_TOKEN` | Bot gửi preview + nhận nút | @BotFather |
| `TELEGRAM_CHAT_ID` | Chat cá nhân của bạn | `getUpdates` sau khi nhắn bot |
| `CLAUDE_CODE_OAUTH_TOKEN` | LLM Claude (gói Pro) | `claude setup-token` (máy local) |
| `GEMINI_API_KEY` | LLM fallback | aistudio.google.com |
| `RSSHUB_BASE` *(tuỳ chọn)* | Instance RSSHub cho Facebook | mặc định instance công khai |

Không có secret nào nằm trong code hay commit. `.gitignore` chặn `.env`.

---

## 7. Xử lý lỗi (tổng hợp)

| Tình huống | Hành vi |
|---|---|
| 1 nguồn thu thập lỗi | Log cảnh báo, bỏ nguồn đó, chạy tiếp |
| Tất cả nguồn lỗi | `CollectError` → báo Telegram → job fail |
| Không tin nào đạt `min_score` | Báo Telegram "không có tin nóng" → exit 0 |
| Claude LLM lỗi/từ chối token | Tự chuyển Gemini |
| Cả Claude + Gemini lỗi | `LLMError` → báo Telegram → job fail |
| Pollinations lỗi | Thumbnail dùng nền gradient Pillow; ảnh phụ bỏ qua |
| Screenshot Playwright timeout | Bỏ ảnh screenshot |
| Còn < 3 ảnh | Vẫn đăng, `low_media=true`, preview cảnh báo |
| FB ok, IG fail | Ghi `posted` rõ ràng, báo Telegram phần fail |
| Xung đột git khi push state | `git pull --rebase` + retry ×3 |
| Token Meta sắp hết hạn | `refresh-token.yml` tạo token mới + nhắc Telegram cập nhật secret |
| Pending quá 12h chưa duyệt | Xoá, báo Telegram "hết hạn" |

---

## 8. Test

- **Framework:** `pytest`.
- **Fixtures cố định** trong `tests/fixtures/`: `sample_feed.xml`, `sample_article.html`, `sample_hn.json`, `sample_reddit.json`, `sample_llm_response.json`, 1 ảnh nền nhỏ.
- `test_collect.py`: parse feed/HN/Reddit mẫu → đúng số Candidate, đúng khử trùng theo `seen.json` giả.
- `test_score.py`: bộ Candidate cố định → tin điểm cao đúng như kỳ vọng; dưới ngưỡng → `None`.
- `test_write.py`: mock `llm.generate` trả `sample_llm_response.json` → `PostContent` parse đủ field, `angle` hợp lệ.
- `test_media.py`: mock HTTP Pollinations + Playwright → tạo đúng số file, thumbnail có kích thước 1200×630, chữ tiếng Việt render không lỗi font.
- `test_publish.py`: `meta.py` và `telegram.py` bị monkeypatch → **dry-run**, kiểm tra payload gọi API đúng cấu trúc, `posted.json` ghi đúng. Không chạm mạng.
- **Lệnh chạy thử toàn luồng offline:**
  `python -m pipeline.run --dry-run --local`
  → collect thật (hoặc từ fixture nếu `--local`), score, write (gọi LLM thật nếu có key, else fixture), media thật, **không** gửi Telegram, **không** đăng; xuất hết ra `output/`. Để bạn xem chất lượng trước khi bật cron.

---

## 9. Bảo mật & pháp lý

- Ảnh từ bài gốc và screenshot: pipeline **luôn ghi rõ nguồn + link** trong caption. Người dùng chịu trách nhiệm cuối cùng về việc đăng lại nội dung của bên thứ ba.
- Không scrape Facebook bằng tài khoản đăng nhập (tránh rủi ro khoá tài khoản). Chỉ dùng RSS-bridge công khai + link dán tay.
- Token và key chỉ nằm trong GitHub Secrets. Log job không in token (dùng masking).
- Repo để **private**.

---

## 10. Giới hạn đã biết

- Nguồn Facebook đầu vào là **best-effort**, có thể ngừng hoạt động bất kỳ lúc nào → luôn có fallback `facebook_urls.txt`.
- OAuth token gói Pro $20 **có thể không được Anthropic cho dùng ngoài app** → khi đó tự động rơi về Gemini free (không gián đoạn, nhưng chất lượng chữ khác đi).
- IG chỉ đăng được ảnh có URL công khai → phải mượn host ảnh tạm (`tmpfiles.org`). Nếu dịch vụ này chết, cần đổi sang host khác.
- `refresh-token.yml` không tự cập nhật secret của chính repo → cần bạn dán token mới mỗi tháng (10 giây).
- GitHub Actions cron có thể trễ 5–15 phút vào giờ cao điểm — chấp nhận được với 1 bài/ngày.
- Mỗi job ≤ 6 giờ (pipeline thực tế chạy ~3–5 phút) — không phải vấn đề.

---

## 11. Giai đoạn 2 (chỉ ghi nhận, không làm bây giờ)

Video: nhận video người dùng cung cấp + nghiên cứu thêm video liên quan → cắt ghép → thêm nhạc nền → nhận audio người dùng thu → clone giọng (F5-TTS / GPT-SoVITS / XTTS-v2 mã nguồn mở, chạy trên Colab free hoặc HF Space vì cần GPU) → xuất video hoàn chỉnh → đăng YouTube (Data API) + TikTok (Content Posting API) + FB/IG Reels. Sẽ có spec riêng.

---

## 12. Định nghĩa "hoàn thành" cho giai đoạn 1

- [ ] 3 workflow chạy được trên GitHub Actions.
- [ ] `python -m pipeline.run --dry-run --local` xuất ra 1 bài mẫu đầy đủ caption + 3–4 ảnh.
- [ ] Chạy thật: nhận preview Telegram, bấm ✅ → bài lên Facebook Page + Instagram đúng như preview.
- [ ] `youtube.txt` + `tiktok.txt` được tạo đúng.
- [ ] State (`seen.json`, `posted/`) commit ngược repo, không xử lý trùng tin.
- [ ] Đổi `APPROVAL_MODE=auto` → bài tự lên không cần bấm.
- [ ] Toàn bộ pytest xanh.
- [ ] README đủ để người dùng tự set secrets và bật workflow.
