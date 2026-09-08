from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from .daily_state import DailyState
from .state import State
from .telegram import Telegram
from . import publish
from .publish import slot_unix, _fb_message, _ig_caption  # noqa: F401 - re-export
from .video import render

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("article_approve")

def _meta():
    from .meta import Meta
    return Meta.from_env()


def _ack(tg, cbq_id: str, text: str = "") -> None:
    try:
        tg.answer_callback(cbq_id, text)
    except Exception as e:  # noqa: BLE001 - an expired callback id must never abort the poll
        log.warning("answer_callback failed: %s", e)


UNDO_GRACE_MIN = 15


def handle_callback(cbq: dict, ds, tg, meta, root: Path, now: datetime) -> str | None:
    parts = cbq.get("data", "").split(":")
    if len(parts) != 4 or parts[0] != "art":
        return None
    _, date, slot_name, action = parts
    if action != "undo":
        # now/sched/drop retired — the pipeline schedules itself
        _ack(tg, cbq["id"], "Nút này không còn dùng.")
        return None

    slot = ds.get_safe(date, slot_name)
    if slot is None or slot.get("status") in ("discarded", "expired"):
        _ack(tg, cbq["id"], "Không có gì để gỡ.")
        return None

    when = slot_unix(date, slot.get("slot_ict", "11:30"))
    if now.timestamp() - when > UNDO_GRACE_MIN * 60:
        _ack(tg, cbq["id"], "Đăng lâu rồi — gỡ tay trên trang.")
        tg.send_message(
            f"⚠️ {date}:{slot_name} đã đăng quá {UNDO_GRACE_MIN} phút, "
            "gỡ thủ công trên Facebook/Instagram.")
        return f"undo-expired:{date}:{slot_name}"

    res = slot.get("result") or {}
    fb_id = (res.get("fb") or {}).get("id") or slot.get("fb_post_id")
    ig_id = (res.get("ig") or {}).get("media_id")
    errs: list[str] = []
    try:
        if fb_id:
            try:
                meta.fb_delete_post(fb_id)
            except Exception as e:  # noqa: BLE001
                errs.append(f"FB: {e}")
        if ig_id:
            try:
                meta.ig_delete_media(ig_id)
            except Exception as e:  # noqa: BLE001
                errs.append(f"IG: {e}")
        # Force the discard past the one-way TERMINAL guard: article_publish_ig
        # may already have promoted this slot scheduled -> posted, and
        # set_status refuses to leave a terminal state. put() does cur.update()
        # and bypasses the guard, so state can't stay "posted" after we've
        # deleted the content.
        ds.put(date, slot_name, status="discarded", result={**res, "undone": True})
    except Exception as e:  # noqa: BLE001 - deletes may have half-succeeded; don't leave state lying
        log.exception("undo commit failed for %s:%s", date, slot_name)
        _ack(tg, cbq["id"], "Lỗi khi gỡ, xem log.")
        tg.send_message(f"⚠️ Lỗi khi gỡ {date}:{slot_name}: {e}")
        return f"error:{date}:{slot_name}"
    _ack(tg, cbq["id"], "Đã gỡ.")
    msg = f"🗑 Đã gỡ {date}:{slot_name} khỏi FB/IG."
    if errs:
        msg += " Lỗi: " + "; ".join(errs)
    tg.send_message(msg)
    return f"discarded:{date}:{slot_name}"


def retry_unscheduled(ds, meta, root: Path, tg, now: datetime) -> list[str]:
    """Re-attempt any slot a transient publish failure left at 'draft'. Only
    slots that already have rendered images + caption and whose slot time is
    still in the future. On failure the slot goes back to 'draft' for the next
    tick; expire_stale sweeps it once the slot time passes."""
    out: list[str] = []
    for f in ds.all_files():
        date = f.stem
        doc = ds.load_safe(date)
        if doc is None:
            continue
        for slot_name, slot in doc["posts"].items():
            if slot.get("status") != "draft":
                continue
            if not (slot.get("images") and slot.get("text_fb")):
                continue
            if now.timestamp() >= slot_unix(date, slot.get("slot_ict", "11:30")):
                continue
            try:
                ds.set_status(date, slot_name, "publishing")
                out.append(publish.schedule_slot(ds, meta, root, date, slot_name, now, tg))
            except Exception as e:  # noqa: BLE001
                ds.set_status(date, slot_name, "draft")
                log.warning("retry schedule %s:%s failed: %s", date, slot_name, e)
    return out


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
                if now.timestamp() >= due:
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
            v = slot.get("video") or {}
            if v.get("status") == "rendering" and v.get("started_at"):
                try:
                    started = datetime.fromisoformat(v["started_at"])
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                except ValueError:
                    started = now
                if (now - started).total_seconds() > 40 * 60:
                    ds.put(date, slot_name, video={**v, "status": "failed"})
                    stuck.append(f"{date}:{slot_name} (video)")
    if out:
        tg.send_message("⚠️ không lên lịch được, đã bỏ: " + ", ".join(out))
    for s in stuck:
        if s.endswith("(video)"):
            tg.send_message(f"⚠️ {s} kẹt khi render, gửi lại audio để thử.")
        else:
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
    log.info("poll: offset=%s, got %d updates", offset, len(updates))
    handled, max_uid = [], offset - 1
    for up in updates:
        try:
            max_uid = max(max_uid, up.get("update_id", max_uid))
            cbq = up.get("callback_query")
            msg = up.get("message")
            if cbq:
                data = cbq.get("data", "")
                if data.startswith("vid:"):
                    r = render.handle_undo(cbq, ds, tg, root, now)
                else:
                    r = handle_callback(cbq, ds, tg, meta, root, now)
                if r:
                    handled.append(r)
            elif msg and render._audio_file_id(msg):
                r = render.receive_audio(msg, ds, tg, root, now)
                if r:
                    handled.append(r)
        except Exception as e:  # noqa: BLE001 - a poison update must not stall the poller
            log.exception("update %s failed: %s", up.get("update_id"), e)
    if updates:
        st.offset_save(max_uid + 1)
    retried = retry_unscheduled(ds, meta, root, tg, now)
    if retried:
        log.info("poll: retried=%s", retried)
    expired = expire_stale(ds, tg, now)
    log.info("poll: handled=%s expired=%s new_offset=%s", handled, expired, max_uid + 1)
    return {"handled": handled, "expired": expired}


def main() -> None:
    print(poll(Path(".")))


if __name__ == "__main__":
    main()
