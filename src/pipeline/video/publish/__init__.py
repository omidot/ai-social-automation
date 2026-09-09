"""Phase 2C — publish a rendered video to external platforms."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from ..models import VideoMeta
from ...meta import Meta
from . import assets as _assets
from . import tiktok as _tiktok
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
    tg: object = None


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
    # channel_footer lives on `video`, youtube_category on `video.publish`
    r = yt.upload(ctx.mp4_path, ctx.meta, {**ctx.cfg, **(ctx.cfg.get("publish") or {})})
    return {"id": r["id"], "url": r["url"]}


def _do_fb_reel(ctx: _Ctx) -> dict:
    desc = (f"{ctx.meta.title}\n\n{ctx.meta.description}".strip()
            + ("\n\n" + " ".join(ctx.meta.hashtags) if ctx.meta.hashtags else ""))
    return Meta.from_env().fb_publish_reel(ctx.asset_url, desc)


def _do_ig_reel(ctx: _Ctx) -> dict:
    cap = (f"{ctx.meta.description}".strip()
           + ("\n\n" + " ".join(ctx.meta.hashtags) if ctx.meta.hashtags else ""))
    return Meta.from_env().ig_publish_reel(ctx.asset_url, cap)


def _do_tiktok(ctx: _Ctx) -> dict:
    return _tiktok.TikTok.from_env().upload_draft(
        ctx.asset_url, ctx.meta.tiktok_caption, tg=ctx.tg)


_PLATFORMS = {"youtube": _do_youtube, "fb_reel": _do_fb_reel}
_PLATFORMS["ig_reel"] = _do_ig_reel
_PLATFORMS["tiktok"] = _do_tiktok


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
               asset_url=asset_url, mp4_path=mp4_path, tg=tg)

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


# ---- undo (🗑 Gỡ tất cả) ----------------------------------------------------

_UNDO_GRACE_MIN = 60


def _ack(tg, cbq, text: str) -> None:
    try:
        tg.answer_callback(cbq["id"], text)
    except Exception:  # noqa: BLE001 - an expired callback id must never abort the poll
        pass


def _delete_platform(p: str, res: dict, tg) -> str | None:
    """Best-effort remote delete. Returns an error string or None."""
    try:
        if p == "youtube":
            _youtube.YouTube.from_env().delete(res["id"])
        elif p == "fb_reel":
            Meta.from_env().fb_delete_post(res["id"])
        elif p == "ig_reel":
            Meta.from_env().ig_delete_media(res["id"])
        elif p == "tiktok":
            return "TikTok: tự xoá nháp trong app"
        return None
    except Exception as e:  # noqa: BLE001 - one platform delete must not block the rest
        return f"{_PLATFORM_LABEL.get(p, p)}: {e}"


def handle_unpublish(cbq: dict, ds, tg, root, now: datetime) -> str | None:
    parts = cbq.get("data", "").split(":")
    if len(parts) != 4 or parts[0] != "vid" or parts[3] != "unpub":
        return None
    _, date, slot, _ = parts
    row = ds.get_safe(date, slot) or {}
    v = row.get("video") or {}
    if v.get("status") != "published":
        _ack(tg, cbq, "Không có gì để gỡ.")
        return None
    try:
        pub_at = datetime.fromisoformat(v["published_at"])
    except (KeyError, ValueError, TypeError):
        pub_at = now
    if (now - pub_at).total_seconds() > _UNDO_GRACE_MIN * 60:
        _ack(tg, cbq, "Đăng lâu rồi — gỡ tay trên từng nền tảng.")
        tg.send_message(f"⚠️ {date}:{slot} đã đăng quá {_UNDO_GRACE_MIN} phút, gỡ thủ công.")
        return f"undo-expired:{date}:{slot}"

    errs: list[str] = []
    result = dict(v.get("result", {}))
    for p, res in list(result.items()):
        if not (res and res.get("id")) and not (res and res.get("status") == "draft_uploaded"):
            continue
        err = _delete_platform(p, res, tg)
        if err:
            errs.append(err)
        result[p] = {**res, "undone": True}
    ds.put(date, slot, video={**((ds.get_safe(date, slot) or {}).get("video") or v),
                              "status": "unpublished", "result": result})
    _ack(tg, cbq, "Đã gỡ.")
    msg = f"🗑 Đã gỡ {date}:{slot}."
    if errs:
        msg += " Lỗi: " + "; ".join(errs)
    tg.send_message(msg)
    return f"unpublished:{date}:{slot}"
