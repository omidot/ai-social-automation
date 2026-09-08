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
    # no config/styles.yaml under root -> the hardcoded default style
    # (white-on-navy, centered layout), so every slide carries the same dark
    # navy field now instead of the old dark-hook / light-item split.
    for idx in (0, 2):
        for px in _corners(Image.open(out[idx]).convert("RGB")):
            assert _brightness(px) < 70, f"slide {idx} corner not navy: {px}"


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
    # the default style's layout is "centered" (now a real fn, not a stub that
    # delegates to _render_item_slide) -> also force it to fail so the item
    # slide has no working render path and the OUTER degrade kicks in.
    monkeypatch.setitem(images.LAYOUTS, "centered", boom)
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
    # default style layout "centered" is a real fn now — force it to fail too so
    # every render path is exhausted and build_images drops to legacy media.
    monkeypatch.setitem(images.LAYOUTS, "centered", boom)
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


def test_handle_line_respects_left_offset():
    from PIL import ImageDraw as _D
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    d = _D.Draw(im)
    images._handle_line(d, (1080, 1350), _pal(), styles.font_paths("grotesk"),
                        centred=False, left=300)
    # nothing drawn left of x=300 in the bottom band
    strip = im.crop((0, 1250, 290, 1330)).getcolors()
    assert strip is not None and len(strip) == 1        # untouched bg only


def test_logo_lockup_returns_int_and_survives_no_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    x = images._logo_lockup(im, (80, 120, 270, 310), _pal(),
                            {"name": "Sora", "domain": "openai.com"}, "tile",
                            tmp_path, 1)
    assert isinstance(x, int) and x >= 270


def test_logo_lockup_accepts_name_font(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    serif = styles.font_paths("editorial")["bold"]
    x = images._logo_lockup(im, (80, 120, 270, 310), _pal(),
                            {"name": "Sora", "domain": "openai.com"}, "mono",
                            tmp_path, 1, name_font=serif)
    assert isinstance(x, int) and x >= 270          # renders, returns int, no raise


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


def test_hook_logos_draws_marks_and_returns_bool(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    before = im.tobytes()
    tools = [{"name": "A", "domain": "a.com"}, {"name": "B", "domain": "b.com"},
             {"name": "C", "domain": "c.com"}, {"name": "D", "domain": "d.com"},
             {"name": "E", "domain": "e.com"}]
    out = images._hook_logos(im, (80, 300, 1000, 700), _pal(), tools, "chip", tmp_path)
    assert out is True                        # chip keeps a glyph even without a real logo
    assert im.tobytes() != before            # something was drawn
    # empty tool list -> nothing drawn, returns False
    im2 = Image.new("RGB", (1080, 1350), _pal()["bg"])
    assert images._hook_logos(im2, (80, 300, 1000, 700), _pal(), [], "chip", tmp_path) is False


def test_logo_lockup_chip_and_mono_paths(tmp_path, monkeypatch):
    # a real (tiny) logo image so the mono desaturate + chip composite paths run
    from PIL import Image as _I
    monkeypatch.setattr(images, "_fetch_logo",
                        lambda *a, **k: _I.new("RGBA", (64, 64), (10, 120, 200, 255)))
    for treatment in ("chip", "mono", "tile"):
        im = _I.new("RGB", (1080, 1350), _pal()["bg"])
        before = im.tobytes()
        x = images._logo_lockup(im, (80, 120, 270, 310), _pal(),
                                {"name": "Sora", "domain": "openai.com"}, treatment,
                                tmp_path, 1)
        assert isinstance(x, int) and x >= 270
        assert im.tobytes() != before, f"{treatment} drew nothing"


def test_logo_lockup_survives_malformed_box(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    x = images._logo_lockup(im, (80, 120, 270), _pal(),      # 3-tuple, malformed
                            {"name": "X", "domain": "x.com"}, "tile", tmp_path, 1)
    assert isinstance(x, int)                                 # did not raise


def test_draw_texture_plain_is_true_noop():
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    before = im.tobytes()
    images._draw_texture(im, "plain", _pal())
    images._draw_texture(im, "totally-unknown-kind", _pal())
    assert im.tobytes() == before


def test_layout_centered_renders_all_roles(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    spies = {k: [] for k in ("lockup", "hook", "swipe", "handle")}
    monkeypatch.setattr(images, "_logo_lockup", lambda *a, **k: spies["lockup"].append(a) or 300)
    monkeypatch.setattr(images, "_hook_logos", lambda *a, **k: spies["hook"].append(a) or True)
    monkeypatch.setattr(images, "_swipe_hint", lambda *a, **k: spies["swipe"].append(a))
    monkeypatch.setattr(images, "_handle_line", lambda *a, **k: spies["handle"].append(a))
    st = _st.Style("t", "centered", "ink-on-white", "grotesk", "dots", "underline", "tile")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["ink-on-white"],
                           _st.font_paths("grotesk"), st, tmp_path, {})
    models = images._slide_models(_story())
    for sm in models:
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["centered"](im, sm, ctx)
        assert im.size == (1080, 1350)
    assert len(spies["hook"]) == 1          # hook drew the logo row
    assert len(spies["lockup"]) == 1        # the one item with a tool (the _story() has 1)
    assert len(spies["swipe"]) == 2         # hook + item, not close
    assert len(spies["handle"]) == 3        # all roles


def test_accent_shape_draws_for_shapes_and_noops_for_none():
    from PIL import ImageDraw as _D
    for kind in ("underline", "bar", "bracket"):
        im = Image.new("RGB", (1080, 1350), _pal()["bg"])
        b = im.tobytes()
        images._accent_shape(_D.Draw(im), (80, 400, 700, 480), kind, _pal()["accent"])
        assert im.tobytes() != b, f"{kind} drew nothing"
    im = Image.new("RGB", (1080, 1350), _pal()["bg"])
    b = im.tobytes()
    images._accent_shape(_D.Draw(im), (80, 400, 700, 480), "none", _pal()["accent"])
    assert im.tobytes() == b


# --- Task 6: the "left-rail" archetype -------------------------------------

def test_layout_left_rail_renders_all_roles(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    spies = {k: [] for k in ("lockup", "hook", "swipe", "handle")}
    monkeypatch.setattr(images, "_logo_lockup", lambda *a, **k: spies["lockup"].append(a) or 360)
    monkeypatch.setattr(images, "_hook_logos", lambda *a, **k: spies["hook"].append(a) or True)
    monkeypatch.setattr(images, "_swipe_hint", lambda *a, **k: spies["swipe"].append(a))
    monkeypatch.setattr(images, "_handle_line", lambda *a, **k: spies["handle"].append(k))
    st = _st.Style("t", "left-rail", "ink-on-white", "grotesk", "dots", "underline", "tile")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["ink-on-white"],
                           _st.font_paths("grotesk"), st, tmp_path, {},
                           article=_story())
    for sm in images._slide_models(_story()):
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["left-rail"](im, sm, ctx)
        assert im.size == (1080, 1350)
    assert len(spies["hook"]) == 1          # hook drew the logo row
    assert len(spies["lockup"]) == 1        # the one item with a tool
    assert len(spies["swipe"]) == 2         # hook + item, not close
    assert len(spies["handle"]) == 3        # all roles
    # the non-close roles anchor the handle past the rail; close stays centred
    assert images._RAIL_X == 170
    lefts = [k.get("left") for k in spies["handle"]]
    assert lefts.count(images._RAIL_X) == 2 and lefts.count(None) == 1


def test_layout_left_rail_bar_accent_downgrades_to_underline(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    monkeypatch.setattr(images, "_logo_lockup", lambda *a, **k: 360)
    monkeypatch.setattr(images, "_hook_logos", lambda *a, **k: True)
    monkeypatch.setattr(images, "_swipe_hint", lambda *a, **k: None)
    monkeypatch.setattr(images, "_handle_line", lambda *a, **k: None)
    seen = []
    real_accent = images._accent_shape
    monkeypatch.setattr(images, "_accent_shape",
                        lambda d, box, kind, col: seen.append(kind) or real_accent(d, box, kind, col))
    st = _st.Style("t", "left-rail", "ink-on-white", "grotesk", "dots", "bar", "tile")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["ink-on-white"],
                           _st.font_paths("grotesk"), st, tmp_path, {},
                           article=_story())
    for sm in images._slide_models(_story()):
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["left-rail"](im, sm, ctx)   # must NOT raise
        assert im.size == (1080, 1350)
    assert seen                                     # _accent_shape was called
    assert "bar" not in seen                        # the rail-clashing bar was swapped
    assert "underline" in seen                      # ...for an underline


# --- Task 7: the "bottom-bar" archetype ----------------------------------

def test_layout_bottom_bar_renders_all_roles(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    spies = {k: [] for k in ("lockup", "hook", "swipe", "handle")}
    monkeypatch.setattr(images, "_logo_lockup", lambda *a, **k: spies["lockup"].append(a) or 300)
    monkeypatch.setattr(images, "_hook_logos", lambda *a, **k: spies["hook"].append(a) or True)
    monkeypatch.setattr(images, "_swipe_hint", lambda *a, **k: spies["swipe"].append(a))
    monkeypatch.setattr(images, "_handle_line", lambda *a, **k: spies["handle"].append(k))
    st = _st.Style("t", "bottom-bar", "ink-on-white", "grotesk", "dots", "underline", "tile")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["ink-on-white"],
                           _st.font_paths("grotesk"), st, tmp_path, {},
                           article=_story())
    for sm in images._slide_models(_story()):
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["bottom-bar"](im, sm, ctx)
        assert im.size == (1080, 1350)
    assert len(spies["hook"]) == 1          # hook drew the logo row
    assert len(spies["lockup"]) == 1        # the one item with a tool
    assert len(spies["swipe"]) == 2         # hook + item, not close
    assert len(spies["handle"]) == 3        # all roles


def test_layout_bottom_bar_survives_every_palette(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    for pname in _st.PALETTE_NAMES:
        st = _st.Style("t", "bottom-bar", pname, "grotesk", "plain", "none", "tile")
        ctx = images.RenderCtx((1080, 1350), _st.PALETTES[pname],
                               _st.font_paths("grotesk"), st, tmp_path, {},
                               article=_story())
        for sm in images._slide_models(_story()):
            im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
            images.LAYOUTS["bottom-bar"](im, sm, ctx)   # shadowed palette must not KeyError
            assert im.size == (1080, 1350)


def test_bottom_bar_item_body_fits_above_handle(tmp_path, monkeypatch):
    # Regression for the review defect: a maxed bulleted item (3-line headline,
    # ~70-word body, 3 bullets) used to push the last bullet down onto the fixed
    # "A Hít Official" / "Vuốt tiếp" furniture (y ~= H-46 / H-54) and clip the
    # canvas bottom. _bottom_bar_copy now caps the body to 3 lines and starts the
    # block higher when bullets are drawn. Rendered on the narrowest face (mono).
    # Fuller visual QA of the spacing is Task 12.
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    st = styles.Style("t", "bottom-bar", "mono-contrast", "mono", "diagonal", "none", "mono")
    ctx = images.RenderCtx((1080, 1350), styles.PALETTES["mono-contrast"],
                           styles.font_paths("mono"), st, tmp_path, {})
    head = "Việc số hai ba bốn năm sáu bảy tám chín mười một hai ba bốn năm sáu"
    body = ("Mô hình nhận một câu mô tả bằng tiếng Việt rồi trả về đoạn phim tám "
            "giây ở độ phân giải 1080p, giữ khuôn mặt nhân vật thật ổn định qua "
            "từng cảnh để cho bạn cắt ghép thành một video hoàn chỉnh chứ không "
            "phải chỉ là một bản trình diễn cho vui mắt, và bạn xuất ra được "
            "ngay trong trình duyệt mà không cần phải cài thêm bất cứ thứ gì cả.")
    assert len(body.split()) >= 68
    sm = images.SlideModel(role="item", index=2, total=4, headline=head,
                           body=body,
                           bullets=["nhập mô tả bằng tiếng Việt cho máy hiểu",
                                    "xuất video 1080p chỉ trong vòng một phút",
                                    "giữ nhân vật ổn định xuyên suốt các cảnh quay"])

    # spy every text draw so we can separate the copy block from the furniture
    real_text = ImageDraw.ImageDraw.text
    rows = []

    def spy_text(self, xy, text, *a, **k):
        bb = self.textbbox(xy, text, font=k.get("font") or (a[0] if a else None))
        rows.append((text, xy[1], bb[3]))
        return real_text(self, xy, text, *a, **k)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy_text)
    im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
    images.LAYOUTS["bottom-bar"](im, sm, ctx)          # must not raise
    monkeypatch.undo()

    assert im.size == (1080, 1350)
    furniture = {"A Hít Official", "Vuốt tiếp  ›"}
    furn_top = min(top for txt, top, _ in rows if txt in furniture)
    copy_bottom = max(bot for txt, _, bot in rows if txt not in furniture)
    # the last bit of copy (bullet 3) must sit clearly above the handle/swipe...
    assert copy_bottom < furn_top - 10, (copy_bottom, furn_top)
    # ...and nothing may run past the canvas bottom edge
    assert max(bot for _, _, bot in rows) <= 1350


# --- Task 8: the "split" archetype -------------------------------------

def test_layout_split_renders_all_roles(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    spies = {k: [] for k in ("lockup", "hook", "swipe", "handle")}
    monkeypatch.setattr(images, "_logo_lockup", lambda *a, **k: spies["lockup"].append(a) or 300)
    monkeypatch.setattr(images, "_hook_logos", lambda *a, **k: spies["hook"].append(a) or True)
    monkeypatch.setattr(images, "_swipe_hint", lambda *a, **k: spies["swipe"].append(a))
    monkeypatch.setattr(images, "_handle_line", lambda *a, **k: spies["handle"].append(k))
    st = _st.Style("t", "split", "ink-on-white", "grotesk", "dots", "underline", "tile")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["ink-on-white"],
                           _st.font_paths("grotesk"), st, tmp_path, {},
                           article=_story())
    for sm in images._slide_models(_story()):
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["split"](im, sm, ctx)
        assert im.size == (1080, 1350)
    assert len(spies["hook"]) == 1          # hook drew the logo row
    assert len(spies["lockup"]) == 1        # the one item with a tool
    assert len(spies["swipe"]) == 2         # hook + item, not close
    assert len(spies["handle"]) == 3        # all roles (close via _centered_close)


def test_layout_split_survives_every_palette(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    for pname in _st.PALETTE_NAMES:
        # accent_shape "bar" also exercises the on-bar headline path per palette
        st = _st.Style("t", "split", pname, "grotesk", "plain", "bar", "tile")
        ctx = images.RenderCtx((1080, 1350), _st.PALETTES[pname],
                               _st.font_paths("grotesk"), st, tmp_path, {},
                               article=_story())
        for sm in images._slide_models(_story()):
            im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
            images.LAYOUTS["split"](im, sm, ctx)   # must not raise
            assert im.size == (1080, 1350)


# --- Task 9: the "magazine" archetype ---------------------------------

def test_layout_magazine_renders_all_roles(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    spies = {k: [] for k in ("lockup", "hook", "swipe", "handle")}
    monkeypatch.setattr(images, "_logo_lockup", lambda *a, **k: spies["lockup"].append((a, k)) or 300)
    monkeypatch.setattr(images, "_hook_logos", lambda *a, **k: spies["hook"].append(a) or True)
    monkeypatch.setattr(images, "_swipe_hint", lambda *a, **k: spies["swipe"].append(a))
    monkeypatch.setattr(images, "_handle_line", lambda *a, **k: spies["handle"].append(k))
    st = _st.Style("t", "magazine", "warm-editorial", "editorial", "plain", "bracket", "mono")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["warm-editorial"],
                           _st.font_paths("editorial"), st, tmp_path, {},
                           article=_story())
    for sm in images._slide_models(_story()):
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["magazine"](im, sm, ctx)
        assert im.size == (1080, 1350)
    assert len(spies["hook"]) == 1          # hook drew the logo row
    assert len(spies["lockup"]) == 1        # the one item with a tool
    assert len(spies["swipe"]) == 2         # hook + item, not close
    assert len(spies["handle"]) == 3        # all roles (close via _centered_close)
    # editorial restraint: the item lockup is forced to the "mono" treatment
    # regardless of ctx.style.logo. spies["lockup"][0] is (args, kwargs);
    # args[4] is the treatment positional in
    # _logo_lockup(img, box, pal, tool, treatment, root, index).
    lk_args, lk_kwargs = spies["lockup"][0]
    assert lk_args[4] == "mono"
    # and the brand name is rendered in the serif face, not the bundled sans
    assert lk_kwargs.get("name_font") == styles.font_paths("editorial")["bold"]


def test_layout_magazine_two_column_body(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    st = styles.Style("t", "magazine", "ink-on-white", "editorial", "plain", "bracket", "mono")
    ctx = images.RenderCtx((1080, 1350), styles.PALETTES["ink-on-white"],
                           styles.font_paths("editorial"), st, tmp_path, {})
    long_body = ("Mô hình nhận một câu mô tả bằng tiếng Việt rồi trả về một đoạn "
                 "phim tám giây ở độ phân giải 1080p, giữ khuôn mặt nhân vật thật "
                 "ổn định qua từng cảnh để cho bạn cắt ghép thành một video hoàn "
                 "chỉnh chứ không phải chỉ là một bản trình diễn cho vui mắt, và "
                 "bạn xuất ra được ngay trong trình duyệt mà không cần cài gì.")
    assert len(long_body.split()) >= 60
    short_body = "Một mô hình mới vừa ra mắt và ai cũng thử được ngay hôm nay."
    assert len(short_body.split()) <= 18

    def _render(body):
        sm = images.SlideModel(role="item", index=2, total=4,
                               headline="Nó làm được những gì cho bạn",
                               body=body,
                               tool={"name": "Sora", "domain": "openai.com"})
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["magazine"](im, sm, ctx)   # must not raise
        assert im.size == (1080, 1350)
        return im.tobytes()

    assert _render(long_body) != _render(short_body)   # layout responds to length


def test_layout_magazine_survives_every_palette(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    for pname in _st.PALETTE_NAMES:
        st = _st.Style("t", "magazine", pname, "editorial", "plain", "underline", "mono")
        ctx = images.RenderCtx((1080, 1350), _st.PALETTES[pname],
                               _st.font_paths("editorial"), st, tmp_path, {},
                               article=_story())
        for sm in images._slide_models(_story()):
            im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
            images.LAYOUTS["magazine"](im, sm, ctx)   # must not raise
            assert im.size == (1080, 1350)


# --- Task 10: the "ticket" archetype ---------------------------------

def test_layout_ticket_renders_all_roles(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    spies = {k: [] for k in ("lockup", "hook", "swipe", "handle")}
    monkeypatch.setattr(images, "_logo_lockup",
                        lambda *a, **k: spies["lockup"].append((a, k)) or 300)
    monkeypatch.setattr(images, "_hook_logos",
                        lambda *a, **k: spies["hook"].append((a, k)) or True)
    monkeypatch.setattr(images, "_swipe_hint",
                        lambda *a, **k: spies["swipe"].append((a, k)))
    monkeypatch.setattr(images, "_handle_line",
                        lambda *a, **k: spies["handle"].append((a, k)))
    st = _st.Style("t", "ticket", "ink-on-white", "grotesk", "dots", "none", "tile")
    ctx = images.RenderCtx((1080, 1350), _st.PALETTES["ink-on-white"],
                           _st.font_paths("grotesk"), st, tmp_path, {},
                           article=_story())
    for sm in images._slide_models(_story()):
        im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
        images.LAYOUTS["ticket"](im, sm, ctx)
        assert im.size == (1080, 1350)
    assert len(spies["hook"]) == 1          # hook drew the logo row
    assert len(spies["lockup"]) == 1        # the one item with a tool
    assert len(spies["swipe"]) == 2         # hook + item, not close
    assert len(spies["handle"]) == 3        # all roles (close via _centered_close)
    # the non-close handle calls sit INSIDE the card: left kwarg well past x=80
    lefts = [k.get("left") for _a, k in spies["handle"] if k.get("left") is not None]
    assert len(lefts) == 2 and all(l > 80 for l in lefts), lefts


def test_layout_ticket_survives_every_palette(tmp_path, monkeypatch):
    _st = styles
    monkeypatch.setattr(images, "_fetch_logo", lambda *a, **k: None)
    for pname in _st.PALETTE_NAMES:
        st = _st.Style("t", "ticket", pname, "grotesk", "plain", "bracket", "tile")
        ctx = images.RenderCtx((1080, 1350), _st.PALETTES[pname],
                               _st.font_paths("grotesk"), st, tmp_path, {},
                               article=_story())
        for sm in images._slide_models(_story()):
            im = Image.new("RGB", (1080, 1350), ctx.palette["bg"])
            images.LAYOUTS["ticket"](im, sm, ctx)   # must not raise
            assert im.size == (1080, 1350)
