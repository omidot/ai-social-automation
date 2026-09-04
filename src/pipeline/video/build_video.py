from __future__ import annotations
import argparse
import json
import logging
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..models import Candidate, PostContent
from . import VideoError
from . import script as _script
from . import variants as _variants
from . import codegen as _codegen
from . import tts as _tts
from . import align as _align

log = logging.getLogger("video.build")


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)


def _make_id(cand: Candidate, now: datetime) -> str:
    return f"{now:%Y-%m-%d}-{_slug(cand.title)[:40]}".rstrip("-")


def _load_voice(root: Path) -> dict:
    return yaml.safe_load((Path(root) / "config/voice.yaml").read_text(encoding="utf-8"))


def _load_story(path: Path) -> tuple[Candidate, PostContent]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return Candidate.from_dict(d["candidate"]), PostContent.from_dict(d["post"])


def build(root: Path, cand: Candidate, post: PostContent, now: datetime, cfg: dict,
          fake: bool = False, render_smoke: bool = False, llm=None) -> dict:
    if not cfg.get("enabled"):
        return {"skipped": "video.enabled=false"}

    root = Path(root)
    video_dir = root / "video"
    voice = _load_voice(root)

    s = _script.generate(cand, post, voice, cfg, llm=llm)
    s = _variants.normalize(s)
    _codegen.write(s, video_dir)
    try:
        _codegen.node_check(video_dir)
    except FileNotFoundError:
        log.warning("node not available, skipping --check")

    pid = _make_id(cand, now)
    out_dir = root / "output" / f"{now:%Y-%m-%d}" / pid / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    _script.write_script_json(s, out_dir)

    voice_mp3 = video_dir / "public" / "voice.mp3"
    seconds = _tts.synthesize(s.spoken_text, voice_mp3, cfg, video_dir, fake=fake)
    backend = "fake" if fake else cfg.get("tts_provider", "auto")

    sil_dur = _align.make_silence_txt(voice_mp3, video_dir / "ref" / "silence.txt", video_dir)
    tl_path = _align.run_aligner(video_dir, sil_dur)
    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    timeline_off = not (25.0 <= tl.get("duration", 0) <= 55.0)

    for f in (video_dir / "tools/cards.mjs", video_dir / "tools/variants.mjs",
              tl_path, voice_mp3):
        shutil.copy(f, out_dir / f.name)

    manifest = {
        "id": pid, "seconds": round(tl.get("duration", seconds), 2),
        "word_count": s.word_count, "cards": len(s.cards),
        "sections": [sec.label for sec in s.sections],
        "timeline_off": timeline_off, "voice_path": str(voice_mp3),
        "video_dir": str(video_dir), "tts_backend": backend,
    }

    if render_smoke:
        r = subprocess.run(
            ["npx", "remotion", "render", "CodexShort", "out/smoke.mp4", "--frames=0-30"],
            cwd=str(video_dir), capture_output=True, text=True)
        manifest["render_smoke_ok"] = r.returncode == 0
        if r.returncode != 0:
            log.error("render smoke failed: %s", r.stderr[-500:])

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Phase 2A — build Remotion inputs for one story")
    ap.add_argument("--root", default=".")
    ap.add_argument("--story", required=False)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--render-smoke", action="store_true")
    ap.add_argument("--tts-check", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root)
    cfg = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")).get("video", {})

    if args.tts_check:
        secs = _tts.synthesize("Xin chào, đây là bản kiểm tra giọng đọc của kênh.",
                               root / "video/public/voice.mp3", cfg, root / "video",
                               fake=args.fake)
        print(f"SUMMARY: tts-check ok, {secs:.1f}s -> video/public/voice.mp3")
        return 0

    if not args.story:
        ap.error("--story is required unless --tts-check")
    cand, post = _load_story(Path(args.story))
    cfg.setdefault("enabled", True)
    try:
        man = build(root, cand, post, datetime.now(timezone.utc), cfg,
                    fake=args.fake, render_smoke=args.render_smoke)
    except VideoError as e:
        print(f"SUMMARY: video build failed: {e}")
        return 1
    print(f"SUMMARY: built {man.get('id')} — {man.get('cards')} cards, "
          f"{man.get('seconds')}s, tts={man.get('tts_backend')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
