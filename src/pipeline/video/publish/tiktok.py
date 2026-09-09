"""Phase 2C — TikTok inbox-draft adapter with single-use refresh-token rotation.

The app is unaudited, so we can only push the video into the user's TikTok
*inbox* (draft). The user opens the app and finishes the post (caption, cover,
privacy) by hand. TikTok rotates the refresh token on every refresh, so we
persist the new one — via `gh secret set` when a PAT is available, else we
Telegram it for a manual paste.
"""
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
        self._client = httpx.Client(timeout=120)

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
