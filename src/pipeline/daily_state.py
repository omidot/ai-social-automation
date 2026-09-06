from __future__ import annotations
import json
import logging
from pathlib import Path

from .state import _atomic_write, _read_json

log = logging.getLogger("daily_state")

TERMINAL = frozenset({"posted", "discarded", "expired"})


class DailyState:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "daily"

    def path(self, date: str) -> Path:
        return self.dir / f"{date}.json"

    def load(self, date: str) -> dict:
        return _read_json(self.path(date), {"date": date, "posts": {}})

    def load_safe(self, date: str) -> dict | None:
        """Like load(), but returns None (with a logged error) instead of
        raising when the on-disk file is corrupt or unreadable. Pollers that
        sweep every daily file use this so one bad file cannot stall the loop."""
        try:
            return self.load(date)
        except (json.JSONDecodeError, OSError) as e:
            log.error("daily-state %s unreadable: %s", date, e)
            return None

    def _save(self, date: str, doc: dict) -> None:
        _atomic_write(self.path(date), json.dumps(doc, ensure_ascii=False, indent=2))

    def get(self, date: str, slot: str) -> dict | None:
        return self.load(date)["posts"].get(slot)

    def get_safe(self, date: str, slot: str) -> dict | None:
        """Like get(), but returns None instead of raising when the on-disk
        file is corrupt/unreadable (load_safe logs the error). Callback
        handling uses this so a poisoned daily file cannot crash the poller."""
        d = self.load_safe(date)
        return None if d is None else d["posts"].get(slot)

    def put(self, date: str, slot: str, **fields) -> dict:
        doc = self.load(date)
        cur = doc["posts"].setdefault(slot, {})
        cur.update(fields)
        self._save(date, doc)
        return cur

    def set_status(self, date: str, slot: str, status: str) -> bool:
        doc = self.load(date)
        cur = doc["posts"].get(slot, {})
        if cur.get("status") in TERMINAL:
            return False
        cur["status"] = status
        doc["posts"][slot] = cur
        self._save(date, doc)
        return True

    def all_files(self) -> list[Path]:
        if not self.dir.exists():
            return []
        return sorted(self.dir.glob("*.json"))
