from datetime import datetime, timezone, timedelta
from pathlib import Path
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
        # mirror real Meta: only genuinely scheduled when >= 600s ahead
        sched = (scheduled_publish_time is not None
                 and now_unix is not None
                 and (scheduled_publish_time - now_unix) >= 600)
        return {"id": "P_1", "url": "https://facebook.com/P_1", "scheduled": sched}
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


def _cbq(action, date="2026-09-06", slot="morning"):
    return {"id": "cb1", "data": f"art:{date}:{slot}:{action}"}


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


def test_sched_too_close_publishes_now(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    # slot is 2026-09-06 11:30 ICT == 04:30 UTC; now is 5 min before -> lead 300s
    now = datetime(2026, 9, 6, 4, 25, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("sched"), ds, tg, meta, tmp_path, now)
    assert res == "posted:2026-09-06:morning"
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "posted"
    assert meta.ig is not None
    assert any("quá sát giờ" in m for m in tg.msgs)


def test_late_callback_on_posted_is_ignored(tmp_path):
    ds = _seed(tmp_path, status="posted")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert res is None
    assert tg.acks == ["Bài này đã xử lý."]
    assert meta.scheduled is None and meta.ig is None


def test_second_callback_on_scheduled_is_ignored(tmp_path):
    ds = _seed(tmp_path, status="scheduled")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert res is None
    assert meta.scheduled is None and meta.ig is None
    assert tg.acks == ["Bài này đã xử lý."]
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"


def test_missing_slot_reports_desync(tmp_path):
    ds = DailyState(tmp_path / "data")            # nothing seeded
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert res is None
    assert tg.acks == ["Không tìm thấy bài này (state chưa đồng bộ), thử lại sau."]
    assert meta.scheduled is None and meta.ig is None


def test_inflight_status_set_before_meta_call(tmp_path):
    ds = _seed(tmp_path)
    tg = FakeTG()

    class RecordingMeta(FakeMeta):
        def __init__(self, ds): super().__init__(); self._ds = ds; self.seen_status = None
        def fb_upload_photo(self, p):
            self.seen_status = self._ds.get("2026-09-06", "morning")["status"]
            return super().fb_upload_photo(p)

    meta = RecordingMeta(ds)
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now)
    assert meta.seen_status == "publishing"
    assert ds.get("2026-09-06", "morning")["status"] == "posted"


def test_exception_after_publish_marks_posted_not_draft(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()

    class PutRaisesOnce(DailyState):
        def __init__(self, inner):
            super().__init__(inner.dir.parent)
            self._raised = False
        def put(self, *a, **kw):
            if not self._raised and "result" in kw:
                self._raised = True
                raise RuntimeError("write to daily state failed")
            return super().put(*a, **kw)

    wrapped = PutRaisesOnce(ds)
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("now"), wrapped, tg, meta, tmp_path, now)
    assert res == "error:2026-09-06:morning"
    status = wrapped.get("2026-09-06", "morning")["status"]
    assert status == "posted"                       # never left draft / publishing
    assert any("kiểm tra Page" in m for m in tg.msgs)


def test_drop_marks_discarded_no_publish(tmp_path):
    ds = _seed(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("drop"), ds, tg, meta, tmp_path, now)
    assert res == "discarded:2026-09-06:morning"
    assert ds.get("2026-09-06", "morning")["status"] == "discarded"
    assert meta.scheduled is None
    assert meta.ig is None


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
