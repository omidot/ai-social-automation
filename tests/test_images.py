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
    art = _art()
    out = images.build_images(art, tmp_path, style_prompt="cinematic",
                              size=(1080, 1350), gen=fake_gen)
    assert len(out) == 3                      # templated cover + 2 briefs
    # cover is now fully Pillow-rendered: gen() runs once per brief, not for the cover
    assert len(calls) == len(art.image_briefs)
    assert all("cinematic" in p for p in calls)
    assert Path(out[0]).name == "01_cover.jpg"
    assert all(Path(p).exists() for p in out)
    cover = Image.open(out[0]).convert("RGB")
    assert cover.size == (1080, 1350)
    # background is mostly light near the corners
    W, H = cover.size
    for xy in [(8, 8), (W - 8, 8), (8, H - 8), (W - 8, H - 8)]:
        px = cover.getpixel(xy)
        assert all(c > 220 for c in px), (xy, px)


def test_render_cover_has_brand_elements():
    art = ArticleContent(format="roundup", caption_fb="x", caption_ig="y",
                         hashtags=["#AI"], cover_title="Ba tin AI đáng chú ý hôm nay",
                         cover_brief="b", image_briefs=["a"],
                         sources=[{"name": "hn", "url": "http://h"}])
    img = images._render_cover(art, (1080, 1350), images.BRAND_DEFAULTS)
    assert img.size == (1080, 1350)
    px = img.load()
    W, H = img.size
    near_black = brand_blue = False
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            r, g, bl = px[x, y]
            if r < 60 and g < 60 and bl < 60:
                near_black = True
            if bl > 150 and r < 120 and g < 130:
                brand_blue = True
        if near_black and brand_blue:
            break
    assert near_black, "expected near-black headline pixels"
    assert brand_blue, "expected brand-blue pill pixels"

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

def test_provider_legacy_skips_gemini(tmp_path, monkeypatch):
    def boom_gen(prompt, size):
        raise AssertionError("gen must not be called when provider='legacy'")
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda art, od, size: [str(tmp_path / "l.jpg")])
    out = images.build_images(_art(), tmp_path, style_prompt="x",
                              size=(1080, 1350), gen=boom_gen, provider="legacy")
    assert out == [str(tmp_path / "l.jpg")]

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
