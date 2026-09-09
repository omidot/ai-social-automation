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
