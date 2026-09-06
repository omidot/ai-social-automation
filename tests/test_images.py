from pathlib import Path
import pytest
from PIL import Image
from pipeline import images
from pipeline.models import ArticleContent


def _art(slides=None):
    return ArticleContent(
        format="deep", caption_fb="x", caption_ig="y", hashtags=["#AI"],
        cover_title="TIN AI HÔM NAY",
        slides=slides if slides is not None else [
            {"headline": "A", "sub": "x"}, {"headline": "B", "sub": "y"}],
        sources=[{"name": "hn", "url": "http://h"}])


def _is_light(path):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    for xy in [(8, 8), (W - 8, 8), (8, H - 8), (W - 8, H - 8)]:
        if not all(c > 220 for c in im.getpixel(xy)):
            return False
    return True


def test_build_images_renders_cover_and_slides(tmp_path):
    art = _art([{"headline": "A", "sub": "x"}, {"headline": "B", "sub": "y"}])
    out = images.build_images(art, tmp_path, size=(1080, 1350), brand=None)
    assert len(out) == 3                                  # cover + 2 slides
    assert Path(out[0]).name == "01_cover.jpg"
    assert [Path(p).name for p in out[1:]] == ["02.jpg", "03.jpg"]
    assert all(Path(p).exists() for p in out)
    for p in out:
        assert Image.open(p).size == (1080, 1350)
        assert _is_light(p), p


def test_build_images_ignores_retired_kwargs(tmp_path):
    # style_prompt / provider / gen are gone; passing them must not raise
    out = images.build_images(_art(), tmp_path, size=(1080, 1350),
                              style_prompt="cinematic", provider="gemini", gen=object())
    assert len(out) == 3


def test_render_slide_has_text():
    img = images._render_slide(1, 3, {"headline": "Tiêu đề ngắn",
                                      "sub": "Một câu bài học"}, (1080, 1350), None)
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
    assert near_black, "expected near-black text pixels"
    assert brand_blue, "expected brand-blue marker/underline pixels"


def test_render_cover_has_brand_elements():
    art = ArticleContent(format="roundup", caption_fb="x", caption_ig="y",
                         hashtags=["#AI"], cover_title="Ba tin AI đáng chú ý hôm nay",
                         slides=[{"headline": "a", "sub": "b"}] * 3,
                         sources=[{"name": "hn", "url": "http://h"}])
    img = images._render_cover(art, (1080, 1350), images.BRAND_DEFAULTS)
    assert img.size == (1080, 1350)
    px = img.load()
    W, H = img.size
    near_black = brand_blue = highlight = tile_white = False
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            r, g, bl = px[x, y]
            if r < 45 and g < 55 and bl < 65:          # headline ink / icon strokes
                near_black = True
            if abs(r - 29) < 45 and abs(g - 78) < 45 and abs(bl - 216) < 55:  # #1D4ED8
                brand_blue = True
            if abs(r - 219) < 22 and abs(g - 231) < 22 and abs(bl - 255) < 12:  # #DBE7FF
                highlight = True
            if y > H // 2 and r > 246 and g > 246 and bl > 246:  # frosted tile
                tile_white = True
    assert near_black, "expected near-black headline pixels"
    assert brand_blue, "expected brand-blue pill/underline pixels"
    assert highlight, "expected light-blue highlight pixels behind the last line"
    assert tile_white, "expected white high-alpha tile pixels in the lower half"


def test_cover_has_icon_fan():
    art = ArticleContent(format="roundup", caption_fb="x", caption_ig="y",
                         hashtags=["#AI"], cover_title="Nam tin AI dang chu y hom nay",
                         slides=[{"headline": h, "sub": "s"} for h in "ABCDE"],
                         sources=[{"name": "hn", "url": "http://h"}])
    img = images._render_cover(art, (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    y0, y1 = int(H * 0.60), int(H * 0.85)
    bright = []
    for x in range(0, W, 4):
        run = best = 0
        for y in range(y0, y1, 4):
            r, g, bl = px[x, y]
            if r > 245 and g > 245 and bl > 245:
                run += 1
                best = max(best, run)
            else:
                run = 0
        bright.append(best >= 3)
    clusters = prev = 0
    for cur in bright:
        if cur and not prev:
            clusters += 1
        prev = cur
    assert clusters >= 5, f"expected >=5 tile clusters in the fan band, got {clusters}"


def test_each_icon_fn_draws_something():
    from PIL import ImageDraw
    for name, fn in images._ICONS.items():
        im = Image.new("RGB", (128, 128), "white")
        fn(ImageDraw.Draw(im), (16, 16, 112, 112), "#1F2937")
        px = im.load()
        nonwhite = sum(1 for y in range(128) for x in range(128)
                       if px[x, y] != (255, 255, 255))
        assert nonwhite >= 40, f"{name} drew only {nonwhite} non-white px"


def test_build_images_falls_back_to_legacy_when_cover_render_fails(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("render broke")

    monkeypatch.setattr(images, "_render_cover", boom)
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda art, od, size: [str(tmp_path / "legacy.jpg")])
    out = images.build_images(_art(), tmp_path, size=(1080, 1350))
    assert out == [str(tmp_path / "legacy.jpg")]


def test_build_images_slide_render_error_returns_cover_only(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("slide broke")

    monkeypatch.setattr(images, "_render_slide", boom)
    called = []
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda *a, **k: called.append(1) or ["nope"])
    out = images.build_images(_art(), tmp_path, size=(1080, 1350))
    assert len(out) == 1
    assert Path(out[0]).name == "01_cover.jpg" and Path(out[0]).exists()
    assert not called, "must not fall to legacy media when only a slide fails"


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
