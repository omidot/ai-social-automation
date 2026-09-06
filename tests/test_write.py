import json
from datetime import datetime, timezone
import pytest
from pipeline.models import Candidate
from pipeline import write
from tests.conftest import FIXTURES

VOICE = {"xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "giong": "thân thiện",
         "cam_ky": ["không giật tít sai"], "ten_kenh": "A Hít Official",
         "mo_bai_mau": ["Có tin này hay nè:"], "cta_mau": ["Bạn nghĩ sao?"]}


def _cand():
    return Candidate(url="https://openai.com/blog/new", title="OpenAI new model",
                     source="rss:OpenAI Blog",
                     published_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                     summary="new model", full_text="OpenAI released a faster model...")


def test_build_prompt_includes_voice_and_article():
    sysp, usr = write.build_prompt(_cand(), VOICE)
    assert "A Hít Official" in sysp
    assert "OpenAI released a faster model" in usr
    assert "JSON" in sysp


def test_write_post_parses_and_validates():
    payload = (FIXTURES / "sample_llm_response.json").read_text(encoding="utf-8")
    post = write.write_post(_cand(), VOICE, generate=lambda s, u, **k: payload)
    assert post.angle == "tin-tuc"
    assert post.hashtags[0] == "#AI"
    assert post.caption_fb.strip().endswith("Nguồn: OpenAI Blog — https://openai.com/blog/new")


def test_write_post_appends_source_if_missing():
    data = json.loads((FIXTURES / "sample_llm_response.json").read_text())
    data["caption_fb"] = "Nội dung không có nguồn."
    post = write.write_post(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))
    assert post.caption_fb.endswith("Nguồn: OpenAI Blog — https://openai.com/blog/new")


def test_write_post_bad_angle_raises():
    data = json.loads((FIXTURES / "sample_llm_response.json").read_text())
    data["angle"] = "clickbait-xyz"
    with pytest.raises(write.WriteError):
        write.write_post(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_post_missing_key_raises():
    data = json.loads((FIXTURES / "sample_llm_response.json").read_text())
    del data["caption_ig"]
    with pytest.raises(write.WriteError):
        write.write_post(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_decide_format():
    from pipeline.write import decide_format
    assert decide_format([(90.0, None)], margin=12) == "deep"
    assert decide_format([(90.0, None), (70.0, None)], margin=12) == "deep"
    assert decide_format([(90.0, None), (85.0, None)], margin=12) == "roundup"
    # Exact-boundary case: difference == margin must be "deep" (testing >= not >)
    assert decide_format([(90.0, None), (78.0, None)], margin=12) == "deep"
    # Empty-list case: documents the defensive <= 1 behavior
    assert decide_format([], margin=12) == "deep"


def test_write_deep_builds_article():
    from pipeline.write import write_deep
    payload = (FIXTURES / "sample_deep_response.json").read_text(encoding="utf-8")
    art = write_deep(_cand(), VOICE, generate=lambda s, u, **k: payload)
    assert art.format == "deep"
    assert art.cover_title == "OPENAI RA MẮT MÔ HÌNH MỚI"
    assert 3 <= len(art.image_briefs) <= 4
    assert art.sources == [{"name": "OpenAI Blog", "url": "https://openai.com/blog/new"}]
    assert art.caption_fb.rstrip().endswith("Nguồn: OpenAI Blog — https://openai.com/blog/new")


def test_write_roundup_one_brief_per_item():
    from pipeline.write import write_roundup
    payload = (FIXTURES / "sample_roundup_response.json").read_text(encoding="utf-8")
    cands = [_cand(),
             Candidate(url="https://b/1", title="Nvidia GPU", source="rss:B",
                       published_at=datetime(2026, 9, 3, tzinfo=timezone.utc), summary="x"),
             Candidate(url="https://c/2", title="Google model", source="rss:C",
                       published_at=datetime(2026, 9, 3, tzinfo=timezone.utc), summary="y")]
    art = write_roundup(cands, VOICE, generate=lambda s, u, **k: payload)
    assert art.format == "roundup"
    assert len(art.image_briefs) == 3
    assert len(art.sources) == 3
    assert art.sources[1] == {"name": "B", "url": "https://b/1"}
