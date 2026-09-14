import json
import sys
import types
from pathlib import Path

from pipeline.video import transcribe


def test_returns_false_when_faster_whisper_not_installed(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    out = tmp_path / "ref" / "words.json"
    ok = transcribe.transcribe_words(tmp_path / "voice.mp3", out)
    assert ok is False
    assert not out.exists()


def _fake_module(segments, *, by_vad=None, calls=None):
    """`segments` for every pass, or `by_vad={True: [...], False: [...]}` to
    return different results depending on the vad_filter argument."""
    mod = types.ModuleType("faster_whisper")

    class FakeModel:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, *a, **k):
            if calls is not None:
                calls.append(k.get("vad_filter"))
            if by_vad is not None:
                return by_vad[k.get("vad_filter")], object()
            return segments, object()

    mod.WhisperModel = FakeModel
    return mod


def test_writes_words_json_on_success(tmp_path, monkeypatch):
    Word = types.SimpleNamespace
    seg = types.SimpleNamespace(no_speech_prob=0.05, words=[
        Word(word=" Xin", start=0.0, end=0.3),
        Word(word=" chào", start=0.3, end=0.6),
    ])
    monkeypatch.setitem(sys.modules, "faster_whisper", _fake_module([seg]))

    out = tmp_path / "ref" / "words.json"
    ok = transcribe.transcribe_words(tmp_path / "voice.mp3", out)
    assert ok is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [
        {"w": "Xin", "start": 0.0, "end": 0.3},
        {"w": "chào", "start": 0.3, "end": 0.6},
    ]


def test_returns_false_on_empty_transcript(tmp_path, monkeypatch):
    seg = types.SimpleNamespace(no_speech_prob=0.05, words=[])
    monkeypatch.setitem(sys.modules, "faster_whisper", _fake_module([seg]))
    out = tmp_path / "ref" / "words.json"
    ok = transcribe.transcribe_words(tmp_path / "voice.mp3", out)
    assert ok is False
    assert not out.exists()


def test_drops_words_from_likely_silence_segments(tmp_path, monkeypatch):
    """Whisper is known to hallucinate stock phrases over silence/noise
    instead of returning nothing -- it flags this itself via a high
    no_speech_prob, so such segments must not leak fake words into the
    timeline (a real incident: a near-silent clip produced a fabricated
    Vietnamese YouTube-outro sentence with no_speech_prob=0.90)."""
    Word = types.SimpleNamespace
    real = types.SimpleNamespace(no_speech_prob=0.1, words=[Word(word=" thật", start=1.0, end=1.3)])
    hallucinated = types.SimpleNamespace(no_speech_prob=0.9, words=[
        Word(word=" Hãy", start=0.0, end=0.1), Word(word=" subscribe", start=0.1, end=0.3),
    ])
    monkeypatch.setitem(sys.modules, "faster_whisper", _fake_module([hallucinated, real]))

    out = tmp_path / "ref" / "words.json"
    ok = transcribe.transcribe_words(tmp_path / "voice.mp3", out)
    assert ok is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [{"w": "thật", "start": 1.0, "end": 1.3}]


def test_retries_without_vad_when_filter_swallows_everything(tmp_path, monkeypatch):
    """The voice-activity filter can swallow a whole quiet recording, which
    would silently cost real timing for the entire video -- an empty
    filtered pass must be retried unfiltered before giving up."""
    Word = types.SimpleNamespace
    unfiltered = types.SimpleNamespace(no_speech_prob=0.1, words=[
        Word(word=" nghe", start=0.4, end=0.7),
    ])
    calls = []
    monkeypatch.setitem(sys.modules, "faster_whisper",
                        _fake_module(None, by_vad={True: [], False: [unfiltered]}, calls=calls))

    out = tmp_path / "ref" / "words.json"
    ok = transcribe.transcribe_words(tmp_path / "voice.mp3", out)
    assert ok is True
    assert calls == [True, False], "must try the filter first, then retry without it"
    assert json.loads(out.read_text(encoding="utf-8")) == [
        {"w": "nghe", "start": 0.4, "end": 0.7}]


def test_clears_a_stale_transcript_when_this_run_fails(tmp_path, monkeypatch):
    """align.mjs reads whatever words.json is on disk. A leftover transcript
    from the PREVIOUS video would otherwise be used to time THIS one's text
    whenever transcription fails, so the file must be cleared up front."""
    out = tmp_path / "ref" / "words.json"
    out.parent.mkdir(parents=True)
    out.write_text('[{"w": "cu", "start": 0.0, "end": 0.1}]', encoding="utf-8")

    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert transcribe.transcribe_words(tmp_path / "voice.mp3", out) is False
    assert not out.exists(), "stale transcript from a previous video must not survive"


def test_returns_false_when_transcription_raises(tmp_path, monkeypatch):
    mod = types.ModuleType("faster_whisper")

    class BoomModel:
        def __init__(self, *a, **k):
            raise RuntimeError("model load failed")

    mod.WhisperModel = BoomModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)

    out = tmp_path / "ref" / "words.json"
    ok = transcribe.transcribe_words(tmp_path / "voice.mp3", out)
    assert ok is False
    assert not out.exists()
