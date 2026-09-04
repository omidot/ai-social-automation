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
