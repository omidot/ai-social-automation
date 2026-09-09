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
