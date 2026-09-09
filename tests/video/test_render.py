from pathlib import Path
import subprocess
import pytest
from pipeline.video import render


def test_audio_file_id_variants():
    assert render._audio_file_id({"voice": {"file_id": "V"}}) == "V"
    assert render._audio_file_id({"audio": {"file_id": "A"}}) == "A"
    assert render._audio_file_id(
        {"document": {"file_id": "D", "mime_type": "audio/mpeg"}}) == "D"
    assert render._audio_file_id(
        {"document": {"file_id": "D", "file_name": "take.m4a"}}) == "D"
    assert render._audio_file_id({"document": {"file_id": "D", "mime_type": "image/png"}}) is None
    assert render._audio_file_id({"text": "hello"}) is None


def test_to_mp3_copies_mp3(tmp_path):
    src = tmp_path / "a.mp3"; src.write_bytes(b"ID3xx")
    dst = tmp_path / "out" / "voice.mp3"
    render._to_mp3(src, dst, tmp_path)
    assert dst.read_bytes() == b"ID3xx"


def test_to_mp3_converts_with_ffmpeg(tmp_path, monkeypatch):
    src = tmp_path / "a.ogg"; src.write_bytes(b"OggS")
    dst = tmp_path / "voice.mp3"
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd); dst.write_bytes(b"mp3")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    render._to_mp3(src, dst, tmp_path)
    assert dst.exists() and calls and "-ar" in calls[0]


def test_to_mp3_ffmpeg_failure_raises(tmp_path, monkeypatch):
    src = tmp_path / "a.wav"; src.write_bytes(b"RIFF")
    monkeypatch.setattr(render.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    from pipeline.video import AlignError
    with pytest.raises(AlignError):
        render._to_mp3(src, tmp_path / "v.mp3", tmp_path)


def test_remotion_render_shells_out(tmp_path, monkeypatch):
    seen = {}
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd; seen["cwd"] = kw.get("cwd")
        return subprocess.CompletedProcess(cmd, 0, "done", "")
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    r = render._remotion_render(tmp_path / "video", "CodexShort", tmp_path / "o.mp4")
    assert r.returncode == 0
    assert "remotion" in seen["cmd"] and "CodexShort" in seen["cmd"]
    assert seen["cwd"] == str(tmp_path / "video")


from datetime import datetime, timezone
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []; self.videos = []
    def download_file(self, fid, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"audio"); return str(dest)
    def send_message(self, text, buttons=None): self.msgs.append(text)
    def send_video(self, path, caption="", buttons=None):
        self.videos.append((path, caption))
        return {"result": {"video": {"file_id": "TGVID"}}}


def _seed(root, slot="morning", date="2026-09-08", *, enabled=True, **extra):
    (root / "config").mkdir(exist_ok=True)
    _yaml = "video:\n  render_composition: CodexShort\n  target_seconds: 40\n"
    if enabled:
        _yaml += "  enabled: true\n"
    (root / "config" / "settings.yaml").write_text(_yaml, encoding="utf-8")
    ds = DailyState(root / "data")
    sp = f"output/{date}/{date}-openai-x/video/script.json"
    v = {"status": extra.pop("extra_status", "awaiting_audio"),
         "meta": {"title": "Tiêu đề video AI dài hơn mười ký tự"},
         "spoken_text": "một hai ba", "script_path": sp, "script_msg_id": 901,
         "result": {"yt": None, "fb": None, "ig": None, "tiktok": None}, **extra}
    ds.put(date, slot, status="scheduled", slot_ict="11:30", video=v)
    return ds


def _mock_pipeline(monkeypatch, render_rc=0):
    monkeypatch.setattr(render, "_to_mp3", lambda *a, **k: None)
    monkeypatch.setattr(render._align, "make_silence_txt", lambda *a, **k: 41.0)
    def fake_aligner(video_dir, dur):
        p = Path(video_dir) / "src" / "timeline.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"duration": 41.0, "cards": [1]}', encoding="utf-8")
        return p
    monkeypatch.setattr(render._align, "run_aligner", fake_aligner)
    import subprocess
    monkeypatch.setattr(render, "_remotion_render",
                        lambda vd, comp, out: (Path(out).parent.mkdir(parents=True, exist_ok=True),
                                               Path(out).write_bytes(b"MP4"),
                                               subprocess.CompletedProcess([], render_rc, "", "err tail"))[-1])


from pipeline.video.models import Script, Card, SectionMark


def _mini_script_dict(token="TOKZZZ"):
    c = Card(lines=[f"dong {token} mot"], variant="stack", anchor="mid",
             motion_in="rise", motion_out="up", num=None)
    return Script(cards=[c], sections=[SectionMark(label="MO", card_start=0)]).to_dict()


# --- record_audio (poller side) ---------------------------------------------

def test_record_audio_attaches_and_marks(tmp_path):
    ds = _seed(tmp_path, enabled=True)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    r = render.record_audio({"message_id": 9, "voice": {"file_id": "V"}},
                            ds, tg, tmp_path, now)
    assert r == "audio_received:2026-09-08:morning"
    v = ds.get_safe("2026-09-08", "morning")["video"]
    assert v["status"] == "audio_received"
    assert v["audio_file_id"] == "V"
    assert v["audio_msg_id"] == 9
    assert any("🎧" in m for m in tg.msgs)


def test_record_audio_disabled_is_silent(tmp_path):
    ds = _seed(tmp_path, enabled=False)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    r = render.record_audio({"message_id": 9, "voice": {"file_id": "V"}},
                            ds, tg, tmp_path, now)
    assert r is None
    assert tg.msgs == []
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "awaiting_audio"


def test_record_audio_no_slot_warns(tmp_path):
    ds = DailyState(tmp_path / "data")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "video:\n  enabled: true\n", encoding="utf-8")
    tg = FakeTG()
    r = render.record_audio({"message_id": 1, "voice": {"file_id": "V"}}, ds, tg,
                            tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert r is None
    assert any("không có video nào đang chờ" in m for m in tg.msgs)


def test_record_audio_matches_by_reply(tmp_path):
    # OLDER slot carries script_msg_id 901; NEWER slot a different id (902).
    ds = _seed(tmp_path, slot="evening", date="2026-09-07", script_msg_id=901)
    _seed(tmp_path, slot="morning", date="2026-09-08", script_msg_id=902)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    r = render.record_audio(
        {"message_id": 30, "voice": {"file_id": "V"},
         "reply_to_message": {"message_id": 901}}, ds, tg, tmp_path, now)
    # Reply points at 901 = the OLDER slot; reply-match must beat date-recency.
    assert r == "audio_received:2026-09-07:evening"
    assert ds.get_safe("2026-09-07", "evening")["video"]["status"] == "audio_received"
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "awaiting_audio"


def test_record_audio_same_day_prefers_later_slot(tmp_path):
    # Both slots on one date, both awaiting_audio, no reply -> newest slot_ict wins (M6).
    ds = _seed(tmp_path, slot="morning", date="2026-09-08")
    ds.put("2026-09-08", "morning", slot_ict="11:30")
    _seed(tmp_path, slot="evening", date="2026-09-08")
    ds.put("2026-09-08", "evening", slot_ict="19:45")
    tg = FakeTG()
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    r = render.record_audio({"message_id": 31, "voice": {"file_id": "V"}},
                            ds, tg, tmp_path, now)
    assert r == "audio_received:2026-09-08:evening"


# --- render_pending (workflow side) ----------------------------------------

def test_render_pending_regenerates_script_and_renders(tmp_path, monkeypatch):
    tok = "CARDTOKEN9"
    ds = _seed(tmp_path, extra_status="audio_received",
               script=_mini_script_dict(tok), audio_file_id="V")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    (tmp_path / "video" / "tools" / "cards.mjs").write_text(
        "// STALE cards from the drafting runner\n", encoding="utf-8")
    _mock_pipeline(monkeypatch)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    out = render.render_pending(ds, tg, tmp_path, now)
    assert out == ["rendered:2026-09-08:morning"]
    v = ds.get_safe("2026-09-08", "morning")["video"]
    assert v["status"] == "rendered"
    assert v["tg_file_id"] == "TGVID"
    assert v["mp4_path"].endswith(".mp4")
    assert v["seconds"] == 41.0 and v["publish_due"]
    assert tg.videos
    cards = (tmp_path / "video" / "tools" / "cards.mjs").read_text(encoding="utf-8")
    assert "STALE" not in cards
    assert tok in cards


def test_render_pending_failure_resets_to_awaiting(tmp_path, monkeypatch):
    ds = _seed(tmp_path, extra_status="audio_received",
               script=_mini_script_dict(), audio_file_id="V")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    _mock_pipeline(monkeypatch, render_rc=1)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    out = render.render_pending(ds, tg, tmp_path, now)
    assert out == ["failed:2026-09-08:morning"]
    v = ds.get_safe("2026-09-08", "morning")["video"]
    assert v["status"] == "awaiting_audio"
    assert "remotion exit 1" in v["render_err"]
    assert any("Render video morning" in m and "lỗi" in m for m in tg.msgs)


def test_render_pending_limit_one(tmp_path, monkeypatch):
    _seed(tmp_path, slot="evening", date="2026-09-07", extra_status="audio_received",
          script=_mini_script_dict(), audio_file_id="V")
    ds = _seed(tmp_path, slot="morning", date="2026-09-08", extra_status="audio_received",
               script=_mini_script_dict(), audio_file_id="V")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    _mock_pipeline(monkeypatch)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    out = render.render_pending(ds, tg, tmp_path, now, limit=1)
    assert out == ["rendered:2026-09-07:evening"]
    assert ds.get_safe("2026-09-07", "evening")["video"]["status"] == "rendered"
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "audio_received"


def test_handle_undo(tmp_path):
    ds = _seed(tmp_path, extra_status="rendered")
    tg = FakeTG()
    out = render.handle_undo({"id": "c1", "data": "vid:2026-09-08:morning:undo"},
                             ds, tg, tmp_path, datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc))
    assert out == "discarded:2026-09-08:morning"
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "discarded"
    assert "🗑 Đã huỷ video 2026-09-08:morning." in tg.msgs


def test_handle_undo_rejects_malformed(tmp_path):
    ds = _seed(tmp_path, extra_status="awaiting_audio")
    tg = FakeTG()
    now = datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc)
    for data in ("vid:2026-09-08:morning",              # 3 parts
                 "art:2026-09-08:morning:undo",         # wrong prefix
                 "vid:2026-09-08:morning:delete",       # wrong suffix
                 "vid:2026-09-08:morning:undo:x"):      # 5 parts
        out = render.handle_undo({"id": "c1", "data": data}, ds, tg, tmp_path, now)
        assert out is None
        assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "awaiting_audio"


def test_handle_undo_ignores_terminal_status(tmp_path):
    ds = _seed(tmp_path, extra_status="discarded")
    tg = FakeTG()
    out = render.handle_undo({"id": "c1", "data": "vid:2026-09-08:morning:undo"},
                             ds, tg, tmp_path, datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc))
    assert out is None
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "discarded"
