from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from pipeline import article_approve
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []; self.acks = []
    def answer_callback(self, cid, text=""): self.acks.append(text)
    def send_message(self, text, buttons=None): self.msgs.append(text)


class FakeMeta:
    def __init__(self): self.scheduled = None; self.ig = None
    def fb_upload_photo(self, p): return "fb:" + Path(p).name
    def fb_create_post(self, msg, ids, scheduled_publish_time=None, now_unix=None):
        self.scheduled = scheduled_publish_time
        return {"id": "P_1", "url": "https://facebook.com/P_1",
                "scheduled": scheduled_publish_time is not None}
    def ig_publish_images(self, urls, caption):
        self.ig = (urls, caption); return {"ok": True, "media_id": "IG_1"}


def _seed(root, status="draft"):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status=status, format="deep",
           text_fb="body", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01_cover.jpg"],
           image_urls=["https://raw/base/assets/posts/2026-09-06/morning/01_cover.jpg"],
           slot_ict="11:30", sources=[{"name": "OpenAI", "url": "https://o/x"}])
    return ds


def _cbq(action):
    return {"id": "cb1", "data": f"art:2026-09-06:morning:{action}"}


def test_now_publishes_both(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert res == "posted:2026-09-06:morning"
    assert meta.scheduled is None and meta.ig is not None
    assert ds.get("2026-09-06", "morning")["status"] == "posted"


def test_sched_uses_native_schedule(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)     # 07:40 ICT
    article_approve.handle_callback(_cbq("sched"), ds, tg, meta, tmp_path, now)
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "scheduled"
    assert meta.scheduled == article_approve.slot_unix("2026-09-06", "11:30")
    assert slot["ig_due"]


def test_late_callback_on_posted_is_ignored(tmp_path):
    ds = _seed(tmp_path, status="posted")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert res is None
    assert tg.acks == ["Bài này đã xử lý."]


def test_expire_stale_marks_old_drafts(tmp_path):
    ds = _seed(tmp_path)
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)     # >24h after 11:30 ICT slot
    tg = FakeTG()
    out = article_approve.expire_stale(ds, tg, now)
    assert out == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["status"] == "expired"


def test_slot_unix_is_ict():
    # 2026-09-06 11:30 ICT == 2026-09-06 04:30 UTC
    assert article_approve.slot_unix("2026-09-06", "11:30") == int(
        datetime(2026, 9, 6, 4, 30, tzinfo=timezone.utc).timestamp())
