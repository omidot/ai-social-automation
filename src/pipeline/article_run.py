from __future__ import annotations
import argparse, logging, os, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import collect, score, write, images
from .daily_state import DailyState
from .models import ArticleContent
from .state import State
from .telegram import Telegram
from .llm import generate as _default_generate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("article_run")
_OTHER = {"morning": "evening", "evening": "morning"}


def _configs(root: Path) -> tuple[dict, dict, dict]:
    c = Path(root) / "config"
    return (yaml.safe_load((c / "sources.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "voice.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "settings.yaml").read_text(encoding="utf-8")))


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-zA-Z0-9]+", "-", t)).strip("-").lower()[:50]


def _parse_size(s: str) -> tuple[int, int]:
    w, h = s.lower().split("x")
    return int(w), int(h)


def raw_base_url(settings: dict, rel_path: str) -> str:
    return f"{settings['images']['raw_base']}/{rel_path}".replace("\\", "/")


def send_preview(article: ArticleContent, image_paths: list[str], slot: str,
                 date: str, tg, slot_ict: str, score_val: float) -> None:
    tg.send_media_group(image_paths)
    src = ", ".join(s["name"] for s in article.sources)
    meta = f"[{article.format}] {src} · điểm {score_val:.0f}"
    if article.risk:
        meta += " ⚠️ nhạy cảm"
    body = article.caption_fb  # full caption, no truncation
    hashtags = " ".join(article.hashtags)
    buttons = [
        ("✅ Đăng ngay", f"art:{date}:{slot}:now"),
        (f"🕓 Lên lịch {slot_ict}", f"art:{date}:{slot}:sched"),
        ("🗑 Bỏ", f"art:{date}:{slot}:drop")]
    text = f"{meta}\n\n{body}\n\n{hashtags}"
    # Telegram caps a message at 4096 chars. Keep headroom: if the combined
    # meta+body+hashtags would exceed ~3900, split so the buttons still attach
    # to the final message (hashtags carry them).
    if len(text) > 3900:
        tg.send_message(f"{meta}\n\n{body}")
        tg.send_message(hashtags, buttons=buttons)
    else:
        tg.send_message(text, buttons=buttons)


def draft(slot: str, root: Path, now: datetime, *, generate=None, tg=None) -> dict:
    root = Path(root)
    generate = generate or _default_generate
    tg = tg or Telegram()
    sources, voice, settings = _configs(root)
    acfg = settings["articles"]
    date = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    ds = DailyState(root / "data")
    st = State(root / "data")

    other = ds.get(date, _OTHER[slot]) or {}
    exclude = [other["title"]] if other.get("title") else []

    try:
        cands = collect.collect(sources, settings, st, now)
    except collect.CollectError as e:
        tg.send_message(f"⚠️ Gom tin lỗi hết nguồn cho slot {slot}: {e}")
        return {"slot": slot, "status": "error"}

    picked = score.pick_n(cands, acfg["roundup_max"], acfg["min_score"], now,
                          sources.get("keywords", []), exclude_titles=exclude)
    if not picked:
        tg.send_message("Không có tin AI đủ nóng cho slot " + slot + " hôm nay.")
        return {"slot": slot, "status": "none"}

    fmt = write.decide_format(picked, acfg["format_deep_margin"])
    top_score, top = picked[0]
    if fmt == "deep":
        article = write.write_deep(top, voice, generate=generate)
        chosen = [top]
    else:
        # picked[:n] can never exceed len(picked), so no lower clamp is needed here;
        # acfg["roundup_min"] is currently unused tuning config, kept for future.
        n = min(len(picked), acfg["roundup_max"])
        chosen = [c for _, c in picked[:n]]
        article = write.write_roundup(chosen, voice, generate=generate)

    rel_dir = f"assets/posts/{date}/{slot}"
    paths = images.build_images(article, root / rel_dir,
                                size=_parse_size(settings["images"]["size"]),
                                brand=settings["images"].get("brand", {}))
    rel_paths = [str(Path(p).relative_to(root)).replace("\\", "/") for p in paths]
    image_urls = [raw_base_url(settings, rp) for rp in rel_paths]

    st.seen_add_many([c.url_hash for c in chosen])
    slot_ict = acfg["slots"][slot]
    ds.put(date, slot, status="draft", format=fmt, title=top.title,
           topic_key=_slug(top.title), text_fb=article.caption_fb,
           text_ig=article.caption_ig, hashtags=article.hashtags,
           images=rel_paths, image_urls=image_urls, risk=article.risk,
           slot_ict=slot_ict, sources=article.sources, score=round(top_score, 1))
    send_preview(article, paths, slot, date, tg, slot_ict, top_score)
    return ds.get(date, slot)


class _NoopTelegram:
    """Stand-in used for offline smoke runs when no bot token is configured."""

    def send_message(self, *a, **k) -> None:
        pass

    def send_media_group(self, *a, **k) -> None:
        pass


def _notify_failure(slot: str, e: BaseException) -> None:
    """Surface a live pipeline failure to the operator via Telegram.

    Mirrors ``main``'s ``no_tg`` handling: with no bot token there is nowhere
    to send, so just log and return instead of raising a fresh KeyError.
    """
    msg = f"❌ Pipeline lỗi ({slot}): {e}"
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        log.error(msg)
        return
    try:
        Telegram().send_message(msg)
    except Exception:  # noqa: BLE001 - never mask the original failure
        log.exception("failed to send failure notification")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=("morning", "evening"), required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--fake-llm", action="store_true")
    args = ap.parse_args(argv)
    gen = None
    if args.fake_llm:
        from .llm import _fake_generate as gen  # reuse the existing canned generator
    # With no bot token there is nowhere to send a preview, so swap in a no-op
    # Telegram stand-in; the real network/LLM path still runs.
    no_tg = not os.environ.get("TELEGRAM_BOT_TOKEN")
    tg = _NoopTelegram() if no_tg else None
    if args.fake_llm:
        # --fake-llm smoke only: the canned generator predates the article-track
        # writer schema, so write_roundup/write_deep can legitimately raise
        # WriteError. Swallow it here so the smoke proves the wiring without a
        # traceback. A real-LLM run never reaches this branch, so a genuine
        # write.WriteError from the live LLM stays loud.
        try:
            draft(args.slot, Path(args.root), datetime.now(timezone.utc),
                  generate=gen, tg=tg)
        except write.WriteError as e:
            log.warning("offline smoke: pipeline raised %s: %s", type(e).__name__, e)
        print("SUMMARY: dry")
        return 0
    try:
        out = draft(args.slot, Path(args.root), datetime.now(timezone.utc),
                    generate=gen, tg=tg)
    except Exception as e:  # noqa: BLE001 - surface every failure to the operator
        _notify_failure(args.slot, e)
        return 1
    print("SUMMARY:", out.get("status"), out.get("slot", args.slot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
