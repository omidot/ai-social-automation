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
