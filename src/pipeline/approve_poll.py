from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import publish
from .state import State
from .telegram import Telegram

log = logging.getLogger("approve")


def _meta():
    from .meta import Meta
    return Meta.from_env()


def _find_pending(st: State, pid: str) -> dict | None:
    for rec in st.pending_list():
        if rec["id"] == pid:
            return rec
    return None


def _out_dir(root: Path, pid: str) -> Path:
    date = pid[:10]
    return Path(root) / "output" / date / pid


def handle_update(update: dict, st: State, tg: Telegram, meta, root: Path,
                  now: datetime) -> str | None:
    cbq = update.get("callback_query")
    if not cbq or ":" not in cbq.get("data", ""):
        return None
    action, pid = cbq["data"].split(":", 1)
    pending = _find_pending(st, pid)
    if pending is None:
        tg.answer_callback(cbq["id"], "Bài này không còn nữa.")
        return None

    if action == "approve":
        try:
            record = publish.publish(pending, meta, _out_dir(root, pid))
            st.posted_save(record)
            st.pending_remove(pid)
            fb = "OK" if record["facebook"]["ok"] else "LỖI"
            ig = "OK" if record["instagram"]["ok"] else "LỖI"
            tg.answer_callback(cbq["id"], "Đang đăng…")
            tg.send_message(f"✅ Đã đăng {pid}: Facebook {fb}, Instagram {ig}.")
            return f"approved:{pid}"
        except publish.PublishError as e:
            tg.answer_callback(cbq["id"], "Đăng thất bại.")
            tg.send_message(f"❌ Đăng {pid} thất bại: {e}")
            return f"failed:{pid}"

    if action == "reject":
        st.pending_remove(pid)
        tg.answer_callback(cbq["id"], "Đã bỏ.")
        tg.send_message(f"❌ Đã bỏ {pid}.")
        return f"rejected:{pid}"

    if action == "edit":
        meta_json = _out_dir(root, pid) / "meta.json"
        if meta_json.exists():
            tg.send_document(str(meta_json), caption=f"Sửa {pid}: chỉnh file rồi bấm ✅ lại.")
        for img in pending.get("images", []):
            if Path(img).exists():
                tg.send_document(img)
        tg.answer_callback(cbq["id"], "Đã gửi file để sửa.")
        return f"edit:{pid}"

    return None


def expire_stale(st: State, tg: Telegram, ttl_hours: int, now: datetime) -> list[str]:
    removed = []
    for rec in st.pending_list():
        created = datetime.fromisoformat(rec["created_at"].replace("Z", "+00:00"))
        if now - created > timedelta(hours=ttl_hours):
            st.pending_remove(rec["id"])
            removed.append(rec["id"])
    if removed:
        tg.send_message("⌛ Hết hạn 12h, đã bỏ: " + ", ".join(removed))
    return removed


def _load_settings(root: Path) -> dict:
    p = Path(root) / "config/settings.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def poll(root: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    settings = _load_settings(root)
    st = State(root / "data")
    tg = Telegram()
    meta = _meta()

    offset = st.offset_load()
    updates = tg.get_updates(offset=offset)
    handled = []
    max_uid = offset - 1
    for up in updates:
        max_uid = max(max_uid, up["update_id"])
        res = handle_update(up, st, tg, meta, root, now)
        if res:
            handled.append(res)
    if updates:
        st.offset_save(max_uid + 1)

    expired = expire_stale(st, tg, settings.get("pending_ttl_hours", 12), now)
    return {"handled": handled, "expired": expired}


if __name__ == "__main__":
    print(poll(Path(".")))
