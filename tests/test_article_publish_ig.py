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


def test_corrupt_file_is_skipped_others_processed(tmp_path):
    daily = tmp_path / "data" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    (daily / "2026-09-05.json").write_text("{ not json", encoding="utf-8")
    ds = _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 46, tzinfo=timezone.utc)
    out = article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    assert out["published"] == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["result"]["ig"]["media_id"] == "IG_9"


def test_ig_failure_increments_attempts(tmp_path):
    ds = _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    tg, meta = FakeTG(), FakeMeta(ok=False)
    now = datetime(2026, 9, 6, 4, 46, tzinfo=timezone.utc)
    article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    slot = ds.get("2026-09-06", "morning")
    assert slot["ig_attempts"] == 1
    assert slot["result"]["ig"] is None
    assert any("lần 1/3" in m for m in tg.msgs)


def test_ig_gives_up_after_3_attempts(tmp_path):
    ds = _seed(tmp_path, ig_due="2026-09-06T04:30:00+00:00")
    ds.put("2026-09-06", "morning", ig_attempts=2)
    tg, meta = FakeTG(), FakeMeta(ok=False)
    now = datetime(2026, 9, 6, 4, 46, tzinfo=timezone.utc)
    article_publish_ig.run(tmp_path, now, tg=tg, meta=meta)
    slot = ds.get("2026-09-06", "morning")
    assert slot["ig_attempts"] == 3
    assert slot["result"]["ig"] == {"ok": False, "error": "ig down", "attempts": 3}
    assert any("bỏ cuộc" in m for m in tg.msgs)
    # slot no longer qualifies -> a later tick must not re-call the publisher
    meta2 = FakeMeta(ok=False)
    article_publish_ig.run(tmp_path, now, tg=FakeTG(), meta=meta2)
    assert meta2.calls == []
