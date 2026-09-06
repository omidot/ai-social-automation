from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from .daily_state import DailyState
from .telegram import Telegram
from .article_approve import _ig_caption

log = logging.getLogger("article_publish_ig")


def _meta():
    from .meta import Meta
    return Meta.from_env()


def due_slots(ds: DailyState, now: datetime) -> list[tuple[str, str, dict]]:
    out: list[tuple[str, str, dict]] = []
    for f in ds.all_files():
        date = f.stem
        doc = ds.load_safe(date)
        if doc is None:
            continue
        for slot_name, slot in doc["posts"].items():
            if slot.get("status") != "scheduled":
                continue
            if not slot.get("ig_due"):
                continue
            due = datetime.fromisoformat(slot["ig_due"])
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due <= now and not (slot.get("result", {}) or {}).get("ig"):
                out.append((date, slot_name, slot))
    return out


def run(root: Path, now: datetime | None = None, *, tg=None, meta=None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    ds = DailyState(root / "data")
    tg = tg or Telegram()
    meta = meta or _meta()
    published: list[str] = []
    failed: list[str] = []
    for date, slot_name, slot in due_slots(ds, now):
        result = dict(slot.get("result") or {})
        try:
            res = meta.ig_publish_images(slot["image_urls"], _ig_caption(slot))
            result["ig"] = res
            ds.put(date, slot_name, result=result)
            if (result.get("fb") or {}).get("scheduled"):
                ds.set_status(date, slot_name, "posted")
            tg.send_message(f"📸 Đã đăng IG {date}:{slot_name}.")
            published.append(f"{date}:{slot_name}")
        except Exception as e:  # noqa: BLE001
            log.error("ig publish %s:%s failed: %s", date, slot_name, e)
            attempts = int(slot.get("ig_attempts", 0)) + 1
            if attempts >= 3:
                # give up: writing result.ig as a dict makes due_slots' filter
                # drop this slot for good, so it stops re-qualifying every tick
                # (and stops spamming Telegram). Status stays "scheduled".
                result["ig"] = {"ok": False, "error": str(e), "attempts": attempts}
                ds.put(date, slot_name, result=result, ig_attempts=attempts)
                tg.send_message(
                    f"❌ IG {date}:{slot_name} bỏ cuộc sau {attempts} lần: {e}")
            else:
                ds.put(date, slot_name, ig_attempts=attempts)
                tg.send_message(
                    f"❌ IG lỗi {date}:{slot_name} (lần {attempts}/3): {e}")
            failed.append(f"{date}:{slot_name}")
    return {"published": published, "failed": failed}


def main() -> None:
    print(run(Path(".")))


if __name__ == "__main__":
    main()
