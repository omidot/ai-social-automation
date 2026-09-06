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
                        lambda art, od: [str(tmp_path / "legacy.jpg")])
    out = images.build_images(_art(), tmp_path, style_prompt="x", size=(1080, 1350), gen=boom)
    assert out == [str(tmp_path / "legacy.jpg")]
