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
        desc = desc[:4900]
        tags: list[str] = []
        total = 0
        for t in meta.keywords:
            total += len(t) + 1
            if total > 450:
                break
            tags.append(t)
        body = {
            "snippet": {"title": title, "description": desc,
                        "tags": tags,
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
