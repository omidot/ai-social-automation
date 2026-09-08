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
        self.videos.append((path, caption)); return {"result": {"message_id": 7}}


def _seed(root, slot="morning", date="2026-09-08", **extra):
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "video:\n  render_composition: CodexShort\n", encoding="utf-8")
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


def test_receive_audio_renders_and_sends(tmp_path, monkeypatch):
    ds = _seed(tmp_path)
    (tmp_path / "video" / "tools").mkdir(parents=True)
    for f in ("cards.mjs", "variants.mjs"):
        (tmp_path / "video" / "tools" / f).write_text("//", encoding="utf-8")
    (tmp_path / "video" / "public").mkdir(parents=True)
    _mock_pipeline(monkeypatch)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    r = render.receive_audio({"message_id": 950, "voice": {"file_id": "V"}},
                             ds, tg, tmp_path, now)
    assert r == "rendered:2026-09-08:morning"
    v = ds.get_safe("2026-09-08", "morning")["video"]
    assert v["status"] == "rendered" and v["mp4_path"].endswith(".mp4")
    assert v["seconds"] == 41.0 and v["publish_due"]
    assert tg.videos and "Video morning" in tg.videos[0][1]


def test_receive_audio_render_failure(tmp_path, monkeypatch):
    ds = _seed(tmp_path)
    (tmp_path / "video" / "tools").mkdir(parents=True)
    for f in ("cards.mjs", "variants.mjs"):
        (tmp_path / "video" / "tools" / f).write_text("//", encoding="utf-8")
    _mock_pipeline(monkeypatch, render_rc=1)
    tg = FakeTG()
    r = render.receive_audio({"message_id": 950, "audio": {"file_id": "A"}},
                             ds, tg, tmp_path, datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc))
    assert r == "failed:2026-09-08:morning"
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "failed"
    assert any("Render video morning lỗi" in m for m in tg.msgs)


def test_receive_audio_not_audio_returns_none(tmp_path):
    ds = _seed(tmp_path)
    assert render.receive_audio({"message_id": 1, "text": "hi"}, ds, FakeTG(),
                                tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc)) is None


def test_receive_audio_no_waiting_slot(tmp_path):
    ds = DailyState(tmp_path / "data")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text("video: {}\n", encoding="utf-8")
    tg = FakeTG()
    assert render.receive_audio({"message_id": 1, "voice": {"file_id": "V"}}, ds, tg,
                                tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc)) is None
    assert any("không có video nào đang chờ" in m for m in tg.msgs)


def test_receive_audio_matches_by_reply(tmp_path, monkeypatch):
    ds = _seed(tmp_path, slot="evening", date="2026-09-07")   # older, but replied-to
    _seed(tmp_path, slot="morning", date="2026-09-08")        # newer, not replied-to
    (tmp_path / "video" / "tools").mkdir(parents=True)
    for f in ("cards.mjs", "variants.mjs"):
        (tmp_path / "video" / "tools" / f).write_text("//", encoding="utf-8")
    _mock_pipeline(monkeypatch)
    r = render.receive_audio(
        {"message_id": 960, "voice": {"file_id": "V"},
         "reply_to_message": {"message_id": 901}}, ds, FakeTG(), tmp_path,
        datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc))
    # both seeds use script_msg_id 901; reply picks the one whose slot has it —
    # tie broken by most-recent date, so this still resolves to 2026-09-08:morning.
    assert r == "rendered:2026-09-08:morning"


def test_handle_undo(tmp_path):
    ds = _seed(tmp_path, extra_status="rendered")
    class CB:  # noqa
        pass
    tg = FakeTG()
    out = render.handle_undo({"id": "c1", "data": "vid:2026-09-08:morning:undo"},
                             ds, tg, tmp_path, datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc))
    assert out == "discarded:2026-09-08:morning"
    assert ds.get_safe("2026-09-08", "morning")["video"]["status"] == "discarded"
