from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from .meta import Meta

log = logging.getLogger("publish")


class PublishError(Exception):
    pass


def _publish_fb(pending: dict, meta: Meta) -> dict:
    message = pending["caption_fb"] + "\n\n" + " ".join(pending["hashtags"])
    fbids = [meta.fb_upload_photo(p) for p in pending["images"]]
    res = meta.fb_create_post(message, fbids)
    return {"ok": True, "post_id": res["id"], "url": res["url"]}


def _publish_ig(pending: dict, meta: Meta) -> dict:
    caption = pending["caption_ig"] + "\n\n" + " ".join(pending["hashtags"])
    child_ids = []
    for p in pending["images"][:10]:
        url = meta.ig_upload_temp(p)
        child_ids.append(meta.ig_create_item(url))
    caro = meta.ig_create_carousel(child_ids, caption)
    res = meta.ig_publish(caro)
    return {"ok": True, "media_id": res["id"]}


def _write_platform_files(pending: dict, outdir: Path) -> tuple[str, str]:
    outdir.mkdir(parents=True, exist_ok=True)
    tags = " ".join(pending["hashtags"])
    yt = outdir / "youtube.txt"
    yt.write_text(
        f"{pending['youtube']['title']}\n\n{pending['youtube']['desc']}\n\n{tags}\n"
        f"\nNguồn: {pending['source']['name']} — {pending['source']['url']}\n",
        encoding="utf-8")
    tt = outdir / "tiktok.txt"
    tt.write_text(f"{pending['tiktok']['caption']}\n\n{tags}\n", encoding="utf-8")
    return str(yt), str(tt)


def publish(pending: dict, meta: Meta, outdir: Path) -> dict:
    outdir = Path(outdir)
    record = {"id": pending["id"], "angle": pending.get("angle"),
              "posted_at": datetime.now(timezone.utc).isoformat()}

    try:
        record["facebook"] = _publish_fb(pending, meta)
    except Exception as e:  # noqa: BLE001
        log.error("facebook publish failed: %s", e)
        record["facebook"] = {"ok": False, "error": str(e)}

    try:
        record["instagram"] = _publish_ig(pending, meta)
    except Exception as e:  # noqa: BLE001
        log.error("instagram publish failed: %s", e)
        record["instagram"] = {"ok": False, "error": str(e)}

    yt, tt = _write_platform_files(pending, outdir)
    record["youtube_file"], record["tiktok_file"] = yt, tt

    if not record["facebook"]["ok"] and not record["instagram"]["ok"]:
        raise PublishError(f"both platforms failed: fb={record['facebook'].get('error')} "
                           f"ig={record['instagram'].get('error')}")
    return record
