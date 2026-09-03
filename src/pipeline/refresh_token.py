from __future__ import annotations
import os

from .meta import Meta
from .telegram import Telegram


def main() -> int:
    m = Meta.from_env()
    res = m.exchange_long_lived_token(os.environ["META_APP_ID"],
                                     os.environ["META_APP_SECRET"],
                                     os.environ["META_PAGE_TOKEN"])
    new_token = res.get("access_token", "")
    masked = new_token[:6] + "…" + new_token[-4:] if new_token else "(none)"
    Telegram().send_message(
        "🔑 Token Meta mới đã được tạo (" + masked + ").\n"
        "Vào GitHub → Settings → Secrets → cập nhật META_PAGE_TOKEN.\n"
        "Giá trị đầy đủ nằm trong log job refresh-token.")
    print("::add-mask::" + new_token)
    print("NEW_META_PAGE_TOKEN=" + new_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
