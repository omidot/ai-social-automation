from __future__ import annotations
from datetime import datetime

from .models import PostContent
from .telegram import Telegram


def build_pending(post: PostContent, images: list[str], pid: str,
                  low_media: bool, now: datetime) -> dict:
    return {
        "id": pid,
        "created_at": now.isoformat(),
        "angle": post.angle,
        "caption_fb": post.caption_fb,
        "caption_ig": post.caption_ig,
        "hashtags": post.hashtags,
        "images": list(images),
        "youtube": {"title": post.youtube_title, "desc": post.youtube_desc},
        "tiktok": {"caption": post.tiktok_caption},
        "source": {"url": post.source_url, "name": post.source_name},
        "low_media": low_media,
    }


def send_preview(pending: dict, tg: Telegram) -> None:
    tg.send_media_group(pending["images"])
    lines = []
    if pending.get("low_media"):
        lines.append("⚠️ Ít ảnh (<3). Kiểm tra kỹ trước khi đăng.")
    lines.append(f"[{pending['angle']}] {pending['source']['name']}")
    lines.append("")
    cap = pending["caption_fb"]
    lines.append(cap if len(cap) <= 900 else cap[:900] + " …")
    lines.append("")
    lines.append(" ".join(pending["hashtags"]))
    pid = pending["id"]
    tg.send_message("\n".join(lines),
                    buttons=[("✅ Đăng", f"approve:{pid}"),
                             ("✏️ Sửa", f"edit:{pid}"),
                             ("❌ Bỏ", f"reject:{pid}")])
