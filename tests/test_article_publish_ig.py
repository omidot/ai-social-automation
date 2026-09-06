from datetime import datetime, timezone
import pytest
from pipeline import article_publish_ig
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None): self.msgs.append(text)


class FakeMeta:
    def __init__(self, ok=True): self.ok = ok; self.calls = []
    def ig_publish_images(self, urls, caption):
        self.calls.append(urls)
        if not self.ok:
            raise RuntimeError("ig down")
        return {"ok": True, "media_id": "IG_9"}


def _seed(root, ig_due, ig_result=None):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", text_ig="ig", hashtags=["#AI"],
           image_urls=["https://raw/x.jpg"], slot_ict="11:30",
           ig_due=ig_due, result={"fb": {"scheduled": True}, "ig": ig_result})
    return ds


def test_due_slot_gets_published(tmp_path):
    ds = _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 46, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["published"] == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["result"]["ig"]["media_id"] == "IG_9"
    assert ds.get("2026-09-06", "morning")["status"] == "posted"


def test_not_due_is_skipped(tmp_path):
    _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 10, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["published"] == [] and meta.calls == []


def test_already_published_is_skipped(tmp_path):
    _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00", ig_result={"ok": True, "media_id": "old"})
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["published"] == [] and meta.calls == []


def test_failure_is_reported_and_retryable(tmp_path):
    ds = _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta(ok=False)
    now = datetime(2026, 9, 6, 4, 46, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["failed"] == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["result"]["ig"] in (None, {"ok": False})
    assert any("IG lỗi" in m for m in tg.msgs)
