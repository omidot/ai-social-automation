from pathlib import Path
import httpx
import pytest
from pipeline.video import screenshot as sc


def test_search_top_url_returns_first_result(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert params["q"] == "GitHub OpenAI Codex"
        assert params["key"] == "K" and params["cx"] == "CX"
        return httpx.Response(200, json={"items": [{"link": "https://github.com/openai/codex"},
                                                    {"link": "https://example.com/other"}]},
                              request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", fake_get)
    url = sc.search_top_url("GitHub OpenAI Codex", api_key="K", cx="CX")
    assert url == "https://github.com/openai/codex"


def test_search_top_url_raises_on_no_results(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"items": []}, request=httpx.Request("GET", "https://x")))
    with pytest.raises(sc.ScreenshotError, match="no results"):
        sc.search_top_url("truly nonexistent query", api_key="K", cx="CX")


def test_search_top_url_raises_on_http_error(monkeypatch):
    def fake_get(*a, **k):
        return httpx.Response(403, json={"error": "quota"}, request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(sc.ScreenshotError):
        sc.search_top_url("q", api_key="K", cx="CX")


def test_search_top_url_raises_on_malformed_json_body(monkeypatch):
    def fake_get(*a, **k):
        r = httpx.Response(200, content=b"not json", request=httpx.Request("GET", "https://x"))
        return r
    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(sc.ScreenshotError, match="malformed"):
        sc.search_top_url("q", api_key="K", cx="CX")


def test_search_top_url_raises_when_result_missing_link(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"items": [{"title": "no link field here"}]},
        request=httpx.Request("GET", "https://x")))
    with pytest.raises(sc.ScreenshotError, match="malformed"):
        sc.search_top_url("q", api_key="K", cx="CX")


def test_search_and_capture_calls_search_then_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "search_top_url", lambda q, *, api_key, cx, timeout=10: "https://found.example")
    captured = {}
    def fake_capture(url, dest):
        captured.update(url=url, dest=dest)
        Path(dest).write_bytes(b"\x89PNG")
    monkeypatch.setattr(sc._media, "capture_screenshot", fake_capture)
    out_path = tmp_path / "shot.png"
    url = sc.search_and_capture("q", out_path, api_key="K", cx="CX")
    assert url == "https://found.example"
    assert captured == {"url": "https://found.example", "dest": out_path}


def test_search_and_capture_raises_on_empty_file(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "search_top_url", lambda q, *, api_key, cx, timeout=10: "https://found.example")
    def fake_capture(url, dest):
        Path(dest).touch()  # "succeeds" but writes nothing
    monkeypatch.setattr(sc._media, "capture_screenshot", fake_capture)
    with pytest.raises(sc.ScreenshotError, match="empty file"):
        sc.search_and_capture("q", tmp_path / "shot.png", api_key="K", cx="CX")


def test_search_and_capture_propagates_capture_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "search_top_url", lambda q, *, api_key, cx, timeout=10: "https://found.example")
    def boom(url, dest):
        raise RuntimeError("playwright timeout")
    monkeypatch.setattr(sc._media, "capture_screenshot", boom)
    with pytest.raises(sc.ScreenshotError, match="playwright timeout"):
        sc.search_and_capture("q", tmp_path / "shot.png", api_key="K", cx="CX")
