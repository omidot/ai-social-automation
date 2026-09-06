from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .daily_state import DailyState
from .state import State
from .telegram import Telegram

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("article_approve")
_ICT = timezone(timedelta(hours=7))

# The ONLY status a callback may act on. A slot in "scheduled" or "publishing"
# is deliberately non-actionable here so a second/late callback can never
# re-publish it. Do NOT add those statuses to daily_state.TERMINAL - that would
# break article_publish_ig's scheduled -> posted promotion.
ACTIONABLE = frozenset({"draft"})


def slot_unix(date: str, slot_ict: str) -> int:
    y, m, d = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in slot_ict.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=_ICT).timestamp())


def _meta():
    from .meta import Meta
    return Meta.from_env()


def _ack(tg, cbq_id: str, text: str = "") -> None:
    try:
        tg.answer_callback(cbq_id, text)
    except Exception as e:  # noqa: BLE001 - an expired callback id must never abort the poll
        log.warning("answer_callback failed: %s", e)


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
    slot = ds.get_safe(date, slot_name)
    if slot is None:
        _ack(tg, cbq["id"], "Không tìm thấy bài này (state chưa đồng bộ), thử lại sau.")
        return None
    if slot.get("status") not in ACTIONABLE:
        _ack(tg, cbq["id"], "Bài này đã xử lý.")
        return None

    try:
        if action == "now":
            # in-flight marker BEFORE the first Meta call: if fb_create_post
            # times out after FB created the post, the outer except must not
            # find this slot back at "draft" (which would re-arm it).
            ds.set_status(date, slot_name, "publishing")
            fbids = [meta.fb_upload_photo(str(Path(root) / p)) for p in slot["images"]]
            fb = meta.fb_create_post(_fb_message(slot), fbids)
            try:
                ig = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
            except Exception as e:  # noqa: BLE001
                ig = {"ok": False, "error": str(e)}
            ds.put(date, slot_name, result={"fb": fb, "ig": ig})
            ds.set_status(date, slot_name, "posted")
            _ack(tg, cbq["id"], "Đang đăng…")
            tail = "" if ig.get("ok") else " (IG lỗi, thử lại sau)"
            tg.send_message(f"✅ Đã đăng {date}:{slot_name}: {fb['url']}{tail}")
            return f"posted:{date}:{slot_name}"

        if action == "sched":
            ds.set_status(date, slot_name, "publishing")
            when = slot_unix(date, slot["slot_ict"])
            fbids = [meta.fb_upload_photo(str(Path(root) / p)) for p in slot["images"]]
            fb = meta.fb_create_post(_fb_message(slot), fbids,
                                     scheduled_publish_time=when,
                                     now_unix=int(now.timestamp()))
            if fb.get("scheduled"):
                ds.put(date, slot_name, fb_post_id=fb["id"],
                       ig_due=datetime.fromtimestamp(when, tz=timezone.utc).isoformat(),
                       result={"fb": fb, "ig": None})
                ds.set_status(date, slot_name, "scheduled")
                _ack(tg, cbq["id"], "Đã lên lịch.")
                tg.send_message(f"🕓 Đã lên lịch {date}:{slot_name}, đăng lúc {slot['slot_ict']}.")
                return f"scheduled:{date}:{slot_name}"
            # too close to the slot -> FB already published; publish IG now too
            try:
                ig = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
            except Exception as e:  # noqa: BLE001
                ig = {"ok": False, "error": str(e)}
            ds.put(date, slot_name, result={"fb": fb, "ig": ig})
            ds.set_status(date, slot_name, "posted")
            _ack(tg, cbq["id"], "Đăng ngay (quá sát giờ).")
            tail = "" if ig.get("ok") else " (IG lỗi, thử lại sau)"
            tg.send_message(f"✅ Đã đăng {date}:{slot_name} (quá sát giờ lên lịch): {fb['url']}{tail}")
            return f"posted:{date}:{slot_name}"

        if action == "drop":
            ds.set_status(date, slot_name, "discarded")
            _ack(tg, cbq["id"], "Đã bỏ.")
            tg.send_message(f"🗑 Đã bỏ {date}:{slot_name}.")
            return f"discarded:{date}:{slot_name}"

        _ack(tg, cbq["id"], "Không rõ thao tác.")
        return None
    except Exception as e:  # noqa: BLE001 - a poison update must never abort the poll
        _ack(tg, cbq["id"], "Lỗi xử lý, xem log.")
        log.exception("article_approve callback failed for %s:%s", date, slot_name)
        if action in ("now", "sched"):
            # something blew up mid-publish: never leave it at "publishing"
            # (it would re-arm) - mark "posted" so it can never re-publish.
            tg.send_message(
                f"⚠️ {date}:{slot_name} có thể đã đăng một phần — kiểm tra Page. Lỗi: {e}")
            ds.set_status(date, slot_name, "posted")
        else:
            tg.send_message(f"❌ Lỗi xử lý {date}:{slot_name}: {e}")
        return f"error:{date}:{slot_name}"


def expire_stale(ds, tg, now: datetime) -> list[str]:
    out: list[str] = []
    stuck: list[str] = []
    for f in ds.all_files():
        date = f.stem
        doc = ds.load_safe(date)
        if doc is None:
            continue
        for slot_name, slot in doc["posts"].items():
            status = slot.get("status")
            due = slot_unix(date, slot.get("slot_ict", "11:30"))
            if status == "draft":
                if now.timestamp() - due > 24 * 3600:
                    ds.set_status(date, slot_name, "expired")
                    out.append(f"{date}:{slot_name}")
            elif status == "publishing":
                # poller was hard-killed between set_status("publishing") and
                # the except handler: the slot is stuck - not actionable, not
                # scheduled, silently dead. Mark it "posted" (cannot re-publish)
                # and alert so the Page can be checked by hand.
                if now.timestamp() - due > 2 * 3600:
                    ds.set_status(date, slot_name, "posted")
                    stuck.append(f"{date}:{slot_name}")
    if out:
        tg.send_message("⌛ Quá 24h chưa duyệt, đã bỏ: " + ", ".join(out))
    for s in stuck:
        tg.send_message(f"⚠️ {s} kẹt ở 'publishing' — đã đánh dấu posted, kiểm tra Page.")
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
        try:
            max_uid = max(max_uid, up.get("update_id", max_uid))
            cbq = up.get("callback_query")
            if cbq:
                r = handle_callback(cbq, ds, tg, meta, root, now)
                if r:
                    handled.append(r)
        except Exception as e:  # noqa: BLE001 - a poison update must not stall the poller
            log.exception("update %s failed: %s", up.get("update_id"), e)
    if updates:
        st.offset_save(max_uid + 1)
    return {"handled": handled, "expired": expire_stale(ds, tg, now)}


def main() -> None:
    print(poll(Path(".")))


if __name__ == "__main__":
    main()
