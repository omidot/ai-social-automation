from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.daily_state import DailyState
from pipeline.video import publish as pub


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))
    def answer_callback(self, cid, text=""): pass


def _settings(root, **flags):
    (root / "config").mkdir(exist_ok=True)
    body = ["video:", "  channel_footer: \"— A Hít Official\"", "  publish:"]
    for k in ("youtube", "fb_reel", "ig_reel", "tiktok"):
        body.append(f"    {k}: {str(flags.get(k, False)).lower()}")
    body.append(f"    youtube_category: {flags.get('youtube_category', 27)}")
    (root / "config" / "settings.yaml").write_text("\n".join(body) + "\n", encoding="utf-8")


def _seed(root, *, date="2026-09-09", slot="morning", status="rendered", result=None):
    ds = DailyState(root / "data")
    v = {"status": status, "meta": {"title": "Tiêu đề video AI đủ dài mười ký",
         "description": "d", "hashtags": ["#AI"], "keywords": ["ai"],
         "tiktok_caption": "c"},
         "mp4_path": f"output/{date}/{date}-x/{date}-x.mp4",
         "tg_file_id": "TG", "asset_url": None, "publish_due": "2026-09-09T04:30:00+00:00",
         "result": result or {"youtube": None, "fb_reel": None,
                              "ig_reel": None, "tiktok": None}}
    ds.put(date, slot, status="scheduled", slot_ict="11:30", video=v)
    (root / "output" / f"{date}" / f"{date}-x").mkdir(parents=True, exist_ok=True)
    (root / "output" / f"{date}" / f"{date}-x" / f"{date}-x.mp4").write_bytes(b"MP4")
    return ds


def _patch(monkeypatch, *, yt_result=None, yt_raises=None):
    monkeypatch.setattr(pub._assets, "upload_release_asset",
                        lambda mp4, name, **k: f"https://gh/rel/{name}")
    deleted = []
    monkeypatch.setattr(pub._assets, "delete_release_asset",
                        lambda name, **k: deleted.append(name) or True)

    class _YT:
        @classmethod
        def from_env(cls): return cls()
        def upload(self, mp4, meta, cfg):
            if yt_raises:
                raise yt_raises
            return yt_result or {"id": "VID", "url": "https://youtu.be/VID"}
    monkeypatch.setattr(pub._youtube, "YouTube", _YT)
    return deleted


def test_disabled_everywhere_is_skip(tmp_path, monkeypatch):
    _settings(tmp_path)                      # all False
    ds = _seed(tmp_path)
    _patch(monkeypatch)
    assert pub.publish_pending(ds, FakeTG(), tmp_path,
                               datetime(2026, 9, 9, 5, tzinfo=timezone.utc)) == []


def test_youtube_happy_path_marks_published(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path)
    deleted = _patch(monkeypatch)
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["published:2026-09-09:morning"]
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "published" and v["published_at"]
    assert v["result"]["youtube"]["id"] == "VID"
    assert v["asset_url"] is None and deleted == ["2026-09-09-morning.mp4"]
    assert any("🚀" in m for m, _ in tg.msgs)
    assert any(btns and btns[0][1] == "vid:2026-09-09:morning:unpub" for _, btns in tg.msgs)


def test_youtube_failure_increments_attempts(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path)
    _patch(monkeypatch, yt_raises=RuntimeError("boom"))
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["publishing:2026-09-09:morning"]
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "publishing"
    assert v["result"]["youtube"]["attempts"] == 1
    assert v["result"]["youtube"]["gave_up"] is False


def test_gave_up_after_5_and_slot_can_finish(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="publishing",
               result={"youtube": {"error": "e", "attempts": 4, "last_at": "x",
                                   "gave_up": False}})
    deleted = _patch(monkeypatch, yt_raises=RuntimeError("boom"))
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["published:2026-09-09:morning"]     # gave_up counts as done
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["result"]["youtube"]["gave_up"] is True
    assert v["status"] == "published" and deleted == ["2026-09-09-morning.mp4"]
    assert any("bỏ cuộc" in m for m, _ in tg.msgs)


def test_mp4_gone_resets_to_awaiting_audio(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path)
    (tmp_path / "output" / "2026-09-09" / "2026-09-09-x" / "2026-09-09-x.mp4").unlink()
    _patch(monkeypatch)
    # also block the telegram-download fallback
    monkeypatch.setattr(pub, "_download_tg_mp4", lambda *a, **k: None)
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "awaiting_audio" and "mp4" in (v["render_err"] or "")


def test_already_published_slot_is_skipped(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="published",
               result={"youtube": {"id": "V", "url": "u", "at": "x"},
                       "fb_reel": None, "ig_reel": None, "tiktok": None})
    _patch(monkeypatch)
    assert pub.publish_pending(ds, FakeTG(), tmp_path,
                               datetime(2026, 9, 9, 5, tzinfo=timezone.utc)) == []


def test_youtube_category_from_publish_block_reaches_upload(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True, youtube_category=22)
    ds = _seed(tmp_path)
    seen = {}
    monkeypatch.setattr(pub._assets, "upload_release_asset",
                        lambda mp4, name, **k: f"https://gh/rel/{name}")
    monkeypatch.setattr(pub._assets, "delete_release_asset", lambda name, **k: True)

    class _YT:
        @classmethod
        def from_env(cls): return cls()
        def upload(self, mp4, meta, cfg):
            seen.update(cfg)
            return {"id": "VID", "url": "https://youtu.be/VID"}
    monkeypatch.setattr(pub._youtube, "YouTube", _YT)
    out = pub.publish_pending(ds, FakeTG(), tmp_path,
                              datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["published:2026-09-09:morning"]
    assert seen["youtube_category"] == 22        # video.publish.youtube_category
    assert seen["channel_footer"] == "— A Hít Official"   # video.channel_footer


def test_two_platforms_partial_then_complete(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True, fb_reel=True)
    ds = _seed(tmp_path)
    _patch(monkeypatch)                       # youtube OK

    def _boom(ctx):
        raise RuntimeError("fb down")
    monkeypatch.setitem(pub._PLATFORMS, "fb_reel", _boom)
    tg = FakeTG()
    out = pub.publish_pending(ds, tg, tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert out == ["publishing:2026-09-09:morning"]   # fb not done yet
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["result"]["youtube"]["id"] == "VID"
    assert v["result"]["fb_reel"]["attempts"] == 1
    assert v["status"] == "publishing" and v["asset_url"]   # asset kept for retry


def test_handle_unpublish_deletes_and_marks(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="published",
               result={"youtube": {"id": "VID", "url": "u", "at": "x"},
                       "fb_reel": None, "ig_reel": None, "tiktok": None})
    ds.put("2026-09-09", "morning",
           video={**ds.get_safe("2026-09-09", "morning")["video"],
                  "published_at": datetime(2026, 9, 9, 5, tzinfo=timezone.utc).isoformat()})
    dels = []

    class _YT:
        @classmethod
        def from_env(cls): return cls()
        def delete(self, vid): dels.append(vid)
    monkeypatch.setattr(pub._youtube, "YouTube", _YT)
    tg = FakeTG()
    out = pub.handle_unpublish({"id": "c", "data": "vid:2026-09-09:morning:unpub"},
                               ds, tg, tmp_path,
                               datetime(2026, 9, 9, 5, 30, tzinfo=timezone.utc))
    assert out == "unpublished:2026-09-09:morning"
    assert dels == ["VID"]
    v = ds.get_safe("2026-09-09", "morning")["video"]
    assert v["status"] == "unpublished" and v["result"]["youtube"]["undone"] is True


def test_handle_unpublish_past_grace(tmp_path, monkeypatch):
    _settings(tmp_path, youtube=True)
    ds = _seed(tmp_path, status="published",
               result={"youtube": {"id": "VID", "url": "u", "at": "x"},
                       "fb_reel": None, "ig_reel": None, "tiktok": None})
    ds.put("2026-09-09", "morning",
           video={**ds.get_safe("2026-09-09", "morning")["video"],
                  "published_at": datetime(2026, 9, 9, 5, tzinfo=timezone.utc).isoformat()})
    tg = FakeTG()
    out = pub.handle_unpublish({"id": "c", "data": "vid:2026-09-09:morning:unpub"},
                               ds, tg, tmp_path,
                               datetime(2026, 9, 9, 7, tzinfo=timezone.utc))   # 120 min
    assert out == "undo-expired:2026-09-09:morning"
    assert ds.get_safe("2026-09-09", "morning")["video"]["status"] == "published"
