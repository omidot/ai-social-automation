import io
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
import pytest
from pipeline.models import Candidate, PostContent
from pipeline import media


def _png_bytes(w=1200, h=630, color=(20, 40, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _post():
    return PostContent(angle="tin-tuc", caption_fb="a", caption_ig="b", hashtags=["#AI"],
                       thumbnail_prompt="glowing neural net", thumbnail_title="OPENAI RA MODEL MỚI",
                       youtube_title="y", youtube_desc="d", tiktok_caption="t",
                       source_url="https://openai.com/x", source_name="OpenAI Blog")


def _cand():
    return Candidate(url="https://openai.com/x", title="t", source="rss:OpenAI Blog",
                     published_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                     top_image="https://img/hero.jpg")


def test_make_thumbnail_dimensions(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes())
    dest = tmp_path / "01.jpg"
    out = media.make_thumbnail("neural", "TIÊU ĐỀ TIẾNG VIỆT CÓ DẤU", dest, "A Hít Official")
    with Image.open(out) as im:
        assert im.size == (1200, 630)


def test_make_thumbnail_gradient_fallback_on_download_error(tmp_path, monkeypatch):
    def boom(url, timeout=60):
        raise RuntimeError("pollinations down")
    monkeypatch.setattr(media, "_download", boom)
    out = media.make_thumbnail("x", "DỰ PHÒNG", tmp_path / "01.jpg", "A Hít Official")
    with Image.open(out) as im:
        assert im.size == (1200, 630)


def test_fetch_source_image_rejects_small(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes(100, 100))
    assert media.fetch_source_image("https://img/small.jpg", tmp_path / "02.jpg") is None


def test_fetch_source_image_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes(1000, 800))
    out = media.fetch_source_image("https://img/big.jpg", tmp_path / "02.jpg")
    assert out and Path(out).exists()


def test_build_media_orders_and_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download", lambda url, timeout=60: _png_bytes(1000, 800))
    monkeypatch.setattr(media, "_shoot", lambda url, dest: Image.new("RGB", (1280, 800)).save(dest))
    paths, low = media.build_media(_cand(), _post(), tmp_path, "A Hít Official")
    assert 3 <= len(paths) <= 4
    assert Path(paths[0]).name.startswith("01_thumbnail")
    assert low is False


def test_build_media_low_flag_when_few(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "_download",
                        lambda url, timeout=60: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(media, "_shoot",
                        lambda url, dest: (_ for _ in ()).throw(RuntimeError("x")))
    cand = _cand()
    cand.top_image = None
    paths, low = media.build_media(cand, _post(), tmp_path, "A Hít Official")
    assert paths and Path(paths[0]).exists()
    assert low is True
