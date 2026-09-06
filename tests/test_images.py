from pathlib import Path
import pytest
from PIL import Image
from pipeline import images
from pipeline.models import ArticleContent

ROLES = ["hook", "what", "why", "how", "close"]


def _art(slides=None):
    return ArticleContent(
        format="share", caption_fb="x", caption_ig="y", hashtags=["#AI"],
        cover_title="AI GIỜ LÀM ĐƯỢC VIỆC NÀY",
        slides=slides if slides is not None else [
            {"role": r, "headline": f"Tiêu đề {r}", "body": f"Một dòng nội dung {r} hơi dài"}
            for r in ROLES],
        sources=[{"name": "hn", "url": "http://h"}])


def _is_light(path):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    for xy in [(8, 8), (W - 8, 8), (8, H - 8), (W - 8, H - 8)]:
        if not all(c > 220 for c in im.getpixel(xy)):
            return False
    return True


def _band_has_brand_blue(path, y0, y1):
    im = Image.open(path).convert("RGB")
    W, _ = im.size
    px = im.load()
    for y in range(y0, y1):
        for x in range(0, W, 2):
            r, g, bl = px[x, y]
            if abs(r - 29) < 45 and abs(g - 78) < 45 and abs(bl - 216) < 55:
                return True
    return False


def test_build_images_renders_5_storyboard_slides(tmp_path):
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), brand=None)
    assert len(out) == 5
    assert [Path(p).name for p in out] == ["01.jpg", "02.jpg", "03.jpg", "04.jpg", "05.jpg"]
    for p in out:
        assert Path(p).exists()
        assert Image.open(p).size == (1080, 1350)
        assert _is_light(p), p


def test_every_slide_has_progress_bar(tmp_path):
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), brand=None)
    assert len(out) == 5
    for p in out:
        # the progress bar sits in a thin band near the top (~y=92, seg_h=12)
        assert _band_has_brand_blue(p, 80, 112), f"no filled progress segment on {p}"


def test_hook_slide_has_icon_fan():
    img = images._render_hook_slide(_art(), (1080, 1350), images.BRAND_DEFAULTS)
    assert img.size == (1080, 1350)
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
    assert clusters >= 5, f"expected >=5 frosted tile clusters, got {clusters}"


def test_hook_slide_has_highlighted_headline():
    img = images._render_hook_slide(_art(), (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    near_black = highlight = False
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            r, g, bl = px[x, y]
            if r < 45 and g < 55 and bl < 65:
                near_black = True
            if abs(r - 219) < 22 and abs(g - 231) < 22 and abs(bl - 255) < 12:  # #DBE7FF
                highlight = True
    assert near_black, "expected near-black headline ink"
    assert highlight, "expected the light-blue highlight block behind the last line"


def test_step_slide_has_pill_and_body():
    slide = {"role": "how", "headline": "Bắt đầu thế nào", "body": "Viết kịch bản ngắn rồi thử"}
    img = images._render_step_slide(2, slide, (1080, 1350), images.BRAND_DEFAULTS)
    assert img.size == (1080, 1350)
    px = img.load()
    W, H = img.size
    near_black = brand_blue = grey_body = False
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            r, g, bl = px[x, y]
            if r < 55 and g < 55 and bl < 55:
                near_black = True
            if abs(r - 29) < 45 and abs(g - 78) < 45 and abs(bl - 216) < 55:
                brand_blue = True
            if abs(r - 51) < 20 and abs(g - 51) < 20 and abs(bl - 51) < 20:  # #333
                grey_body = True
    assert near_black, "expected near-black headline pixels"
    assert brand_blue, "expected brand-blue kicker pill / underline pixels"
    assert grey_body, "expected #333 body pixels"


def test_each_icon_fn_draws_something():
    from PIL import ImageDraw
    for name, fn in images._ICONS.items():
        im = Image.new("RGB", (128, 128), "white")
        fn(ImageDraw.Draw(im), (16, 16, 112, 112), "#1F2937")
        px = im.load()
        nonwhite = sum(1 for y in range(128) for x in range(128)
                       if px[x, y] != (255, 255, 255))
        assert nonwhite >= 40, f"{name} drew only {nonwhite} non-white px"


def test_build_images_ignores_retired_kwargs(tmp_path):
    out = images.build_images(_art(), tmp_path, size=(1080, 1350),
                              style_prompt="cinematic", provider="gemini", gen=object())
    assert len(out) == 5


def test_build_images_slide_error_degrades_to_hook_only(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("step render broke")

    monkeypatch.setattr(images, "_render_step_slide", boom)
    called = []
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda *a, **k: called.append(1) or ["nope"])
    out = images.build_images(_art(), tmp_path, size=(1080, 1350))
    assert len(out) == 1
    assert Path(out[0]).name == "01.jpg" and Path(out[0]).exists()
    assert not called, "must not drop to legacy media when the hook slide still renders"


def test_build_images_falls_back_to_legacy_when_hook_render_fails(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("render broke")

    monkeypatch.setattr(images, "_render_hook_slide", boom)
    monkeypatch.setattr(images, "_render_step_slide", boom)
    monkeypatch.setattr(images, "_legacy_fallback",
                        lambda art, od, size: [str(tmp_path / "legacy.jpg")])
    out = images.build_images(_art(), tmp_path, size=(1080, 1350))
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
