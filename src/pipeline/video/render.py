from __future__ import annotations
import logging
import shutil
import subprocess
from pathlib import Path

from . import AlignError
from . import align as _align

log = logging.getLogger("video.render")

_AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".oga")


def _audio_file_id(msg: dict) -> str | None:
    if isinstance(msg.get("voice"), dict) and msg["voice"].get("file_id"):
        return msg["voice"]["file_id"]
    if isinstance(msg.get("audio"), dict) and msg["audio"].get("file_id"):
        return msg["audio"]["file_id"]
    doc = msg.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        mime = str(doc.get("mime_type", ""))
        name = str(doc.get("file_name", "")).lower()
        if mime.startswith("audio/") or name.endswith(_AUDIO_EXT):
            return doc["file_id"]
    return None


def _to_mp3(src: Path, dst: Path, video_dir: Path) -> None:
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".mp3":
        shutil.copy(src, dst)
        return
    ff = _align._ffmpeg_bin(video_dir)
    r = subprocess.run([ff, "-y", "-hide_banner", "-i", str(src),
                        "-ac", "1", "-ar", "44100", "-b:a", "128k", str(dst)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise AlignError(f"ffmpeg mp3 convert failed: {(r.stderr or '')[-300:]}")


def _remotion_render(video_dir: Path, composition: str,
                     out_mp4: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["npx", "remotion", "render", composition, str(out_mp4)],
        cwd=str(video_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
