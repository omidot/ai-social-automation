from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path

from . import AlignError

_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")


def _ffmpeg_bin(video_dir: Path) -> str:
    env = os.environ.get("FFMPEG_BIN")
    if env:
        return env
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = Path(video_dir) / "node_modules" / "ffmpeg-static" / name
        if p.exists():
            return str(p)
    return "ffmpeg"


def make_silence_txt(voice: Path, out_txt: Path, video_dir: Path,
                     noise_db: int = -32, min_silence: float = 0.35) -> float:
    ff = _ffmpeg_bin(video_dir)
    r = subprocess.run(
        [ff, "-hide_banner", "-i", str(voice),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    err = r.stderr or ""
    kept = [ln for ln in err.splitlines() if "silence_" in ln]
    Path(out_txt).parent.mkdir(parents=True, exist_ok=True)
    Path(out_txt).write_text("\n".join(kept) + "\n", encoding="utf-8")

    m = _DUR.search(err)
    if not m:
        raise AlignError(f"could not read duration from ffmpeg: {err[-300:]}")
    h, mm, ss = m.groups()
    return int(h) * 3600 + int(mm) * 60 + float(ss)


def run_aligner(video_dir: Path, duration: float) -> Path:
    video_dir = Path(video_dir)
    r = subprocess.run(["node", "tools/align.mjs", f"{duration:.3f}"],
                       cwd=str(video_dir), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise AlignError(f"align.mjs exit {r.returncode}: {r.stderr.strip()[:400]}")
    tl_path = video_dir / "src" / "timeline.json"
    if not tl_path.exists():
        raise AlignError("align.mjs produced no src/timeline.json")
    try:
        tl = json.loads(tl_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AlignError(f"timeline.json invalid: {e}") from e
    if not tl.get("cards"):
        raise AlignError("timeline.json has no cards")
    return tl_path
