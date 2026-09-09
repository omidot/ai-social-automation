from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..daily_state import DailyState
from ..telegram import Telegram
from . import render


def run(root: Path, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    ds = DailyState(root / "data")
    tg = Telegram()
    return render.render_pending(ds, tg, root, now)


def main() -> None:
    print(run(Path(".")))


if __name__ == "__main__":
    main()
