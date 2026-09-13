import pytest
from pipeline.video.models import Card, SectionMark, Script

def _card(lines, **kw):
    kw.setdefault("variant", "stack"); kw.setdefault("anchor", "mid")
    kw.setdefault("motion_in", "rise"); kw.setdefault("motion_out", "up")
    return Card(lines=lines, **kw)

def test_card_spoken_includes_filler_without_tilde():
    c = _card(["Bây giờ", "~cái", "AI nghĩ hộ bạn"])
    assert c.spoken == "Bây giờ cái AI nghĩ hộ bạn"

def test_card_displayed_words_excludes_filler():
    c = _card(["Bây giờ", "~cái", "AI nghĩ hộ bạn"])
    assert c.displayed_words == 2 + 4

def test_script_spoken_text_newline_between_cards():
    s = Script(cards=[_card(["một hai"]), _card(["ba bốn năm"])],
               sections=[SectionMark("MỞ", 0)])
    assert s.spoken_text == "một hai\nba bốn năm"
    assert s.word_count == 5

def test_script_roundtrip():
    s = Script(cards=[_card(["x y"], num=None), _card(["2000 lính"], variant="numeral", num=2000)],
               sections=[SectionMark("A", 0), SectionMark("B", 1)])
    assert Script.from_dict(s.to_dict()).to_dict() == s.to_dict()

def test_card_from_dict_strips_unit_from_num():
    # the LLM occasionally returns "50 USD" instead of a bare 50 -- codegen
    # writes num verbatim into a JS array literal, so a stray unit there
    # breaks the generated file. from_dict must extract the numeric part.
    c = Card.from_dict({"lines": ["x"], "variant": "numeral", "anchor": "mid",
                        "motion_in": "rise", "motion_out": "up", "num": "50 USD"})
    assert c.num == 50


def test_card_from_dict_keeps_plain_number():
    c = _card(["x"], num=2000)
    d = c.to_dict()
    assert Card.from_dict(d).num == 2000


def test_card_from_dict_drops_unparseable_num():
    c = Card.from_dict({"lines": ["x"], "variant": "stack", "anchor": "mid",
                        "motion_in": "rise", "motion_out": "up", "num": "many"})
    assert c.num is None


from pipeline.video.models import ChartSpec, ScreenshotSpec

def test_chartspec_roundtrip():
    c = ChartSpec(kind="bar", items=[{"label": "Astra", "value": 1.67},
                                     {"label": "Fable 5.1", "value": 3.76}], unit="$")
    assert ChartSpec.from_dict(c.to_dict()) == c

def test_screenshotspec_roundtrip():
    s = ScreenshotSpec(query="GitHub OpenAI Codex repository")
    assert ScreenshotSpec.from_dict(s.to_dict()) == s

def test_card_chart_and_screenshot_roundtrip():
    chart = ChartSpec(kind="line", items=[{"value": 1}, {"value": 2}, {"value": 5}])
    c = _card(["x"], num=None)
    c.chart = chart
    d = c.to_dict()
    assert d["chart"] == chart.to_dict()
    assert d["screenshot"] is None
    assert d["screenshot_file"] is None
    back = Card.from_dict(d)
    assert back.chart == chart
    assert back.screenshot is None

    shot = ScreenshotSpec(query="Anthropic Claude Fable 5.1")
    c2 = _card(["y"])
    c2.screenshot = shot
    c2.screenshot_file = "screenshots/2.png"
    c2.screenshot_url = "https://anthropic.com/claude-fable-5-1"
    d2 = c2.to_dict()
    back2 = Card.from_dict(d2)
    assert back2.screenshot == shot
    assert back2.screenshot_file == "screenshots/2.png"
    assert back2.screenshot_url == "https://anthropic.com/claude-fable-5-1"

def test_card_from_dict_defaults_chart_and_screenshot_to_none():
    # existing fixtures (norm_script.json etc.) never include these keys
    c = Card.from_dict({"lines": ["x"], "variant": "stack", "anchor": "mid",
                        "motion_in": "rise", "motion_out": "up"})
    assert c.chart is None and c.screenshot is None and c.screenshot_file is None


from pipeline.video.models import VideoMeta

def test_videometa_roundtrip():
    m = VideoMeta(title="Tiêu đề giật tít về AI", description="Mô tả. CTA.",
                  hashtags=["#AI", "#congnghe", "#tudonghoa", "#ainews",
                            "#chatgpt", "#automation", "#ahit", "#vn"],
                  keywords=["ai", "tự động hoá", "công nghệ", "chatgpt", "n8n"],
                  tiktok_caption="AI vừa có bước nhảy lớn #AI #congnghe #fyp")
    assert VideoMeta.from_dict(m.to_dict()) == m
