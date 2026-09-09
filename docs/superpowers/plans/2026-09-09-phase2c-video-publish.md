# Phase 2C — Video Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish each `video.status == "rendered"` slot's MP4 to YouTube, Facebook Reels, Instagram Reels, and TikTok (draft), recording per-platform outcomes and offering a 60-minute undo.

**Architecture:** A new `src/pipeline/video/publish/` package. `render_run.run()` calls `publish_pending()` right after `render_pending()` in the same `video-render` GitHub Actions job. The MP4 is hosted as a GitHub Release asset (public repo → public download URL) so IG/FB/TikTok can pull it; YouTube uploads bytes from disk. Each platform is a small adapter behind a `config/settings.yaml` `video.publish.<platform>` flag. State lives in `posts.<slot>.video` (`status`, `result.<platform>`, `asset_url`, …).

**Tech Stack:** Python 3.12, `httpx` (already pinned, sync `Client`), GitHub REST API (`GITHUB_TOKEN`), YouTube Data API v3 (OAuth2 refresh-token), Meta Graph API v21.0 (existing `META_PAGE_TOKEN`), TikTok Content Posting API, `gh` CLI (on the runner, for writing back the TikTok secret). No new pip dependency.

## Global Constraints

- Python 3.12. Run from repo root `D:\Automation Social`, interpreter `.venv/Scripts/python.exe`, `PYTHONUTF8=1`.
- Repo `github.com/omidot/ai-social-automation` is **public**: GitHub Actions minutes are free/unlimited; **never commit a token or secret to the repo** — all credentials come from env (GitHub Secrets).
- `DailyState.put(date, slot, video={...})` does `cur.update(fields)` → every video write must spread the prior dict: `ds.put(date, slot, video={**v, ...})`, and re-read via `ds.get_safe` before a follow-up write.
- Video state machine (2C additions): `rendered → publishing → published`; `published → unpublished` via undo. Never a terminal `failed`. These live in `posts.<slot>.video`, not `posts.<slot>.status`.
- `video.result.<platform>` per platform key `youtube` / `fb_reel` / `ig_reel` / `tiktok`: `null` = not attempted; `{"id","url","at"}` = OK; `{"error","attempts","last_at","gave_up"}` = failing (`gave_up` at `attempts >= 5`); `{"status":"draft_uploaded","at"}` = TikTok done. "done" = `{id}` OR `{status:"draft_uploaded"}` OR `{gave_up:true}`.
- New `video` keys: `asset_url`, `published_at`, `publish_started_at`, `publish_stale_warned`.
- `video.publish` in `config/settings.yaml` read null-safe: `(cfg.get("publish") or {})`. A disabled platform is never called and never written to `video.result`.
- `publish_pending` processes at most `limit=1` slot per invocation (same budgeting as `render_pending`).
- Retry ceiling per platform: 5 attempts, then `gave_up:true` + one Telegram warning.
- Undo window: `UNDO_GRACE_MIN` (already `60` in `article_approve`), measured from `video.published_at`.
- Callback data: `vid:{date}:{slot}:unpub` (4 colon-parts) for 2C undo, alongside 2B's `vid:{date}:{slot}:undo`.
- ICT = UTC+7. `slot_unix(date, slot_ict)` lives in `pipeline.publish`.
- Telegram helper API: `tg.send_message(text, buttons=None)` where `buttons` is `list[tuple[label, callback_data]]`; `tg.answer_callback(cbq_id, text="")`; `tg.download_file(file_id, dest) -> str`.
- Meta helper API (`src/pipeline/meta.py`): `Meta.from_env()`, `self.token`, `self.page_id`, `self.ig_id`, `self._client` (`httpx.Client(timeout=120)`), `self._get(path, params) -> dict`, `self._post(url, data=None, files=None) -> dict`, `_raise_for_graph(r)`, `BASE = "https://graph.facebook.com/v21.0"`, `MetaError`. Existing `fb_delete_post(id)`, `ig_delete_media(id)`.
- `VideoMeta` (`src/pipeline/video/models.py`): `.from_dict(d)`, `.to_dict()`, fields `title` (10–70 chars), `description`, `hashtags` (list), `keywords` (list), `tiktok_caption` (≤150).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pipeline/video/publish/__init__.py` | `publish_pending()` orchestrator, `handle_unpublish()` undo, `_PLATFORMS` registry |
| `src/pipeline/video/publish/assets.py` | `upload_release_asset()`, `delete_release_asset()` — GitHub Release asset I/O |
| `src/pipeline/video/publish/youtube.py` | `YouTube` — OAuth refresh, resumable `upload()`, `delete()` |
| `src/pipeline/video/publish/tiktok.py` | `TikTok` — token refresh + rotation write-back, `upload_draft()` (Task 7) |
| `src/pipeline/meta.py` | + `fb_publish_reel()`, `ig_publish_reel()` |
| `src/pipeline/video/render_run.py` | `run()` also calls `publish_pending()` |
| `src/pipeline/article_approve.py` | `poll` routes `vid:*:unpub`; `expire_stale` nudges `video.status=="publishing"` >6h |
| `scripts/mint_youtube_token.py` | one-time local OAuth helper (prints refresh token) |
| `config/settings.yaml` | `video.publish` block + `video.channel_footer` |
| `.github/workflows/video-render.yml` | gate matches `rendered`/`publishing`; publish secrets in `env:` |
| `README.md` | "Đăng video (Phase 2C)" section |

Build order: **Task 1** assets → **Task 2** YouTube adapter + mint script → **Task 3** orchestrator + config + `render_run` wiring → **Task 4** undo + `expire_stale` + workflow + README → **Task 5** FB Reel → **Task 6** IG Reel → **Task 7** TikTok.

---

## Task 1: GitHub Release asset store

**Files:**
- Create: `src/pipeline/video/publish/__init__.py` (empty package marker for now — just a module docstring)
- Create: `src/pipeline/video/publish/assets.py`
- Test: `tests/video/test_publish_assets.py`

**Interfaces:**
- Consumes: nothing (leaf module). Env: `GITHUB_TOKEN`, `GITHUB_REPOSITORY` (both set by Actions).
- Produces:
  - `upload_release_asset(mp4: Path, name: str, *, repo: str | None = None, token: str | None = None) -> str` — returns the public download URL `https://github.com/{repo}/releases/download/video-assets/{name}`. Ensures the `video-assets` release exists (creates once, `prerelease=True`); if an asset named `name` already exists, deletes it first; uploads `mp4` as `name`.
  - `delete_release_asset(name: str, *, repo: str | None = None, token: str | None = None) -> bool` — deletes the asset named `name` from the `video-assets` release; returns `True` if something was deleted, `False` if it was absent. Never raises on "not found".
  - `RELEASE_TAG = "video-assets"`

- [ ] **Step 1: Write the failing tests**

Create `tests/video/test_publish_assets.py`:

```python
from pathlib import Path
import httpx
import pytest
from pipeline.video.publish import assets


class _MockAPI:
    """Fake GitHub REST + uploads endpoints backed by a dict of assets."""
    def __init__(self, *, release_exists=True):
        self.assets = {}          # name -> id
        self._next_id = 100
        self.release_id = 42
        self.release_exists = release_exists
        self.created_release = False
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        m, url = request.method, str(request.url)
        self.calls.append(f"{m} {url}")
        if url.endswith("/releases/tags/video-assets"):
            if self.release_exists:
                return httpx.Response(200, json={"id": self.release_id,
                                                 "assets": [{"id": i, "name": n}
                                                            for n, i in self.assets.items()]})
            return httpx.Response(404, json={})
        if m == "POST" and url.endswith("/releases"):
            self.release_exists = True
            self.created_release = True
            return httpx.Response(201, json={"id": self.release_id, "assets": []})
        if m == "DELETE" and "/releases/assets/" in url:
            aid = int(url.rsplit("/", 1)[1])
            self.assets = {n: i for n, i in self.assets.items() if i != aid}
            return httpx.Response(204)
        if m == "POST" and "uploads.github.com" in url:
            name = httpx.QueryParams(request.url.query).get("name")
            self._next_id += 1
            self.assets[name] = self._next_id
            return httpx.Response(201, json={"id": self._next_id, "name": name})
        return httpx.Response(500, json={"unhandled": url})


def _client(api):
    return httpx.Client(transport=httpx.MockTransport(api.handler))


def test_upload_creates_release_when_missing(monkeypatch, tmp_path):
    api = _MockAPI(release_exists=False)
    monkeypatch.setattr(assets, "_client", lambda token: _client(api))
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"MP4DATA")
    url = assets.upload_release_asset(mp4, "2026-09-09-morning.mp4",
                                     repo="omidot/ai-social-automation", token="T")
    assert url == ("https://github.com/omidot/ai-social-automation/releases/download/"
                   "video-assets/2026-09-09-morning.mp4")
    assert api.created_release
    assert "2026-09-09-morning.mp4" in api.assets


def test_upload_replaces_existing_asset(monkeypatch, tmp_path):
    api = _MockAPI()
    api.assets["2026-09-09-morning.mp4"] = 999
    monkeypatch.setattr(assets, "_client", lambda token: _client(api))
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"NEW")
    assets.upload_release_asset(mp4, "2026-09-09-morning.mp4",
                               repo="omidot/ai-social-automation", token="T")
    assert any("DELETE" in c and "/releases/assets/999" in c for c in api.calls)
    assert api.assets["2026-09-09-morning.mp4"] != 999


def test_delete_asset_present_and_absent(monkeypatch):
    api = _MockAPI()
    api.assets["x.mp4"] = 7
    monkeypatch.setattr(assets, "_client", lambda token: _client(api))
    assert assets.delete_release_asset("x.mp4", repo="o/r", token="T") is True
    assert assets.delete_release_asset("x.mp4", repo="o/r", token="T") is False


def test_env_fallback(monkeypatch, tmp_path):
    api = _MockAPI()
    monkeypatch.setattr(assets, "_client", lambda token: _client(api))
    monkeypatch.setenv("GITHUB_REPOSITORY", "omidot/ai-social-automation")
    monkeypatch.setenv("GITHUB_TOKEN", "ENVTOK")
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"D")
    url = assets.upload_release_asset(mp4, "d.mp4")
    assert url.startswith("https://github.com/omidot/ai-social-automation/releases/download/")
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_publish_assets.py -q`
Expected: FAIL — `ModuleNotFoundError: pipeline.video.publish` / `assets`.

- [ ] **Step 3: Create the package marker**

Create `src/pipeline/video/publish/__init__.py`:

```python
"""Phase 2C — publish a rendered video to external platforms."""
```

- [ ] **Step 4: Implement `assets.py`**

Create `src/pipeline/video/publish/assets.py`:

```python
from __future__ import annotations
import os
from pathlib import Path

import httpx

_API = "https://api.github.com"
_UPLOADS = "https://uploads.github.com"
RELEASE_TAG = "video-assets"


class AssetError(RuntimeError):
    pass


def _client(token: str) -> httpx.Client:
    return httpx.Client(
        timeout=300.0,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )


def _repo_token(repo: str | None, token: str | None) -> tuple[str, str]:
    repo = repo or os.environ["GITHUB_REPOSITORY"]
    token = token or os.environ["GITHUB_TOKEN"]
    return repo, token


def _get_or_create_release(c: httpx.Client, repo: str) -> dict:
    r = c.get(f"{_API}/repos/{repo}/releases/tags/{RELEASE_TAG}")
    if r.status_code == 200:
        return r.json()
    if r.status_code != 404:
        raise AssetError(f"get release -> {r.status_code}: {r.text[:300]}")
    r = c.post(f"{_API}/repos/{repo}/releases", json={
        "tag_name": RELEASE_TAG, "name": "video assets — transient",
        "body": "Auto-managed by Phase 2C. Assets are deleted after publish.",
        "prerelease": True})
    if r.status_code not in (200, 201):
        raise AssetError(f"create release -> {r.status_code}: {r.text[:300]}")
    return r.json()


def upload_release_asset(mp4: Path, name: str, *,
                         repo: str | None = None, token: str | None = None) -> str:
    repo, token = _repo_token(repo, token)
    mp4 = Path(mp4)
    with _client(token) as c:
        rel = _get_or_create_release(c, repo)
        for a in rel.get("assets", []):
            if a["name"] == name:
                c.delete(f"{_API}/repos/{repo}/releases/assets/{a['id']}")
        up = c.post(
            f"{_UPLOADS}/repos/{repo}/releases/{rel['id']}/assets",
            params={"name": name},
            headers={"Content-Type": "video/mp4"},
            content=mp4.read_bytes())
        if up.status_code not in (200, 201):
            raise AssetError(f"upload asset -> {up.status_code}: {up.text[:300]}")
    return f"https://github.com/{repo}/releases/download/{RELEASE_TAG}/{name}"


def delete_release_asset(name: str, *,
                         repo: str | None = None, token: str | None = None) -> bool:
    repo, token = _repo_token(repo, token)
    with _client(token) as c:
        r = c.get(f"{_API}/repos/{repo}/releases/tags/{RELEASE_TAG}")
        if r.status_code == 404:
            return False
        r.raise_for_status()
        for a in r.json().get("assets", []):
            if a["name"] == name:
                d = c.delete(f"{_API}/repos/{repo}/releases/assets/{a['id']}")
                return d.status_code in (204, 200)
    return False
```

- [ ] **Step 5: Run the tests, verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_publish_assets.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Full video suite + non-video regression**

Run: `.venv/Scripts/python.exe -m pytest tests/video -q` → PASS
Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q` → PASS (209, unchanged)

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/video/publish/__init__.py src/pipeline/video/publish/assets.py tests/video/test_publish_assets.py
git commit -m "feat(p2c): GitHub Release asset store for rendered MP4s"
```

---

## Task 2: YouTube adapter + one-time token helper

**Files:**
- Create: `src/pipeline/video/publish/youtube.py`
- Create: `scripts/mint_youtube_token.py`
- Test: `tests/video/test_youtube.py`

**Interfaces:**
- Consumes: `VideoMeta` (`pipeline.video.models`). Env: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`.
- Produces:
  - `YouTube.from_env() -> YouTube`
  - `YouTube.upload(mp4: Path, meta: VideoMeta, cfg: dict) -> dict` → `{"id": str, "url": str}` (`url = https://youtu.be/{id}`). `cfg` keys used: `channel_footer` (str, default `""`), `youtube_category` (int, default `27`).
  - `YouTube.delete(video_id: str) -> None`
  - `YouTubeError(RuntimeError)`

- [ ] **Step 1: Write the failing tests**

Create `tests/video/test_youtube.py`:

```python
from pathlib import Path
import json
import httpx
import pytest
from pipeline.video.publish.youtube import YouTube, YouTubeError
from pipeline.video.models import VideoMeta

_META = VideoMeta(
    title="Cách dùng AI dựng landing page trong 30 phút",
    description="Mô tả ngắn về video.", hashtags=["#AI", "#nangsuat", "#lam"],
    keywords=["ai", "landing page", "khong code"],
    tiktok_caption="AI dựng landing page #AI")


class _YTMock:
    def __init__(self, *, upload_status=200):
        self.upload_status = upload_status
        self.snippet = None
        self.deleted = []
        self.token_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://oauth2.googleapis.com/token"):
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": "ATK", "expires_in": 3599})
        if "upload/youtube/v3/videos" in url:
            body = json.loads(request.content)
            self.snippet = body
            return httpx.Response(200, headers={"Location": "https://up.example/resumable"})
        if url == "https://up.example/resumable":
            return httpx.Response(self.upload_status, json={"id": "VID123"})
        if "youtube/v3/videos" in url and request.method == "DELETE":
            self.deleted.append(httpx.QueryParams(request.url.query).get("id"))
            return httpx.Response(204)
        return httpx.Response(500, json={"unhandled": url})


def _yt(mock):
    yt = YouTube("CID", "CSEC", "RTOK")
    yt._client = httpx.Client(transport=httpx.MockTransport(mock.handler))
    return yt


def test_upload_builds_snippet_and_returns_id(tmp_path):
    mock = _YTMock()
    yt = _yt(mock)
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"BYTES")
    out = yt.upload(mp4, _META, {"channel_footer": "— A Hít Official", "youtube_category": 27})
    assert out == {"id": "VID123", "url": "https://youtu.be/VID123"}
    sn = mock.snippet["snippet"]
    assert sn["title"].endswith(" #Shorts") and "landing page" in sn["title"]
    assert "— A Hít Official" in sn["description"] and "#AI" in sn["description"]
    assert sn["tags"] == ["ai", "landing page", "khong code"]
    assert sn["categoryId"] == "27"
    assert mock.snippet["status"] == {"privacyStatus": "public",
                                      "selfDeclaredMadeForKids": False}
    assert mock.token_calls == 1


def test_upload_raises_on_bad_status(tmp_path):
    mock = _YTMock(upload_status=403)
    yt = _yt(mock)
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"B")
    with pytest.raises(YouTubeError):
        yt.upload(mp4, _META, {})


def test_title_truncated_under_100(tmp_path):
    mock = _YTMock()
    yt = _yt(mock)
    long_meta = VideoMeta(title="x" * 130, description="d", hashtags=["#a"],
                          keywords=["k"], tiktok_caption="c")
    mp4 = tmp_path / "v.mp4"; mp4.write_bytes(b"B")
    yt.upload(mp4, long_meta, {})
    assert len(mock.snippet["snippet"]["title"]) <= 100


def test_delete_hits_endpoint():
    mock = _YTMock()
    yt = _yt(mock)
    yt.delete("VID999")
    assert mock.deleted == ["VID999"]


def test_from_env(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "a")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "b")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "c")
    yt = YouTube.from_env()
    assert yt.client_id == "a" and yt.refresh_token == "c"
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_youtube.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `youtube.py`**

Create `src/pipeline/video/publish/youtube.py`:

```python
from __future__ import annotations
import os
from pathlib import Path

import httpx

from ..models import VideoMeta

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
               "?uploadType=resumable&part=snippet,status")
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeError(RuntimeError):
    pass


class YouTube:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._client = httpx.Client(timeout=300.0)

    @classmethod
    def from_env(cls) -> "YouTube":
        return cls(os.environ["YOUTUBE_CLIENT_ID"],
                   os.environ["YOUTUBE_CLIENT_SECRET"],
                   os.environ["YOUTUBE_REFRESH_TOKEN"])

    def _access_token(self) -> str:
        r = self._client.post(_TOKEN_URL, data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": self.refresh_token, "grant_type": "refresh_token"})
        if not r.is_success:
            raise YouTubeError(f"token refresh -> {r.status_code}: {r.text[:300]}")
        return r.json()["access_token"]

    def upload(self, mp4: Path, meta: VideoMeta, cfg: dict) -> dict:
        mp4 = Path(mp4)
        token = self._access_token()
        title = (meta.title[:92].rstrip() + " #Shorts")[:100]
        footer = cfg.get("channel_footer", "")
        desc = meta.description.strip()
        if meta.hashtags:
            desc += "\n\n" + " ".join(meta.hashtags)
        if footer:
            desc += "\n\n" + footer
        body = {
            "snippet": {"title": title, "description": desc,
                        "tags": list(meta.keywords),
                        "categoryId": str(cfg.get("youtube_category", 27))},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        init = self._client.post(
            _UPLOAD_URL,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/*"},
            json=body)
        if not init.is_success or "Location" not in init.headers:
            raise YouTubeError(f"resumable init -> {init.status_code}: {init.text[:300]}")
        up = self._client.put(
            init.headers["Location"],
            headers={"Authorization": f"Bearer {token}", "Content-Type": "video/*"},
            content=mp4.read_bytes())
        if up.status_code not in (200, 201):
            raise YouTubeError(f"resumable upload -> {up.status_code}: {up.text[:300]}")
        vid = up.json()["id"]
        return {"id": vid, "url": f"https://youtu.be/{vid}"}

    def delete(self, video_id: str) -> None:
        token = self._access_token()
        r = self._client.delete(_VIDEOS_URL, params={"id": video_id},
                                headers={"Authorization": f"Bearer {token}"})
        if r.status_code not in (204, 200, 404):
            raise YouTubeError(f"delete -> {r.status_code}: {r.text[:300]}")
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_youtube.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Write the one-time token helper**

Create `scripts/mint_youtube_token.py` (run locally by the user, not by CI):

```python
"""One-time: mint a YouTube Data API refresh token.

Prereq: a Google Cloud project with the YouTube Data API v3 enabled, an OAuth
client of type "Desktop app", and the OAuth consent screen set to **Production**
(Testing-mode refresh tokens expire after 7 days). Add scope
https://www.googleapis.com/auth/youtube.upload

Usage:
    python scripts/mint_youtube_token.py --client-id XXX --client-secret YYY

It opens a browser, you approve, and it prints the three secret values to put in
GitHub → Settings → Secrets and variables → Actions:
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
"""
from __future__ import annotations
import argparse
import http.server
import secrets
import urllib.parse
import webbrowser

import httpx

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
_REDIRECT = "http://localhost:8765/"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    args = ap.parse_args()

    state = secrets.token_urlsafe(16)
    q = urllib.parse.urlencode({
        "client_id": args.client_id, "redirect_uri": _REDIRECT,
        "response_type": "code", "scope": _SCOPE, "state": state,
        "access_type": "offline", "prompt": "consent"})
    code_box: dict[str, str] = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            p = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(p.query)
            if qs.get("state", [""])[0] == state and "code" in qs:
                code_box["code"] = qs["code"][0]
                self.send_response(200); self.end_headers()
                self.wfile.write(b"OK - close this tab.")
            else:
                self.send_response(400); self.end_headers()
        def log_message(self, *a):  # noqa: A003
            pass

    print("Opening browser for Google consent...")
    webbrowser.open(f"{_AUTH}?{q}")
    srv = http.server.HTTPServer(("localhost", 8765), H)
    while "code" not in code_box:
        srv.handle_request()

    r = httpx.post(_TOKEN, data={
        "client_id": args.client_id, "client_secret": args.client_secret,
        "code": code_box["code"], "grant_type": "authorization_code",
        "redirect_uri": _REDIRECT})
    r.raise_for_status()
    rt = r.json()["refresh_token"]
    print("\n=== GitHub Secrets ===")
    print(f"YOUTUBE_CLIENT_ID={args.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={args.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={rt}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Regression**

Run: `.venv/Scripts/python.exe -m pytest tests/video -q` → PASS
Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q` → PASS (209)

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/video/publish/youtube.py scripts/mint_youtube_token.py tests/video/test_youtube.py
git commit -m "feat(p2c): YouTube upload adapter + one-time token minting helper"
```

---

## Task 3: Publish orchestrator + config + render_run wiring

**Files:**
- Modify: `src/pipeline/video/publish/__init__.py`
- Modify: `src/pipeline/video/render_run.py`
- Modify: `config/settings.yaml`
- Test: `tests/video/test_publish_orchestrator.py`

**Interfaces:**
- Consumes: `assets.upload_release_asset` / `delete_release_asset` (Task 1); `youtube.YouTube` (Task 2); `pipeline.publish.slot_unix`; `VideoMeta`; `DailyState`; a `tg` with `send_message`.
- Produces:
  - `publish_pending(ds, tg, root: Path, now: datetime, *, limit: int = 1) -> list[str]` — return strings like `"publishing:{date}:{slot}"` / `"published:{date}:{slot}"` / `"skip:{date}:{slot}"`.
  - `_PLATFORMS: dict[str, callable]` — maps a `video.publish` flag key to a `_do_<platform>(ctx) -> dict` function. Task 3 registers only `"youtube"`.
  - `_ctx` dataclass carrying `root, cfg, meta (VideoMeta), asset_url, mp4_path (Path|None)` — passed to each `_do_*`.

- [ ] **Step 1: Write the failing tests**

Create `tests/video/test_publish_orchestrator.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.daily_state import DailyState
from pipeline.video import publish as pub


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))


def _settings(root, **flags):
    (root / "config").mkdir(exist_ok=True)
    body = ["video:", "  channel_footer: \"— A Hít Official\"", "  publish:"]
    for k in ("youtube", "fb_reel", "ig_reel", "tiktok"):
        body.append(f"    {k}: {str(flags.get(k, False)).lower()}")
    body.append("    youtube_category: 27")
    (root / "config" / "settings.yaml").write_text("\n".join(body) + "\n", encoding="utf-8")


def _seed(root, *, date="2026-09-09", slot="morning", status="rendered", result=None):
    ds = DailyState(root / "data")
    v = {"status": status, "meta": {"title": "Tiêu đề video AI đủ dài mười ký",
         "description": "d", "hashtags": ["#AI"], "keywords": ["ai"],
         "tiktok_caption": "c"},
         "mp4_path": f"output/{date}/{date}-x/{date}-x.mp4",
         "tg_file_id": "TG", "asset_url": None, "publish_due": "2026-09-09T04:30:00+00:00",
         "result": result or {"youtube": None, "fb_reel": None,
                              "ig_reel": None, "tiktok": None}}
    ds.put(date, slot, status="scheduled", slot_ict="11:30", video=v)
    (root / "output" / f"{date}" / f"{date}-x").mkdir(parents=True, exist_ok=True)
    (root / "output" / f"{date}" / f"{date}-x" / f"{date}-x.mp4").write_bytes(b"MP4")
    return ds


def _patch(monkeypatch, *, yt_result=None, yt_raises=None):
    monkeypatch.setattr(pub._assets, "upload_release_asset",
                        lambda mp4, name, **k: f"https://gh/rel/{name}")
    deleted = []
    monkeypatch.setattr(pub._assets, "delete_release_asset",
                        lambda name, **k: deleted.append(name) or True)

    class _YT:
        @classmethod
        def from_env(cls): return cls()
        def upload(self, mp4, meta, cfg):
            if yt_raises:
                raise yt_raises
            return yt_result or {"id": "VID", "url": "https://youtu.be/VID"}
    monkeypatch.setattr(pub._youtube, "YouTube", _YT)
    return deleted


def test_disabled_everywhere_is_skip(tmp_path, monkeypatch):
    _settings(tmp_path)                      # all False
    ds = _seed(tmp_path)
    _patch(monkeypatch)
    assert pub.publish_pending(ds, FakeTG(), tmp_path,
                               datetime(2026, 9, 9, 5, tzinfo=timezone.utc)) == []


def test_youtube_happy_path_marks_published(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path)
    deleted = _patch(monkeypatch)
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["published:2026-09-09:morning"]
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "published" and v["published_at"]
    assert v["result"]["youtube"]["id"] == "VID"
    assert v["asset_url"] is None and deleted == ["2026-09-09-morning.mp4"]
    assert any("🚀" in m for m, _ in tg.msgs)
    assert any(btns and btns[0][1] == "vid:2026-09-09:morning:unpub" for _, btns in tg.msgs)


def test_youtube_failure_increments_attempts(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path)
    _patch(monkeypatch, yt_raises=RuntimeError("boom"))
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["publishing:2026-09-09:morning"]
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "publishing"
    assert v["result"]["youtube"]["attempts"] == 1
    assert v["result"]["youtube"]["gave_up"] is False


def test_gave_up_after_5_and_slot_can_finish(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="publishing",
               result={"youtube": {"error": "e", "attempts": 4, "last_at": "x",
                                   "gave_up": False}})
    deleted = _patch(monkeypatch, yt_raises=RuntimeError("boom"))
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["published:2026-09-09:morning"]     # gave_up counts as done
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["result"]["youtube"]["gave_up"] is True
    assert v["status"] == "published" and deleted == ["2026-09-09-morning.mp4"]
    assert any("bỏ cuộc" in m for m, _ in tg.msgs)


def test_mp4_gone_resets_to_awaiting_audio(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path)
    (tmp_path / "output" / "2026-09-09" / "2026-09-09-x" / "2026-09-09-x.mp4").unlink()
    _patch(monkeypatch)
    # also block the telegram-download fallback
    monkeypatch.setattr(pub, "_download_tg_mp4", lambda *a, **k: None)
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "awaiting_audio" and "mp4" in (v["render_err"] or "")


def test_already_published_slot_is_skipped(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="published",
               result={"youtube": {"id": "V", "url": "u", "at": "x"},
                       "fb_reel": None, "ig_reel": None, "tiktok": None})
    _patch(monkeypatch)
    assert pub.publish_pending(ds, FakeTG(), tmp_path,
                               datetime(2026, 9, 9, 5, tzinfo=timezone.utc)) == []
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_publish_orchestrator.py -q`
Expected: FAIL — `publish` has no `publish_pending`.

- [ ] **Step 3: Implement the orchestrator**

Replace `src/pipeline/video/publish/__init__.py` with:

```python
"""Phase 2C — publish a rendered video to external platforms."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..models import VideoMeta
from . import assets as _assets
from . import youtube as _youtube

log = logging.getLogger("video.publish")

_PLATFORM_LABEL = {"youtube": "YouTube", "fb_reel": "FB Reel",
                   "ig_reel": "IG Reel", "tiktok": "TikTok"}
_MAX_ATTEMPTS = 5


@dataclass
class _Ctx:
    root: Path
    cfg: dict
    meta: VideoMeta
    asset_url: str
    mp4_path: Path | None


def _cfg(root: Path) -> dict:
    data = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")) or {}
    return data.get("video") or {}


def _done(res: dict | None) -> bool:
    if not res:
        return False
    return bool(res.get("id") or res.get("gave_up")
               or res.get("status") == "draft_uploaded")


def _download_tg_mp4(tg, file_id: str, dest: Path) -> Path | None:
    try:
        return Path(tg.download_file(file_id, str(dest)))
    except Exception:  # noqa: BLE001
        log.exception("tg mp4 download failed")
        return None


# ---- per-platform actions -------------------------------------------------

def _do_youtube(ctx: _Ctx) -> dict:
    yt = _youtube.YouTube.from_env()
    if ctx.mp4_path is None:
        raise _youtube.YouTubeError("youtube needs the mp4 on disk")
    r = yt.upload(ctx.mp4_path, ctx.meta, ctx.cfg)
    return {"id": r["id"], "url": r["url"]}


_PLATFORMS = {"youtube": _do_youtube}          # Tasks 5-7 add fb_reel / ig_reel / tiktok


# ---- orchestrator -------------------------------------------------------

def publish_pending(ds, tg, root: Path, now: datetime, *, limit: int = 1) -> list[str]:
    root = Path(root)
    cfg = _cfg(root)
    enabled = [p for p in _PLATFORMS if (cfg.get("publish") or {}).get(p)]
    if not enabled:
        return []

    picked: list[tuple[str, str, dict]] = []
    for f in sorted(ds.all_files()):
        doc = ds.load_safe(f.stem)
        if doc is None:
            continue
        for slot, row in doc["posts"].items():
            v = row.get("video") or {}
            if v.get("status") not in ("rendered", "publishing"):
                continue
            if any(not _done(v.get("result", {}).get(p)) for p in enabled):
                picked.append((f.stem, slot, v))
    if not picked:
        return []

    out: list[str] = []
    for date, slot, v in picked[:limit]:
        out.append(_publish_one(ds, tg, root, cfg, enabled, date, slot, v, now))
    return out


def _publish_one(ds, tg, root, cfg, enabled, date, slot, v, now) -> str:
    # --- ensure asset ---
    asset_url = v.get("asset_url")
    mp4_path = None
    if v.get("mp4_path"):
        p = root / v["mp4_path"]
        if p.exists():
            mp4_path = p
    if not asset_url:
        src = mp4_path
        if src is None and v.get("tg_file_id"):
            src = _download_tg_mp4(tg, v["tg_file_id"], root / "output" / f"{date}-{slot}.mp4")
            mp4_path = src
        if src is None:
            cur = (ds.get_safe(date, slot) or {}).get("video") or v
            ds.put(date, slot, video={**cur, "status": "awaiting_audio",
                                      "render_err": "mp4 unavailable for publish"})
            tg.send_message(f"⚠️ {date}:{slot} không có MP4 để đăng — cần render lại.")
            return f"skip:{date}:{slot}"
        asset_url = _assets.upload_release_asset(src, f"{date}-{slot}.mp4")

    cur = (ds.get_safe(date, slot) or {}).get("video") or v
    patch = {**cur, "status": "publishing", "asset_url": asset_url}
    patch.setdefault("publish_started_at", now.isoformat())
    if not patch.get("publish_started_at"):
        patch["publish_started_at"] = now.isoformat()
    ds.put(date, slot, video=patch)

    ctx = _Ctx(root=root, cfg=cfg, meta=VideoMeta.from_dict(v["meta"]),
               asset_url=asset_url, mp4_path=mp4_path)

    for p in enabled:
        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        if cur.get("status") != "publishing":
            return f"publishing:{date}:{slot}"          # an undo landed
        res = cur.get("result", {}).get(p)
        if _done(res):
            continue
        try:
            got = _PLATFORMS[p](ctx)
            new = {**got, "at": now.isoformat()}
        except Exception as e:  # noqa: BLE001 - one platform must not block the rest
            log.exception("publish %s:%s %s failed", date, slot, p)
            attempts = int((res or {}).get("attempts", 0)) + 1
            gave_up = attempts >= _MAX_ATTEMPTS
            new = {"error": str(e)[:300], "attempts": attempts,
                   "last_at": now.isoformat(), "gave_up": gave_up}
            if gave_up:
                tg.send_message(f"⚠️ {_PLATFORM_LABEL[p]} bỏ cuộc sau {_MAX_ATTEMPTS} "
                                f"lần với {date}:{slot}: {str(e)[:200]}")
        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        ds.put(date, slot, video={**cur, "result": {**cur.get("result", {}), p: new}})

    cur = (ds.get_safe(date, slot) or {}).get("video") or v
    if all(_done(cur.get("result", {}).get(p)) for p in enabled):
        _assets.delete_release_asset(f"{date}-{slot}.mp4")
        ds.put(date, slot, video={**cur, "status": "published",
                                  "published_at": now.isoformat(), "asset_url": None})
        tg.send_message(_summary(date, slot, cur, enabled),
                        buttons=[("🗑 Gỡ tất cả", f"vid:{date}:{slot}:unpub")])
        return f"published:{date}:{slot}"
    return f"publishing:{date}:{slot}"


def _summary(date, slot, v, enabled) -> str:
    lines = [f"🚀 Video {slot} ({date}) đã đăng:"]
    for p in enabled:
        r = v.get("result", {}).get(p) or {}
        if r.get("id"):
            lines.append(f"✅ {_PLATFORM_LABEL[p]} {r.get('url', '')}".rstrip())
        elif r.get("status") == "draft_uploaded":
            lines.append(f"📥 {_PLATFORM_LABEL[p]} — mở app đăng nháp")
        else:
            lines.append(f"❌ {_PLATFORM_LABEL[p]} (bỏ cuộc)")
    return "\n".join(lines)
```

(Note the `publish_started_at` guard is written defensively twice in the draft above —
collapse to one line in your implementation: `patch.setdefault("publish_started_at",
now.isoformat())` is enough since `cur` may already carry it.)

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_publish_orchestrator.py -q`
Expected: PASS (7 tests). Fix real mismatches minimally.

- [ ] **Step 5: Wire into `render_run.py`**

Replace `src/pipeline/video/render_run.py`:

```python
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from ..daily_state import DailyState
from ..telegram import Telegram
from . import render
from .publish import publish_pending


def run(root: Path, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    ds = DailyState(root / "data")
    tg = Telegram()
    out = render.render_pending(ds, tg, root, now)
    out += publish_pending(ds, tg, root, now)
    return out


def main() -> None:
    print(run(Path(".")))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: `config/settings.yaml`**

Under the existing `video:` block, add:

```yaml
  channel_footer: "— A Hít Official · AI & năng suất mỗi ngày"
  publish:
    youtube: false
    fb_reel: false
    ig_reel: false
    tiktok: false
    youtube_category: 27
```

- [ ] **Step 7: Regression**

Run: `.venv/Scripts/python.exe -m pytest tests/video -q` → PASS
Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q` → PASS (209)
(`render_run` still importable: `python -c "import pipeline.video.render_run"`.)

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/video/publish/__init__.py src/pipeline/video/render_run.py config/settings.yaml tests/video/test_publish_orchestrator.py
git commit -m "feat(p2c): publish_pending orchestrator + render_run wiring + settings"
```

---

## Task 4: Undo, expire_stale nudge, workflow, README

**Files:**
- Modify: `src/pipeline/video/publish/__init__.py` (add `handle_unpublish`)
- Modify: `src/pipeline/article_approve.py`
- Modify: `.github/workflows/video-render.yml`
- Modify: `README.md`
- Test: `tests/test_article_approve.py`, `tests/test_workflows.py`

**Interfaces:**
- Consumes: `youtube.YouTube`, `Meta.from_env` (for `fb_delete_post` / `ig_delete_media`), `pipeline.publish.slot_unix`.
- Produces:
  - `publish.handle_unpublish(cbq: dict, ds, tg, root: Path, now: datetime) -> str | None` — parses `vid:{date}:{slot}:unpub`; returns `"unpublished:{date}:{slot}"` / `"undo-expired:{date}:{slot}"` / `None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_article_approve.py`:

```python
def test_poll_routes_vid_unpub(tmp_path, monkeypatch):
    from pipeline import article_approve
    from pipeline.state import State
    seen = {"unpub": 0, "undo": 0}
    monkeypatch.setattr(article_approve.render, "handle_undo",
                        lambda *a, **k: seen.__setitem__("undo", seen["undo"] + 1) or "x")
    monkeypatch.setattr(article_approve._pub, "handle_unpublish",
                        lambda *a, **k: seen.__setitem__("unpub", seen["unpub"] + 1) or "y")

    class FakeTelegram:
        def __init__(self, *a, **k): pass
        def get_updates(self, offset, timeout=0):
            return [{"update_id": 5, "callback_query": {"id": "c",
                     "data": "vid:2026-09-09:morning:unpub"}},
                    {"update_id": 6, "callback_query": {"id": "c2",
                     "data": "vid:2026-09-09:morning:undo"}}]
        def send_message(self, *a, **k): pass
        def answer_callback(self, *a, **k): pass
    monkeypatch.setattr(article_approve, "Telegram", FakeTelegram)
    monkeypatch.setattr(article_approve, "_meta", lambda: object())
    article_approve.poll(tmp_path, now=datetime(2026, 9, 9, 6, tzinfo=timezone.utc))
    assert seen == {"unpub": 1, "undo": 1}


def test_expire_stale_nudges_stuck_publishing_video(tmp_path):
    from pipeline import article_approve
    ds = DailyState(tmp_path / "data")
    ds.put("2026-09-09", "morning", status="scheduled", slot_ict="11:30",
           video={"status": "publishing",
                  "publish_started_at": datetime(2026, 9, 9, 0, tzinfo=timezone.utc).isoformat()})
    tg = FakeTG()
    article_approve.expire_stale(ds, tg, datetime(2026, 9, 9, 7, tzinfo=timezone.utc))
    assert any("đăng video kẹt" in m for m in tg.msgs)
    assert ds.get_safe("2026-09-09", "morning")["video"]["publish_stale_warned"] is True
    tg.msgs.clear()
    article_approve.expire_stale(ds, tg, datetime(2026, 9, 9, 8, tzinfo=timezone.utc))
    assert not any("đăng video kẹt" in m for m in tg.msgs)   # once only
```

Add to `tests/video/test_publish_orchestrator.py`:

```python
def test_handle_unpublish_deletes_and_marks(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="published",
               result={"youtube": {"id": "VID", "url": "u", "at": "x"},
                       "fb_reel": None, "ig_reel": None, "tiktok": None})
    ds.put("2026-09-09", "morning",
           video={**ds.get_safe("2026-09-09", "morning")["video"],
                  "published_at": datetime(2026, 9, 9, 5, tzinfo=timezone.utc).isoformat()})
    dels = []

    class _YT:
        @classmethod
        def from_env(cls): return cls()
        def delete(self, vid): dels.append(vid)
    monkeypatch.setattr(pub._youtube, "YouTube", _YT)
    tg = FakeTG()
    out = pub.handle_unpublish({"id": "c", "data": "vid:2026-09-09:morning:unpub"},
                               ds, tg, tmp_path,
                               datetime(2026, 9, 9, 5, 30, tzinfo=timezone.utc))
    assert out == "unpublished:2026-09-09:morning"
    assert dels == ["VID"]
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "unpublished" and v["result"]["youtube"]["undone"] is True


def test_handle_unpublish_past_grace(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="published",
               result={"youtube": {"id": "VID", "url": "u", "at": "x"},
                       "fb_reel": None, "ig_reel": None, "tiktok": None})
    ds.put("2026-09-09", "morning",
           video={**ds.get_safe("2026-09-09", "morning")["video"],
                  "published_at": datetime(2026, 9, 9, 5, tzinfo=timezone.utc).isoformat()})
    tg = FakeTG()
    out = pub.handle_unpublish({"id": "c", "data": "vid:2026-09-09:morning:unpub"},
                               ds, tg, tmp_path,
                               datetime(2026, 9, 9, 7, tzinfo=timezone.utc))   # 120 min
    assert out == "undo-expired:2026-09-09:morning"
    assert ds.get_safe("2026-09-09", "morning")["video"]["status"] == "published"
```

(`FakeTG` in `test_article_approve.py` already collects `send_message` into `.msgs` and has `answer_callback`. In `test_publish_orchestrator.py`, extend the local `FakeTG` with `def answer_callback(self, cid, text=""): pass`.)

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_article_approve.py -q -k "unpub or stuck_publishing_video"` and `... tests/video/test_publish_orchestrator.py -q -k unpublish`
Expected: FAIL — `_pub` / `handle_unpublish` missing.

- [ ] **Step 3: Add `handle_unpublish` to `publish/__init__.py`**

Append to `src/pipeline/video/publish/__init__.py`:

```python
from ...publish import slot_unix          # noqa: E402  (kept with siblings below)
from ...meta import Meta                  # noqa: E402

_UNDO_GRACE_MIN = 60


def _delete_platform(p: str, res: dict, tg) -> str | None:
    """Best-effort remote delete. Returns an error string or None."""
    try:
        if p == "youtube":
            _youtube.YouTube.from_env().delete(res["id"])
        elif p == "fb_reel":
            Meta.from_env().fb_delete_post(res["id"])
        elif p == "ig_reel":
            Meta.from_env().ig_delete_media(res["id"])
        elif p == "tiktok":
            return "TikTok: tự xoá nháp trong app"
        return None
    except Exception as e:  # noqa: BLE001
        return f"{_PLATFORM_LABEL[p]}: {e}"


def handle_unpublish(cbq: dict, ds, tg, root, now: datetime) -> str | None:
    parts = cbq.get("data", "").split(":")
    if len(parts) != 4 or parts[0] != "vid" or parts[3] != "unpub":
        return None
    _, date, slot, _ = parts
    row = ds.get_safe(date, slot) or {}
    v = row.get("video") or {}
    if v.get("status") != "published":
        _ack(tg, cbq, "Không có gì để gỡ.")
        return None
    try:
        pub_at = datetime.fromisoformat(v["published_at"])
    except (KeyError, ValueError, TypeError):
        pub_at = now
    if (now - pub_at).total_seconds() > _UNDO_GRACE_MIN * 60:
        _ack(tg, cbq, "Đăng lâu rồi — gỡ tay trên từng nền tảng.")
        tg.send_message(f"⚠️ {date}:{slot} đã đăng quá {_UNDO_GRACE_MIN} phút, gỡ thủ công.")
        return f"undo-expired:{date}:{slot}"

    errs: list[str] = []
    result = dict(v.get("result", {}))
    for p, res in list(result.items()):
        if not (res and res.get("id")) and not (res and res.get("status") == "draft_uploaded"):
            continue
        err = _delete_platform(p, res, tg)
        if err:
            errs.append(err)
        result[p] = {**res, "undone": True}
    ds.put(date, slot, video={**((ds.get_safe(date, slot) or {}).get("video") or v),
                              "status": "unpublished", "result": result})
    _ack(tg, cbq, "Đã gỡ.")
    msg = f"🗑 Đã gỡ {date}:{slot}."
    if errs:
        msg += " Lỗi: " + "; ".join(errs)
    tg.send_message(msg)
    return f"unpublished:{date}:{slot}"


def _ack(tg, cbq, text: str) -> None:
    try:
        tg.answer_callback(cbq["id"], text)
    except Exception:  # noqa: BLE001
        pass
```

- [ ] **Step 4: Route it in `article_approve.py`**

In `src/pipeline/article_approve.py`:

Add near the top imports:
```python
from .video import publish as _pub
```

In `poll()`, the callback branch currently is:
```python
            if cbq:
                data = cbq.get("data", "")
                if data.startswith("vid:"):
                    r = render.handle_undo(cbq, ds, tg, root, now)
                else:
                    r = handle_callback(cbq, ds, tg, meta, root, now)
```
Change the `vid:` line to dispatch by suffix:
```python
                if data.startswith("vid:") and data.endswith(":unpub"):
                    r = _pub.handle_unpublish(cbq, ds, tg, root, now)
                elif data.startswith("vid:"):
                    r = render.handle_undo(cbq, ds, tg, root, now)
```

In `expire_stale()`, inside the `for slot_name, slot in doc["posts"].items():` loop, after the existing `v = slot.get("video") or {}` / `rendering` block, add:
```python
            if (v.get("status") == "publishing" and v.get("publish_started_at")
                    and not v.get("publish_stale_warned")):
                try:
                    ps = datetime.fromisoformat(v["publish_started_at"])
                    if ps.tzinfo is None:
                        ps = ps.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    ps = now
                if (now - ps).total_seconds() > 6 * 3600:
                    ds.put(date, slot_name, video={**v, "publish_stale_warned": True})
                    tg.send_message(f"⚠️ {date}:{slot_name} đăng video kẹt >6h, xem log")
```

- [ ] **Step 5: `.github/workflows/video-render.yml`**

Current gate step:
```yaml
      - name: Any pending audio?
        id: g
        run: |
          if grep -lR '"audio_received"' data/daily/ 2>/dev/null | grep -q .; then
            echo "go=1" >> "$GITHUB_OUTPUT"
          else
            echo "go=0" >> "$GITHUB_OUTPUT"
          fi
```
Replace the `grep` line with a match on any of the three statuses:
```yaml
        run: |
          if grep -lRE '"(audio_received|rendered|publishing)"' data/daily/ 2>/dev/null | grep -q .; then
            echo "go=1" >> "$GITHUB_OUTPUT"
          else
            echo "go=0" >> "$GITHUB_OUTPUT"
          fi
```
Rename the render step `- name: Render pending videos` → `- name: Render + publish`, and add to its `env:` block:
```yaml
          YOUTUBE_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
          YOUTUBE_CLIENT_SECRET: ${{ secrets.YOUTUBE_CLIENT_SECRET }}
          YOUTUBE_REFRESH_TOKEN: ${{ secrets.YOUTUBE_REFRESH_TOKEN }}
          META_PAGE_ID: ${{ secrets.META_PAGE_ID }}
          META_PAGE_TOKEN: ${{ secrets.META_PAGE_TOKEN }}
          IG_BUSINESS_ID: ${{ secrets.IG_BUSINESS_ID }}
```
(`GITHUB_TOKEN` and `GITHUB_REPOSITORY` are provided automatically.)

- [ ] **Step 6: README — add "Đăng video (Phase 2C)"**

Under "Luồng video (Phase 2B)" add:

```markdown
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
```

- [ ] **Step 7: Update `tests/test_workflows.py`**

The workflow test that reads `video-render.yml` — add:
```python
    assert "YOUTUBE_REFRESH_TOKEN" in v
    assert "publishing" in v            # gate matches the publish status
```

- [ ] **Step 8: Run everything**

Run: `.venv/Scripts/python.exe -m pytest tests/video -q` → PASS
Run: `.venv/Scripts/python.exe -m pytest tests --ignore=tests/video -q` → PASS

- [ ] **Step 9: Commit**

```bash
git add src/pipeline/video/publish/__init__.py src/pipeline/article_approve.py .github/workflows/video-render.yml README.md tests/test_article_approve.py tests/test_workflows.py tests/video/test_publish_orchestrator.py
git commit -m "feat(p2c): unpublish undo, stuck-publish nudge, workflow secrets, README"
```

---

## Task 5: Facebook Reel adapter

**Files:**
- Modify: `src/pipeline/meta.py`
- Modify: `src/pipeline/video/publish/__init__.py` (register `fb_reel`)
- Test: `tests/video/test_meta_reels.py`, `tests/video/test_publish_orchestrator.py`

**Interfaces:**
- Produces: `Meta.fb_publish_reel(video_url: str, description: str) -> dict` → `{"id": str, "url": str}` (`url = https://facebook.com/reel/{id}`).

- [ ] **Step 1: Write the failing test**

Create `tests/video/test_meta_reels.py`:

```python
import httpx
import pytest
from pipeline.meta import Meta


def _meta(handler):
    m = Meta("PAGE", "TOK", "IGID")
    m._client = httpx.Client(transport=httpx.MockTransport(handler))
    return m


def test_fb_publish_reel_three_phase():
    seen = []

    def h(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen.append(f"{req.method} {url}")
        if url.endswith("/PAGE/video_reels") and b"start" in req.content:
            return httpx.Response(200, json={"video_id": "RID",
                                             "upload_url": "https://rupload.fb/RID"})
        if url == "https://rupload.fb/RID":
            assert req.headers.get("file_url") == "https://gh/rel/x.mp4"
            return httpx.Response(200, json={"success": True})
        if url.endswith("/PAGE/video_reels") and b"finish" in req.content:
            return httpx.Response(200, json={"success": True})
        if "/RID" in url and req.method == "GET":
            return httpx.Response(200, json={"status": {"video_status": "ready"}})
        return httpx.Response(500, json={"u": url})

    m = _meta(h)
    out = m.fb_publish_reel("https://gh/rel/x.mp4", "Tiêu đề\n\nMô tả #AI")
    assert out == {"id": "RID", "url": "https://facebook.com/reel/RID"}
    assert any("start" in s or "video_reels" in s for s in seen)


def test_fb_publish_reel_raises_on_error_status():
    def h(req):
        url = str(req.url)
        if url.endswith("/PAGE/video_reels") and b"start" in req.content:
            return httpx.Response(200, json={"video_id": "RID", "upload_url": "https://x/RID"})
        if url == "https://x/RID":
            return httpx.Response(200, json={"success": True})
        if b"finish" in req.content:
            return httpx.Response(200, json={"success": True})
        if req.method == "GET":
            return httpx.Response(200, json={"status": {"video_status": "error",
                                                        "processing_progress": 100}})
        return httpx.Response(500, json={})
    with pytest.raises(Exception):
        _meta(h).fb_publish_reel("https://x/x.mp4", "d")
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_meta_reels.py -q`
Expected: FAIL — `Meta` has no `fb_publish_reel`.

- [ ] **Step 3: Implement `fb_publish_reel` in `meta.py`**

Add to the `Meta` class (after `fb_create_post`):

```python
    def fb_publish_reel(self, video_url: str, description: str) -> dict:
        import time as _t
        start = self._post(f"{BASE}/{self.page_id}/video_reels",
                           data={"upload_phase": "start", "access_token": self.token})
        vid = str(start["video_id"])
        up = self._client.post(start["upload_url"],
                               headers={"Authorization": f"OAuth {self.token}",
                                        "file_url": video_url})
        _raise_for_graph(up)
        self._post(f"{BASE}/{self.page_id}/video_reels",
                   data={"upload_phase": "finish", "video_id": vid,
                         "video_state": "PUBLISHED", "description": description,
                         "access_token": self.token})
        deadline = _t.time() + 300
        while _t.time() < deadline:
            st = self._get(vid, {"fields": "status"})
            vs = (st.get("status") or {}).get("video_status")
            if vs in ("ready", "published"):
                return {"id": vid, "url": f"https://facebook.com/reel/{vid}"}
            if vs == "error":
                raise MetaError(f"fb reel {vid} processing error: {st}")
            _t.sleep(10)
        raise MetaError(f"fb reel {vid} not ready after 300s")
```

- [ ] **Step 4: Register `fb_reel` in the orchestrator**

In `src/pipeline/video/publish/__init__.py`:

```python
from ...meta import Meta          # already added in Task 4; ensure present


def _do_fb_reel(ctx: _Ctx) -> dict:
    desc = (f"{ctx.meta.title}\n\n{ctx.meta.description}".strip()
            + ("\n\n" + " ".join(ctx.meta.hashtags) if ctx.meta.hashtags else ""))
    return Meta.from_env().fb_publish_reel(ctx.asset_url, desc)


_PLATFORMS["fb_reel"] = _do_fb_reel
```

- [ ] **Step 5: Orchestrator test for two enabled platforms**

Add to `tests/video/test_publish_orchestrator.py`:

```python
def test_two_platforms_partial_then_complete(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True, fb_reel=True)
    ds = _seed(tmp_path)
    _patch(monkeypatch)                       # youtube OK
    monkeypatch.setattr(pub, "_do_fb_reel",
                        lambda ctx: (_ for _ in ()).throw(RuntimeError("fb down")))
    pub._PLATFORMS["fb_reel"] = pub._do_fb_reel
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["publishing:2026-09-09:morning"]   # fb not done yet
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["result"]["youtube"]["id"] == "VID"
    assert v["result"]["fb_reel"]["attempts"] == 1
    assert v["status"] == "publishing" and v["asset_url"]   # asset kept for retry
```

- [ ] **Step 6: Run + regression + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/video -q` and `... tests --ignore=tests/video -q` → PASS

```bash
git add src/pipeline/meta.py src/pipeline/video/publish/__init__.py tests/video/test_meta_reels.py tests/video/test_publish_orchestrator.py
git commit -m "feat(p2c): Facebook Reels publish adapter"
```

---

## Task 6: Instagram Reel adapter

**Files:**
- Modify: `src/pipeline/meta.py`
- Modify: `src/pipeline/video/publish/__init__.py` (register `ig_reel`)
- Test: `tests/video/test_meta_reels.py`

**Interfaces:**
- Produces: `Meta.ig_publish_reel(video_url: str, caption: str) -> dict` → `{"id": str, "url": str}`.

- [ ] **Step 1: Add the failing test**

Add to `tests/video/test_meta_reels.py`:

```python
def test_ig_publish_reel_create_poll_publish():
    seen = []

    def h(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen.append(f"{req.method} {url}")
        if url.endswith("/IGID/media") and req.method == "POST":
            assert b"REELS" in req.content and b"share_to_feed" in req.content
            return httpx.Response(200, json={"id": "CREATION1"})
        if "/CREATION1" in url and req.method == "GET":
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if url.endswith("/IGID/media_publish"):
            return httpx.Response(200, json={"id": "MEDIA9"})
        if "/MEDIA9" in url and req.method == "GET":
            return httpx.Response(200, json={"permalink": "https://instagram.com/reel/abc"})
        return httpx.Response(500, json={"u": url})

    out = _meta(h).ig_publish_reel("https://gh/rel/x.mp4", "caption #AI")
    assert out["id"] == "MEDIA9"
    assert out["url"] == "https://instagram.com/reel/abc"


def test_ig_publish_reel_raises_on_error_status():
    def h(req):
        url = str(req.url)
        if url.endswith("/IGID/media") and req.method == "POST":
            return httpx.Response(200, json={"id": "C1"})
        if "/C1" in url:
            return httpx.Response(200, json={"status_code": "ERROR"})
        return httpx.Response(500, json={})
    with pytest.raises(Exception):
        _meta(h).ig_publish_reel("https://x/x.mp4", "c")
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_meta_reels.py -q -k ig_publish_reel`
Expected: FAIL.

- [ ] **Step 3: Implement `ig_publish_reel` in `meta.py`**

```python
    def ig_publish_reel(self, video_url: str, caption: str) -> dict:
        import time as _t
        res = self._post(f"{BASE}/{self.ig_id}/media",
                         data={"media_type": "REELS", "video_url": video_url,
                               "caption": caption, "share_to_feed": "true",
                               "access_token": self.token})
        creation = str(res["id"])
        deadline = _t.time() + 300
        while _t.time() < deadline:
            st = self._get(creation, {"fields": "status_code"})
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code == "ERROR":
                raise MetaError(f"ig reel {creation} processing ERROR: {st}")
            _t.sleep(10)
        else:
            raise MetaError(f"ig reel {creation} not FINISHED after 300s")
        pub = self._post(f"{BASE}/{self.ig_id}/media_publish",
                         data={"creation_id": creation, "access_token": self.token})
        mid = str(pub["id"])
        try:
            link = self._get(mid, {"fields": "permalink"}).get("permalink")
        except Exception:  # noqa: BLE001
            link = None
        return {"id": mid, "url": link or f"https://instagram.com/reel/{mid}"}
```

- [ ] **Step 4: Register `ig_reel`**

In `src/pipeline/video/publish/__init__.py`:

```python
def _do_ig_reel(ctx: _Ctx) -> dict:
    cap = (f"{ctx.meta.description}".strip()
           + ("\n\n" + " ".join(ctx.meta.hashtags) if ctx.meta.hashtags else ""))
    return Meta.from_env().ig_publish_reel(ctx.asset_url, cap)


_PLATFORMS["ig_reel"] = _do_ig_reel
```

- [ ] **Step 5: Run + regression + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/video -q` and `... tests --ignore=tests/video -q` → PASS

```bash
git add src/pipeline/meta.py src/pipeline/video/publish/__init__.py tests/video/test_meta_reels.py
git commit -m "feat(p2c): Instagram Reels publish adapter"
```

---

## Task 7: TikTok draft adapter + refresh-token rotation

**Files:**
- Create: `src/pipeline/video/publish/tiktok.py`
- Modify: `src/pipeline/video/publish/__init__.py` (register `tiktok`)
- Modify: `.github/workflows/video-render.yml` (TikTok + `GH_PAT` secrets)
- Modify: `README.md` (TikTok secrets)
- Test: `tests/video/test_tiktok.py`

**Interfaces:**
- Consumes: env `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`, optional `GH_PAT`, `GITHUB_REPOSITORY`.
- Produces:
  - `TikTok.from_env() -> TikTok`
  - `TikTok.upload_draft(video_url: str, caption: str, *, tg=None) -> dict` → `{"status": "draft_uploaded"}`. Refreshes the access token, persists the rotated refresh token (via `gh secret set` when `GH_PAT` is present, else Telegram), then calls the inbox init endpoint.
  - `TikTokError(RuntimeError)`

- [ ] **Step 1: Write the failing tests**

Create `tests/video/test_tiktok.py`:

```python
import subprocess
import httpx
import pytest
from pipeline.video.publish.tiktok import TikTok, TikTokError


def _tt(handler, **env):
    t = TikTok("CK", "CS", "OLD_RT")
    t._client = httpx.Client(transport=httpx.MockTransport(handler))
    return t


def _handler(*, new_rt="NEW_RT", init_status=200):
    def h(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.startswith("https://open.tiktokapis.com/v2/oauth/token/"):
            return httpx.Response(200, json={"access_token": "ATK", "refresh_token": new_rt,
                                             "expires_in": 86400})
        if "post/publish/inbox/video/init/" in url:
            assert b"PULL_FROM_URL" in req.content
            return httpx.Response(init_status, json={"data": {"publish_id": "PUB1"},
                                                     "error": {"code": "ok"}})
        return httpx.Response(500, json={"u": url})
    return h


def test_upload_draft_persists_rotated_token_via_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: calls.append(a[0]) or subprocess.CompletedProcess(a[0], 0))
    monkeypatch.setenv("GH_PAT", "PAT")
    monkeypatch.setenv("GITHUB_REPOSITORY", "omidot/ai-social-automation")
    t = _tt(_handler(new_rt="ROTATED"))
    out = t.upload_draft("https://gh/rel/x.mp4", "cap #AI")
    assert out == {"status": "draft_uploaded"}
    assert any("gh" in c[0] and "TIKTOK_REFRESH_TOKEN" in " ".join(c) for c in calls)


def test_upload_draft_telegrams_token_without_pat(monkeypatch):
    monkeypatch.delenv("GH_PAT", raising=False)

    class TG:
        def __init__(self): self.msgs = []
        def send_message(self, t, buttons=None): self.msgs.append(t)
    tg = TG()
    t = _tt(_handler(new_rt="ROTATED2"))
    t.upload_draft("https://gh/rel/x.mp4", "cap", tg=tg)
    assert any("ROTATED2" in m and "TIKTOK_REFRESH_TOKEN" in m for m in tg.msgs)


def test_upload_draft_raises_on_init_error(monkeypatch):
    monkeypatch.delenv("GH_PAT", raising=False)
    t = _tt(_handler(init_status=403))
    with pytest.raises(TikTokError):
        t.upload_draft("https://gh/rel/x.mp4", "cap")
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/Scripts/python.exe -m pytest tests/video/test_tiktok.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `tiktok.py`**

```python
from __future__ import annotations
import os
import subprocess

import httpx

_TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
_INBOX = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"


class TikTokError(RuntimeError):
    pass


class TikTok:
    def __init__(self, client_key: str, client_secret: str, refresh_token: str):
        self.client_key = client_key
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._client = httpx.Client(timeout=120.0)

    @classmethod
    def from_env(cls) -> "TikTok":
        return cls(os.environ["TIKTOK_CLIENT_KEY"],
                   os.environ["TIKTOK_CLIENT_SECRET"],
                   os.environ["TIKTOK_REFRESH_TOKEN"])

    def _refresh(self, tg=None) -> str:
        r = self._client.post(_TOKEN, data={
            "client_key": self.client_key, "client_secret": self.client_secret,
            "grant_type": "refresh_token", "refresh_token": self.refresh_token})
        if not r.is_success:
            raise TikTokError(f"tiktok token refresh -> {r.status_code}: {r.text[:300]}")
        body = r.json()
        new_rt = body.get("refresh_token")
        if new_rt and new_rt != self.refresh_token:
            self._persist_refresh_token(new_rt, tg)
            self.refresh_token = new_rt
        return body["access_token"]

    def _persist_refresh_token(self, new_rt: str, tg=None) -> None:
        pat = os.environ.get("GH_PAT")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if pat and repo:
            subprocess.run(
                ["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN",
                 "--body", new_rt, "--repo", repo],
                env={**os.environ, "GH_TOKEN": pat},
                check=True, capture_output=True, text=True)
            return
        if tg is not None:
            tg.send_message("🔑 TikTok refresh token vừa xoay vòng — cập nhật GitHub "
                            f"Secret `TIKTOK_REFRESH_TOKEN`:\n{new_rt}")

    def upload_draft(self, video_url: str, caption: str, *, tg=None) -> dict:
        access = self._refresh(tg)
        r = self._client.post(
            _INBOX,
            headers={"Authorization": f"Bearer {access}",
                     "Content-Type": "application/json; charset=UTF-8"},
            json={"source_info": {"source": "PULL_FROM_URL", "video_url": video_url}})
        if not r.is_success:
            raise TikTokError(f"tiktok inbox init -> {r.status_code}: {r.text[:300]}")
        err = (r.json().get("error") or {}).get("code", "ok")
        if err not in ("ok", "", None):
            raise TikTokError(f"tiktok inbox init error: {r.json().get('error')}")
        return {"status": "draft_uploaded"}
```

(`caption` is accepted for parity/logging; the inbox endpoint does not take a caption —
the user writes it in the app. Keep the parameter.)

- [ ] **Step 4: Register `tiktok` in the orchestrator**

In `src/pipeline/video/publish/__init__.py`:

```python
from . import tiktok as _tiktok


def _do_tiktok(ctx: _Ctx) -> dict:
    return _tiktok.TikTok.from_env().upload_draft(ctx.asset_url, ctx.meta.tiktok_caption)


_PLATFORMS["tiktok"] = _do_tiktok
```

Add a `tg` hook: `_do_tiktok` cannot see `tg`. Extend `_Ctx` with `tg=None` and set it in
`_publish_one` (`ctx = _Ctx(..., tg=tg)`), then `_do_tiktok` passes `tg=ctx.tg` to
`upload_draft`. Update the `_Ctx` dataclass and the one construction site.

- [ ] **Step 5: Workflow + README**

`.github/workflows/video-render.yml` — add to the render step `env:`:
```yaml
          TIKTOK_CLIENT_KEY: ${{ secrets.TIKTOK_CLIENT_KEY }}
          TIKTOK_CLIENT_SECRET: ${{ secrets.TIKTOK_CLIENT_SECRET }}
          TIKTOK_REFRESH_TOKEN: ${{ secrets.TIKTOK_REFRESH_TOKEN }}
          GH_PAT: ${{ secrets.GH_PAT }}
```

`README.md` — under the Phase 2C section, append:
```markdown
- TikTok: đăng vào hộp nháp (app chưa audit). Secrets `TIKTOK_CLIENT_KEY/SECRET/
  REFRESH_TOKEN` + `GH_PAT` (fine-grained PAT repo này, quyền Secrets: read/write —
  để workflow tự ghi lại refresh token TikTok mỗi lần xoay vòng). Không có `GH_PAT`
  thì bot Telegram token mới cho bạn dán tay.
```

- [ ] **Step 6: `tests/test_workflows.py`** — add `assert "TIKTOK_REFRESH_TOKEN" in v`.

- [ ] **Step 7: Run everything + commit**

Run: `.venv/Scripts/python.exe -m pytest tests -q` (both suites) → PASS

```bash
git add src/pipeline/video/publish/tiktok.py src/pipeline/video/publish/__init__.py .github/workflows/video-render.yml README.md tests/video/test_tiktok.py tests/test_workflows.py
git commit -m "feat(p2c): TikTok inbox-draft adapter with refresh-token rotation"
```

---

## Self-Review

**Spec coverage:**
- §2.1 four platforms, YT-first, per-platform flag → Tasks 2–7 + `video.publish` block (Task 3).
- §2.2 Release asset host → Task 1; consumed in Task 3 `_publish_one`.
- §2.3 folded into `video-render.yml` → Task 3 (`render_run`), Task 4 (workflow env + gate).
- §2.4 public publish + `🗑 Gỡ tất cả` + TikTok draft → Task 3 summary/button, Task 4 `handle_unpublish`, Task 7 TikTok.
- §2.5 `mint_youtube_token.py` → Task 2.
- §2.6 FB/IG reuse `META_PAGE_TOKEN` → Tasks 5–6 (`Meta.from_env()`).
- §3 state machine, `result` shape, new `video` keys → Task 3 (`_done`, `publish_started_at`, `asset_url`, `published_at`), Task 4 (`publish_stale_warned`).
- §4 orchestrator steps 1–7 → Task 3 `publish_pending` / `_publish_one`; `expire_stale` nudge → Task 4.
- §5.1 assets → Task 1. §5.2 YouTube → Task 2. §5.3 FB → Task 5. §5.4 IG → Task 6. §5.5 TikTok + rotation → Task 7. §5.6 metadata mapping → the `_do_*` functions.
- §6 undo `vid:*:unpub`, 60-min grace, per-platform delete, `unpublished` → Task 4.
- §7 workflow gate + env + config + secrets → Tasks 3–4 (+ 7 for TikTok).
- §8 module layout → File Structure table; each adapter isolated + mock-tested.
- §9 test list → every task's test steps.
- §10 build order → Task order 1→7.
- §11 out of scope — nothing in the plan adds scheduling / analytics / per-platform re-encode / thumbnails.

**Placeholder scan:** no "TBD"/"handle appropriately"/"similar to". The Task 3 `publish_started_at` double-guard is called out with the one-line collapse to use. Task 7 Step 4 spells out the `_Ctx.tg` addition explicitly.

**Type consistency:** `publish_pending(ds, tg, root, now, *, limit=1)` and `handle_unpublish(cbq, ds, tg, root, now)` match §4/§6 and the Task 4 routing. `_PLATFORMS` keys (`youtube`/`fb_reel`/`ig_reel`/`tiktok`) match the `video.publish` flags and `video.result` keys throughout. Adapter returns are uniform `{"id","url"}` (or `{"status":"draft_uploaded"}` for TikTok), consumed identically by `_publish_one` and `_summary`. `YouTube.upload(mp4, meta, cfg)`, `Meta.fb_publish_reel(video_url, description)`, `Meta.ig_publish_reel(video_url, caption)`, `TikTok.upload_draft(video_url, caption, *, tg=None)` — all as declared in their task Interfaces blocks and called with matching args in the `_do_*` functions.
