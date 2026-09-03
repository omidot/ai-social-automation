import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from pipeline import approve_poll
from pipeline.state import State

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


class FakeTG:
    def __init__(self):
        self.msgs = []
        self.docs = []
        self.acks = []

    def send_message(self, text, buttons=None):
        self.msgs.append(text)

    def send_document(self, path, caption=""):
        self.docs.append((path, caption))

    def answer_callback(self, cid, text=""):
        self.acks.append((cid, text))


class FakeMeta:
    pass


def _pending(st, pid, created):
    rec = {"id": pid, "created_at": created.isoformat(), "angle": "tin-tuc",
           "caption_fb": "c", "caption_ig": "c", "hashtags": ["#AI"],
           "images": ["a.jpg"], "youtube": {"title": "t", "desc": "d"},
           "tiktok": {"caption": "tk"}, "source": {"url": "u", "name": "n"}, "low_media": False}
    st.pending_add(rec)
    return rec


def _cbq(data, uid=1):
    return {"update_id": uid, "callback_query": {"id": "cb1", "data": data,
            "message": {"message_id": 10}}}


def test_approve_publishes_and_moves(tmp_path, monkeypatch):
    st = State(tmp_path / "data")
    _pending(st, "p1", NOW)
    monkeypatch.setattr(approve_poll.publish, "publish",
                        lambda pending, meta, outdir: {"id": "p1", "posted_at": NOW.isoformat(),
                                                       "facebook": {"ok": True},
                                                       "instagram": {"ok": True}})
    tg = FakeTG()
    res = approve_poll.handle_update(_cbq("approve:p1"), st, tg, FakeMeta(), tmp_path, NOW)
    assert res == "approved:p1"
    assert st.pending_list() == []
    assert (tmp_path / "data/posted/p1.json").exists()
    assert tg.acks


def test_reject_removes_pending(tmp_path):
    st = State(tmp_path / "data")
    _pending(st, "p2", NOW)
    tg = FakeTG()
    res = approve_poll.handle_update(_cbq("reject:p2"), st, tg, FakeMeta(), tmp_path, NOW)
    assert res == "rejected:p2" and st.pending_list() == []


def test_edit_keeps_pending_and_sends_doc(tmp_path):
    st = State(tmp_path / "data")
    pid = "2026-09-03-p3"
    _pending(st, pid, NOW)
    (tmp_path / "output/2026-09-03" / pid).mkdir(parents=True)
    (tmp_path / "output/2026-09-03" / pid / "meta.json").write_text("{}", encoding="utf-8")
    tg = FakeTG()
    res = approve_poll.handle_update(_cbq(f"edit:{pid}"), st, tg, FakeMeta(), tmp_path, NOW)
    assert res == f"edit:{pid}"
    assert [r["id"] for r in st.pending_list()] == [pid]
    assert tg.docs


def test_expire_stale(tmp_path):
    st = State(tmp_path / "data")
    _pending(st, "old", NOW - timedelta(hours=13))
    _pending(st, "fresh", NOW - timedelta(hours=1))
    tg = FakeTG()
    removed = approve_poll.expire_stale(st, tg, ttl_hours=12, now=NOW)
    assert removed == ["old"]
    assert [r["id"] for r in st.pending_list()] == ["fresh"]


def test_poll_advances_offset(tmp_path, monkeypatch):
    st = State(tmp_path / "data")
    _pending(st, "p9", NOW)
    monkeypatch.setattr(approve_poll.publish, "publish",
                        lambda *a, **k: {"id": "p9", "posted_at": NOW.isoformat(),
                                         "facebook": {"ok": True}, "instagram": {"ok": True}})

    class TG(FakeTG):
        def get_updates(self, offset, timeout=0):
            return [] if offset else [_cbq("approve:p9", uid=7)]

    monkeypatch.setattr(approve_poll, "Telegram", lambda: TG())
    monkeypatch.setattr(approve_poll, "_meta", lambda: FakeMeta())
    out = approve_poll.poll(tmp_path, NOW)
    assert out["handled"] == ["approved:p9"]
    assert State(tmp_path / "data").offset_load() == 8
