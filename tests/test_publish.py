from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import publish
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))


class FakeMeta:
    def __init__(self): self.sched_arg = None; self.ig = None
    def fb_upload_photo(self, p): return "fb:" + Path(p).name
    def fb_create_post(self, msg, ids, scheduled_publish_time=None, now_unix=None):
        self.sched_arg = scheduled_publish_time
        sched = (scheduled_publish_time is not None and now_unix is not None
                 and (scheduled_publish_time - now_unix) >= 600)
        return {"id": "P_1", "url": "https://facebook.com/P_1", "scheduled": sched}
    def ig_publish_images(self, urls, caption):
        self.ig = (urls, caption); return {"ok": True, "media_id": "IG_1"}


def _seed(root):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="publishing", format="share",
           title="Chủ đề X", text_fb="thân bài", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01.jpg"],
           image_urls=["https://raw/base/assets/posts/2026-09-06/morning/01.jpg"],
           slot_ict="11:30", sources=[])
    return ds


def test_slot_unix_is_ict():
    assert publish.slot_unix("2026-09-06", "11:30") == int(
        datetime(2026, 9, 6, 4, 30, tzinfo=timezone.utc).timestamp())


def test_schedule_slot_uses_native_schedule(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)      # 07:05 ICT, lead ~4h
    res = publish.schedule_slot(ds, meta, tmp_path, "2026-09-06", "morning", now, tg)
    assert res == "scheduled:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "scheduled"
    assert slot["fb_post_id"] == "P_1"
    assert slot["ig_due"]
    assert meta.sched_arg == publish.slot_unix("2026-09-06", "11:30")
    text, buttons = tg.msgs[-1]
    assert "lên lịch" in text.lower()
    assert buttons == [("🗑 Gỡ bài", "art:2026-09-06:morning:undo")]


def test_schedule_slot_too_close_publishes_now(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 25, tzinfo=timezone.utc)     # 5 min before slot
    res = publish.schedule_slot(ds, meta, tmp_path, "2026-09-06", "morning", now, tg)
    assert res == "posted:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "posted"
    assert meta.ig is not None
    assert slot["result"]["ig"]["media_id"] == "IG_1"


def test_schedule_slot_ig_failure_still_posts(tmp_path):
    ds = _seed(tmp_path)
    tg = FakeTG()

    class IGBoom(FakeMeta):
        def ig_publish_images(self, urls, caption):
            raise RuntimeError("IG 400")

    meta = IGBoom()
    now = datetime(2026, 9, 6, 4, 25, tzinfo=timezone.utc)
    res = publish.schedule_slot(ds, meta, tmp_path, "2026-09-06", "morning", now, tg)
    assert res == "posted:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "posted"
    assert slot["result"]["ig"]["ok"] is False
    assert any("IG lỗi" in t for t, _ in tg.msgs)


def test_schedule_slot_never_raises_after_fb_post_exists(tmp_path):
    ds = _seed(tmp_path)

    class TGBoom(FakeTG):
        def send_message(self, text, buttons=None):
            raise RuntimeError("Telegram 503")

    meta = FakeMeta()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)      # scheduled branch
    res = publish.schedule_slot(ds, meta, tmp_path, "2026-09-06", "morning", now, TGBoom())
    # the guard now derives its tag from the observed status, so a scheduled
    # slot reports "scheduled:" and never the contradictory "posted:".
    assert res == "scheduled:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    # the scheduled branch already advanced the slot; the post-publish
    # bookkeeping guard must NOT downgrade "scheduled" -> "posted" (that would
    # strand IG — the IG poller only polls "scheduled", "posted" is terminal).
    assert slot["status"] == "scheduled"
    assert slot["ig_due"]                       # IG poller stays armed


def test_schedule_slot_bookkeeping_forces_posted_when_still_publishing(tmp_path):
    ds = _seed(tmp_path)
    real_set_status = ds.set_status

    def flaky_set_status(date, slot, status):
        if status == "scheduled":
            raise RuntimeError("state write 500")
        return real_set_status(date, slot, status)

    ds.set_status = flaky_set_status
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)      # scheduled branch
    res = publish.schedule_slot(ds, FakeMeta(), tmp_path, "2026-09-06", "morning", now, tg)
    assert res == "posted:2026-09-06:morning"
    # set_status("scheduled") never landed -> slot was still "publishing" when
    # the guard ran -> it is forced to "posted" (FB post exists, nothing else recorded).
    assert ds.get("2026-09-06", "morning")["status"] == "posted"
    # the operator is alerted that FB is out but the post-steps failed.
    assert any("kiểm tra Page" in t for t, _ in tg.msgs)


def test_schedule_slot_raises_when_upload_fails(tmp_path):
    ds = _seed(tmp_path)
    tg = FakeTG()

    class UploadBoom(FakeMeta):
        def fb_upload_photo(self, p):
            raise RuntimeError("(190) Session has expired")

    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError):
        publish.schedule_slot(ds, UploadBoom(), tmp_path, "2026-09-06", "morning", now, tg)
    # nothing published, status untouched by schedule_slot itself
    assert ds.get("2026-09-06", "morning")["status"] == "publishing"
