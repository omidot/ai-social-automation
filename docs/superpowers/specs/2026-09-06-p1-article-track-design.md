# P1 — Article track (2 posts/day, scheduled + approved)

Status: design approved 2026-09-06. Part of the multi-phase "daily autonomous social pipeline"
vision (see bottom). Depends on Meta secrets being set — see Blockers.

## Goal

Every day, publish **two** Vietnamese AI-news posts to the "A Hít Official" Facebook Page
and Instagram: post #1 at **11:30 ICT**, post #2 at **19:45 ICT**. Each post is gathered
and drafted automatically, previewed to the user on Telegram, and only published after the
user taps an approval button. Nothing goes live without a human tap.

This phase is **articles only**. Video (script → audio → render → multi-platform publish)
is P2/P3 and is out of scope here. Audience-engagement-driven topic ranking is P4.

## North-star daily schedule (for context; only the article rows are P1)

| ICT | What | Channel | Phase |
|-----|------|---------|-------|
| ~07:00 | Gather latest AI news, pick article #1 | — | **P1** |
| ~09:00 | Send video #1 script + hook to Telegram | Telegram | P2 |
| after user sends audio #1 | Render video #1 → Telegram → approve | Telegram | P2 |
| **11:30** | Publish **article #1** | FB Page + IG | **P1** |
| 11:45 | Publish video #1 | FB Reel + YouTube + TikTok + IG | P3 |
| ~15:00 | Send video #2 script + hook to Telegram | Telegram | P2 |
| after user sends audio #2 | Render video #2 → Telegram → approve | Telegram | P2 |
| ~17:00 | Gather news, pick article #2 | — | **P1** |
| **19:45** | Publish **article #2** (+ video #2) | FB Page + IG | **P1** |

## Blockers (user action, outside this spec)

1. **Meta secrets not set** on GitHub (`META_PAGE_ID`, `META_PAGE_TOKEN`, `IG_BUSINESS_ID`,
   `META_APP_ID`, `META_APP_SECRET`). Nothing publishes until these exist. Code and tests
   can be built and merged before then; live runs will fail at the publish step with a
   clear Telegram error until the secrets land.
2. `GEMINI_API_KEY` is set and working. Gemini **image generation** quota is unverified —
   the design has a fallback (see Content generation).

## Architecture

Four GitHub Actions workflows plus changes to the `pipeline` package. All cron times are
UTC; ICT = UTC+7, no DST.

### Workflows

| Workflow | Cron (UTC) | ICT | Job |
|----------|-----------|-----|-----|
| `article-morning.yml` | `0 0 * * *` | 07:00 | Gather → pick #1 → draft text + images → commit images → write state → send Telegram preview |
| `article-evening.yml` | `0 10 * * *` | 17:00 | Gather (fresh) → pick #2 (exclude #1's topic) → draft → preview |
| `article-approve.yml` | `*/10 * * * *` | every 10 min | Poll Telegram `getUpdates`, handle `[Đăng ngay] / [Lên lịch] / [Bỏ]` callbacks |
| `article-publish-ig.yml` | `0,15,30,45 4,5,12,13 * * *` | ≈11:00–13:00 & 19:00–21:00 ICT, every 15 min | For any post that is `scheduled` and whose `ig_due` has passed, publish the IG carousel |

GitHub cron can fire 5–20 min late. Consequences:
- Morning/evening drafts: a few minutes' slack is fine — preview just arrives a bit later.
- FB publish at the slot: exact, because FB does it natively via `scheduled_publish_time`.
- IG publish: up to ~15 min late (poll interval + cron jitter). Accepted.

`article-approve.yml` and `article-publish-ig.yml` both need Meta + Telegram secrets;
they must NOT install the heavy `requirements-video.txt` (keep them cheap — they run often).

### Existing workflows

`build.yml` (the current single-story pipeline) is **replaced** by `article-morning.yml`
+ `article-evening.yml`. Delete `build.yml` and its `run.py` `build()` publish path, or
leave `build.yml` disabled — decide in the plan. `approve.yml` (10-min Telegram poll for
the old approval flow) is **replaced** by `article-approve.yml`. `refresh-token.yml`
stays as-is. `video-smoke.yml` stays as-is.

## Module design

New/changed modules under `src/pipeline/`:

### `sources.py` (change)
- Add a **Google News RSS** source: `https://news.google.com/rss/search?q=<query>&hl=<lang>`
  for `q` in an AI keyword set, `hl` in `en-US` and `vi`. Parsed like any other RSS feed.
- Keep existing tech-press RSS + Hacker News. Reddit stays configured but is known-blocked
  from GitHub IPs (non-fatal).

### `collect.py` (change)
- After fetching all candidates, **deduplicate near-identical stories**: group by
  normalized title similarity + shared URL host + shared entities; each group collapses to
  one `Candidate` carrying `source_count` = number of distinct feeds that carried it.
- `source_count` becomes a ranking signal ("many outlets → viral").

### `score.py` (change)
- `pick_n(candidates, n, exclude_topics, settings, now, keywords) -> list[ScoredCandidate]`
  returns up to `n` candidates, each a **distinct topic**, above `min_score`.
- Score = recency + keyword match + source weight + `source_count` bonus + HN points/comments.
- `exclude_topics`: set of `topic_key` values already used today (evening call passes the
  morning post's `topic_key`).
- `topic_key`: a slug derived from the candidate's dominant entity/title, used only for
  cross-post dedup.

### `write.py` (change)
- New `decide_format(top, rest) -> "deep" | "roundup"`: `deep` if `top.score` exceeds the
  runner-up by a configurable margin (`format_deep_margin`, default e.g. 12 points) or
  there is only one candidate; else `roundup`.
- `write_deep(cand, voice, generate)` → `PostContent` with long `caption_fb` (~200–350
  words), short `caption_ig`, hashtags, `image_briefs` (3–4 short prompts), `risk` flag.
- `write_roundup(cands[3..5], voice, generate)` → numbered items (2–4 sentences + source
  link each), `caption_ig` summary, hashtags, one `image_brief` per item, `risk` flag.
- System prompt forbids: historical distortion, fabricated numbers, unlawful/defamatory
  content, politically sensitive framing, clickbait that misrepresents facts (keep
  `config/voice.yaml` `cam_ky`). The model returns `risk: true` when the post touches a
  sensitive area; this does not block, it just annotates the preview.

### `images.py` (new)
- `build_images(post, out_dir) -> list[Path]`:
  - Image 1 = **cover**: a Gemini image + a Vietnamese headline overlaid with Pillow
    (reuse the existing overlay helper from `media.py`).
  - Images 2..N = clean Gemini illustrations (no text), one per `image_brief`.
  - All sized 1080×1350 (4:5).
  - Style prompt prefix from `config/settings.yaml` `images.style_prompt`
    (default: "digital art, glowing neural/tech motifs, blue and violet, cinematic, no text").
- `_gemini_image(prompt) -> bytes`: call `google-genai` image generation with
  `os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.6-flash")`.
- **Fallback**: on any Gemini image error (quota, safety, API), fall back to the current
  `media.build_media` path (Pillow thumbnail + source image + Playwright screenshot +
  Pollinations). Log which path was used; preview still goes out.
- Output dir `assets/posts/<YYYY-MM-DD>/<slot>/`, committed to the repo so
  `https://raw.githubusercontent.com/<owner>/<repo>/master/assets/posts/...` serves IG.

### `meta.py` (change)
- `publish_photos_fb(image_paths, message, scheduled_unix=None) -> dict`:
  upload each photo `published=false` → collect `photo_id`s → `POST /{page}/feed` with
  `attached_media` + `message`. If `scheduled_unix` given: add `published=false` +
  `scheduled_publish_time`; else `published=true`. Returns `{post_id, scheduled}`.
  If `scheduled_unix` is <10 min ahead, publish immediately and set `scheduled=False`
  with a warning.
- `publish_carousel_ig(image_urls, caption) -> dict`: one child container per image
  (`is_carousel_item=true`) → carousel container (`media_type=CAROUSEL`, `children`) →
  `media_publish`. If only one image, publish a single-image container instead.

### `daily_state.py` (new)
- Read/write `data/daily/<YYYY-MM-DD>.json` (schema below). One-way `status` transitions;
  helper `mark(slot, status, **fields)`.
- Reuses the existing atomic-write + `commit_state.sh` mechanism.

### `article_run.py` (new — replaces the article path of `run.py`)
- `draft(slot: "morning"|"evening", root, now)`:
  gather → dedup → `pick_n` (n=1, exclude today's other slot topic) → `decide_format` →
  `write_*` → `build_images` → commit images → write state (`status="draft"`) →
  `send_preview(...)`.
- `send_preview(post, images, slot)`: Telegram media group + text + meta line + 3 inline
  buttons with callback data `art:<date>:<slot>:now|sched|drop`.

### `article_approve.py` (new — replaces `approve.py` for this flow)
- Poll `getUpdates` from the stored offset. For each `callback_query` matching
  `art:<date>:<slot>:<action>`:
  - Load state; if the post is already `posted`/`discarded`/`expired` → ack and ignore.
  - `now` → `publish_photos_fb(published)` + `publish_carousel_ig` immediately →
    `status="posted"`, store `result`, Telegram confirm with links.
  - `sched` → `publish_photos_fb(scheduled_unix=<slot>)` → store `fb_post_id`,
    `ig_due=<slot UTC>`, `status="scheduled"`, Telegram "đã lên lịch 11:30".
  - `drop` → `status="discarded"`, Telegram confirm.
- Also: any `draft` post whose slot time passed by >24h → `status="expired"`.

### `article_publish_ig.py` (new)
- For each `data/daily/*.json` with a `scheduled` post whose `ig_due <= now` and no
  `result.ig` yet → `publish_carousel_ig` → store `result.ig`; on failure, Telegram
  "IG lỗi: …" with a retry hint. FB half is already handled by FB's native scheduler.

## State schema — `data/daily/<YYYY-MM-DD>.json`

```json
{
  "date": "2026-09-06",
  "posts": {
    "morning": {
      "status": "scheduled",
      "format": "deep",
      "topic_key": "openai-gpt-6-launch",
      "text_fb": "…full caption as it will post…",
      "text_ig": "…short caption…",
      "hashtags": ["#AI", "#ahitofficial"],
      "images": ["assets/posts/2026-09-06/morning/01_cover.jpg", "…"],
      "risk": false,
      "slot_ict": "11:30",
      "fb_post_id": "123_456",
      "ig_due": "2026-09-06T04:30:00Z",
      "result": { "fb": { "ok": true, "id": "…" }, "ig": null }
    },
    "evening": { "status": "draft", "...": "..." }
  }
}
```

`status`: `draft → scheduled | posted | discarded | expired`. Never moves backward.

## Config additions — `config/settings.yaml`

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
  provider: gemini            # gemini | legacy
  style_prompt: "digital art, glowing neural and tech motifs, blue and violet, cinematic, no text"
  size: "1080x1350"
```

`GEMINI_IMAGE_MODEL` env var overrides the image model (default `gemini-3.6-flash`),
same pattern as the recent `GEMINI_MODEL` fix.

## Error handling / edge cases

| Case | Behavior |
|------|----------|
| All sources fail to fetch | Telegram "gom tin lỗi hết nguồn", no post that slot |
| < 2 stories above `min_score` in the morning | Still produce #1; evening retries for #2 |
| 0 stories above threshold | Telegram "không có tin đủ nóng", skip slot |
| Gemini image error / quota / safety block | Fall back to legacy media path; preview still sent |
| User doesn't tap by slot time | Post stays `draft`; not published; user acts later; auto-`expired` after 24h |
| FB ok, IG fails (or vice-versa) | Telegram names the failed platform; other platform kept; "thử lại IG" hint |
| Callback arrives for an already-`posted` post | Acked and ignored (one-way status guard) |
| `article-morning` runs so late it's < 10 min before 11:30 | FB publishes immediately instead of scheduling; warning logged |
| Meta token expired | `refresh-token.yml` handles; if still failing, Telegram error |

## Testing (TDD, matches prior phases)

Unit:
- Google News RSS parsing; collect dedup + `source_count`.
- `pick_n`: returns N distinct topics, respects `exclude_topics` and `min_score`.
- `decide_format`: deep vs roundup at the margin boundary; single-candidate → deep.
- `write_deep` / `write_roundup` shape validation with `--fake-llm`.
- `build_images`: Gemini path (mocked) and fallback path; cover overlay applied to image 1;
  correct count per format.
- Callback state machine: each button from `draft`; late callback on `posted`/`discarded`;
  `draft → expired` after 24h.
- `publish_photos_fb` payload: multi-photo, `published=true` vs `scheduled_publish_time`,
  the <10-min-ahead immediate-publish fallback.
- `publish_carousel_ig` payload: multi-image carousel vs single image.
- Slot → `scheduled_publish_time` unix conversion (ICT→UTC).

Fakes/mocks: `--fake-llm`, mock Gemini image, mock Graph API (httpx), mock Telegram.

Offline smoke: full morning `draft(...)` with fakes, no credentials, asserts a written
state file + a (mock) preview call.

CI: a dedicated `article-test.yml` (or fold into the existing test workflow) running the
unit + smoke suite on Python 3.12.

## Out of scope for P1

- Any video work (P2/P3).
- YouTube / TikTok (P3).
- Engagement-driven topic ranking (P4).
- Editing a draft in-place before approval (future: a "viết lại" button).
- Custom per-day schedule times from Telegram (buttons use fixed slots only).
- Social-media sources beyond Hacker News (no free API).
