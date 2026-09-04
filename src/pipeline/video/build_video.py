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

_CFG_DEFAULTS = {"enabled": False, "target_seconds": 40, "words_min": 110,
                 "words_max": 140, "tts_provider": "auto"}

# Canned script for --fake-llm: lets the CLI / CI smoke run the full chain with
# no LLM credentials. ~117 displayed Vietnamese words, 14 cards, 3 sections.
_FAKE_SCRIPT_JSON = json.dumps({
    "sections": [
        {"label": "AI ĐANG TĂNG TỐC", "card_start": 0},
        {"label": "CHUYỆN GÌ XẢY RA", "card_start": 5},
        {"label": "SỰ THẬT", "card_start": 10},
    ],
    "cards": [
        {"lines": ["Hôm nay", "~thì", "AI lại vừa có một bước nhảy lớn."],
         "variant": "stack", "anchor": "mid", "motion_in": "rise", "motion_out": "up"},
        {"lines": ["Một mô hình mới", "vừa được công bố."],
         "variant": "stack", "anchor": "top", "motion_in": "fall", "motion_out": "down"},
        {"lines": ["Nó nhanh gấp đôi", "~cái", "bản trước đó."],
         "variant": "right", "anchor": "low", "motion_in": "slideR", "motion_out": "dissolve"},
        {"lines": ["Chi phí thì", "giảm gần một nửa."],
         "variant": "mark", "anchor": "mid", "motion_in": "wipe", "motion_out": "up"},
        {"lines": ["Người bình thường", "cũng dùng được ngay."],
         "variant": "stack", "anchor": "mid", "motion_in": "slideL", "motion_out": "shrink"},
        {"lines": ["Các công ty lớn", "đã tích hợp nó rồi."],
         "variant": "stair", "anchor": "mid", "motion_in": "slam", "motion_out": "shrink"},
        {"lines": ["Còn bạn", "~thì", "vẫn đang làm thủ công."],
         "variant": "mark", "anchor": "mid", "motion_in": "fall", "motion_out": "wipeOut"},
        {"lines": ["Khoảng cách", "đang giãn ra mỗi ngày."],
         "variant": "stack", "anchor": "top", "motion_in": "rise", "motion_out": "down"},
        {"lines": ["Ai bắt nhịp sớm", "sẽ đi trước rất xa."],
         "variant": "right", "anchor": "mid", "motion_in": "slideR", "motion_out": "shrink"},
        {"lines": ["Ai chậm chân", "sẽ bị bỏ lại phía sau."],
         "variant": "stack", "anchor": "mid", "motion_in": "wipe", "motion_out": "up"},
        {"lines": ["Công cụ", "đã nằm sẵn trong tay bạn."],
         "variant": "hero", "anchor": "mid", "motion_in": "pop", "motion_out": "dissolve"},
        {"lines": ["Miễn phí", "và ai cũng chạm tới được."],
         "variant": "stack", "anchor": "top", "motion_in": "rise", "motion_out": "down"},
        {"lines": ["Sự thật là", "nó đang ở đây rồi."],
         "variant": "invert", "anchor": "mid", "motion_in": "pop", "motion_out": "wipeOut"},
        {"lines": ["Chỉ là", "bạn đã bắt đầu chưa?"],
         "variant": "invert", "anchor": "mid", "motion_in": "fall", "motion_out": "wipeOut"},
    ],
}, ensure_ascii=False)


def _fake_llm(system: str, user: str, **kwargs) -> str:
    return _FAKE_SCRIPT_JSON


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
    cfg = {**_CFG_DEFAULTS, **(cfg or {})}
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
            cwd=str(video_dir), capture_output=True, text=True,
            encoding="utf-8", errors="replace")
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
    ap.add_argument("--fake-llm", action="store_true",
                    help="use a canned script instead of calling any LLM (offline smoke)")
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
    cfg["enabled"] = True  # an explicit CLI invocation IS the request to build
    try:
        man = build(root, cand, post, datetime.now(timezone.utc), cfg,
                    fake=args.fake, render_smoke=args.render_smoke,
                    llm=_fake_llm if args.fake_llm else None)
    except VideoError as e:
        print(f"SUMMARY: video build failed: {e}")
        return 1
    print(f"SUMMARY: built {man.get('id')} — {man.get('cards')} cards, "
          f"{man.get('seconds')}s, tts={man.get('tts_backend')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
