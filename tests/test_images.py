from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from pipeline import images, styles
from pipeline.models import ArticleContent


_LONG = ("Đây là một đoạn thân bài đủ dài để mô tả cụ thể một tính năng vừa ra "
         "mắt, có ví dụ và con số, trải ra nhiều dòng trên slide chứ không phải "
         "một câu cụt ngủn như bản cũ trước đây từng làm.")


def _slides():
    return [
        {"role": "hook", "headline": "5 công cụ AI ít ai biết",
         "body": "Bộ công cụ giúp bạn làm nhanh hơn hẳn", "tools": []},
        {"role": "item", "headline": "Việc số một", "body": _LONG,
         "tool": None, "bullets": ["điểm một", "điểm hai"]},
        {"role": "item", "headline": "Việc số hai", "body": _LONG,
         "tool": None, "bullets": []},
        {"role": "item", "headline": "Việc số ba", "body": _LONG,
         "tool": None, "bullets": ["một dòng ngắn"]},
        {"role": "item", "headline": "Việc số bốn", "body": _LONG,
         "tool": None, "bullets": []},
        {"role": "close", "headline": "Chốt lại", "body": "Một câu đọng lại thật ngắn gọn"},
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
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), brand=None,
                              root=tmp_path)
    assert [Path(p).name for p in out] == \
        ["01.jpg", "02.jpg", "03.jpg", "04.jpg", "05.jpg", "06.jpg"]
    for p in out:
        assert Image.open(p).size == (1080, 1350)
    # slide 1 is the dark hook slide, slide 3 is a light item slide
    for px in _corners(Image.open(out[0]).convert("RGB")):
        assert _brightness(px) < 60, f"hook corner too bright: {px}"
    for px in _corners(Image.open(out[2]).convert("RGB")):
        assert all(c > 220 for c in px), f"item corner too dark: {px}"


def test_slides_have_no_progress_bar(tmp_path):
    # v4: the segmented top progress bar is gone — no long horizontal brand-blue
    # run anywhere in the top 60px band of any slide.
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), brand=None,
                              root=tmp_path)
    for p in out:
        im = Image.open(p).convert("RGB")
        W, _ = im.size
        px = im.load()
        for y in range(0, 60):
            run = 0
            for x in range(W):
                r, g, bl = px[x, y]
                if abs(r - 29) < 55 and abs(g - 78) < 55 and bl > 165:
                    run += 1
                    assert run <= 40, f"progress-bar-like blue run at y={y} on {p}"
                else:
                    run = 0


def test_build_images_ignores_retired_kwargs(tmp_path):
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), root=tmp_path,
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

def _item(tool=None, body="Mô tả ngắn về công cụ này", bullets=None):
    return {"role": "item", "headline": "Một công cụ hay", "body": body,
            "tool": tool, "bullets": bullets or []}


def test_hook_slide_shows_tool_logos(monkeypatch):
    red = Image.new("RGBA", (120, 120), (255, 0, 0, 255))
    monkeypatch.setattr(images, "_fetch_logo", lambda d, r: red)
    slides = _slides()
    slides[0]["tools"] = [{"name": "A", "domain": "a.com"},
                          {"name": "B", "domain": "b.com"},
                          {"name": "C", "domain": "c.com"}]
    img = images._render_hook_slide(_art(slides), slides[0], (1080, 1350),
                                    images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    band = [(x, y) for y in range(int(H * 0.34), int(H * 0.82), 2)
            for x in range(0, W, 2)
            if px[x, y][0] > 180 and px[x, y][1] < 90 and px[x, y][2] < 90]
    assert len(band) > 150, f"expected red logo pixels in the mid band, got {len(band)}"
    xs = sorted({x for x, _ in band})
    gaps = sum(1 for a, c in zip(xs, xs[1:]) if c - a > 20)
    assert gaps >= 2, f"expected 3 separated logo clusters, got {gaps + 1}"


def test_item_slide_logo_lockup_left(monkeypatch):
    red = Image.new("RGBA", (128, 128), (255, 0, 0, 255))
    monkeypatch.setattr(images, "_fetch_logo", lambda d, r: red)
    img = images._render_item_slide(2, 6, _item({"name": "Foo", "domain": "foo.com"}),
                                    (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    red_xs = [x for y in range(90, 340, 2) for x in range(0, W, 2)
              if px[x, y][0] > 200 and px[x, y][1] < 80 and px[x, y][2] < 80]
    assert red_xs, "no logo pixels found"
    assert max(red_xs) < W // 3, "the logo tile must sit in the left third"
    right = max(red_xs)
    dark = sum(1 for y in range(120, 320, 2) for x in range(right + 12, right + 420, 2)
               if all(c < 80 for c in px[x, y]))
    assert dark > 15, f"expected dark brand-name pixels right of the logo, got {dark}"


def test_item_slide_falls_back_to_icon_without_logo(monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda d, r: None)
    img = images._render_item_slide(3, 6, _item({"name": "Bar", "domain": "bar.com"}),
                                    (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    dark = sum(1 for y in range(110, 330, 2) for x in range(0, W // 3, 2)
               if all(c < 95 for c in px[x, y]))
    assert dark > 20, f"expected a dark fallback glyph in the left third, got {dark}"


def test_item_slide_renders_long_body_and_bullets(monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda d, r: None)
    body = " ".join(["từ"] * 60)
    slide = _item({"name": "OpenAI", "domain": "openai.com"}, body=body,
                  bullets=["điểm quan trọng số một", "điểm quan trọng số hai"])
    img = images._render_item_slide(2, 6, slide, (1080, 1350), images.BRAND_DEFAULTS)
    px = img.load()
    W, H = img.size
    dark = sum(1 for y in range(520, 1150, 3) for x in range(80, W - 80, 3)
               if all(c < 110 for c in px[x, y]))
    assert dark > 60, f"expected substantial dark body/bullet text, got {dark}"


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
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), root=tmp_path)
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
    out = images.build_images(_art(), tmp_path, size=(1080, 1350), root=tmp_path)
    assert out == [str(tmp_path / "legacy.jpg")]


def _story():
    slides = [
        {"role": "hook", "headline": "AI dựng phim tám giây", "body": "Một mô hình mới.",
         "tools": [{"name": "Sora", "domain": "openai.com"},
                   {"name": "Veo", "domain": "deepmind.google"}]},
        {"role": "item", "headline": "Nó làm được gì", "tool": {"name": "Sora", "domain": "openai.com"},
         "body": ("Mô hình nhận một câu tiếng Việt rồi trả về đoạn phim tám giây ở "
                  "1080p, giữ khuôn mặt nhân vật ổn định để cắt ghép thật chứ không "
                  "chỉ là bản trình diễn cho vui mắt, và bạn xuất được ngay."),
         "bullets": ["điểm nhấn một", "điểm nhấn hai"]},
        {"role": "close", "headline": "Chốt lại", "body": "Kỹ năng mới là viết mô tả."},
    ]
    return ArticleContent(format="share", caption_fb="fb", caption_ig="ig",
                          hashtags=["#AI"], cover_title="AI dựng phim",
                          slides=slides, sources=[])


def test_build_images_with_explicit_style(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    st = styles.Style("t", "centered", "ink-on-white", "grotesk", "dots", "underline", "tile")
    picked = []
    monkeypatch.setattr(styles, "pick_style",
                        lambda root, now=None: picked.append(root) or st)
    seen = {}

    def recorder(img, sm, ctx):
        seen.setdefault("style", ctx.style)
        seen.setdefault("palette", ctx.palette)

    monkeypatch.setitem(images.LAYOUTS, "centered", recorder)
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path, style=st)
    assert len(out) == 3
    for p in out:
        assert Image.open(p).size == (1080, 1350)
    assert picked == []                         # explicit style must NOT consult pick_style
    assert seen["style"] is st                  # the given style reached the layout
    assert seen["palette"] == styles.palette_for(st, {})


def test_build_images_picks_a_style_when_none(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    seen = {}
    st = styles.Style("x", "left-rail", "white-on-navy", "grotesk", "plain", "bar", "chip")
    called = []
    monkeypatch.setattr(styles, "pick_style",
                        lambda root, now=None: (called.append(root), st)[1])

    def recorder(img, sm, ctx):
        seen.setdefault("style", ctx.style)

    monkeypatch.setitem(images.LAYOUTS, "left-rail", recorder)
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path)
    assert len(out) == 3
    assert called == [tmp_path]                 # pick_style was consulted with root
    assert seen["style"].name == "x"            # and the chosen style reached the layout


def test_one_bad_layout_slide_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    calls = {"n": 0}
    real_centered = images.LAYOUTS["centered"]

    def flaky(img, sm, ctx):
        calls["n"] += 1
        if sm.role == "item":
            raise RuntimeError("layout boom")
        return real_centered(img, sm, ctx)

    monkeypatch.setitem(images.LAYOUTS, "centered", flaky)
    st = styles.Style("t", "centered", "ink-on-white", "grotesk", "dots", "underline", "tile")
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path, style=st)
    assert len(out) == 3                          # still 3 images, bad item via _via_fallback
    assert Image.open(out[1]).size == (1080, 1350)


def test_bad_style_config_uses_default(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    monkeypatch.setattr(styles, "pick_style",
                        lambda *a, **k: (_ for _ in ()).throw(styles.StyleError("boom")))
    seen = {}

    def recorder(img, sm, ctx):
        seen.setdefault("style", ctx.style)

    monkeypatch.setitem(images.LAYOUTS, "centered", recorder)
    out = images.build_images(_story(), tmp_path / "o", size=(1080, 1350),
                              brand={}, root=tmp_path)      # must not raise
    assert len(out) == 3
    assert seen["style"].name == "default"      # bad config -> hardcoded default look
    assert seen["style"].layout == "centered"


# --- Task 4: shared furniture helpers ---------------------------------

def _pal():
    return styles.PALETTES["ink-on-white"]


def test_draw_texture_variants_dont_crash_and_change_pixels(tmp_path):
    for kind in styles.TEXTURE_NAMES:
        im = Image.new("RGB", (1080, 1350), _pal()["bg"])
        before = im.tobytes()
        images._draw_texture(im, kind, _pal())
        if kind != "plain":
            assert im.tobytes() != before
        assert im.size == (1080, 1350)


def test_furniture_helpers_draw_expected_text(tmp_path):
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    d = ImageDraw.Draw(im)
    fonts = styles.font_paths("grotesk")
    images._handle_line(d, (1080, 1350), _pal(), fonts, centred=True)
    images._swipe_hint(d, (1080, 1350), _pal(), fonts)
    # bottom 120px band now has non-bg pixels
    band = im.crop((0, 1230, 1080, 1350)).getcolors(maxcolors=100000)
    assert len(band) > 1


def test_logo_lockup_returns_int_and_survives_no_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    x = images._logo_lockup(im, (80, 120, 270, 310), _pal(),
                            {"name": "Sora", "domain": "openai.com"}, "tile",
                            tmp_path, 1)
    assert isinstance(x, int) and x >= 270


def test_accent_shape_variants_dont_crash():
    for kind in styles.ACCENT_SHAPES:
        im = Image.new("RGB", (1080, 1350), _pal()["bg"])
        images._accent_shape(ImageDraw.Draw(im), (80, 400, 700, 480), kind,
                             _pal()["accent"])


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
