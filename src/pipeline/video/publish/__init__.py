"""Phase 2C — publish a rendered video to external platforms."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..models import VideoMeta
from . import assets as _assets
from . import youtube as _youtube

log = logging.getLogger("video.publish")

_PLATFORM_LABEL = {"youtube": "YouTube", "fb_reel": "FB Reel",
                   "ig_reel": "IG Reel", "tiktok": "TikTok"}
_MAX_ATTEMPTS = 5


@dataclass
class _Ctx:
    root: Path
    cfg: dict
    meta: VideoMeta
    asset_url: str
    mp4_path: Path | None


def _cfg(root: Path) -> dict:
    data = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8")) or {}
    return data.get("video") or {}


def _done(res: dict | None) -> bool:
    if not res:
        return False
    return bool(res.get("id") or res.get("gave_up")
               or res.get("status") == "draft_uploaded")


def _download_tg_mp4(tg, file_id: str, dest: Path) -> Path | None:
    try:
        return Path(tg.download_file(file_id, str(dest)))
    except Exception:  # noqa: BLE001
        log.exception("tg mp4 download failed")
        return None


# ---- per-platform actions -------------------------------------------------

def _do_youtube(ctx: _Ctx) -> dict:
    yt = _youtube.YouTube.from_env()
    if ctx.mp4_path is None:
        raise _youtube.YouTubeError("youtube needs the mp4 on disk")
    r = yt.upload(ctx.mp4_path, ctx.meta, ctx.cfg)
    return {"id": r["id"], "url": r["url"]}


_PLATFORMS = {"youtube": _do_youtube}          # Tasks 5-7 add fb_reel / ig_reel / tiktok


# ---- orchestrator -------------------------------------------------------

def publish_pending(ds, tg, root: Path, now: datetime, *, limit: int = 1) -> list[str]:
    root = Path(root)
    cfg = _cfg(root)
    enabled = [p for p in _PLATFORMS if (cfg.get("publish") or {}).get(p)]
    if not enabled:
        return []

    picked: list[tuple[str, str, dict]] = []
    for f in sorted(ds.all_files()):
        doc = ds.load_safe(f.stem)
        if doc is None:
            continue
        for slot, row in doc["posts"].items():
            v = row.get("video") or {}
            if v.get("status") not in ("rendered", "publishing"):
                continue
            if any(not _done(v.get("result", {}).get(p)) for p in enabled):
                picked.append((f.stem, slot, v))
    if not picked:
        return []

    out: list[str] = []
    for date, slot, v in picked[:limit]:
        out.append(_publish_one(ds, tg, root, cfg, enabled, date, slot, v, now))
    return out


def _publish_one(ds, tg, root, cfg, enabled, date, slot, v, now) -> str:
    # --- ensure asset ---
    asset_url = v.get("asset_url")
    mp4_path = None
    if v.get("mp4_path"):
        p = root / v["mp4_path"]
        if p.exists():
            mp4_path = p
    if not asset_url:
        src = mp4_path
        if src is None and v.get("tg_file_id"):
            src = _download_tg_mp4(tg, v["tg_file_id"], root / "output" / f"{date}-{slot}.mp4")
            mp4_path = src
        if src is None:
            cur = (ds.get_safe(date, slot) or {}).get("video") or v
            ds.put(date, slot, video={**cur, "status": "awaiting_audio",
                                      "render_err": "mp4 unavailable for publish"})
            tg.send_message(f"⚠️ {date}:{slot} không có MP4 để đăng — cần render lại.")
            return f"skip:{date}:{slot}"
        asset_url = _assets.upload_release_asset(src, f"{date}-{slot}.mp4")

    cur = (ds.get_safe(date, slot) or {}).get("video") or v
    patch = {**cur, "status": "publishing", "asset_url": asset_url}
    patch.setdefault("publish_started_at", now.isoformat())
    ds.put(date, slot, video=patch)

    ctx = _Ctx(root=root, cfg=cfg, meta=VideoMeta.from_dict(v["meta"]),
               asset_url=asset_url, mp4_path=mp4_path)

    for p in enabled:
        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        if cur.get("status") != "publishing":
            return f"publishing:{date}:{slot}"          # an undo landed
        res = cur.get("result", {}).get(p)
        if _done(res):
            continue
        try:
            got = _PLATFORMS[p](ctx)
            new = {**got, "at": now.isoformat()}
        except Exception as e:  # noqa: BLE001 - one platform must not block the rest
            log.exception("publish %s:%s %s failed", date, slot, p)
            attempts = int((res or {}).get("attempts", 0)) + 1
            gave_up = attempts >= _MAX_ATTEMPTS
            new = {"error": str(e)[:300], "attempts": attempts,
                   "last_at": now.isoformat(), "gave_up": gave_up}
            if gave_up:
                tg.send_message(f"⚠️ {_PLATFORM_LABEL[p]} bỏ cuộc sau {_MAX_ATTEMPTS} "
                                f"lần với {date}:{slot}: {str(e)[:200]}")
        cur = (ds.get_safe(date, slot) or {}).get("video") or v
        ds.put(date, slot, video={**cur, "result": {**cur.get("result", {}), p: new}})

    cur = (ds.get_safe(date, slot) or {}).get("video") or v
    if all(_done(cur.get("result", {}).get(p)) for p in enabled):
        _assets.delete_release_asset(f"{date}-{slot}.mp4")
        ds.put(date, slot, video={**cur, "status": "published",
                                  "published_at": now.isoformat(), "asset_url": None})
        tg.send_message(_summary(date, slot, cur, enabled),
                        buttons=[("🗑 Gỡ tất cả", f"vid:{date}:{slot}:unpub")])
        return f"published:{date}:{slot}"
    return f"publishing:{date}:{slot}"


def _summary(date, slot, v, enabled) -> str:
    lines = [f"🚀 Video {slot} ({date}) đã đăng:"]
    for p in enabled:
        r = v.get("result", {}).get(p) or {}
        if r.get("id"):
            lines.append(f"✅ {_PLATFORM_LABEL[p]} {r.get('url', '')}".rstrip())
        elif r.get("status") == "draft_uploaded":
            lines.append(f"📥 {_PLATFORM_LABEL[p]} — mở app đăng nháp")
        else:
            lines.append(f"❌ {_PLATFORM_LABEL[p]} (bỏ cuộc)")
    return "\n".join(lines)
