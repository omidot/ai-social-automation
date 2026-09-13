import json
from datetime import datetime, timedelta, timezone

import pytest

from pipeline import topics
from pipeline.daily_state import DailyState

VOICE = {"ten_kenh": "A Hít Official", "xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}}


def _d(offset_days: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=offset_days)).strftime("%Y-%m-%d")


def test_recent_titles_reads_daily_state(tmp_path):
    ds = DailyState(tmp_path / "data")
    ds.put(_d(5), "morning", status="posted", title="Bài trong cửa sổ")
    ds.put(_d(100), "evening", status="posted", title="Bài quá cũ")
    assert topics.recent_titles(tmp_path, 45) == ["Bài trong cửa sổ"]


def test_recent_titles_skips_corrupt_file(tmp_path):
    ds = DailyState(tmp_path / "data")
    ds.put(_d(3), "morning", status="draft", title="Bài tốt")
    (tmp_path / "data" / "daily" / f"{_d(4)}.json").write_text("{ not json", encoding="utf-8")
    assert topics.recent_titles(tmp_path, 45) == ["Bài tốt"]


def test_propose_topic_parses_and_validates():
    good = lambda s, u, **k: json.dumps(
        {"topic": "5 công cụ AI dựng video", "angle": "quan-diem", "why": "giúp bạn ra video nhanh hơn"})
    out = topics.propose_topic({}, [], VOICE, good)
    assert out == {"topic": "5 công cụ AI dựng video", "angle": "quan-diem", "why": "giúp bạn ra video nhanh hơn"}

    with pytest.raises(topics.TopicError):
        topics.propose_topic({}, [], VOICE, lambda s, u, **k: json.dumps({}))


def test_propose_topic_passes_recent_to_prompt():
    seen = {}

    def gen(s, u, **k):
        seen["user"] = u
        return json.dumps({"topic": "chủ đề mới", "angle": "abc"})

    topics.propose_topic({"seeds": ["x"]},
                         ["Tiêu đề đã đăng A", "Tiêu đề đã đăng B"], VOICE, gen)
    assert "Tiêu đề đã đăng A" in seen["user"]
    assert "Tiêu đề đã đăng B" in seen["user"]


def test_load_topics_has_takes_and_shifts(tmp_path):
    (tmp_path / "config").mkdir()
    import shutil
    shutil.copy("config/topics.yaml", tmp_path / "config" / "topics.yaml")
    t = topics.load_topics(tmp_path)
    assert "takes" in t and "shifts" in t
    assert "formats" not in t and "seeds" not in t


def test_propose_topic_returns_angle_and_why():
    spec = topics.propose_topic(
        {"takes": ["A"], "shifts": ["B"]}, [], VOICE,
        generate=lambda s, u, **k: json.dumps(
            {"topic": "Một chủ đề", "angle": "xu-huong", "why": "vì lý do X"}))
    assert spec == {"topic": "Một chủ đề", "angle": "xu-huong", "why": "vì lý do X"}


def test_propose_topic_defaults_bad_angle_to_quan_diem(caplog):
    spec = topics.propose_topic(
        {"takes": ["A"], "shifts": ["B"]}, [], VOICE,
        generate=lambda s, u, **k: json.dumps(
            {"topic": "Một chủ đề", "angle": "linh-tinh", "why": "x"}))
    assert spec["angle"] == "quan-diem"


def test_propose_topic_prompt_includes_sibling_angle_hint():
    sysp, _usr = topics._build_prompt({"takes": [], "shifts": []}, [], VOICE,
                                      sibling_angle="tin-nong")
    assert "tin-nong" in sysp
