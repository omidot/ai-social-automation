import re
from pipeline.video.models import Card, SectionMark, Script
from pipeline.video import variants

def C(lines, variant="stack", anchor="mid", mi="rise", mo="up", num=None):
    return Card(lines=lines, variant=variant, anchor=anchor, motion_in=mi, motion_out=mo, num=num)

def test_digit_card_becomes_numeral():
    s = Script(cards=[C(["mở đầu"]), C(["đã tăng gấp 10 lần"]), C(["kết"])],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    assert out.cards[1].variant == "numeral" and out.cards[1].num == 10

def test_no_adjacent_shared_motion_in():
    s = Script(cards=[C([f"c{i}"], mi="rise") for i in range(6)],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    for a, b in zip(out.cards, out.cards[1:]):
        assert a.motion_in != b.motion_in

def test_section_final_stack_becomes_strike_and_last_is_invert():
    s = Script(cards=[C(["a"]), C(["b"]), C(["c"]), C(["d"])],
               sections=[SectionMark("S1", 0), SectionMark("S2", 2)])
    out = variants.normalize(s)
    assert out.cards[1].variant == "strike"   # last of S1
    assert out.cards[3].variant == "invert"   # last of whole script

def test_invalid_fields_get_defaults():
    s = Script(cards=[C(["x"], variant="weird", anchor="??", mi="zzz", mo="qqq")],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    c = out.cards[0]
    assert c.variant in {"stack", "invert"} and c.anchor == "mid"
    assert c.motion_in == "rise" and c.motion_out in {"up", "wipeOut"}

def test_idempotent():
    s = Script(cards=[C([f"c{i} có {i}0 thứ"]) for i in range(7)],
               sections=[SectionMark("A", 0), SectionMark("B", 3), SectionMark("C", 5)])
    once = variants.normalize(s)
    twice = variants.normalize(once)
    assert once.to_dict() == twice.to_dict()

def test_anchor_breaks_three_in_a_row():
    s = Script(cards=[C(["a"], anchor="mid"), C(["b"], anchor="mid"), C(["c"], anchor="mid")],
               sections=[SectionMark("A", 0)])
    out = variants.normalize(s)
    assert not (out.cards[0].anchor == out.cards[1].anchor == out.cards[2].anchor)
