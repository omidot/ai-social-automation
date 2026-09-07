from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("publish")
_ICT = timezone(timedelta(hours=7))


def slot_unix(date: str, slot_ict: str) -> int:
    y, m, d = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in slot_ict.split(":"))
    return int(datetime(y, m, d, hh, mm, tzinfo=_ICT).timestamp())


def _fb_message(slot: dict) -> str:
    return slot["text_fb"] + "\n\n" + " ".join(slot["hashtags"])


def _ig_caption(slot: dict) -> str:
    return slot["text_ig"] + "\n\n" + " ".join(slot["hashtags"])


def schedule_slot(ds, meta, root, date: str, slot_name: str,
                  now: datetime, tg) -> str:
    """Upload the carousel and schedule it on Facebook for the slot's ICT time;
    arm the IG poller via ``ig_due``. If the slot is < 600s away, Facebook
    publishes immediately and this also publishes Instagram now.

    Caller MUST have written the content fields and set status "publishing"
    first. Raises on any failure BEFORE ``fb_create_post`` returns (nothing was
    published — the caller makes the slot retryable). After that point never
    raises: an IG/state/telegram error still ends "posted".
    """
    root = Path(root)
    slot = ds.get(date, slot_name)
    when = slot_unix(date, slot["slot_ict"])

    fbids = [meta.fb_upload_photo(str(root / p)) for p in slot["images"]]
    fb = meta.fb_create_post(_fb_message(slot), fbids,
                             scheduled_publish_time=when,
                             now_unix=int(now.timestamp()))
    # --- point of no return: the FB post/creation call has returned ----------
    # Nothing below here may raise: the FB post already exists, so the slot must
    # never look unpublished to the retry sweep (which only re-acts on "draft").
    try:
        undo = [("🗑 Gỡ bài", f"art:{date}:{slot_name}:undo")]
        title = slot.get("title", "")

        if fb.get("scheduled"):
            ds.put(date, slot_name, fb_post_id=fb["id"],
                   ig_due=datetime.fromtimestamp(when, tz=timezone.utc).isoformat(),
                   result={"fb": fb, "ig": None})
            ds.set_status(date, slot_name, "scheduled")
            log.info("scheduled %s:%s for %s", date, slot_name, slot["slot_ict"])
            tg.send_message(
                f"🗓 Đã lên lịch {slot['slot_ict']}: {title}\n{fb['url']}", buttons=undo)
            return f"scheduled:{date}:{slot_name}"

        try:
            ig = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
        except Exception as e:  # noqa: BLE001 - FB already out; IG retry is the poller's job
            ig = {"ok": False, "error": str(e)}
        ds.put(date, slot_name, fb_post_id=fb["id"], result={"fb": fb, "ig": ig})
        ds.set_status(date, slot_name, "posted")
        tail = "" if ig.get("ok") else " (IG lỗi, thử lại sau)"
        tg.send_message(
            f"✅ Đã đăng {slot['slot_ict']}: {title}\n{fb['url']}{tail}", buttons=undo)
        return f"posted:{date}:{slot_name}"
    except Exception:  # noqa: BLE001 - FB post exists; bookkeeping failure must not double-post
        log.exception(
            "schedule_slot post-publish bookkeeping failed for %s:%s", date, slot_name)
        try:
            ds.set_status(date, slot_name, "posted")
        except Exception:  # noqa: BLE001 - even a state failure here must not raise
            log.exception(
                "schedule_slot could not mark %s:%s posted after bookkeeping failure",
                date, slot_name)
        return f"posted:{date}:{slot_name}"
