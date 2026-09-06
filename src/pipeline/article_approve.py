from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .daily_state import DailyState, TERMINAL
from .state import State
from .telegram import Telegram

log = logging.getLogger("article_approve")
_ICT = timezone(timedelta(hours=7))


def slot_unix(date: str, slot_ict: str) -> int:
    y, m, d = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in slot_ict.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=_ICT).timestamp())


def _meta():
    from .meta import Meta
    return Meta.from_env()


def _fb_message(slot: dict) -> str:
    return slot["text_fb"] + "\n\n" + " ".join(slot["hashtags"])


def _ig_caption(slot: dict) -> str:
    return slot["text_ig"] + "\n\n" + " ".join(slot["hashtags"])


def handle_callback(cbq: dict, ds, tg, meta, root: Path, now: datetime) -> str | None:
    data = cbq.get("data", "")
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "art":
        return None
    _, date, slot_name, action = parts
    slot = ds.get(date, slot_name)
    if slot is None or slot.get("status") in TERMINAL:
        tg.answer_callback(cbq["id"], "Bài này đã xử lý.")
        return None

    if action == "now":
        fbids = [meta.fb_upload_photo(str(Path(root) / p)) for p in slot["images"]]
        fb = meta.fb_create_post(_fb_message(slot), fbids)
        try:
            ig = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
        except Exception as e:  # noqa: BLE001
            ig = {"ok": False, "error": str(e)}
        ds.put(date, slot_name, result={"fb": fb, "ig": ig})
        ds.set_status(date, slot_name, "posted")
        tg.answer_callback(cbq["id"], "Đang đăng…")
        tail = "" if ig.get("ok") else " (IG lỗi, thử lại sau)"
        tg.send_message(f"✅ Đã đăng {date}:{slot_name}: {fb['url']}{tail}")
        return f"posted:{date}:{slot_name}"

    if action == "sched":
        when = slot_unix(date, slot["slot_ict"])
        fbids = [meta.fb_upload_photo(str(Path(root) / p)) for p in slot["images"]]
        fb = meta.fb_create_post(_fb_message(slot), fbids,
                                 scheduled_publish_time=when,
                                 now_unix=int(now.timestamp()))
        ds.put(date, slot_name, fb_post_id=fb["id"],
               ig_due=datetime.fromtimestamp(when, tz=timezone.utc).isoformat(),
               result={"fb": fb, "ig": None})
        ds.set_status(date, slot_name, "scheduled")
        tg.answer_callback(cbq["id"], "Đã lên lịch.")
        tg.send_message(f"🕓 Đã lên lịch {date}:{slot_name}, đăng lúc {slot['slot_ict']}.")
        return f"scheduled:{date}:{slot_name}"

    if action == "drop":
        ds.set_status(date, slot_name, "discarded")
        tg.answer_callback(cbq["id"], "Đã bỏ.")
        tg.send_message(f"🗑 Đã bỏ {date}:{slot_name}.")
        return f"discarded:{date}:{slot_name}"
    return None


def expire_stale(ds, tg, now: datetime) -> list[str]:
    out: list[str] = []
    for f in ds.all_files():
        date = f.stem
        for slot_name, slot in ds.load(date)["posts"].items():
            if slot.get("status") != "draft":
                continue
            due = slot_unix(date, slot.get("slot_ict", "11:30"))
            if now.timestamp() - due > 24 * 3600:
                ds.set_status(date, slot_name, "expired")
                out.append(f"{date}:{slot_name}")
    if out:
        tg.send_message("⌛ Quá 24h chưa duyệt, đã bỏ: " + ", ".join(out))
    return out


def poll(root: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    st = State(root / "data")
    ds = DailyState(root / "data")
    tg = Telegram()
    meta = _meta()
    offset = st.offset_load()
    updates = tg.get_updates(offset=offset)
    handled, max_uid = [], offset - 1
    for up in updates:
        max_uid = max(max_uid, up["update_id"])
        cbq = up.get("callback_query")
        if cbq:
            r = handle_callback(cbq, ds, tg, meta, root, now)
            if r:
                handled.append(r)
    if updates:
        st.offset_save(max_uid + 1)
    return {"handled": handled, "expired": expire_stale(ds, tg, now)}


def main() -> None:
    print(poll(Path(".")))


if __name__ == "__main__":
    main()
