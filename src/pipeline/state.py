from __future__ import annotations
import json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class State:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.seen_path = self.dir / "seen.json"
        self.pending_dir = self.dir / "pending"
        self.posted_dir = self.dir / "posted"
        self.offset_path = self.dir / "telegram_offset.json"

    # ---- seen ----
    def _seen(self) -> dict:
        return _read_json(self.seen_path, {})

    def seen_has(self, url_hash: str) -> bool:
        return url_hash in self._seen()

    def seen_add_many(self, hashes: Iterable[str]) -> None:
        data = self._seen()
        now = datetime.now(timezone.utc).isoformat()
        for h in hashes:
            data.setdefault(h, now)
        _atomic_write(self.seen_path, json.dumps(data, ensure_ascii=False, indent=2))

    # ---- pending ----
    def pending_add(self, record: dict) -> Path:
        p = self.pending_dir / f"{record['id']}.json"
        _atomic_write(p, json.dumps(record, ensure_ascii=False, indent=2))
        return p

    def pending_list(self) -> list[dict]:
        if not self.pending_dir.exists():
            return []
        return [json.loads(f.read_text(encoding="utf-8"))
                for f in sorted(self.pending_dir.glob("*.json"))]

    def pending_remove(self, pid: str) -> None:
        p = self.pending_dir / f"{pid}.json"
        if p.exists():
            p.unlink()

    # ---- posted ----
    def posted_save(self, record: dict) -> Path:
        p = self.posted_dir / f"{record['id']}.json"
        _atomic_write(p, json.dumps(record, ensure_ascii=False, indent=2))
        return p

    # ---- telegram offset ----
    def offset_load(self) -> int:
        return int(_read_json(self.offset_path, {"offset": 0})["offset"])

    def offset_save(self, v: int) -> None:
        _atomic_write(self.offset_path, json.dumps({"offset": int(v)}))
