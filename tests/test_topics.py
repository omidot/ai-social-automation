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
        {"topic": "5 công cụ AI dựng video", "angle": "giúp bạn ra video nhanh hơn"})
    out = topics.propose_topic({}, [], VOICE, good)
    assert out == {"topic": "5 công cụ AI dựng video", "angle": "giúp bạn ra video nhanh hơn"}

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
