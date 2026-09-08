from __future__ import annotations
import argparse, logging, os, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import write, images, topics, collect, score, publish, styles
from .video import draft_script as _video_draft
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


def _meta():
    from .meta import Meta
    return Meta.from_env()


def raw_base_url(settings: dict, rel_path: str) -> str:
    return f"{settings['images']['raw_base']}/{rel_path}".replace("\\", "/")


def draft(slot: str, root: Path, now: datetime, *, generate=None, tg=None, meta=None) -> dict:
    root = Path(root)
    generate = generate or _default_generate
    tg = tg or Telegram()
    sources, voice, settings = _configs(root)
    acfg = settings["articles"]
    date = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    ds = DailyState(root / "data")

    # Never clobber a slot the operator has already acted on. A same-day re-run
    # of article-morning/evening must leave a scheduled/posted/publishing slot
    # untouched (it used to silently overwrite it back to "draft"). Re-drafting
    # over an un-acted preview (draft/discarded/expired/error/none/absent) is fine.
    existing = ds.get_safe(date, slot)
    if existing and existing.get("status") in {"scheduled", "posted", "publishing"}:
        tg.send_message(
            f"⏭️ Bài {slot} hôm nay đã ở trạng thái '{existing['status']}', "
            "bỏ qua lần chạy này.")
        return {"slot": slot, "status": "skipped"}

    topics_cfg = topics.load_topics(root)
    recent = topics.recent_titles(root, topics_cfg.get("recent_window_days", 45))
    other = ds.get_safe(date, _OTHER[slot]) or {}
    if other.get("title"):
        recent = [other["title"]] + recent

    # --- 1. launch-news first: what big tech just shipped ------------------
    # Any collect failure (CollectError or otherwise) is non-fatal — we just
    # fall straight through to the curated topic bank below.
    keywords = sources.get("keywords", [])
    picked: list = []
    try:
        cands = collect.collect(sources, settings, State(root / "data"), now)
        picked = score.pick_n(cands, 4, acfg["min_score"], now, keywords,
                              exclude_titles=recent)
        picked = [(sc, c) for sc, c in picked if score.has_body(c)]
    except collect.CollectError as e:
        log.warning("collect failed (%s) — using the topic bank", e)
    except Exception as e:  # noqa: BLE001 - a broken source must not sink the run
        log.warning("collect raised %s: %s — using the topic bank", type(e).__name__, e)

    article: ArticleContent | None = None
    news_title = ""
    news_sources: list[dict] = []
    attempted: list[str] = []
    for sc, cand in picked:
        attempted.append(cand.url_hash)
        try:
            article = write.write_share(cand, voice, generate=generate)
        except write.WriteError as e:
            log.warning("write_share rejected %r: %s", cand.title, e)
            continue
        news_title = cand.title
        src = cand.source.split(":", 1)[1] if ":" in cand.source else cand.source
        news_sources = [{"name": src, "url": cand.url}]
        break

    if attempted:
        try:
            State(root / "data").seen_add_many(attempted)
        except Exception as e:  # noqa: BLE001 - best effort
            log.warning("seen_add_many failed: %s", e)

    is_news = article is not None

    # --- 2. fall back to the curated topic bank --------------------------
    if article is None:
        try:
            spec = topics.propose_topic(topics_cfg, recent, voice, generate)
        except Exception as e:  # noqa: BLE001 - any proposal failure is non-fatal
            tg.send_message(f"⚠️ Không đề xuất được chủ đề {slot}: {e}")
            return {"slot": slot, "status": "error"}
        try:
            article = write.write_topic_post(
                spec["topic"], spec.get("angle", ""), voice, generate=generate)
        except write.WriteError as e:
            tg.send_message(
                f"⚠️ Không viết được bài {slot} (chủ đề: {spec['topic']}): {e}")
            return {"slot": slot, "status": "error"}
        title = spec["topic"]
        angle = spec.get("angle", "")
        state_sources: list[dict] = []
    else:
        title = news_title
        angle = ""
        state_sources = news_sources

    rel_dir = f"assets/posts/{date}/{slot}"
    try:
        chosen_style = styles.pick_style(root)
        style_name = chosen_style.name
    except Exception as e:  # noqa: BLE001 - bad styles.yaml -> build_images self-defaults
        log.warning("pick_style failed (%s)", e)
        chosen_style, style_name = None, "default"
    paths = images.build_images(article, root / rel_dir,
                                size=_parse_size(settings["images"]["size"]),
                                brand=settings["images"].get("brand", {}),
                                root=root, style=chosen_style)
    rel_paths = [str(Path(p).relative_to(root)).replace("\\", "/") for p in paths]
    image_urls = [raw_base_url(settings, rp) for rp in rel_paths]
    slot_ict = acfg["slots"][slot]

    # preview the carousel to Telegram (informational only — no buttons)
    marker = "📰" if is_news else "💡"
    try:
        tg.send_media_group(paths, caption=f"{marker} {title}")
    except Exception as e:  # noqa: BLE001 - a preview failure must not stop publishing
        log.warning("preview send failed: %s", e)

    ds.put(date, slot, status="publishing", format="share", title=title,
           style=style_name,
           topic_key=_slug(title), text_fb=article.caption_fb,
           text_ig=article.caption_ig, hashtags=article.hashtags,
           images=rel_paths, image_urls=image_urls, risk=article.risk,
           slot_ict=slot_ict, sources=state_sources, angle=angle)
    # Flag a risky article to the operator BEFORE scheduling: the schedule may
    # fail and fall to retry_unscheduled (which sends no risk notice), so this
    # must fire regardless of which path ends up posting. Single send.
    if article.risk:
        try:
            tg.send_message(f"⚠️ {date}:{slot} — bài này gắn cờ nhạy cảm, kiểm tra nhanh.")
        except Exception as e:  # noqa: BLE001 - a notice failure must not stop publishing
            log.warning("risk notice send failed: %s", e)
    try:
        publish.schedule_slot(ds, meta or _meta(), root, date, slot, now, tg)
    except Exception as e:  # noqa: BLE001 - transient publish failure -> retryable
        ds.set_status(date, slot, "draft")
        _notify_failure(slot, e)
        return {"slot": slot, "status": "error"}

    # The article is scheduled. If video is on, kick off script generation for
    # the same story — but a video failure must never break the article flow.
    if settings.get("video", {}).get("enabled"):
        try:
            _video_draft.draft(
                slot, root, title=title,
                source_url=(state_sources[0]["url"] if state_sources else ""),
                body_text=article.caption_fb, caption_fb=article.caption_fb,
                angle=angle, now=now, generate=generate, tg=tg)
        except Exception as e:  # noqa: BLE001 - video is secondary; the article is already scheduled
            log.warning("video draft_script failed: %s", e)
            try:
                tg.send_message(f"⚠️ Kịch bản video {slot} lỗi: {e}")
            except Exception:  # noqa: BLE001
                pass
    return ds.get(date, slot)


class _NoopTelegram:
    """Stand-in used for offline smoke runs when no bot token is configured."""

    def send_message(self, *a, **k) -> None:
        pass

    def send_media_group(self, *a, **k) -> None:
        pass


class _NoopMeta:
    """Stand-in for Meta used by the ``--fake-llm`` offline smoke so a run on a
    machine with ``META_*`` exported never touches the real Graph API."""

    def fb_upload_photo(self, *a, **k) -> str:
        return "noop"

    def fb_create_post(self, *a, **k) -> dict:
        return {"id": "noop", "url": "", "scheduled": True}

    def ig_publish_images(self, *a, **k) -> dict:
        return {"ok": True, "media_id": "noop"}

    def fb_delete_post(self, *a, **k) -> dict:
        return {"success": True}

    def ig_delete_media(self, *a, **k) -> dict:
        return {"success": True}


def _notify_failure(slot: str, e: BaseException) -> None:
    """Surface a live pipeline failure to the operator via Telegram.

    Mirrors ``main``'s ``no_tg`` handling: with no bot token there is nowhere
    to send, so just log and return instead of raising a fresh KeyError.
    """
    msg = f"❌ Pipeline lỗi ({slot}): {type(e).__name__}: {e}"
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
        # writer schema, so write_share can legitimately raise
        # WriteError. Swallow it here so the smoke proves the wiring without a
        # traceback. A real-LLM run never reaches this branch, so a genuine
        # write.WriteError from the live LLM stays loud.
        try:
            draft(args.slot, Path(args.root), datetime.now(timezone.utc),
                  generate=gen, tg=tg, meta=_NoopMeta())
        except write.WriteError as e:
            log.warning("offline smoke: pipeline raised %s: %s", type(e).__name__, e)
        print("SUMMARY: dry")
        return 0
    try:
        out = draft(args.slot, Path(args.root), datetime.now(timezone.utc),
                    generate=gen, tg=tg)
    except Exception as e:  # noqa: BLE001 - surface every failure to the operator
        log.exception("draft(%s) failed", args.slot)
        _notify_failure(args.slot, e)
        return 1
    print("SUMMARY:", out.get("status"), out.get("slot", args.slot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
