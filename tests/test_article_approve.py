from datetime import datetime, timezone, timedelta
from pathlib import Path
from pipeline import article_approve
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []; self.acks = []
    def answer_callback(self, cid, text=""): self.acks.append(text)
    def send_message(self, text, buttons=None): self.msgs.append(text)


class FakeMeta:
    def __init__(self):
        self.scheduled = None; self.ig = None
        self.fb_deleted = []; self.ig_deleted = []
    def fb_delete_post(self, pid): self.fb_deleted.append(pid); return {"success": True}
    def ig_delete_media(self, mid): self.ig_deleted.append(mid); return {"success": True}
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


def _seed_scheduled(root):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", format="share",
           text_fb="body", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01.jpg"],
           image_urls=["https://raw/x/01.jpg"], slot_ict="11:30", sources=[],
           fb_post_id="P_1", result={"fb": {"id": "P_1"}, "ig": {"media_id": "IG_1"}})
    return ds


def test_undo_deletes_fb_and_ig_within_grace(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)     # 5 min after slot
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now)
    assert res == "discarded:2026-09-06:morning"
    assert meta.fb_deleted == ["P_1"] and meta.ig_deleted == ["IG_1"]
    assert ds.get("2026-09-06", "morning")["status"] == "discarded"


def test_undo_past_grace_is_refused(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)      # 30 min after slot
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now)
    assert res == "undo-expired:2026-09-06:morning"
    assert meta.fb_deleted == [] and meta.ig_deleted == []
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"
    assert any("gỡ thủ công" in m for m in tg.msgs)


def test_undo_missing_slot_is_noop(tmp_path):
    ds = DailyState(tmp_path / "data")
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)
    assert article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now) is None
    assert meta.fb_deleted == []


def test_legacy_now_button_is_inert(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)
    assert article_approve.handle_callback(_cbq("now"), ds, tg, meta, tmp_path, now) is None
    assert meta.fb_deleted == [] and meta.scheduled is None
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"


def test_undo_fb_delete_error_still_marks_discarded(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg = FakeTG()

    class DelBoom(FakeMeta):
        def fb_delete_post(self, pid): raise RuntimeError("Graph 100")

    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, DelBoom(), tmp_path, now)
    assert res == "discarded:2026-09-06:morning"
    assert ds.get("2026-09-06", "morning")["status"] == "discarded"
    assert any("Lỗi" in m for m in tg.msgs)


def test_undo_on_posted_slot(tmp_path):
    """The normal post-publish undo lands on a slot article_publish_ig already
    promoted scheduled -> posted. set_status refuses to leave TERMINAL, so the
    undo must force the discard via put() or state ends up lying."""
    ds = DailyState(tmp_path / "data")
    ds.put("2026-09-06", "morning", status="posted", format="share",
           text_fb="body", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01.jpg"],
           image_urls=["https://raw/x/01.jpg"], slot_ict="11:30", sources=[],
           fb_post_id="P_1", result={"fb": {"id": "P_1"}, "ig": {"media_id": "IG_1"}})
    tg, meta = FakeTG(), FakeMeta()
    now = datetime(2026, 9, 6, 4, 40, tzinfo=timezone.utc)     # 10 min after 04:30 UTC slot
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now)
    assert res == "discarded:2026-09-06:morning"
    assert meta.fb_deleted == ["P_1"] and meta.ig_deleted == ["IG_1"]
    assert ds.get("2026-09-06", "morning")["status"] == "discarded"


def test_undo_commit_failure_acks_and_does_not_raise(tmp_path):
    ds = _seed_scheduled(tmp_path)
    tg, meta = FakeTG(), FakeMeta()
    real_put = ds.put

    def boom_put(date, slot, **fields):
        if fields.get("status") == "discarded":
            raise RuntimeError("state write 500")
        return real_put(date, slot, **fields)

    ds.put = boom_put
    now = datetime(2026, 9, 6, 4, 35, tzinfo=timezone.utc)
    res = article_approve.handle_callback(_cbq("undo"), ds, tg, meta, tmp_path, now)
    assert res == "error:2026-09-06:morning"
    assert meta.fb_deleted == ["P_1"] and meta.ig_deleted == ["IG_1"]
    assert tg.acks and "Lỗi khi gỡ" in tg.acks[-1]
    assert ds.get("2026-09-06", "morning")["status"] != "discarded"


def test_expire_stale_marks_old_drafts(tmp_path):
    ds = _seed(tmp_path)
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)     # any time past the 11:30 ICT slot time
    tg = FakeTG()
    out = article_approve.expire_stale(ds, tg, now)
    assert out == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["status"] == "expired"


def test_expire_stale_skips_corrupt_file(tmp_path):
    daily = tmp_path / "data" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    (daily / "2026-09-04.json").write_text("{ not json", encoding="utf-8")
    ds = _seed(tmp_path)                                       # valid 2026-09-06 draft
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    tg = FakeTG()
    out = article_approve.expire_stale(ds, tg, now)
    assert out == ["2026-09-06:morning"]                        # corrupt file did not abort
    assert ds.get("2026-09-06", "morning")["status"] == "expired"


def test_poll_skips_poison_update_and_advances_offset(tmp_path, monkeypatch):
    from pipeline.state import State

    _seed(tmp_path)
    updates = [
        {"update_id": 10, "callback_query": _cbq("now")},       # poisoned below
        {"update_id": 11, "callback_query": _cbq("undo")},      # good
    ]

    class FakeTelegram:
        def __init__(self, *a, **k): self.msgs = []
        def get_updates(self, offset, timeout=0): return updates
        def send_message(self, text, buttons=None): self.msgs.append(text)
        def answer_callback(self, cid, text=""): pass

    monkeypatch.setattr(article_approve, "Telegram", FakeTelegram)
    monkeypatch.setattr(article_approve, "_meta", lambda: FakeMeta())

    real = article_approve.handle_callback
    calls = {"n": 0}

    def flaky(cbq, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("poison update")
        return real(cbq, *a, **k)

    monkeypatch.setattr(article_approve, "handle_callback", flaky)

    now = datetime(2026, 9, 6, 0, 40, tzinfo=timezone.utc)
    res = article_approve.poll(tmp_path, now=now)               # must not raise

    assert State(tmp_path / "data").offset_load() == 12          # max(update_id) + 1
    assert res["handled"] == ["discarded:2026-09-06:morning"]    # good update handled
    assert DailyState(tmp_path / "data").get("2026-09-06", "morning")["status"] == "discarded"


def test_expire_stale_sweeps_stuck_publishing(tmp_path):
    ds = _seed(tmp_path, status="publishing")
    tg = FakeTG()
    # 3h past the 11:30 ICT (== 04:30 UTC) slot -> swept
    out = article_approve.expire_stale(
        ds, tg, datetime(2026, 9, 6, 7, 30, tzinfo=timezone.utc))
    assert out == []                                            # not a "draft expired"
    assert ds.get("2026-09-06", "morning")["status"] == "posted"
    assert any("kẹt ở 'publishing'" in m for m in tg.msgs)

    # a publishing slot only 30 min past its slot is NOT swept
    ds2 = _seed(tmp_path, status="publishing")                  # rewrites file back
    tg2 = FakeTG()
    article_approve.expire_stale(
        ds2, tg2, datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc))
    assert ds2.get("2026-09-06", "morning")["status"] == "publishing"
    assert tg2.msgs == []


def test_slot_unix_is_ict():
    # 2026-09-06 11:30 ICT == 2026-09-06 04:30 UTC
    assert article_approve.slot_unix("2026-09-06", "11:30") == int(
        datetime(2026, 9, 6, 4, 30, tzinfo=timezone.utc).timestamp())


def _seed_draft_ready(root, slot_ict="11:30"):
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="draft", format="share",
           title="X", text_fb="body", text_ig="ig", hashtags=["#AI"],
           images=["assets/posts/2026-09-06/morning/01.jpg"],
           image_urls=["https://raw/x/01.jpg"], slot_ict=slot_ict, sources=[])
    return ds


def test_retry_unscheduled_schedules_ready_draft(tmp_path, monkeypatch):
    ds = _seed_draft_ready(tmp_path)
    tg = FakeTG()
    calls = []
    monkeypatch.setattr(article_approve.publish, "schedule_slot",
                        lambda ds, meta, root, date, slot, now, tg:
                            (calls.append((date, slot)),
                             ds.set_status(date, slot, "scheduled"),
                             f"scheduled:{date}:{slot}")[-1])
    now = datetime(2026, 9, 6, 0, 30, tzinfo=timezone.utc)     # before 11:30 ICT
    out = article_approve.retry_unscheduled(ds, FakeMeta(), tmp_path, tg, now)
    assert out == ["scheduled:2026-09-06:morning"]
    assert calls == [("2026-09-06", "morning")]
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"


def test_retry_unscheduled_resets_to_draft_on_failure(tmp_path, monkeypatch):
    ds = _seed_draft_ready(tmp_path)
    monkeypatch.setattr(article_approve.publish, "schedule_slot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("token")))
    now = datetime(2026, 9, 6, 0, 30, tzinfo=timezone.utc)
    out = article_approve.retry_unscheduled(ds, FakeMeta(), tmp_path, FakeTG(), now)
    assert out == []
    assert ds.get("2026-09-06", "morning")["status"] == "draft"


def test_retry_unscheduled_skips_past_slot(tmp_path, monkeypatch):
    ds = _seed_draft_ready(tmp_path)
    monkeypatch.setattr(article_approve.publish, "schedule_slot",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not schedule a past slot")))
    now = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)      # after 11:30 ICT
    assert article_approve.retry_unscheduled(ds, FakeMeta(), tmp_path, FakeTG(), now) == []


def test_expire_stale_expires_draft_the_moment_slot_passes(tmp_path):
    ds = _seed_draft_ready(tmp_path)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 4, 31, tzinfo=timezone.utc)     # 1 min past 04:30 UTC
    out = article_approve.expire_stale(ds, tg, now)
    assert out == ["2026-09-06:morning"]
    assert ds.get("2026-09-06", "morning")["status"] == "expired"
    assert any("không lên lịch được" in m for m in tg.msgs)


def test_poll_routes_video_audio_and_undo(tmp_path, monkeypatch):
    from pipeline import article_approve
    from pipeline.state import State
    seen = {"audio": 0, "undo": 0}
    monkeypatch.setattr(article_approve.render, "receive_audio",
                        lambda msg, ds, tg, root, now: seen.__setitem__("audio", seen["audio"] + 1) or "rendered:x:y")
    monkeypatch.setattr(article_approve.render, "handle_undo",
                        lambda cbq, ds, tg, root, now: seen.__setitem__("undo", seen["undo"] + 1) or "discarded:x:y")
    updates = [
        {"update_id": 20, "message": {"message_id": 1, "voice": {"file_id": "V"}}},
        {"update_id": 21, "callback_query": {"id": "c", "data": "vid:2026-09-08:morning:undo"}},
        {"update_id": 22, "callback_query": {"id": "c2", "data": "art:2026-09-08:morning:undo"}},
    ]

    class FakeTelegram:
        def __init__(self, *a, **k): pass
        def get_updates(self, offset, timeout=0): return updates
        def send_message(self, *a, **k): pass
        def answer_callback(self, *a, **k): pass
    monkeypatch.setattr(article_approve, "Telegram", FakeTelegram)
    monkeypatch.setattr(article_approve, "_meta", lambda: object())
    monkeypatch.setattr(article_approve, "handle_callback", lambda *a, **k: "art-handled")
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    res = article_approve.poll(tmp_path, now=now)
    assert seen == {"audio": 1, "undo": 1}
    assert State(tmp_path / "data").offset_load() == 23


def test_expire_stale_fails_stuck_video_render(tmp_path):
    from pipeline import article_approve
    ds = DailyState(tmp_path / "data")
    ds.put("2026-09-08", "morning", status="scheduled", slot_ict="11:30",
           video={"status": "rendering",
                  "started_at": datetime(2026, 9, 8, 2, 0, tzinfo=timezone.utc).isoformat()})
    tg = FakeTG()
    article_approve.expire_stale(ds, tg, datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc))
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "failed"
    assert any("kẹt khi render" in m for m in tg.msgs)
