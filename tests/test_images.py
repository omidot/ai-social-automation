from pathlib import Path
import pytest
from PIL import Image
from pipeline import images
from pipeline.models import ArticleContent


def _slides():
    return [
        {"role": "hook", "headline": "5 công cụ AI ít ai biết",
         "body": "Bộ công cụ giúp bạn làm nhanh hơn hẳn", "tool": None},
        {"role": "item", "headline": "Việc số một", "body": "Một dòng nội dung hơi dài để bọc",
         "tool": None},
        {"role": "item", "headline": "Việc số hai", "body": "Một dòng nội dung khác cũng hơi dài",
         "tool": None},
        {"role": "item", "headline": "Việc số ba", "body": "Thêm một dòng nội dung nữa ở đây",
         "tool": None},
        {"role": "item", "headline": "Việc số bốn", "body": "Dòng nội dung thứ tư hơi dài chút",
         "tool": None},
        {"role": "close", "headline": "Chốt lại", "body": "Một câu đọng lại thật ngắn gọn",
         "tool": None},
    ]


def _art(slides=None):
    return ArticleContent(
        format="share", caption_fb="x", caption_ig="y", hashtags=["#AI"],
        cover_title="5 CÔNG CỤ AI ÍT AI BIẾT",
        slides=_slides() if slides is None else slides,
        sources=[{"name": "hn", "url": "http://h"}])


def _corners(im):
    W, H = im.size
    return [im.getpixel(xy) for xy in
            [(8, 8), (W - 8, 8), (8, H - 8), (W - 8, H - 8)]]


def _brightness(px):
    return sum(px[:3]) / 3


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


# --- full carousel ------------------------------------------------------

def test_build_images_renders_hook_plus_items(tmp_path):
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), brand=None)
    assert [Path(p).name for p in out] == \
        ["01.jpg", "02.jpg", "03.jpg", "04.jpg", "05.jpg", "06.jpg"]
    for p in out:
        assert Image.open(p).size == (1080, 1350)
    # slide 1 is the dark hook slide, slide 3 is a light item slide
    for px in _corners(Image.open(out[0]).convert("RGB")):
        assert _brightness(px) < 60, f"hook corner too bright: {px}"
    for px in _corners(Image.open(out[2]).convert("RGB")):
        assert all(c > 220 for c in px), f"item corner too dark: {px}"


def test_every_slide_has_progress_bar(tmp_path):
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), brand=None)
    for p in out:
        assert _band_has_brand_blue(p, 80, 112), f"no filled progress segment on {p}"


def test_build_images_ignores_retired_kwargs(tmp_path):
    out = images.build_images(_art(), tmp_path, size=(1080, 1350),
                              style_prompt="cinematic", provider="gemini", gen=object())
    assert len(out) == 6


# --- hook slide -------------------------------------------------------

def test_hook_slide_has_swipe_cta():
    art = _art()
    img = images._render_hook_slide(art, art.slides[0], (1080, 1350),
                                    images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    found = False
    for y in range(int(H * 0.78), int(H * 0.92)):
        for x in range(0, W, 2):
            r, g, bl = px[x, y]
            if min(r, g, bl) > 205 and max(r, g, bl) < 250 and max(r, g, bl) - min(r, g, bl) < 25:
                found = True
                break
        if found:
            break
    assert found, "expected light-grey swipe-CTA text in the bottom band"


# --- item slide + logos --------------------------------------------------

def _item(tool=None):
    return {"role": "item", "headline": "Một công cụ hay", "body": "Mô tả ngắn về công cụ này",
            "tool": tool}


def test_item_slide_uses_logo_when_available(monkeypatch):
    red = Image.new("RGBA", (128, 128), (255, 0, 0, 255))
    monkeypatch.setattr(images, "_fetch_logo", lambda d, r: red)
    img = images._render_item_slide(2, 6, _item({"name": "Foo", "domain": "foo.com"}),
                                    (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    hits = sum(1 for y in range(0, H // 2) for x in range(W // 2, W, 2)
               if px[x, y][0] > 200 and px[x, y][1] < 80 and px[x, y][2] < 80)
    assert hits > 50, f"expected red logo pixels top-right, got {hits}"


def test_item_slide_falls_back_to_icon_without_logo(monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda d, r: None)
    img = images._render_item_slide(3, 6, _item({"name": "Bar", "domain": "bar.com"}),
                                    (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    dark = sum(1 for y in range(0, H // 2) for x in range(W // 2, W, 2)
               if all(c < 80 for c in px[x, y]))
    assert dark > 20, f"expected a dark fallback glyph top-right, got {dark}"


def test_close_slide_has_no_swipe_hint():
    slide = {"role": "close", "headline": "Chốt lại", "body": "Một câu đọng lại ngắn", "tool": None}
    img = images._render_item_slide(6, 6, slide, (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    handle = any(_brightness(px[x, y]) < 150
                 for y in range(int(H * 0.90), int(H * 0.97))
                 for x in range(int(W * 0.30), int(W * 0.70), 2))
    assert handle, "expected the handle text bottom-centre"
    swipe = sum(1 for y in range(int(H * 0.88), int(H * 0.95))
                for x in range(int(W * 0.72), W - 10, 2)
                if _brightness(px[x, y]) < 170)
    assert swipe < 20, f"bottom-right swipe zone should be clean, got {swipe}"


# --- _fetch_logo -------------------------------------------------------

def test_fetch_logo_uses_cache(tmp_path, monkeypatch):
    d = tmp_path / "assets" / "logos"
    d.mkdir(parents=True)
    Image.new("RGBA", (64, 64), (0, 128, 255, 255)).save(d / "example.com.png")

    def boom(*a, **k):
        raise AssertionError("network must not be touched on a cache hit")

    monkeypatch.setattr(images.httpx, "get", boom)
    out = images._fetch_logo("example.com", tmp_path)
    assert out is not None and out.size == (64, 64)


def test_fetch_logo_returns_none_on_failure(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no net")

    monkeypatch.setattr(images.httpx, "get", boom)
    assert images._fetch_logo("nope.example", tmp_path) is None


# --- misc / fallback -------------------------------------------------

def test_each_icon_fn_draws_something():
    from PIL import ImageDraw
    for name, fn in images._ICONS.items():
        im = Image.new("RGB", (128, 128), "white")
        fn(ImageDraw.Draw(im), (16, 16, 112, 112), "#1F2937")
        px = im.load()
        nonwhite = sum(1 for y in range(128) for x in range(128)
                       if px[x, y] != (255, 255, 255))
        assert nonwhite >= 40, f"{name} drew only {nonwhite} non-white px"


def test_build_images_slide_error_degrades_to_hook_only(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("item render broke")

    monkeypatch.setattr(images, "_render_item_slide", boom)
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
    monkeypatch.setattr(images, "_render_item_slide", boom)
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
