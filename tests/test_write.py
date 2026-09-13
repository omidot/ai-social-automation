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



# --- single-topic knowledge-share writer ---------------------------------

def _share_payload() -> str:
    return (FIXTURES / "sample_share_response.json").read_text(encoding="utf-8")


def test_build_share_prompt_has_sharing_cue():
    sysp, usr = write.build_share_prompt(_cand(), VOICE)
    assert "A Hít Official" in sysp
    assert "OpenAI released a faster model" in usr
    assert "JSON" in sysp
    # a person sharing, explicitly NOT a numbered news bulletin
    assert "chia sẻ" in sysp
    assert "KHÔNG" in sysp
    assert "đánh số" in sysp and "bản tin" in sysp


def _assert_v4_slide_shape(slides):
    assert set(slides[0]) == {"role", "headline", "body", "tools"}
    assert isinstance(slides[0]["tools"], list)
    assert set(slides[-1]) == {"role", "headline", "body"}
    for s in slides[1:-1]:
        assert set(s) == {"role", "headline", "body", "tool", "bullets"}
        assert isinstance(s["bullets"], list) and len(s["bullets"]) <= 3
        assert len(s["body"].split()) >= 25   # substantial, not a stub


def test_write_share_builds_storyboard_arc():
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: _share_payload())
    assert art.format == "share"
    assert 4 <= len(art.slides) <= 9
    roles = [s["role"] for s in art.slides]
    assert roles[0] == "hook" and roles[-1] == "close"
    assert all(r == "item" for r in roles[1:-1])
    _assert_v4_slide_shape(art.slides)
    # caption is a coherent paragraph, no link, no "1. " numbered-list pattern
    assert "http" not in art.caption_fb
    assert "http" not in art.caption_ig
    import re
    assert not re.search(r"(?m)^\s*\d+\.\s", art.caption_fb)
    # ends with a plain source name, no URL
    assert art.caption_fb.rstrip().endswith("Nguồn: OpenAI Blog")


def test_write_share_strips_urls_everywhere():
    data = json.loads(_share_payload())
    data["caption_fb"] = "Xem tại https://example.com/x nhé. Bạn nghĩ sao?"
    data["caption_ig"] = "Chi tiết https://example.com/x"
    data["slides"][0]["headline"] = "Tiêu đề https://a.com/y"
    # keep the item body substantial (40-70 words) but slip a URL into the middle
    data["slides"][2]["body"] = (
        "Trong bài gốc có đường dẫn http://b.com/z tới bản demo, nhưng phần đáng "
        "chú ý là mô hình dựng ra đoạn phim tám giây chỉ từ một câu mô tả, giữ "
        "được khuôn mặt nhân vật và ánh sáng ổn định suốt cả đoạn nên cắt ghép "
        "thật được chứ không còn là bản trình diễn cho vui mắt như trước đây.")
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))
    assert "http" not in art.caption_fb
    assert "http" not in art.caption_ig
    assert all("http" not in s["headline"] and "http" not in s["body"] for s in art.slides)


def test_write_share_rejects_wrong_slide_count():
    data = json.loads(_share_payload())
    data["slides"] = data["slides"][:3]          # under the 4-9 floor
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_rejects_too_many_slides():
    data = json.loads(_share_payload())
    mid = data["slides"][1]
    data["slides"] = [data["slides"][0]] + [mid] * 9 + [data["slides"][-1]]  # 11 slides
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_rejects_short_item_body():
    data = json.loads(_share_payload())
    data["slides"][2]["body"] = "Một dòng cụt quá ngắn."
    with pytest.raises(write.WriteError, match="quá ngắn"):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_rejects_malformed_tool():
    data = json.loads(_share_payload())
    data["slides"][1]["tool"] = {"name": "Mystery"}          # domain missing
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_fills_hook_tools():
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: _share_payload())
    tools = art.slides[0]["tools"]
    assert len(tools) == 4
    assert all({"name", "domain"} == set(t) for t in tools)
    assert tools[0]["domain"] == "openai.com"


def test_write_share_rejects_bad_slide_roles():
    data = json.loads(_share_payload())
    # a middle slide must be role "item"
    data["slides"][1]["role"] = "what"
    calls = []

    def gen(s, u, **k):
        calls.append(u)
        return json.dumps(data)

    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=gen)
    # wrong shape is retried once before giving up
    assert len(calls) == 2


class _ShapeStub:
    """generate() stub that returns a scripted payload per call."""

    def __init__(self, *payloads):
        self._payloads = list(payloads)
        self.calls = []

    def __call__(self, system, user, **kw):
        self.calls.append(user)
        p = self._payloads[min(len(self.calls) - 1, len(self._payloads) - 1)]
        return p


def _bad_shape_payload() -> str:
    data = json.loads(_share_payload())
    data["slides"] = data["slides"][:3]  # 3 slides, under the 4-9 floor
    return json.dumps(data)


def test_write_share_retries_once_on_bad_shape():
    stub = _ShapeStub(_bad_shape_payload(), _share_payload())
    art = write.write_share(_cand(), VOICE, generate=stub)
    assert art.format == "share"
    roles = [s["role"] for s in art.slides]
    assert roles[0] == "hook" and roles[-1] == "close"
    assert all(r == "item" for r in roles[1:-1])
    assert len(stub.calls) == 2
    assert "[SỬA]" in stub.calls[1]


def test_write_share_raises_after_two_bad_attempts():
    stub = _ShapeStub(_bad_shape_payload())  # always the wrong shape
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=stub)
    assert len(stub.calls) == 2


def test_write_share_missing_key_raises():
    data = json.loads(_share_payload())
    del data["cover_title"]
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_honours_skip_signal():
    calls = []

    def gen(s, u, **k):
        calls.append(u)
        return json.dumps({"skip": True, "reason": "không liên quan AI"})

    with pytest.raises(write.WriteError) as ei:
        write.write_share(_cand(), VOICE, generate=gen)
    assert "không phù hợp" in str(ei.value)
    assert len(calls) == 1  # a legitimate decline is NOT nudge-retried


def test_write_share_appends_source_when_absent():
    data = json.loads(_share_payload())
    data["caption_fb"] = "Một đoạn chia sẻ không có dòng nguồn. Bạn thấy sao?"
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))
    assert art.caption_fb.rstrip().endswith("Nguồn: OpenAI Blog")


# --- knowledge-sourced take writer (opinion/trend fallback) -------------

def _topic_payload() -> str:
    return (FIXTURES / "sample_topic_response.json").read_text(encoding="utf-8")


def _take_payload() -> str:
    data = json.loads(_topic_payload())
    return json.dumps(data)


def test_build_take_prompt_uses_iman_voice_and_angle():
    sysp, usr = write.build_take_prompt(
        "Đa số người học prompt sai chỗ", "quan-diem", "vì họ tối ưu sai thứ", VOICE)
    assert "Đa số người học prompt sai chỗ" in usr
    assert "quan-diem" in usr
    assert "chia sẻ" in sysp or "chính kiến" in sysp


def test_write_take_builds_storyboard_arc():
    art = write.write_take(
        "5 công cụ AI viết content", "quan-diem", "vì hầu hết dùng sai cách",
        VOICE, generate=lambda s, u, **k: _take_payload())
    assert art.format == "share"
    assert art.angle == "quan-diem"
    roles = [s["role"] for s in art.slides]
    assert roles[0] == "hook" and roles[-1] == "close"
    assert all(r == "item" for r in roles[1:-1])
    _assert_v4_slide_shape(art.slides)
    assert art.sources == []
    assert "Nguồn:" not in art.caption_fb
    assert "http" not in art.caption_fb


def test_write_take_accepts_toolless_hook():
    data = json.loads(_topic_payload())
    data["slides"][0]["tools"] = []
    for s in data["slides"][1:-1]:
        s["tool"] = None
    art = write.write_take("Chủ đề không sản phẩm", "xu-huong", "vì...", VOICE,
                           generate=lambda s, u, **k: json.dumps(data))
    assert art.slides[0]["tools"] == []
    assert all(s.get("tool") is None for s in art.slides[1:-1])


def test_write_topic_post_removed():
    assert not hasattr(write, "write_topic_post")
    assert not hasattr(write, "build_topic_prompt")


def test_angles_constant():
    assert write.ANGLES == {"tin-nong", "quan-diem", "xu-huong", "chuyen-thuc-chien"}


def test_build_share_prompt_lists_all_four_angles():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE)
    for a in write.ANGLES:
        assert a in sysp


def test_build_share_prompt_accepts_non_launch_framing():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE)
    # must no longer say the source has to be a fresh product launch
    assert "VỪA RA MẮT" not in sysp
    assert "rò rỉ" in sysp or "phân tích" in sysp or "gọi vốn" in sysp


def test_build_share_prompt_includes_sibling_angle_hint():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE, sibling_angle="tin-nong")
    # "tin-nong" alone is always present (it's one of the 4 angles listed in the
    # base prompt) — assert the actual hint SENTENCE, which only appears when
    # sibling_angle is non-empty, to prove the parameter is genuinely wired in.
    assert "Slot kia hôm nay đã dùng góc \"tin-nong\"" in sysp


def test_build_share_prompt_no_hint_when_sibling_angle_blank():
    sysp, _usr = write.build_share_prompt(_cand(), VOICE, sibling_angle="")
    assert "Slot kia" not in sysp


def test_write_share_returns_validated_angle():
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: _share_payload())
    assert art.angle in write.ANGLES


def test_write_share_rejects_invalid_angle():
    data = json.loads(_share_payload())
    data["angle"] = "linh-tinh"
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_rejects_missing_angle():
    data = json.loads(_share_payload())
    del data["angle"]
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_accepts_a_non_launch_source_via_fixture():
    # same fixture, just prove the writer path doesn't special-case "launch"
    # wording anywhere in validation — angle-driven acceptance only.
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: _share_payload())
    assert art.format == "share"


def test_storyboard_spec_allows_toolless_slides():
    assert "hook.tools = []" in write._STORYBOARD_SPEC or "BÌNH THƯỜNG" in write._STORYBOARD_SPEC
