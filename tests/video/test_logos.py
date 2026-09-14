import httpx
import pytest

from pipeline.video import logos
from pipeline.video.logos import LogoError


def test_detects_brands_in_order_without_duplicates():
    got = logos.detect_brands("GPT-6 Astra đấu Claude Fable 5.1, và Claude lại thắng")
    assert got == ["gpt", "claude", "fable"]


def test_detects_brands_regardless_of_spacing_and_case():
    assert logos.detect_brands("chatgpt") == ["chatgpt"]
    assert logos.detect_brands("DeepSeek") == ["deepseek"]
    assert logos.detect_brands("Hugging Face") == ["huggingface"] or \
        logos.detect_brands("huggingface") == ["huggingface"]


def test_ignores_text_with_no_brand():
    assert logos.detect_brands("hôm nay trời đẹp") == []
    assert logos.detect_brands("") == []


def test_every_brand_maps_to_a_label_and_domain():
    for key, value in logos.BRANDS.items():
        label, domain = value
        assert label and domain
        assert "." in domain, f"{key} must map to a real domain"


def test_fetch_logo_writes_the_bytes(tmp_path, monkeypatch):
    calls = {}

    def fake_get(url, **kw):
        calls["domain"] = kw["params"]["domain"]
        return httpx.Response(200, content=b"\x89PNG-logo-bytes")

    monkeypatch.setattr(logos.httpx, "get", fake_get)
    dest = tmp_path / "logos" / "openai.png"
    logos.fetch_logo("openai.com", dest)
    assert dest.read_bytes() == b"\x89PNG-logo-bytes"
    assert calls["domain"] == "openai.com"


def test_fetch_logo_reuses_cache_without_network(tmp_path, monkeypatch):
    dest = tmp_path / "logos" / "openai.png"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"cached")

    def boom(*a, **k):
        raise AssertionError("must not hit the network when cached")

    monkeypatch.setattr(logos.httpx, "get", boom)
    assert logos.fetch_logo("openai.com", dest) == dest
    assert dest.read_bytes() == b"cached"


def test_fetch_logo_raises_on_bad_response(tmp_path, monkeypatch):
    monkeypatch.setattr(logos.httpx, "get", lambda url, **kw: httpx.Response(404))
    with pytest.raises(LogoError):
        logos.fetch_logo("nope.example", tmp_path / "x.png")


def test_fetch_logo_raises_on_empty_body(tmp_path, monkeypatch):
    """A 200 with no bytes would otherwise leave a 0-byte file that renders
    as a broken image instead of degrading to no logo at all."""
    monkeypatch.setattr(logos.httpx, "get", lambda url, **kw: httpx.Response(200, content=b""))
    with pytest.raises(LogoError):
        logos.fetch_logo("empty.example", tmp_path / "x.png")


def test_fetch_logo_wraps_transport_errors(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(logos.httpx, "get", boom)
    with pytest.raises(LogoError):
        logos.fetch_logo("openai.com", tmp_path / "x.png")


def test_collect_logos_returns_label_and_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(logos.httpx, "get",
                        lambda url, **kw: httpx.Response(200, content=b"png"))
    got = logos.collect_logos("GPT-6 vs Claude", tmp_path)
    assert got["gpt"] == {"label": "OpenAI", "file": "logos/gpt.png"}
    assert got["claude"] == {"label": "Anthropic", "file": "logos/claude.png"}
    assert (tmp_path / "logos/gpt.png").exists()


def test_collect_logos_skips_a_brand_that_fails(tmp_path, monkeypatch):
    """One unreachable logo must not cost the whole video -- the brand is
    dropped and the rest still render."""
    def selective(url, **kw):
        if kw["params"]["domain"] == "openai.com":
            raise httpx.ConnectError("down")
        return httpx.Response(200, content=b"png")

    monkeypatch.setattr(logos.httpx, "get", selective)
    got = logos.collect_logos("GPT-6 vs Claude", tmp_path)
    assert "gpt" not in got
    assert got["claude"]["label"] == "Anthropic"
