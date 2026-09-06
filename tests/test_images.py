from pathlib import Path
import pytest
from PIL import Image
import io
from pipeline import images
from pipeline.models import ArticleContent

def _art():
    return ArticleContent(format="deep", caption_fb="x", caption_ig="y", hashtags=["#AI"],
                          cover_title="TIN AI HÔM NAY", cover_brief="neural core",
                          image_briefs=["a", "b"], sources=[{"name": "hn", "url": "http://h"}])

def _png_bytes(color=(20, 40, 120)):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()

def test_build_images_gemini_path(tmp_path):
    calls = []
    def fake_gen(prompt, size):
        calls.append(prompt)
        return _png_bytes()
    out = images.build_images(_art(), tmp_path, style_prompt="cinematic",
                              size=(1080, 1350), gen=fake_gen)
    assert len(out) == 3                      # cover + 2 briefs
    assert Path(out[0]).name == "01_cover.jpg"
    assert all(Path(p).exists() for p in out)
    assert Image.open(out[0]).size == (1080, 1350)
    assert "cinematic" in calls[0]

def test_build_images_falls_back_on_error(tmp_path, monkeypatch):
    def boom(prompt, size):
        raise RuntimeError("quota")
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda art, od, size: [str(tmp_path / "legacy.jpg")])
    out = images.build_images(_art(), tmp_path, style_prompt="x", size=(1080, 1350), gen=boom)
    assert out == [str(tmp_path / "legacy.jpg")]

def test_build_images_falls_back_on_undecodable_bytes(tmp_path, monkeypatch):
    # realistic Gemini failure: gen() returns bytes PIL cannot decode
    def bad_gen(prompt, size):
        return b"not-an-image"
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda art, od, size: [str(tmp_path / "legacy.jpg")])
    out = images.build_images(_art(), tmp_path, style_prompt="x",
                              size=(1080, 1350), gen=bad_gen)
    assert out == [str(tmp_path / "legacy.jpg")]

def test_legacy_fallback_normalizes_to_size(tmp_path, monkeypatch):
    size = (1080, 1350)

    def fake_build_media(cand, post, outdir, channel):
        d = Path(outdir)
        d.mkdir(parents=True, exist_ok=True)
        p1, p2 = d / "01_thumbnail.jpg", d / "02_source.jpg"
        Image.new("RGB", (1200, 630), (10, 20, 30)).save(p1, format="JPEG")
        Image.new("RGB", (800, 800), (40, 50, 60)).save(p2, format="JPEG")
        return [str(p1), str(p2)], False

    monkeypatch.setattr(images.media, "build_media", fake_build_media)
    out = images._legacy_fallback(_art(), tmp_path, size)
    assert len(out) == 2
    assert all(Image.open(p).size == size for p in out)
