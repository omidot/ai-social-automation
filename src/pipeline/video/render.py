from __future__ import annotations
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import AlignError
from . import align as _align
from . import codegen as _codegen
from . import screenshot as _screenshot
from . import script as _script
from ..publish import slot_unix

log = logging.getLogger("video.render")

_AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".oga")
# How long to hold a slot before rendering once its newest audio part
# arrived, so a burst of multi-take uploads (a long script recorded as
# several files) has time to finish landing before render_pending locks in
# whatever audio_parts currently holds.
_AUDIO_GRACE_SECONDS = 90


def _audio_file_id(msg: dict) -> str | None:
    return _audio_file_id_and_name(msg)[0]


def _audio_file_id_and_name(msg: dict) -> tuple[str | None, str]:
    if isinstance(msg.get("voice"), dict) and msg["voice"].get("file_id"):
        return msg["voice"]["file_id"], ""
    if isinstance(msg.get("audio"), dict) and msg["audio"].get("file_id"):
        a = msg["audio"]
        return a["file_id"], str(a.get("file_name") or "")
    doc = msg.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        mime = str(doc.get("mime_type", ""))
        name = str(doc.get("file_name", ""))
        if mime.startswith("audio/") or name.lower().endswith(_AUDIO_EXT):
            return doc["file_id"], name
    return None, ""


def _part_sort_key(part: dict, index: int) -> tuple[int, int]:
    """Order audio parts by a leading number in the filename ("1.mp3" before
    "2.mp3") when present, falling back to arrival order otherwise -- lets
    the user record a long script in several takes and send them as
    separate files instead of one single recording."""
    m = re.match(r"\s*(\d+)", part.get("name") or "")
    return (0, int(m.group(1))) if m else (1, index)


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


def _fetch_voice(v: dict, tg, video_dir: Path) -> Path:
    """Download the slot's audio -- one file, or several takes stitched into
    one in the order implied by their filenames (falling back to arrival
    order) -- and return the path to the raw (pre-mp3) result.

    Each part is normalized to the same WAV format before concatenation
    (rather than stream-copying the originals): a voice note and an
    uploaded mp3 file are not guaranteed to share a codec, and ffmpeg's
    concat demuxer only stream-copies cleanly when every input already
    matches. Re-encoding each short part first costs little and never
    silently produces a corrupt joined file.
    """
    public = video_dir / "public"
    parts = list(v.get("audio_parts") or [])
    if len(parts) <= 1:
        fid = parts[0]["file_id"] if parts else v["audio_file_id"]
        return Path(tg.download_file(fid, str(public / "voice_in")))

    # sorted(), not parts.sort(): CPython's in-place list.sort() detaches
    # the list's backing array while it runs, so a key function that reads
    # `parts` (as _part_sort_key's arrival-order fallback does via
    # .index()) sees it as empty and raises. sorted() leaves the original
    # list intact for the key function to read.
    orig = list(parts)
    parts = sorted(parts, key=lambda p: _part_sort_key(p, orig.index(p)))
    ff = _align._ffmpeg_bin(video_dir)
    raw_dir = public / "voice_parts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[Path] = []
    for i, p in enumerate(parts):
        raw = Path(tg.download_file(p["file_id"], str(raw_dir / f"{i}_raw")))
        wav = raw_dir / f"{i}.wav"
        r = subprocess.run(
            [ff, "-y", "-hide_banner", "-i", str(raw), "-ac", "1", "-ar", "44100", str(wav)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise AlignError(f"ffmpeg normalize audio part {i + 1} failed: "
                             f"{(r.stderr or '')[-300:]}")
        normalized.append(wav)

    list_path = raw_dir / "concat.txt"
    list_path.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in normalized) + "\n",
        encoding="utf-8")
    joined = public / "voice_in_joined"
    r = subprocess.run(
        # the leading "-f concat" sets the INPUT demuxer; "voice_in_joined"
        # has no extension for ffmpeg to infer an output container from, so
        # the output side needs its own explicit "-f wav" (the parts were
        # just normalized to wav) or ffmpeg refuses to open it.
        [ff, "-y", "-hide_banner", "-f", "concat", "-safe", "0", "-i", str(list_path),
         "-c", "copy", "-f", "wav", str(joined)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise AlignError(f"ffmpeg concat of {len(parts)} audio parts failed: "
                         f"{(r.stderr or '')[-300:]}")
    return joined


def _remotion_render(video_dir: Path, composition: str,
                     out_mp4: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["npx", "remotion", "render", composition, str(out_mp4)],
        cwd=str(video_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace")


def _accepts_more_audio(v: dict) -> bool:
    """A slot can still take an audio part: either nothing has arrived yet,
    or parts have but rendering hasn't started -- a script this long (2-5
    min) is routinely recorded as several takes sent as separate messages,
    and each one must reach the same slot instead of only the last-received
    part surviving."""
    if v.get("status") == "awaiting_audio":
        return True
    return v.get("status") == "audio_received" and v.get("mp4_path") is None


def _find_slot(ds, msg: dict, now: datetime):
    """(date, slot, videodict) of the slot this audio belongs to, or
    (None, None, None). Prefer a reply to a known script_msg_id; else the
    most recently *sent* script (highest script_msg_id) still accepting
    audio within 3 days -- falling back to the later slot_ict on a tie (M6),
    since two ad hoc test scripts or a real slot plus a test-tool script can
    be open at once and the operator is almost always replying to whichever
    script they read last, not whichever posts later in the day. "Accepting
    audio" includes a slot already holding earlier takes but not yet
    rendered, so a script recorded as several separate files all reach it."""
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
            if not _accepts_more_audio(v):
                continue
            if reply_id is not None and v.get("script_msg_id") == reply_id:
                return date, slot, v
            if best is None or (v.get("script_msg_id") or -1) > (best[2].get("script_msg_id") or -1):
                best = (date, slot, v)
    return best if best else (None, None, None)


def _cfg(root: Path) -> dict:
    data = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")) or {}
    return data.get("video") or {}          # null `video:` key -> {}  (I5)


def is_audio(msg: dict) -> bool:
    return _audio_file_id(msg) is not None


def record_audio(msg: dict, ds, tg, root: Path, now: datetime) -> str | None:
    """Poller side: attach the uploaded audio to a waiting slot and mark it
    `audio_received`. The heavy render happens later in `render_pending`.

    A long script (2-5 min) is routinely recorded as several takes sent as
    separate files -- each one APPENDS to `audio_parts` instead of the
    newest silently overwriting `audio_file_id` and discarding the rest.
    `audio_file_id`/`audio_msg_id` stay in sync with the newest part for any
    reader that hasn't been updated to look at `audio_parts`."""
    fid, name = _audio_file_id_and_name(msg)
    if fid is None:
        return None
    root = Path(root)
    if not _cfg(root).get("enabled"):
        return None                         # branch dormant (M9)
    date, slot, v = _find_slot(ds, msg, now)
    if date is None:
        tg.send_message("⚠️ Nhận được audio nhưng không có video nào đang chờ.")
        return None
    parts = list(v.get("audio_parts") or [])
    parts.append({"file_id": fid, "msg_id": msg.get("message_id"), "name": name,
                  "received_at": msg.get("date")})
    ds.put(date, slot, video={**v, "status": "audio_received",
                              "audio_file_id": fid,
                              "audio_msg_id": msg.get("message_id"),
                              "audio_parts": parts,
                              "render_err": None})
    n = len(parts)
    note = f" (phần {n})" if n > 1 else ""
    tg.send_message(f"🎧 Đã nhận audio{note} cho video {slot} ({date}). "
                    "Đang dựng, vài phút nữa có kết quả.")
    return f"audio_received:{date}:{slot}"


def render_pending(ds, tg, root: Path, now: datetime, *, limit: int = 1) -> list[str]:
    """Workflow side: render up to `limit` slots sitting at `audio_received`
    (oldest first). Regenerates the Remotion project from `video.script` in
    state; on any failure the slot returns to `awaiting_audio`."""
    from .models import Script

    # _remotion_render() runs `npx remotion render` with cwd=video_dir, so any
    # relative out_mp4 (e.g. the production caller's root=Path(".")) gets
    # resolved by remotion against video_dir instead of the caller's cwd --
    # the render then succeeds (exit 0) but writes to the wrong nested path,
    # and this process's out_mp4.exists() check (still relative to the
    # original cwd) never finds it. Resolve once, up front, so every path
    # built from root downstream is unambiguous regardless of subprocess cwd.
    root = Path(root).resolve()
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
            if v.get("status") != "audio_received":
                continue
            # A long script is often recorded as several takes sent close
            # together -- if the newest one just arrived, hold off one cycle
            # so a take still in flight lands before rendering locks in
            # whatever audio_parts currently has.
            parts = v.get("audio_parts") or []
            received = [p.get("received_at") for p in parts if p.get("received_at")]
            if received and (now.timestamp() - max(received)) < _AUDIO_GRACE_SECONDS:
                continue
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

            s = Script.from_dict(v["script"])
            api_key, cx = os.environ.get("GOOGLE_CSE_API_KEY"), os.environ.get("GOOGLE_CSE_CX")
            for ci, card in enumerate(s.cards):
                if card.screenshot is None:
                    continue
                if not (api_key and cx):
                    card.screenshot = None
                    continue
                shot_path = video_dir / "public" / "screenshots" / f"{ci}.png"
                try:
                    url = _screenshot.search_and_capture(card.screenshot.query, shot_path,
                                                         api_key=api_key, cx=cx)
                    card.screenshot_file = f"screenshots/{ci}.png"
                    card.screenshot_url = url
                except _screenshot.ScreenshotError as e:
                    log.warning("screenshot card %d failed (%s) -- falling back to text card", ci, e)
                    card.screenshot = None
            _codegen.write(s, video_dir)   # C1

            raw = _fetch_voice(v, tg, video_dir)
            _to_mp3(raw, video_dir / "public" / "voice.mp3", video_dir)
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

            slot_ict = (ds.get_safe(date, slot) or {}).get("slot_ict", "11:30")
            due = max(now, datetime.fromtimestamp(slot_unix(date, slot_ict), tz=timezone.utc))

            # An undo pressed mid-render must win: re-read before we send/persist,
            # so a discarded slot is neither sent nor overwritten with `rendered`. (I-D)
            cur = (ds.get_safe(date, slot) or {}).get("video") or v
            if cur.get("status") == "discarded":
                log.info("render_pending %s:%s discarded mid-render, dropping result", date, slot)
                out.append(f"discarded:{date}:{slot}")
                continue

            sz = out_mp4.stat().st_size
            if sz > 50 * 1024 * 1024:                    # Telegram sendVideo hard cap (M10)
                raise RuntimeError(f"MP4 {sz // 1024 // 1024}MB > 50MB Telegram limit")

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
            # Length is flexible per script now (2-5 min, driven by how much
            # real content it has), so "off" means off THIS script's own
            # word count, not a fixed config target that no longer matches
            # most drafts.
            expected = s.word_count / _script.WORDS_PER_MINUTE * 60
            if not (expected * 0.6 <= seconds <= expected * 1.4):
                tg.send_message(f"⚠️ Timeline lệch ({seconds:.0f}s), xem kỹ trước khi đăng.")
            out.append(f"rendered:{date}:{slot}")
        except Exception as e:  # noqa: BLE001 - any failure => slot back to awaiting_audio (C2/C3)
            log.exception("render_pending %s:%s failed", date, slot)
            out.append(_fail(e))
            continue

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
