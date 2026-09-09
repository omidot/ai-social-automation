# Phase 2C — Publish the rendered video to YouTube / FB Reel / IG Reel / TikTok

**Status:** design approved 2026-09-09. Base: `master` @ `df91af1` (Phase 2B merged).

## 1. Context & goal

Phase 2B ends with a slot at `video.status == "rendered"`: a 1080×1920 ~40s MP4 on the
`video-render` runner's disk (`video.mp4_path`, under gitignored `output/`), plus
`video.tg_file_id` (Telegram, 20 MB `getFile` cap), `video.meta` (a `VideoMeta`:
`title` / `description` / `hashtags` / `keywords` / `tiktok_caption`), and
`video.publish_due` (ISO). `video.result` is `{yt,fb,ig,tiktok}` all `null`.

Phase 2C publishes that MP4 to four destinations and records the outcome. Channels:
YouTube `@ahitofficials`, TikTok `@ahitofficial`, the Facebook Page
(`META_PAGE_ID` = `1381130541740424`), and its linked Instagram (`IG_BUSINESS_ID`).

**North Star:** fully autonomous, runs free on GitHub Actions. The repo
`github.com/omidot/ai-social-automation` is **public** → Actions minutes are free and
unlimited, and **no token may ever be committed to the repo** — all credentials live in
GitHub Secrets.

## 2. Decisions (from brainstorming)

1. **All four platforms**, built in order: (1) shared infra + **YouTube**, (2) FB Reel,
   (3) IG Reel, (4) TikTok. Each platform is an independently shippable module behind a
   per-platform enable flag; a disabled platform is skipped.
2. **MP4 hosting = a GitHub Release asset.** The `video-render` job uploads the MP4 to a
   fixed hidden Release (tag `video-assets`) using the built-in `GITHUB_TOKEN`, producing
   a public `releases/download/…` URL. IG/FB/TikTok pull from that URL; YouTube uploads
   the bytes directly from disk. The asset is deleted once every enabled platform is done.
3. **Publishing is folded into `video-render.yml`** — no new workflow. `render_run` calls
   `render_pending` then `publish_pending`.
4. **YouTube / FB Reel / IG Reel publish directly as public**, consistent with the article
   track. A `🗑 Gỡ tất cả` button gives a 60-minute undo window. **TikTok** can only
   upload to the user's inbox as a draft (unaudited app) — the user finalises it in the
   TikTok app; a Telegram nudge says so.
5. **YouTube OAuth**: the user runs a local `scripts/mint_youtube_token.py` once to mint a
   refresh token, then creates `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` /
   `YOUTUBE_REFRESH_TOKEN` secrets — same "user handles all credentials" pattern as Meta.
6. **FB Reel / IG Reel reuse the existing `META_PAGE_TOKEN` + `IG_BUSINESS_ID`** — no new
   Meta credential (the token already carries `pages_manage_posts` /
   `instagram_content_publish`).

## 3. State machine

`video.status` gains: `rendered → publishing → published`, plus `unpublished` (after undo).
`published` is terminal for the pipeline; the article-style one-way `TERMINAL` guard does
**not** cover these video statuses (they live in `posts.<slot>.video`, not
`posts.<slot>.status`), so `DailyState.put` writes them directly, always spreading the
prior `video` dict (`{**v, ...}`).

`video.result.<platform>` — one key per platform (`youtube`, `fb_reel`, `ig_reel`,
`tiktok`):

| value | meaning |
|---|---|
| `null` | not attempted yet |
| `{ "id": str, "url": str, "at": iso }` | published OK |
| `{ "error": str, "attempts": int, "last_at": iso, "gave_up": bool }` | failing; `gave_up` after 5 attempts |
| `{ "status": "draft_uploaded", "at": iso }` | TikTok only — draft sits in the user's inbox |

New `video` keys: `asset_url` (str \| null — the Release download URL while publishing),
`published_at` (iso — set when `status` first reaches `published`, drives the undo window),
`publish_started_at` (iso — set on the first `→ publishing` transition, drives the
`expire_stale` stuck-nudge), `publish_stale_warned` (bool — guards that nudge so it fires
once).

A platform counts as **done** when its `result` is `{id}` / `{status:"draft_uploaded"}` /
`{gave_up:true}`. When every **enabled** platform is done → `status = "published"`,
`published_at = now`, delete the Release asset, `asset_url = null`, send the Telegram
summary. Disabled platforms are ignored for this check and never written to.

## 4. Orchestrator — `src/pipeline/video/publish/__init__.py`

`publish_pending(ds, tg, root, now, *, limit=1) -> list[str]` — called by `render_run`
immediately after `render_pending`:

1. Read `config/settings.yaml` `video.publish` (null-safe: `.get("publish") or {}`).
   `enabled = {p for p,on in publish_cfg.items() if on}`. If empty → return `[]`.
2. Scan `sorted(ds.all_files())` (oldest date first) for the first slot with
   `video.status ∈ {"rendered","publishing"}` **and** at least one `p ∈ enabled` whose
   `video.result[p]` is not done. None → return `[]`. Respect `limit` (default 1 — one
   unit of publish work per tick, same budgeting as render).
3. **Asset**: if `video.asset_url` is falsy → `assets.upload_release_asset(mp4, tag)`.
   `mp4` source order: `root / video.mp4_path` if it exists on disk (same job as the
   render), else download `video.tg_file_id` via Telegram (only if ≤ ~20 MB), else if
   `video.asset_url` already set reuse it. If none available →
   `video.render_err = "mp4 unavailable for publish"`, `video.status = "awaiting_audio"`
   (re-render), Telegram warn, return.
4. `video.status = "publishing"`; set `video.publish_started_at = now` if unset.
5. For each `p ∈ enabled` not yet done: call the adapter (§5). Wrap each in try/except so
   one platform's failure never blocks the others.
   - success → `video.result[p] = {id, url, at:now}` (or `{status:"draft_uploaded"}` for
     TikTok).
   - exception → `attempts = (prev.attempts or 0) + 1`;
     `video.result[p] = {error: str(e)[:300], attempts, last_at: now,
     gave_up: attempts >= 5}`. On `gave_up` send `⚠️ {platform} bỏ cuộc sau 5 lần: …`.
   Re-read + spread `video` before each write. After each write, re-read `video.status`;
   if it is no longer `"publishing"` (an `unpub`/undo landed) → stop the loop, mirroring
   2B's I-D fix.
6. If every enabled platform is now done →
   `video.status="published"`, `video.published_at=now`,
   `assets.delete_release_asset(tag)`, `video.asset_url=null`; send the summary:
   `🚀 {slot} ({date}) đã đăng:` + per-platform lines (`✅ YouTube <url>`,
   `❌ FB Reel (bỏ cuộc)`, `📥 TikTok — mở app đăng nháp`) + a `🗑 Gỡ tất cả` button
   (`vid:{date}:{slot}:unpub`).
7. Return e.g. `["publishing:2026-09-09:morning"]` / `["published:2026-09-09:morning"]`.

`expire_stale` (in `article_approve`, runs every 5 min): a slot with
`video.status == "publishing"`, `video.publish_stale_warned` not set, and
`now - fromiso(video.publish_started_at) > 6*3600` → send
`⚠️ {date}:{slot} đăng video kẹt >6h, xem log` and set
`video.publish_stale_warned = true`. It does **not** force a state change — the next
`video-render` tick keeps retrying the not-done platforms.

## 5. Platform adapters

### 5.1 Assets — `src/pipeline/video/publish/assets.py`

- `upload_release_asset(mp4: Path, name: str, repo: str, token: str) -> str` — ensure a
  Release with tag `video-assets` exists (create once, `prerelease=true`, name
  "video assets — transient"); delete any existing asset of the same `name`; upload
  `mp4` as `name` (`<date>-<slot>.mp4`); return
  `https://github.com/{repo}/releases/download/video-assets/{name}`. Uses the GitHub REST
  API with `GITHUB_TOKEN` (httpx; `gh` CLI is also on the runner as a fallback).
- `delete_release_asset(name, repo, token) -> None` — delete the asset by name; missing =
  no-op.
- `repo` = `GITHUB_REPOSITORY` env; `token` = `GITHUB_TOKEN` env.

### 5.2 YouTube — `src/pipeline/video/publish/youtube.py`

- `YouTube.from_env()` → reads `YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN`.
- `_access_token()` — `POST https://oauth2.googleapis.com/token`
  (`grant_type=refresh_token`); refresh tokens for an OAuth consent screen in
  **Production** status do not expire, so no persistence needed.
- `upload(mp4: Path, meta: VideoMeta, cfg: dict) -> {id, url}` — resumable upload to
  `https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`.
  `snippet`: `title = meta.title[:95] + " #Shorts"`, `description = meta.description +
  "\n\n" + " ".join(meta.hashtags) + "\n\n" + cfg["channel_footer"]`,
  `tags = meta.keywords`, `categoryId = str(cfg.get("youtube_category", 27))`.
  `status`: `privacyStatus="public"`, `selfDeclaredMadeForKids=false`.
  `url = f"https://youtu.be/{id}"`.
- `delete(video_id) -> None` — `DELETE …/youtube/v3/videos?id=`.

### 5.3 Facebook Reel — new methods on `src/pipeline/meta.py`

- `fb_publish_reel(video_url: str, description: str) -> {id, url}` — three-phase
  `POST /{page_id}/video_reels`: `upload_phase=start` → `POST` the `video_url` to the
  returned `upload_url` (Meta pulls the bytes) → `upload_phase=finish` with
  `video_state=PUBLISHED` + `description`. Poll `GET /{video_id}?fields=status` until
  `status.video_status == "ready"` (or `"published"`), timeout ~5 min.
  `url = f"https://facebook.com/reel/{id}"`. Uses `self.token`.
- Undo reuses the existing `fb_delete_post(id)`.

### 5.4 Instagram Reel — new methods on `src/pipeline/meta.py`

- `ig_publish_reel(video_url: str, caption: str) -> {id, url}` —
  `POST /{ig_id}/media` with `media_type=REELS`, `video_url`, `caption`,
  `share_to_feed=true` → poll `GET /{creation_id}?fields=status_code` until `FINISHED`
  (timeout ~5 min; `ERROR` → raise) → `POST /{ig_id}/media_publish` with `creation_id`.
  `url = f"https://instagram.com/reel/{shortcode}"` if derivable else the media id.
- Undo reuses the existing `ig_delete_media(id)`.

### 5.5 TikTok — `src/pipeline/video/publish/tiktok.py` (step 4)

- `TikTok.from_env()` → `TIKTOK_CLIENT_KEY/SECRET/REFRESH_TOKEN`.
- Access tokens last 24 h; the refresh token is **single-use** and rotates on every
  refresh (new one returned, old invalidated), 365-day life. Persistence: after a
  refresh, write the new refresh token back to the `TIKTOK_REFRESH_TOKEN` **GitHub
  Secret** via the REST API using a `GH_PAT` (scope `repo`, so it can write Actions
  secrets — the default `GITHUB_TOKEN` cannot). If `GH_PAT` is absent, fall back to
  Telegram-ing the new token to the user (Meta `refresh-token.yml` pattern).
- `upload_draft(video_url: str, caption: str) -> {status: "draft_uploaded"}` —
  `POST /v2/post/publish/inbox/video/init/` with `source_info` =
  `{source: "PULL_FROM_URL", video_url}`. No publish step — the video lands in the user's
  TikTok inbox; they post it from the app. No API undo path.

### 5.6 Metadata mapping recap

`VideoMeta` fields → per §5.2–5.5. `meta.title` is validated 10–70 chars (2B), safely
under YouTube's 100. `meta.tiktok_caption` is validated ≤150 (2B), under TikTok's limit.

## 6. Undo — `vid:{date}:{slot}:unpub`

`article_approve.poll` already routes `callback_query.data` starting `vid:` to
`render.handle_undo`. Extend: `vid:*:unpub` → a new
`publish.handle_unpublish(cbq, ds, tg, root, now)`:

1. Parse 4 colon-parts, suffix `unpub`. Slot's `video.status` must be `published` (else
   ack "không có gì để gỡ").
2. `now - fromiso(video.published_at) > UNDO_GRACE_MIN*60` (60) → ack
   "Đăng lâu rồi — gỡ tay trên từng nền tảng." + `undo-expired:…`.
3. For each `p` with `video.result[p] == {id}`: call the platform delete
   (`YouTube.delete`, `meta.fb_delete_post`, `meta.ig_delete_media`). Collect errors, do
   not abort on the first. TikTok: no API path — the summary line says
   "TikTok: tự xoá nháp trong app".
4. `video.status = "unpublished"`; keep `video.result.*` but tag each undone one
   `undone: true`. Telegram: `🗑 Đã gỡ {date}:{slot}` + any errors.

`UNDO_GRACE_MIN` (currently 60, in `article_approve`) is reused as-is.

## 7. Workflow & config

### 7.1 `.github/workflows/video-render.yml` (edit the 2B file, no new workflow)

- The bash gate `id: g` matches `'"audio_received"'` **or** `'"rendered"'` **or**
  `'"publishing"'` in `data/daily/` → `go=1` (heavy steps still gated; publish-only ticks
  still need Node? No — publishing is pure Python/httpx. But the gate already guards
  `Install deps` which publishing needs, and Node/Remotion steps are harmless when a tick
  is publish-only. Keep them gated together for simplicity.)
- Rename the run step to "Render + publish"; it runs `python -m pipeline.video.render_run`
  unchanged (the module now also calls `publish_pending`).
- Add to that step's `env:`: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`,
  `YOUTUBE_REFRESH_TOKEN`, `META_PAGE_ID`, `META_PAGE_TOKEN`, `IG_BUSINESS_ID`
  (later: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`, `GH_PAT`).
  `GITHUB_TOKEN` is implicit; also pass `GITHUB_REPOSITORY` (implicit) — no action needed.
- `Commit state: if: always()` already present (2B).
- `timeout-minutes: 25` unchanged (a publish-only tick is well under this; a
  render+publish tick that runs long is bounded the same as 2B).

### 7.2 `config/settings.yaml`

```yaml
video:
  # …existing 2B keys…
  channel_footer: "— A Hít Official · AI & năng suất mỗi ngày"
  publish:
    youtube: false        # flip to true once the 3 YOUTUBE_* secrets exist
    fb_reel: false
    ig_reel: false
    tiktok: false
    youtube_category: 27  # Education
```

### 7.3 Secrets (user creates; README + helper documents this)

- Now: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
  (from `scripts/mint_youtube_token.py` — opens the Google consent flow locally, prints
  the refresh token; requires the OAuth consent screen set to **Production** or the
  refresh token expires in 7 days).
- Step 4: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`, and
  `GH_PAT` (fine-grained PAT, this repo, **Secrets: read/write** — lets the workflow
  persist TikTok's rotating refresh token).

## 8. Module layout

```
src/pipeline/video/publish/
  __init__.py        # publish_pending(), handle_unpublish()
  assets.py          # upload_release_asset(), delete_release_asset()
  youtube.py         # YouTube.from_env(), .upload(), .delete()
  tiktok.py          # TikTok.from_env(), .upload_draft()   (step 4)
src/pipeline/meta.py # + fb_publish_reel(), ig_publish_reel()
src/pipeline/video/render_run.py  # run(): render_pending(...) then publish_pending(...)
src/pipeline/article_approve.py   # poll routes vid:*:unpub; expire_stale publishing>6h nudge
scripts/mint_youtube_token.py     # one-time local OAuth helper
```

Each adapter is independently testable: one class / module, HTTP mocked, no live
credentials. `publish_pending` depends only on `ds`, `tg`, the adapters, and the config.

## 9. Testing

- `tests/video/test_publish_assets.py` — create-release-once, replace-asset, delete,
  missing-asset no-op; `httpx` mocked.
- `tests/video/test_youtube.py` — refresh→access exchange; `upload` builds the resumable
  request with the right `snippet`/`status` (title has ` #Shorts`, footer appended,
  `tags` = keywords, `madeForKids=false`, `public`); `delete` hits the right URL.
- `tests/video/test_meta_reels.py` — `fb_publish_reel` does start/upload/finish with
  `video_url`; `ig_publish_reel` does create→poll→publish with `media_type=REELS` +
  `share_to_feed=true`; both mocked.
- `tests/video/test_publish_orchestrator.py` — slot selection (oldest, right statuses,
  only enabled platforms); asset uploaded once then reused; per-platform success/failure
  recorded; `attempts` increments and hits `gave_up` at 5; all-done →
  `status="published"` + asset deleted + summary sent with the `unpub` button; a disabled
  platform is never touched; MP4 unavailable → `awaiting_audio` + warn; a mid-loop
  `discarded` stops the loop.
- `tests/video/test_tiktok.py` (step 4) — `upload_draft` builds PULL_FROM_URL init;
  refresh-token rotation writes back via the PAT path, falls back to Telegram without it.
- `tests/test_article_approve.py` — `poll` routes `vid:*:unpub` to `handle_unpublish`
  (and still routes `vid:*:undo` to `render.handle_undo`); `handle_unpublish` deletes
  each `{id}` platform, collects errors, refuses past 60 min, sets `unpublished`;
  `expire_stale` sends the >6h `publishing` nudge once.
- `tests/test_workflows.py` — `video-render.yml` still valid; new env keys present; gate
  string includes `rendered` / `publishing`.

## 10. Build order (→ implementation plan)

1. **Infra + YouTube**: state-machine keys, `assets.py`, `youtube.py`,
   `publish/__init__.py` (`publish_pending`), `render_run` wiring, `settings.yaml`
   `video.publish` block, `video-render.yml` env, `handle_unpublish` + `poll` routing +
   `expire_stale` nudge, `scripts/mint_youtube_token.py`, README section, all tests above
   except TikTok. Ship with only `youtube` flippable.
2. **FB Reel**: `meta.fb_publish_reel` + orchestrator wires `fb_reel`; tests.
3. **IG Reel**: `meta.ig_publish_reel` + `ig_reel`; tests.
4. **TikTok**: `tiktok.py` (incl. refresh-token rotation via `GH_PAT` / Telegram
   fallback) + `tiktok` platform + secrets doc; tests.

## 11. Out of scope

- No scheduling of the publish time — `publish_pending` fires as soon as a slot is
  `rendered` (the render already happened after `publish_due`). `video.publish_due`
  stays informational.
- No analytics / view tracking.
- No re-encoding per platform — the single 1080×1920 H.264 MP4 is accepted by all four.
- No thumbnail upload to YouTube (Shorts uses an auto-frame); revisit later if wanted.
- The >20 MB Telegram `getFile` gap is closed by the Release asset for the
  render+publish-same-job path; a publish tick landing on a *different* runner with the
  MP4 gone falls back to the Release asset (already uploaded) — only a slot that failed
  before the asset upload needs a re-render.
