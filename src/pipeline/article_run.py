from __future__ import annotations
import argparse, logging, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import collect, score, write, images
from .daily_state import DailyState
from .models import ArticleContent
from .state import State
from .telegram import Telegram
from .llm import generate as _default_generate

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
    cap = article.caption_fb
    body = cap if len(cap) <= 900 else cap[:900] + " …"
    text = f"{meta}\n\n{body}\n\n{' '.join(article.hashtags)}"
    tg.send_message(text, buttons=[
        ("✅ Đăng ngay", f"art:{date}:{slot}:now"),
        (f"🕓 Lên lịch {slot_ict}", f"art:{date}:{slot}:sched"),
        ("🗑 Bỏ", f"art:{date}:{slot}:drop")])


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
    else:
        n = min(max(len(picked), acfg["roundup_min"]), acfg["roundup_max"])
        article = write.write_roundup([c for _, c in picked[:n]], voice, generate=generate)

    rel_dir = f"assets/posts/{date}/{slot}"
    paths = images.build_images(article, root / rel_dir,
                                style_prompt=settings["images"]["style_prompt"],
                                size=_parse_size(settings["images"]["size"]))
    rel_paths = [str(Path(p).relative_to(root)).replace("\\", "/") for p in paths]
    image_urls = [raw_base_url(settings, rp) for rp in rel_paths]

    st.seen_add_many([top.url_hash])
    slot_ict = acfg["slots"][slot]
    ds.put(date, slot, status="draft", format=fmt, title=top.title,
           topic_key=_slug(top.title), text_fb=article.caption_fb,
           text_ig=article.caption_ig, hashtags=article.hashtags,
           images=rel_paths, image_urls=image_urls, risk=article.risk,
           slot_ict=slot_ict, sources=article.sources, score=round(top_score, 1))
    send_preview(article, paths, slot, date, tg, slot_ict, top_score)
    return ds.get(date, slot)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=("morning", "evening"), required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--fake-llm", action="store_true")
    args = ap.parse_args(argv)
    gen = None
    if args.fake_llm:
        from .run import _fake_generate as gen  # reuse the existing canned generator
    out = draft(args.slot, Path(args.root), datetime.now(timezone.utc), generate=gen)
    print("SUMMARY:", out.get("status"), out.get("slot", args.slot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
