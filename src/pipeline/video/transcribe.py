from __future__ import annotations
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("video.transcribe")


def transcribe_words(audio: Path, out_json: Path, *, language: str = "vi") -> bool:
    """Best-effort real word-level timestamps via a local Whisper model.

    Writes ``out_json`` as ``[{"w": text, "start": s, "end": s}, ...]`` and
    returns True on success. Never raises: align.mjs falls back to its
    silence-heuristic estimate when this returns False or writes nothing,
    so a missing dependency, a bad audio file, or a slow/failed model load
    must never break an otherwise-working render.
    """
    # A leftover transcript from the PREVIOUS video would otherwise be picked
    # up by align.mjs whenever this run fails, silently timing one video's
    # text to another's speech -- so the target is cleared before any work.
    out_json = Path(out_json)
    out_json.unlink(missing_ok=True)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log.warning("faster-whisper not installed -- skipping real word alignment")
        return False

    model_size = os.environ.get("WHISPER_MODEL_SIZE", "small")
    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        # The voice-activity filter occasionally swallows a whole quiet or
        # heavily-compressed recording, which would silently cost us real
        # timing for the entire video -- so an empty first pass is retried
        # with the filter off before giving up.
        words: list[dict] = []
        for vad in (True, False):
            segments, _info = model.transcribe(
                str(audio), language=language, word_timestamps=True, vad_filter=vad,
                condition_on_previous_text=False)
            # Whisper is known to hallucinate stock phrases (e.g. Vietnamese
            # channel outros) over silence/noise instead of returning nothing --
            # it flags this itself via no_speech_prob, so segments it considers
            # more likely silence than speech are dropped rather than trusted.
            words = [
                {"w": w.word.strip(), "start": w.start, "end": w.end}
                for seg in segments if seg.no_speech_prob < 0.6
                for w in (seg.words or []) if w.word.strip()
            ]
            if words:
                break
            log.warning("whisper returned nothing with vad_filter=%s", vad)
    except Exception as e:
        log.warning("whisper transcription failed (%s) -- falling back to silence heuristic", e)
        return False

    if not words:
        log.warning("whisper produced no words -- falling back to silence heuristic")
        return False

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    log.info("transcribe: %d words -> %s", len(words), out_json)
    return True
