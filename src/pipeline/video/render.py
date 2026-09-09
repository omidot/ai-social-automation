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
        try:
            if slot_unix(date, "00:00") < cutoff:
                break  # files iterate newest-first, so every later one is older too (M7)
        except (ValueError, TypeError):
            continue
        for slot, row in sorted(doc["posts"].items(),
                                key=lambda kv: kv[1].get("slot_ict", ""),
                                reverse=True):  # same-day tie prefers the later slot (M6)
            v = row.get("video") or {}
            if v.get("status") != "awaiting_audio":
                continue
            if reply_id is not None and v.get("script_msg_id") == reply_id:
                return date, slot, v
            if best is None:
                best = (date, slot, v)
    return best if best else (None, None, None)


def _cfg(root: Path) -> dict:
    data = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")) or {}
    return data.get("video") or {}          # null `video:` key -> {}  (I5)


def is_audio(msg: dict) -> bool:
    return _audio_file_id(msg) is not None


def record_audio(msg: dict, ds, tg, root: Path, now: datetime) -> str | None:
    """Poller side: attach the uploaded audio to a waiting slot and mark it
    `audio_received`. The heavy render happens later in `render_pending`."""
    fid = _audio_file_id(msg)
    if fid is None:
        return None
    root = Path(root)
    if not _cfg(root).get("enabled"):
        return None                         # branch dormant (M9)
    date, slot, v = _find_slot(ds, msg, now)
    if date is None:
        tg.send_message("⚠️ Nhận được audio nhưng không có video nào đang chờ.")
        return None
    ds.put(date, slot, video={**v, "status": "audio_received",
                              "audio_file_id": fid,
                              "audio_msg_id": msg.get("message_id"),
                              "render_err": None})
    tg.send_message(f"🎧 Đã nhận audio cho video {slot} ({date}). "
                    "Đang dựng, vài phút nữa có kết quả.")
    return f"audio_received:{date}:{slot}"


def render_pending(ds, tg, root: Path, now: datetime, *, limit: int = 1) -> list[str]:
    """Workflow side: render up to `limit` slots sitting at `audio_received`
    (oldest first). Regenerates the Remotion project from `video.script` in
    state; on any failure the slot returns to `awaiting_audio`."""
    from . import codegen as _codegen
    from .models import Script

    root = Path(root)
    cfg = _cfg(root)
    comp = cfg.get("render_composition", "CodexShort")
    video_dir = root / "video"
    out: list[str] = []

    pending: list[tuple[str, str, dict]] = []
    for f in sorted(ds.all_files()):                     # oldest date first
        doc = ds.load_safe(f.stem)
        if doc is None:
            continue
        for slot, row in doc["posts"].items():
            v = row.get("video") or {}
            if v.get("status") == "audio_received":
                pending.append((f.stem, slot, v))

    for date, slot, v in pending[:limit]:
        ds.put(date, slot, video={**v, "status": "rendering",
                                  "started_at": now.isoformat()})

        def _fail(exc: Exception) -> str:
            cur = (ds.get_safe(date, slot) or {}).get("video") or v
            ds.put(date, slot, video={**cur, "status": "awaiting_audio",
                                      "render_err": f"{type(exc).__name__}: {exc}"[-500:]})
            tg.send_message(f"❌ Render video {slot} ({date}) lỗi: {exc}\n"
                            "Gửi lại audio để thử lại.")
            return f"failed:{date}:{slot}"

        try:
            script_rel = v["script_path"]
            out_dir = root / Path(script_rel).parent
            pid = out_dir.parent.name                    # real story id, not "video" (M2)
            out_mp4 = out_dir / f"{pid}.mp4"

            _codegen.write(Script.from_dict(v["script"]), video_dir)   # C1

            raw = tg.download_file(v["audio_file_id"], str(video_dir / "public" / "voice_in"))
            _to_mp3(Path(raw), video_dir / "public" / "voice.mp3", video_dir)
            dur = _align.make_silence_txt(video_dir / "public" / "voice.mp3",
                                         video_dir / "ref" / "silence.txt", video_dir)
            tl_path = _align.run_aligner(video_dir, dur)
            tl = json.loads(tl_path.read_text(encoding="utf-8"))
            seconds = float(tl.get("duration", 0) or 0)

            out_dir.mkdir(parents=True, exist_ok=True)
            for name in ("tools/cards.mjs", "tools/variants.mjs"):
                src = video_dir / name
                if src.exists():
                    shutil.copy(src, out_dir / Path(name).name)
            shutil.copy(tl_path, out_dir / "timeline.json")
            vmp3 = video_dir / "public" / "voice.mp3"
            if vmp3.exists():
                shutil.copy(vmp3, out_dir / "voice.mp3")

            r = _remotion_render(video_dir, comp, out_mp4)
            if r.returncode != 0 or not out_mp4.exists():
                raise RuntimeError(f"remotion exit {r.returncode}: {(r.stderr or '')[-300:]}")
        except Exception as e:  # noqa: BLE001 - any failure => slot back to awaiting_audio (C2/C3)
            log.exception("render_pending %s:%s failed", date, slot)
            out.append(_fail(e))
            continue

        slot_ict = (ds.get_safe(date, slot) or {}).get("slot_ict", "11:30")
        due = max(now, datetime.fromtimestamp(slot_unix(date, slot_ict), tz=timezone.utc))
        cap = (f"🎬 Video {slot} — {(v.get('meta') or {}).get('title', '')}\n"
               f"{round(seconds, 1)}s. Tự lên lịch đăng {slot_ict}.")
        resp = tg.send_video(str(out_mp4), caption=cap,
                             buttons=[("🗑 Gỡ", f"vid:{date}:{slot}:undo")])
        tg_file_id = (((resp or {}).get("result") or {}).get("video") or {}).get("file_id")   # I1

        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        ds.put(date, slot, video={**cur, "status": "rendered",
                                  "mp4_path": str(out_mp4.relative_to(root)).replace("\\", "/"),
                                  "tg_file_id": tg_file_id,
                                  "seconds": round(seconds, 1), "render_err": None,
                                  "publish_due": due.isoformat()})
        target = cfg.get("target_seconds", 40)
        if not (target * 0.6 <= seconds <= target * 1.4):
            tg.send_message(f"⚠️ Timeline lệch ({seconds:.0f}s), xem kỹ trước khi đăng.")
        out.append(f"rendered:{date}:{slot}")

    return out


def handle_undo(cbq: dict, ds, tg, root: Path, now: datetime) -> str | None:
    parts = cbq.get("data", "").split(":")
    if len(parts) != 4 or parts[0] != "vid" or parts[3] != "undo":
        return None
    _, date, slot, _ = parts
    row = ds.get_safe(date, slot) or {}
    v = row.get("video") or {}
    if v.get("status") not in ("awaiting_audio", "audio_received", "rendering", "rendered"):
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
