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
