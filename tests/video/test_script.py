import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.models import Candidate, PostContent
from pipeline.video import script, VideoScriptError
from pipeline.video.models import Script, VideoMeta

FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"
CFG = {"target_seconds": 40, "words_min": 110, "words_max": 140}
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
    assert "110" in sysp and "140" in sysp
    assert "A Hít Official" in sysp
    assert "OpenAI ra model nhanh gấp đôi" in usr

def test_generate_parses_valid_response():
    raw = (FX / "raw_script.json").read_text(encoding="utf-8")
    s = script.generate(_cand(), _post(), VOICE, CFG, llm=lambda sy, u, **k: raw)
    assert isinstance(s, Script)
    assert len(s.cards) == 14 and len(s.sections) == 4
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
    assert 95 <= s.word_count <= 155

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
_CFG = {"target_seconds": 40, "words_min": 110, "words_max": 140}


def _fake_full_reply():
    cards = [{"lines": [f"Dòng số {i}", "thêm vài từ nữa cho đủ"], "variant": "stack",
              "anchor": "mid", "motion_in": "rise", "motion_out": "up"} for i in range(12)]
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


def test_generate_from_article_retries_on_word_band():
    short = json.dumps({
        "sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 3}],
        "cards": [{"lines": ["ngắn"], "variant": "stack", "anchor": "mid",
                   "motion_in": "rise", "motion_out": "up"} for _ in range(10)],
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
