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


def test_write_share_builds_5_slide_arc():
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: _share_payload())
    assert art.format == "share"
    assert len(art.slides) == 5
    assert [s["role"] for s in art.slides] == ["hook", "what", "why", "how", "close"]
    assert all(set(s) == {"role", "headline", "body"} for s in art.slides)
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
    data["slides"][2]["body"] = "Thân bài http://b.com/z ok"
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))
    assert "http" not in art.caption_fb
    assert "http" not in art.caption_ig
    assert all("http" not in s["headline"] and "http" not in s["body"] for s in art.slides)


def test_write_share_rejects_wrong_slide_count():
    data = json.loads(_share_payload())
    data["slides"] = data["slides"][:4]
    with pytest.raises(write.WriteError):
        write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))


def test_write_share_rejects_bad_slide_roles():
    data = json.loads(_share_payload())
    # swap two roles so the order is no longer hook/what/why/how/close
    data["slides"][1]["role"], data["slides"][2]["role"] = (
        data["slides"][2]["role"], data["slides"][1]["role"])
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
    data["slides"] = data["slides"][:4]  # 4 slides, not 5
    return json.dumps(data)


def test_write_share_retries_once_on_bad_shape():
    stub = _ShapeStub(_bad_shape_payload(), _share_payload())
    art = write.write_share(_cand(), VOICE, generate=stub)
    assert art.format == "share"
    assert [s["role"] for s in art.slides] == ["hook", "what", "why", "how", "close"]
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


def test_write_share_appends_source_when_absent():
    data = json.loads(_share_payload())
    data["caption_fb"] = "Một đoạn chia sẻ không có dòng nguồn. Bạn thấy sao?"
    art = write.write_share(_cand(), VOICE, generate=lambda s, u, **k: json.dumps(data))
    assert art.caption_fb.rstrip().endswith("Nguồn: OpenAI Blog")
