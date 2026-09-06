"""One-off: pull audio/video files the user sent to the project's Telegram bot
and save them locally. Requires TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in env.

Shares the same Telegram update offset as the article-approve poller so it
won't cause it to reprocess anything (plain messages are already ignored by
the poller, which only reacts to callback_query updates).

Usage:
    python scripts/fetch_telegram_media.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pipeline.state import State
from pipeline.telegram import Telegram

ROOT = Path(__file__).resolve().parent.parent
VOICE_DIR = ROOT / "assets" / "voice"
VIDEO_DIR = ROOT / "video" / "public"

EXT_BY_MIME = {
    "audio/ogg": ".oga", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
    "audio/wav": ".wav", "audio/x-wav": ".wav",
    "video/mp4": ".mp4", "video/quicktime": ".mov",
}


def _dest_for(kind: str, name: str | None, mime: str | None) -> Path:
    ext = Path(name).suffix if name else EXT_BY_MIME.get(mime or "", "")
    if kind == "video":
        return VIDEO_DIR / f"bg-incoming{ext or '.mp4'}"
    return VOICE_DIR / f"sample_incoming{ext or '.oga'}"


def fetch(root: Path = ROOT) -> list[str]:
    st = State(root / "data")
    tg = Telegram()
    offset = st.offset_load()
    updates = tg.get_updates(offset=offset, timeout=5)
    saved = []
    max_uid = offset - 1
    for up in updates:
        max_uid = max(max_uid, up["update_id"])
        msg = up.get("message") or {}
        for kind, key in (("audio", "voice"), ("audio", "audio"), ("video", "video"), ("audio", "document")):
            item = msg.get(key)
            if not item:
                continue
            file_id = item["file_id"]
            name = item.get("file_name")
            mime = item.get("mime_type")
            kind_ = "video" if (mime or "").startswith("video") or key == "video" else kind
            dest = _dest_for(kind_, name, mime)
            tg.download_file(file_id, str(dest))
            saved.append(str(dest))
            print(f"saved {key} -> {dest}")
    if updates:
        st.offset_save(max_uid + 1)
    return saved


if __name__ == "__main__":
    result = fetch()
    if not result:
        print("Không có audio/video mới trong Telegram.")
