from pathlib import Path
import pytest
from pipeline.video import tts, TTSError

CFG = {"tts_provider": "auto"}
ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"

def test_order_auto():
    assert tts._order("auto") == ["gptsovits", "f5tts", "hfspace"]
    assert tts._order("f5tts") == ["f5tts"]

def test_ensure_sample_text_reads_existing(tmp_path):
    stxt = tmp_path / "sample.txt"
    stxt.write_text("xin chào đây là giọng mẫu", encoding="utf-8")
    got = tts.ensure_sample_text(tmp_path / "sample.wav", stxt, tmp_path / "cache")
    assert got == "xin chào đây là giọng mẫu"

def test_synthesize_falls_through_backends(tmp_path, monkeypatch):
    calls = []
    def ok_wav(ref_wav, ref_text, target, out_wav):
        calls.append("f5")
        import math, wave, struct
        sr = 44100
        samples = [int(3277 * math.sin(2 * math.pi * 220 * i / sr)) for i in range(sr)]
        with wave.open(str(out_wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(struct.pack("<%dh" % sr, *samples))
    monkeypatch.setitem(tts._BACKENDS, "gptsovits",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("no torch")))
    monkeypatch.setitem(tts._BACKENDS, "f5tts", ok_wav)
    monkeypatch.setattr(tts, "ensure_sample_text", lambda *a, **k: "ref text")
    monkeypatch.setattr(tts, "_ref_wav", lambda root: tmp_path / "ref.wav")
    (tmp_path / "ref.wav").write_bytes(b"RIFF")   # presence only; backend is faked
    dur = tts.synthesize("một hai ba bốn năm", tmp_path / "out.mp3", CFG, VIDEO,
                         )
    assert calls == ["f5"]
    assert (tmp_path / "out.mp3").exists()
    assert dur > 0.5
    assert (tmp_path / "out.mp3").stat().st_size > 1000

def test_synthesize_all_fail_raises(tmp_path, monkeypatch):
    for k in ("gptsovits", "f5tts", "hfspace"):
        monkeypatch.setitem(tts._BACKENDS, k,
                            lambda *a: (_ for _ in ()).throw(RuntimeError("nope")))
    monkeypatch.setattr(tts, "ensure_sample_text", lambda *a, **k: "ref")
    monkeypatch.setattr(tts, "_ref_wav", lambda root: tmp_path / "r.wav")
    (tmp_path / "r.wav").write_bytes(b"RIFF")
    with pytest.raises(TTSError):
        tts.synthesize("abc", tmp_path / "o.mp3", CFG, VIDEO)

@pytest.mark.needs_node
def test_fake_produces_wav_of_expected_length(tmp_path):
    dur = tts.synthesize("một hai ba bốn năm sáu bảy tám chín mười",
                         tmp_path / "o.mp3", CFG, VIDEO, fake=True)
    assert (tmp_path / "o.mp3").exists()
    assert 2.0 <= dur <= 8.0
