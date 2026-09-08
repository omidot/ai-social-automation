from __future__ import annotations
import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import AlignError
from . import align as _align
from ..daily_state import DailyState
from ..publish import slot_unix

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


def _find_slot(ds, msg: dict, now: datetime):
    """(date, slot, videodict) of the awaiting_audio slot this audio belongs to,
    or (None, None, None). Prefer a reply to a known script_msg_id; else newest
    awaiting_audio within 3 days."""
    reply_id = (msg.get("reply_to_message") or {}).get("message_id")
    best = None
    cutoff = now.timestamp() - 3 * 86400
    for f in sorted(ds.all_files(), reverse=True):
        date = f.stem
        doc = ds.load_safe(date)
        if doc is None:
            continue
        for slot, row in doc["posts"].items():
            v = row.get("video") or {}
            if v.get("status") != "awaiting_audio":
                continue
            try:
                if slot_unix(date, "00:00") < cutoff:
                    continue
            except Exception:  # noqa: BLE001
                continue
            if reply_id is not None and v.get("script_msg_id") == reply_id:
                return date, slot, v
            if best is None:
                best = (date, slot, v)
    return best if best else (None, None, None)


def receive_audio(msg: dict, ds, tg, root: Path, now: datetime) -> str | None:
    if _audio_file_id(msg) is None:
        return None
    date, slot, v = _find_slot(ds, msg, now)
    if date is None:
        tg.send_message("⚠️ Nhận được audio nhưng không có video nào đang chờ.")
        return None

    root = Path(root)
    cfg = (yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
           or {}).get("video", {})
    comp = cfg.get("render_composition", "CodexShort")
    video_dir = root / "video"
    script_rel = v["script_path"]
    out_dir = root / Path(script_rel).parent
    pid = out_dir.name
    out_mp4 = out_dir / f"{pid}.mp4"

    ds.put(date, slot, video={**v, "status": "rendering",
                              "audio_msg_id": msg.get("message_id"),
                              "started_at": now.isoformat()})

    def _fail(reason: str, err_tail: str = "") -> str:
        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        ds.put(date, slot, video={**cur, "status": "failed", "render_err": err_tail[-500:]})
        tg.send_message(f"❌ Render video {slot} lỗi: {reason}\n{err_tail[-500:]}\n"
                        "Gửi lại audio để thử lại.")
        return f"failed:{date}:{slot}"

    try:
        raw = tg.download_file(_audio_file_id(msg), str(video_dir / "public" / "voice_in"))
        _to_mp3(Path(raw), video_dir / "public" / "voice.mp3", video_dir)
        sil = _align.make_silence_txt(video_dir / "public" / "voice.mp3",
                                      video_dir / "ref" / "silence.txt", video_dir)
        tl_path = _align.run_aligner(video_dir, sil)
        tl = json.loads(tl_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.exception("prep failed")
        return _fail(f"{type(e).__name__}: {e}")

    dur = float(tl.get("duration", 0) or 0)
    timeline_off = not (25.0 <= dur <= 55.0)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("tools/cards.mjs", "tools/variants.mjs"):
        src = video_dir / name
        if src.exists():
            shutil.copy(src, out_dir / Path(name).name)
    shutil.copy(tl_path, out_dir / "timeline.json")
    _voice_mp3 = video_dir / "public" / "voice.mp3"
    if _voice_mp3.exists():
        shutil.copy(_voice_mp3, out_dir / "voice.mp3")

    r = _remotion_render(video_dir, comp, out_mp4)
    if r.returncode != 0 or not out_mp4.exists():
        return _fail(f"remotion exit {r.returncode}", r.stderr or "")

    slot_ict = (ds.get_safe(date, slot) or {}).get("slot_ict", "11:30")
    due = max(now, datetime.fromtimestamp(slot_unix(date, slot_ict), tz=timezone.utc))
    cur = (ds.get_safe(date, slot) or {}).get("video") or v
    ds.put(date, slot, video={**cur, "status": "rendered",
                              "mp4_path": str(out_mp4.relative_to(root)).replace("\\", "/"),
                              "seconds": round(dur, 1), "render_err": None,
                              "publish_due": due.isoformat()})
    title = (v.get("meta") or {}).get("title", "")
    cap = f"🎬 Video {slot} — {title}\n{round(dur, 1)}s. Tự lên lịch đăng {slot_ict}."
    tg.send_video(str(out_mp4), caption=cap,
                  buttons=[("🗑 Gỡ", f"vid:{date}:{slot}:undo")])
    if timeline_off:
        tg.send_message(f"⚠️ Timeline lệch ({dur:.0f}s), xem kỹ trước khi đăng.")
    return f"rendered:{date}:{slot}"


def handle_undo(cbq: dict, ds, tg, root: Path, now: datetime) -> str | None:
    parts = cbq.get("data", "").split(":")
    if len(parts) != 4 or parts[0] != "vid" or parts[3] != "undo":
        return None
    _, date, slot, _ = parts
    row = ds.get_safe(date, slot) or {}
    v = row.get("video") or {}
    if v.get("status") not in ("awaiting_audio", "rendering", "rendered"):
        try:
            tg.answer_callback(cbq["id"], "Video này đã xử lý.")
        except Exception:  # noqa: BLE001
            pass
        return None
    ds.put(date, slot, video={**v, "status": "discarded"})
    try:
        tg.answer_callback(cbq["id"], "Đã huỷ.")
    except Exception:  # noqa: BLE001
        pass
    tg.send_message(f"🗑 Đã huỷ video {date}:{slot}.")
    return f"discarded:{date}:{slot}"
