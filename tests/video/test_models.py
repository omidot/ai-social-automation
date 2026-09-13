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


from pipeline.video.models import VideoMeta

def test_videometa_roundtrip():
    m = VideoMeta(title="Tiêu đề giật tít về AI", description="Mô tả. CTA.",
                  hashtags=["#AI", "#congnghe", "#tudonghoa", "#ainews",
                            "#chatgpt", "#automation", "#ahit", "#vn"],
                  keywords=["ai", "tự động hoá", "công nghệ", "chatgpt", "n8n"],
                  tiktok_caption="AI vừa có bước nhảy lớn #AI #congnghe #fyp")
    assert VideoMeta.from_dict(m.to_dict()) == m
