from __future__ import annotations
import os
import subprocess
import time
import wave
from pathlib import Path

from . import TTSError
from .align import _ffmpeg_bin

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _order(provider: str) -> list[str]:
    if provider == "auto":
        return ["gptsovits", "f5tts", "hfspace"]
    return [provider]


def _ref_wav(root: Path) -> Path:
    return Path(root) / "assets" / "voice" / "sample.wav"


def ensure_sample_text(sample_wav: Path, sample_txt: Path, cache_dir: Path) -> str:
    sample_txt = Path(sample_txt)
    if sample_txt.exists():
        return sample_txt.read_text(encoding="utf-8").strip()
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / "sample.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8").strip()
    if not Path(sample_wav).exists():
        raise TTSError(f"missing voice sample: {sample_wav}. "
                       "Đặt assets/voice/sample.wav (3-10 phút) + assets/voice/sample.txt.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TTSError("faster-whisper not installed and no sample.txt provided") from e
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(sample_wav), language="vi")
    text = " ".join(seg.text.strip() for seg in segments).strip()
    cached.write_text(text, encoding="utf-8")
    return text


# ---- backends: fn(ref_wav, ref_text, target_text, out_wav) -> None ----
def _run_script(script: Path, ref_wav, ref_text, target, out_wav) -> None:
    if not script.exists():
        raise RuntimeError(f"{script.name} not present (spike Task 1 authored it?)")
    r = subprocess.run(["bash", str(script), str(ref_wav), ref_text, target, str(out_wav)],
                       capture_output=True, text=True, timeout=1800,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not Path(out_wav).exists():
        raise RuntimeError(f"{script.name} failed: {r.stderr.strip()[:400]}")


def _gptsovits(ref_wav, ref_text, target, out_wav):
    _run_script(_SCRIPTS / "tts_gptsovits.sh", ref_wav, ref_text, target, out_wav)


def _f5tts(ref_wav, ref_text, target, out_wav):
    _run_script(_SCRIPTS / "tts_f5.sh", ref_wav, ref_text, target, out_wav)


def _hfspace(ref_wav, ref_text, target, out_wav):
    space = os.environ.get("HF_SPACE_ID")
    if not space:
        raise RuntimeError("HF_SPACE_ID not set")
    from gradio_client import Client, handle_file
    last = None
    for attempt in range(3):
        try:
            client = Client(space, hf_token=os.environ.get("HF_TOKEN"))
            res = client.predict(handle_file(str(ref_wav)), ref_text, target,
                                 api_name="/infer")
            src = res[0] if isinstance(res, (list, tuple)) else res
            Path(out_wav).write_bytes(Path(src).read_bytes())
            return
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < 2:
                time.sleep(60)
    raise RuntimeError(f"HF Space failed after retries: {last}")


_BACKENDS = {"gptsovits": _gptsovits, "f5tts": _f5tts, "hfspace": _hfspace}


def _to_mp3(wav_path: Path, out_mp3: Path, video_dir: Path) -> float:
    ff = _ffmpeg_bin(video_dir)
    out_mp3 = Path(out_mp3)
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [ff, "-y", "-i", str(wav_path),
             "-af", "silenceremove=start_periods=1:start_silence=0.3:start_threshold=-40dB:"
                    "stop_periods=1:stop_silence=0.5:stop_threshold=-40dB",
             "-ar", "44100", "-ac", "1", "-q:a", "2", str(out_mp3)],
            check=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except subprocess.CalledProcessError as e:
        raise TTSError(
            f"ffmpeg mp3 encode failed: {e.stderr[-300:] if e.stderr else e}") from e
    # duration
    with wave.open(str(wav_path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _fake_wav(target_text: str, out_wav: Path) -> None:
    import math
    import struct
    words = max(1, len(target_text.split()))
    secs = max(2.0, words * 0.38)
    sr = 44100
    n = int(sr * secs)
    # Low-amplitude tone (~-20 dBFS) rather than pure zeros: the silenceremove
    # filter in _to_mp3 strips a fully-silent signal down to an unreadable mp3.
    # Duration (from wav frame count) is unchanged by the sample values.
    amp = 3277
    samples = (int(amp * math.sin(2 * math.pi * 220 * i / sr)) for i in range(n))
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(struct.pack("<%dh" % n, *samples))


def synthesize(target_text: str, out_mp3: Path, cfg: dict, video_dir: Path,
               fake: bool = False) -> float:
    import tempfile
    _fd, _tmp_name = tempfile.mkstemp(suffix=".wav")
    os.close(_fd)  # Windows: close leaked fd so tmp_wav.unlink() below can succeed
    tmp_wav = Path(_tmp_name)
    try:
        if fake:
            _fake_wav(target_text, tmp_wav)
            return _to_mp3(tmp_wav, out_mp3, video_dir)

        root = Path(video_dir).parent
        ref_wav = _ref_wav(root)
        ref_text = ensure_sample_text(ref_wav, root / "assets/voice/sample.txt",
                                      root / "data/voice_cache")
        errors = []
        for name in _order(cfg.get("tts_provider", "auto")):
            try:
                _BACKENDS[name](ref_wav, ref_text, target_text, tmp_wav)
                break
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")
        else:
            raise TTSError("all TTS backends failed -> " + " | ".join(errors))
        # A backend wrote tmp_wav; convert once here so an ffmpeg failure is
        # reported as a TTSError about encoding, not misattributed to a backend.
        return _to_mp3(tmp_wav, out_mp3, video_dir)
    finally:
        tmp_wav.unlink(missing_ok=True)
