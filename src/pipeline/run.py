from __future__ import annotations
import argparse, json, logging, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import collect, score, write, media, review, publish
from .llm import generate as _generate
from .state import State

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("run")


def load_configs(root: Path) -> tuple[dict, dict, dict]:
    c = Path(root) / "config"
    return (yaml.safe_load((c / "sources.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "voice.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((c / "settings.yaml").read_text(encoding="utf-8")))


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)


def make_id(cand, now: datetime) -> str:
    return f"{now:%Y-%m-%d}-{_slug(cand.title)[:40]}".rstrip("-")


def _notify(msg: str) -> None:
    try:
        from .telegram import Telegram
        Telegram().send_message(msg)
    except Exception as e:  # noqa: BLE001
        log.warning("telegram notify failed: %s", e)


def _load_local_candidates(root: Path) -> list:
    f = Path(root) / "tests/fixtures/local_candidates.json"
    if not f.exists():
        return []
    from .models import Candidate
    return [Candidate.from_dict(d) for d in json.loads(f.read_text(encoding="utf-8"))]


def _summary_line(record: dict) -> str:
    fb = "OK" if record.get("facebook", {}).get("ok") else "LỖI"
    ig = "OK" if record.get("instagram", {}).get("ok") else "LỖI"
    return f"Đã đăng {record['id']}: Facebook {fb}, Instagram {ig}."


def build(root: Path, now: datetime, dry_run: bool, local: bool, generate=None) -> dict | None:
    generate = generate or _generate
    root = Path(root)
    sources, voice, settings = load_configs(root)
    st = State(root / "data")

    if local:
        cands = _load_local_candidates(root) or collect.collect(sources, settings, st, now)
    else:
        cands = collect.collect(sources, settings, st, now)
    log.info("collected %d candidates", len(cands))

    st.seen_add_many([c.url_hash for c in cands])

    best, best_score = score.pick(cands, settings.get("min_score", 45), now,
                                  sources.get("keywords", []))
    if best is None:
        log.info("no story above threshold (best=%.1f)", best_score)
        if not dry_run:
            _notify(f"Hôm nay không có tin AI đủ nóng (điểm cao nhất "
                    f"{best_score:.0f}/{settings.get('min_score', 45)}).")
        return None
    log.info("picked: %s (score %.1f)", best.title, best_score)

    post = write.write_post(best, voice, generate=generate)

    pid = make_id(best, now)
    out_dir = root / "output" / f"{now:%Y-%m-%d}" / pid
    (out_dir / "img").mkdir(parents=True, exist_ok=True)

    images, low_media = media.build_media(best, post, out_dir, voice.get("ten_kenh", ""))

    (out_dir / "caption_fb.txt").write_text(
        post.caption_fb + "\n\n" + " ".join(post.hashtags), encoding="utf-8")
    (out_dir / "caption_ig.txt").write_text(
        post.caption_ig + "\n\n" + " ".join(post.hashtags), encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(
        {"candidate": best.to_dict(), "post": post.to_dict(), "images": images,
         "low_media": low_media, "score": best_score}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    pending = review.build_pending(post, images, pid, low_media, now)

    if dry_run:
        log.info("dry-run: wrote %s (no telegram, no publish)", out_dir)
        return pending

    mode = settings.get("approval_mode", "telegram")
    if mode == "telegram":
        from .telegram import Telegram
        review.send_preview(pending, Telegram())
        st.pending_add(pending)
        log.info("sent Telegram preview for %s", pid)
        return pending

    from .meta import Meta
    record = publish.publish(pending, Meta.from_env(), out_dir)
    st.posted_save(record)
    _notify(_summary_line(record))
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI social automation — build stage")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        result = build(Path(args.root), now, dry_run=args.dry_run, local=args.local)
    except (collect.CollectError, write.WriteError, publish.PublishError) as e:
        log.error("pipeline failed: %s", e)
        if not args.dry_run:
            _notify(f"Pipeline lỗi: {e}")
        return 1
    if result is None:
        print("SUMMARY: no post today")
        return 0
    if "posted_at" in result:
        print("SUMMARY: " + _summary_line(result))
    elif args.dry_run:
        print(f"SUMMARY: dry-run built {result['id']}")
    else:
        print(f"SUMMARY: pending {result['id']} awaiting approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
