from __future__ import annotations
import logging, time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import feedparser
import httpx

from .models import Candidate
from .state import State

log = logging.getLogger("collect")
_HTTP = httpx.Client(timeout=20.0, follow_redirects=True,
                     headers={"User-Agent": "ai-social-bot/0.1 (+github actions)"})
MAX_AGE_HOURS = 48


class CollectError(Exception):
    pass


def _get(url: str, params: dict | None = None) -> httpx.Response:
    r = _HTTP.get(url, params=params)
    r.raise_for_status()
    return r


def _extract(url: str) -> tuple[str, str | None]:
    import trafilatura
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return "", None
    text = trafilatura.extract(downloaded, include_comments=False) or ""
    meta = trafilatura.extract_metadata(downloaded)
    image = getattr(meta, "image", None) if meta else None
    return text, image


def _fresh(dt: datetime, now: datetime) -> bool:
    return (now - dt) <= timedelta(hours=MAX_AGE_HOURS) and dt <= now + timedelta(hours=1)


def _parse_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        v = entry.get(key)
        if v:
            return datetime(*v[:6], tzinfo=timezone.utc)
    return None


def _collapse_similar(cands: list[Candidate]) -> list[Candidate]:
    groups: list[list[Candidate]] = []
    for c in cands:
        placed = False
        for g in groups:
            if SequenceMatcher(None, c.title.lower(), g[0].title.lower()).ratio() >= 0.72:
                g.append(c)
                placed = True
                break
        if not placed:
            groups.append([c])
    out: list[Candidate] = []
    for g in groups:
        rep = min(g, key=lambda x: x.published_at)
        rep.source_count = len(g)
        if rep.source.startswith("rss:Google News ("):
            better = next(
                (m.source for m in g if not m.source.startswith("rss:Google News (")),
                None)
            if better:
                rep.source = better
        for m in g:
            if not rep.full_text and m.full_text:
                rep.full_text = m.full_text
            if not rep.top_image and m.top_image:
                rep.top_image = m.top_image
        out.append(rep)
    return out


def from_rss(feeds: list[dict], now: datetime) -> list[Candidate]:
    out: list[Candidate] = []
    for feed in feeds:
        try:
            raw = _get(feed["url"]).text
        except Exception as e:  # noqa: BLE001
            log.warning("rss %s failed: %s", feed["name"], e)
            continue
        parsed = feedparser.parse(raw)
        for e in parsed.entries:
            dt = _parse_date(e)
            if not dt or not _fresh(dt, now):
                continue
            out.append(Candidate(
                url=e.get("link", ""), title=e.get("title", "").strip(),
                source=f"rss:{feed['name']}", published_at=dt,
                summary=(e.get("summary", "") or "")[:500]))
    return out


def from_google_news(queries: list[str], langs: list[str], now: datetime) -> list[Candidate]:
    out: list[Candidate] = []
    for lang in langs:
        for q in queries:
            hl = "vi" if lang == "vi" else "en-US"
            url = "https://news.google.com/rss/search"
            try:
                raw = _get(url, params={"q": q, "hl": hl,
                                        "gl": "VN" if lang == "vi" else "US"}).text
            except Exception as e:  # noqa: BLE001
                log.warning("google news %r/%s failed: %s", q, lang, e)
                continue
            parsed = feedparser.parse(raw)
            for e in parsed.entries:
                dt = _parse_date(e)
                if not dt or not _fresh(dt, now):
                    continue
                title = e.get("title", "").strip()
                publisher = _gnews_publisher(e)
                if publisher:
                    source = f"rss:{publisher}"
                    suffix = f" - {publisher}"
                    if title.endswith(suffix):
                        title = title[: -len(suffix)].rstrip()
                else:
                    source = f"rss:Google News ({q})"
                out.append(Candidate(
                    url=e.get("link", ""), title=title,
                    source=source, published_at=dt,
                    summary=(e.get("summary", "") or "")[:500]))
    return out


def _gnews_publisher(entry) -> str:
    """Google News RSS carries the real publisher in <source>; feedparser maps
    it to entry.source (title = publisher name, href = publisher site)."""
    src = entry.get("source")
    if not src:
        return ""
    if isinstance(src, dict):
        return (src.get("title") or "").strip()
    return (getattr(src, "title", "") or "").strip()


def from_hn(min_points: int, now: datetime) -> list[Candidate]:
    data = _get("http://hn.algolia.com/api/v1/search_by_date",
                params={"tags": "story", "query": "AI",
                        "numericFilters": f"points>={min_points}"}).json()
    out = []
    for h in data.get("hits", []):
        if not h.get("url") or (h.get("points") or 0) < min_points:
            continue
        dt = datetime.fromisoformat(h["created_at"].replace("Z", "+00:00"))
        if not _fresh(dt, now):
            continue
        out.append(Candidate(url=h["url"], title=h["title"].strip(), source="hn",
                             published_at=dt, raw_score_hint=float(h["points"]),
                             summary=h["title"]))
    return out


def from_reddit(subs: list[str], min_ups: int, now: datetime) -> list[Candidate]:
    out = []
    for sub in subs:
        try:
            data = _get(f"https://www.reddit.com/r/{sub}/top.json",
                        params={"t": "day", "limit": 25}).json()
        except Exception as e:  # noqa: BLE001
            log.warning("reddit r/%s failed: %s", sub, e)
            continue
        for child in data.get("data", {}).get("children", []):
            d = child["data"]
            if (d.get("ups") or 0) < min_ups or not d.get("url"):
                continue
            dt = datetime.fromtimestamp(d["created_utc"], tz=timezone.utc)
            if not _fresh(dt, now):
                continue
            out.append(Candidate(url=d["url"], title=d["title"].strip(),
                                 source=f"reddit:{sub}", published_at=dt,
                                 raw_score_hint=float(d["ups"]),
                                 summary=(d.get("selftext") or d["title"])[:500]))
    return out


def from_facebook(pages: list[dict], rsshub_base: str, now: datetime) -> list[Candidate]:
    out = []
    for pg in pages:
        url = f"{rsshub_base.rstrip('/')}/facebook/page/{pg['id']}"
        try:
            raw = _get(url).text
        except Exception as e:  # noqa: BLE001
            log.warning("facebook page %s via rss-bridge failed: %s", pg.get("name"), e)
            continue
        parsed = feedparser.parse(raw)
        for e in parsed.entries:
            dt = _parse_date(e) or now
            if not _fresh(dt, now):
                continue
            out.append(Candidate(url=e.get("link", ""), title=e.get("title", "").strip()[:200],
                                 source=f"facebook:{pg.get('name', pg['id'])}",
                                 published_at=dt, summary=(e.get("summary", "") or "")[:500]))
    return out


def from_manual(path: Path) -> list[Candidate]:
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        text, image = _extract(line)
        out.append(Candidate(url=line, title=(text[:80] or "Bài Facebook"), source="manual",
                             published_at=datetime.now(timezone.utc),
                             summary=text[:500], full_text=text, top_image=image))
    return out


def collect(sources: dict, settings: dict, seen: State, now: datetime,
            fulltext_top: int = 5) -> list[Candidate]:
    raised = False
    merged: list[Candidate] = []
    jobs = [
        lambda: from_rss(sources.get("rss", []), now),
        lambda: from_google_news(
            sources.get("google_news", {}).get("queries", []),
            sources.get("google_news", {}).get("langs", []), now),
        lambda: from_hn(sources.get("hn_min_points", 50), now),
        lambda: from_reddit(sources.get("subreddits", []),
                            sources.get("reddit_min_ups", 100), now),
        lambda: from_facebook(sources.get("facebook_pages", []),
                              settings.get("rsshub_base", "https://rsshub.app"), now),
        lambda: from_manual(Path("config/facebook_urls.txt")),
    ]
    for job in jobs:
        try:
            merged.extend(job())
        except Exception as e:  # noqa: BLE001
            raised = True
            log.warning("source job failed: %s", e)

    dedup: dict[str, Candidate] = {}
    for c in merged:
        if not c.url or seen.seen_has(c.url_hash):
            continue
        dedup.setdefault(c.url_hash, c)
    collapsed = _collapse_similar(list(dedup.values()))
    result = sorted(collapsed, key=lambda c: c.published_at, reverse=True)

    if not result and raised:
        raise CollectError("all collect sources failed and produced nothing")

    for c in result[:fulltext_top]:
        if c.full_text:
            continue
        try:
            c.full_text, img = _extract(c.url)
            c.top_image = c.top_image or img
        except Exception as e:  # noqa: BLE001
            log.warning("extract %s failed: %s", c.url, e)
        time.sleep(0.5)
    return result
