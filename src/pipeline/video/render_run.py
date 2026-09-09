from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from ..daily_state import DailyState
from ..telegram import Telegram
from . import render
from .publish import publish_pending


def run(root: Path, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    ds = DailyState(root / "data")
    tg = Telegram()
    out = render.render_pending(ds, tg, root, now)
    out += publish_pending(ds, tg, root, now)
    return out


def main() -> None:
    print(run(Path(".")))


if __name__ == "__main__":
    main()
