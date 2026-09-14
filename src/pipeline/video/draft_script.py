from __future__ import annotations
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..daily_state import DailyState
from ..telegram import Telegram
from . import VideoScriptError
from . import script as _script
from . import variants as _variants
from . import codegen as _codegen

log = logging.getLogger("video.draft_script")


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)


def _make_id(slot: str, title: str, now: datetime) -> str:
    return f"{now:%Y-%m-%d}-{slot}-{_slug(title)[:40]}".rstrip("-")


def draft(slot: str, root: Path, *, title: str, source_url: str, body_text: str,
          caption_fb: str, angle: str, now: datetime, generate=None, tg=None) -> dict:
    root = Path(root)
    cfg = (yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
           or {}).get("video") or {}
    if not cfg.get("enabled"):
        return {"skipped": True}

    voice = yaml.safe_load((root / "config/voice.yaml").read_text(encoding="utf-8"))
    date = now.astimezone(timezone.utc).strftime("%Y-%m-%d")

    try:
        s, meta = _script.generate_from_article(
            title=title, source_url=source_url, body_text=body_text,
            caption_fb=caption_fb, angle=angle, voice=voice, cfg=cfg, llm=generate)
        s = _variants.normalize(s)
    except VideoScriptError as e:
        if tg is not None:
            try:
                tg.send_message(f"⚠️ Kịch bản video {slot} lỗi: {e}")
            except Exception:  # noqa: BLE001
                log.exception("warn send failed")
        return {"status": "error"}

    video_dir = root / "video"
    _codegen.write(s, video_dir)
    try:
        _codegen.node_check(video_dir)
    except FileNotFoundError:
        log.warning("node not available, skipping tools/*.mjs --check")

    pid = _make_id(slot, title, now)
    out_dir = root / "output" / date / pid / "video"
    _script.write_script_json(s, out_dir)

    spoken = s.spoken_text
    src_line = f"🔗 Nguồn: {source_url}\n\n" if source_url else ""
    msg = (f"🎬 Kịch bản video {slot} ({date})\n\n{src_line}{spoken}\n\n"
           f"▶️ Thu âm đọc đúng đoạn trên (~{cfg.get('target_seconds', 40)}s), "
           "gửi file audio lại cho bot.")
    script_msg_id = None
    if tg is not None:
        try:
            r = tg.send_message(msg)
            script_msg_id = (r or {}).get("result", {}).get("message_id")
        except Exception:  # noqa: BLE001 - a preview failure must not lose the record
            log.exception("script msg send failed")

    ds = DailyState(root / "data")
    video = {
        "status": "awaiting_audio",
        "source_url": source_url or None,
        "meta": meta.to_dict(),
        "spoken_text": spoken,
        "script": s.to_dict(),
        "script_path": str((out_dir / "script.json").relative_to(root)).replace("\\", "/"),
        "script_msg_id": script_msg_id,
        "audio_file_id": None,
        "audio_msg_id": None,
        "mp4_path": None,
        "seconds": None,
        "render_err": None,
        "started_at": None,
        "publish_due": None,
        "result": {"yt": None, "fb": None, "ig": None, "tiktok": None},
    }
    existing = ds.get_safe(date, slot) or {}
    ds.put(date, slot, video={**(existing.get("video") or {}), **video})
    return video


def redraft(slot: str, date: str, root: Path) -> dict:
    """Re-run video script generation for a slot that already has an article
    committed (used to pick up a script-quality fix without re-running the
    whole article draft, which refuses to touch an already-scheduled slot)."""
    root = Path(root)
    ds = DailyState(root / "data")
    existing = ds.get(date, slot)
    if not existing:
        raise SystemExit(f"no slot {date}:{slot} found")
    sources = existing.get("sources") or []
    return draft(
        slot, root, title=existing.get("title", ""),
        source_url=(sources[0]["url"] if sources else ""),
        body_text=existing.get("text_fb", ""), caption_fb=existing.get("text_fb", ""),
        angle=existing.get("angle", ""), now=datetime.now(timezone.utc),
        tg=Telegram())


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=("morning", "evening"), required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    out = redraft(args.slot, args.date, Path(args.root))
    print("SUMMARY:", out.get("status", "awaiting_audio"))


if __name__ == "__main__":
    main()
