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
