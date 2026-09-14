import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.models import Candidate, PostContent
from pipeline.video import script, VideoScriptError
from pipeline.video.models import Script, VideoMeta

FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"
CFG = {"target_seconds": 150, "words_min": 230, "words_max": 300}
VOICE = {"xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "giong": "thân thiện",
         "cam_ky": ["không giật tít sai"], "ten_kenh": "A Hít Official"}

def _cand():
    return Candidate(url="https://openai.com/x", title="OpenAI ra model mới",
                     source="rss:OpenAI Blog",
                     published_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                     summary="model mới", full_text="OpenAI ra model nhanh gấp đôi, rẻ hơn.")

def _post():
    return PostContent(angle="phan-tich", caption_fb="x", caption_ig="y", hashtags=["#AI"],
                       thumbnail_prompt="p", thumbnail_title="T", youtube_title="a",
                       youtube_desc="b", tiktok_caption="c",
                       source_url="https://openai.com/x", source_name="OpenAI Blog")

def test_build_prompt_carries_constraints():
    sysp, usr = script.build_prompt(_cand(), _post(), VOICE, CFG)
    assert "230" in sysp and "300" in sysp
    assert "A Hít Official" in sysp
    assert "OpenAI ra model nhanh gấp đôi" in usr

def test_generate_parses_valid_response():
    raw = (FX / "raw_script.json").read_text(encoding="utf-8")
    s = script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: raw)
    assert isinstance(s, Script)
    assert len(s.cards) == 30 and len(s.sections) == 4
    assert s.sections[0].card_start == 0
    assert s.cards[10].num == 10

def test_generate_retries_on_short_script():
    short = (FX / "raw_script_short.json").read_text(encoding="utf-8")
    full = (FX / "raw_script.json").read_text(encoding="utf-8")
    calls = []
    def fake_llm(sy, u, **k):
        calls.append(u)
        return short if len(calls) == 1 else full
    s = script.generate(_cand(), _post(), VOICE, CFG, llm=fake_llm)
    assert len(calls) == 2
    assert "từ" in calls[1].lower()   # corrective feedback mentions word count
    assert "[SỬA]" in calls[1]        # corrective marker present
    assert 230 <= s.word_count <= 300

def test_generate_raises_after_second_bad():
    short = (FX / "raw_script_short.json").read_text(encoding="utf-8")
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: short)

def test_generate_raises_on_bad_schema():
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: '{"cards": []}')

def test_generate_wraps_llm_error():
    from pipeline.llm import LLMError
    def boom(sy, u, **k):
        raise LLMError("upstream down")
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=boom)

def test_generate_rejects_first_section_not_zero():
    data = json.loads((FX / "raw_script.json").read_text(encoding="utf-8"))
    data["sections"][0]["card_start"] = 1
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: json.dumps(data))

def test_generate_rejects_non_increasing_sections():
    data = json.loads((FX / "raw_script.json").read_text(encoding="utf-8"))
    data["sections"] = [{"label": "A", "card_start": 0}, {"label": "B", "card_start": 0}]
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: json.dumps(data))

def test_generate_rejects_section_start_beyond_cards():
    data = json.loads((FX / "raw_script.json").read_text(encoding="utf-8"))
    data["sections"][-1]["card_start"] = 999
    with pytest.raises(VideoScriptError):
        script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: json.dumps(data))

def test_write_script_json(tmp_path):
    raw = (FX / "raw_script.json").read_text(encoding="utf-8")
    s = script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: raw)
    p = script.write_script_json(s, tmp_path)
    assert p.exists() and json.loads(p.read_text(encoding="utf-8"))["cards"]
    assert p.name == "script.json"

_GOOD_META = {
    "title": "AI vừa có một bước nhảy lớn hôm nay",
    "description": "Một mô hình mới vừa ra mắt. Theo dõi kênh để không bỏ lỡ.",
    "hashtags": ["#AI", "#congnghe", "#tudonghoa", "#ainews", "#chatgpt",
                 "#automation", "#ahitofficial", "#vietnam"],
    "keywords": ["ai", "tự động hoá", "công nghệ", "mô hình ngôn ngữ", "n8n", "chatgpt"],
    "tiktok_caption": "AI vừa nhảy vọt, bạn theo kịp chưa? #AI #congnghe #fyp",
}

def test_validate_meta_ok():
    m = script._validate_meta(dict(_GOOD_META))
    assert m.title.startswith("AI vừa")
    assert len(m.hashtags) == 8

@pytest.mark.parametrize("mutate", [
    lambda d: d.update(title="Ngắn"),                                   # < 10 chars
    lambda d: d.update(title="x" * 71),                                 # > 70
    lambda d: d.update(hashtags=d["hashtags"][:5]),                     # < 8
    lambda d: d.update(hashtags=d["hashtags"] + ["#a"] * 6),            # > 12
    lambda d: d.update(hashtags=["no-hash"] + d["hashtags"][1:]),       # bad element
    lambda d: d.update(keywords=d["keywords"][:3]),                     # < 5
    lambda d: d.update(tiktok_caption="x" * 151),                       # > 150
    lambda d: d.pop("description"),                                     # missing
])
def test_validate_meta_rejects(mutate):
    d = dict(_GOOD_META)
    mutate(d)
    with pytest.raises(VideoScriptError):
        script._validate_meta(d)


_VOICE = {"ten_kenh": "A Hít Official", "giong": "gãy gọn",
          "xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "cam_ky": []}
_CFG = {"target_seconds": 150, "words_min": 230, "words_max": 300}


def _fake_full_reply():
    cards = [{"lines": [f"Dòng số {i}", "thêm vài từ nữa cho đủ dài", "và thêm chút"],
              "variant": "stack", "anchor": "mid", "motion_in": "rise",
              "motion_out": "up"} for i in range(20)]
    return json.dumps({
        "sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 6}],
        "cards": cards,
        "publish": dict(_GOOD_META),
    }, ensure_ascii=False)


def test_build_prompt_with_meta_toggles_publish_ask():
    plain_sys, _ = script.build_prompt(_cand(), _post(), VOICE, CFG)
    meta_sys, meta_usr = script.build_prompt(_cand(), _post(), VOICE, CFG, with_meta=True)
    assert "publish" not in plain_sys
    assert "publish" in meta_sys
    assert "tiktok_caption" in meta_sys
    # user construction unchanged between the two modes
    _, plain_usr = script.build_prompt(_cand(), _post(), VOICE, CFG)
    assert plain_usr == meta_usr


def test_generate_from_article_returns_script_and_meta():
    calls = []
    def llm(system, user, provider="auto"):
        calls.append((system, user)); return _fake_full_reply()
    s, m = script.generate_from_article(
        title="OpenAI ra mắt mô hình video", source_url="https://openai.com/x",
        body_text="Nội dung bài viết dài...", caption_fb="Caption tham khảo.",
        angle="chia sẻ", voice=_VOICE, cfg=_CFG, llm=llm)
    assert isinstance(s, Script) and isinstance(m, VideoMeta)
    assert "publish" in calls[0][0]                 # with_meta prompt used
    assert m.title.startswith("AI vừa")


def test_generate_from_article_bad_meta_raises():
    def llm(system, user, provider="auto"):
        d = json.loads(_fake_full_reply()); d["publish"]["hashtags"] = ["#a", "#b"]
        return json.dumps(d, ensure_ascii=False)
    with pytest.raises(VideoScriptError):
        script.generate_from_article(title="x" * 20, source_url="", body_text="b",
                                     caption_fb="c", angle="a", voice=_VOICE, cfg=_CFG, llm=llm)


def test_generate_from_article_retries_on_validation_error():
    # a validation failure (here: tiktok_caption 1 char over the 150 limit)
    # must get the same one-shot corrective retry as a bad word count does,
    # instead of failing the whole run on the first bad response.
    bad = json.loads(_fake_full_reply())
    bad["publish"]["tiktok_caption"] = "x" * 151
    calls = []
    def llm(system, user, provider="auto"):
        calls.append(user)
        return json.dumps(bad, ensure_ascii=False) if len(calls) == 1 else _fake_full_reply()
    s, m = script.generate_from_article(
        title="OpenAI ra mắt mô hình video", source_url="", body_text="b",
        caption_fb="c", angle="a", voice=_VOICE, cfg=_CFG, llm=llm)
    assert len(calls) == 2
    assert "[SỬA]" in calls[1] and "150" in calls[1]
    assert isinstance(s, Script) and isinstance(m, VideoMeta)


def test_generate_from_article_retries_on_word_band():
    short = json.dumps({
        "sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 3}],
        "cards": [{"lines": ["ngắn"], "variant": "stack", "anchor": "mid",
                   "motion_in": "rise", "motion_out": "up"} for _ in range(20)],
        "publish": dict(_GOOD_META),
    }, ensure_ascii=False)
    calls = []
    def llm(system, user, provider="auto"):
        calls.append(user)
        return short if len(calls) == 1 else _fake_full_reply()
    s, m = script.generate_from_article(
        title="OpenAI ra mắt mô hình video", source_url="", body_text="b",
        caption_fb="c", angle="a", voice=_VOICE, cfg=_CFG, llm=llm)
    assert len(calls) == 2
    assert "[SỬA]" in calls[1] and "publish" in calls[1]
    assert isinstance(s, Script) and isinstance(m, VideoMeta)


def _base_card():
    return {"lines": ["x"], "variant": "stack", "anchor": "mid",
            "motion_in": "rise", "motion_out": "up"}

def _script_with_card(extra_card_fields, n_extra_cards=20):
    # _validate() requires 18 <= len(cards) <= 48 -- 18 is the floor, so this
    # default must stay above 18 or every test below would fail on the
    # card-count check before ever reaching the chart/screenshot validation
    # this helper exists to exercise.
    cards = [_base_card() for _ in range(n_extra_cards)]
    cards[3] = {**_base_card(), **extra_card_fields}
    return {"sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 4}],
            "cards": cards}

def test_validate_rejects_card_with_both_num_and_chart():
    data = _script_with_card({"num": 5, "chart": {"kind": "bar",
                              "items": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]}})
    with pytest.raises(VideoScriptError, match="chỉ được set 1 trong"):
        script._validate(data, CFG)

def test_validate_rejects_bad_chart_kind():
    data = _script_with_card({"chart": {"kind": "pie", "items": [{"value": 1}]}})
    with pytest.raises(VideoScriptError, match="kind"):
        script._validate(data, CFG)

def test_validate_rejects_bar_with_wrong_item_count():
    data = _script_with_card({"chart": {"kind": "bar",
                              "items": [{"label": "A", "value": 1}]}})
    with pytest.raises(VideoScriptError, match="items"):
        script._validate(data, CFG)

def test_validate_rejects_chart_item_without_numeric_value():
    data = _script_with_card({"chart": {"kind": "line",
                              "items": [{"value": 1}, {"value": 2}, {"value": "nhiều"}]}})
    with pytest.raises(VideoScriptError, match="value"):
        script._validate(data, CFG)

def test_validate_rejects_chart_item_with_bool_value():
    data = _script_with_card({"chart": {"kind": "bar",
                              "items": [{"label": "A", "value": True}, {"label": "B", "value": 2}]}})
    with pytest.raises(VideoScriptError, match="value"):
        script._validate(data, CFG)

def test_validate_accepts_valid_line_chart():
    data = _script_with_card({"chart": {"kind": "line",
                              "items": [{"value": 1}, {"value": 2}, {"value": 5}], "unit": "%"}})
    s = script._validate(data, CFG)
    assert s.cards[3].chart.kind == "line"

def test_validate_rejects_empty_screenshot_query():
    data = _script_with_card({"screenshot": {"query": "  "}})
    with pytest.raises(VideoScriptError, match="query"):
        script._validate(data, CFG)

def test_validate_rejects_screenshot_query_too_long():
    data = _script_with_card({"screenshot": {"query": "x" * 101}})
    with pytest.raises(VideoScriptError, match="query"):
        script._validate(data, CFG)

def test_validate_accepts_valid_screenshot():
    data = _script_with_card({"screenshot": {"query": "GitHub OpenAI Codex"}})
    s = script._validate(data, CFG)
    assert s.cards[3].screenshot.query == "GitHub OpenAI Codex"

def test_build_prompt_mentions_chart_and_screenshot():
    sysp, _ = script.build_prompt(_cand(), _post(), VOICE, CFG)
    assert "chart" in sysp and "screenshot" in sysp

def test_build_prompt_shape_hint_includes_chart_and_screenshot():
    sysp, _ = script.build_prompt(_cand(), _post(), VOICE, CFG)
    assert "chart?" in sysp and "screenshot?" in sysp


def test_chips_cards_need_labels_not_numbers():
    """Chips are names, so demanding a numeric value would force the writer
    to invent meaningless figures -- labels are what get validated."""
    ok = _script_with_card({"chart": {"kind": "chips",
                                      "items": [{"label": "Flare"}, {"label": "Sunburst"}]}})
    out = script._validate(ok, CFG)
    assert out.cards[3].chart.kind == "chips"

    bad = _script_with_card({"chart": {"kind": "chips",
                                       "items": [{"label": ""}, {"label": "Sunburst"}]}})
    with pytest.raises(VideoScriptError, match="label"):
        script._validate(bad, CFG)


def test_gauge_needs_a_score_and_a_ceiling():
    ok = _script_with_card({"chart": {"kind": "gauge",
                                      "items": [{"label": "Điểm", "value": 98.6},
                                                {"label": "Tối đa", "value": 100}]}})
    out = script._validate(ok, CFG)
    assert out.cards[3].chart.kind == "gauge"

    bad = _script_with_card({"chart": {"kind": "gauge",
                                       "items": [{"label": "Điểm", "value": 98.6}]}})
    with pytest.raises(VideoScriptError, match="items"):
        script._validate(bad, CFG)


def _reply_with_word_count(target_words):
    """A valid script whose displayed-word count lands near `target_words`."""
    # 40 cards is the card-count ceiling, so length is varied per card
    # instead -- otherwise an over-long script trips card count first and
    # never reaches the word-count path under test.
    n = 40
    per = max(4, round(target_words / n))
    line = " ".join(["từ"] * per)
    cards = [{"lines": [line], "variant": "stack", "anchor": "mid",
              "motion_in": "rise", "motion_out": "up"} for _ in range(n)]
    return json.dumps({
        "sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 6}],
        "cards": cards,
    }, ensure_ascii=False)


def test_slightly_overlong_script_is_kept_not_discarded():
    """A real draft was thrown away for running 509 words against a 490 cap,
    losing the whole script -- and the user's turn -- over pacing. An
    off-length but renderable script is now kept after the retry."""
    over = _reply_with_word_count(560)
    calls = []
    def llm(system, user, provider="auto"):
        calls.append(user); return over
    s = script.generate(_cand(), _post(), VOICE,
                        {"target_seconds": 150, "words_min": 380, "words_max": 490},
                        llm=llm)
    assert len(calls) == 2, "it still retries once before settling"
    assert s.word_count > 490


def test_absurdly_long_script_is_still_rejected():
    """Salvage has a ceiling: a script twice the intended length would blow
    the video's runtime, so that one still fails loudly."""
    huge = _reply_with_word_count(1400)
    def llm(system, user, provider="auto"):
        return huge
    with pytest.raises(VideoScriptError, match="word count"):
        script.generate(_cand(), _post(), VOICE,
                        {"target_seconds": 150, "words_min": 380, "words_max": 490},
                        llm=llm)
