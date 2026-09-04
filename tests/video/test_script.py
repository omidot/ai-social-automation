import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.models import Candidate, PostContent
from pipeline.video import script, VideoScriptError
from pipeline.video.models import Script

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
