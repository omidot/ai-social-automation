import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from pipeline import collect
from pipeline import collect as _collect_mod
from pipeline.models import Candidate
from pipeline.state import State
from tests.conftest import FIXTURES

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


class FakeResp:
    def __init__(self, text="", data=None, status=200):
        self._text = text
        self._data = data
        self.status_code = status

    @property
    def text(self):
        return self._text

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_from_rss_filters_old_and_builds_candidate(monkeypatch):
    xml = (FIXTURES / "sample_feed.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(text=xml))
    cands = collect.from_rss([{"name": "OpenAI Blog", "url": "http://x/feed"}], NOW)
    assert len(cands) == 1
    c = cands[0]
    assert c.title == "OpenAI ra model mới"
    assert c.source == "rss:OpenAI Blog"
    assert c.url == "https://openai.com/blog/new-model"


def test_from_hn_applies_min_points(monkeypatch):
    data = json.loads((FIXTURES / "sample_hn.json").read_text())
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(data=data))
    cands = collect.from_hn(min_points=50, now=NOW)
    assert [c.title for c in cands] == ["New AI agent framework"]
    assert cands[0].raw_score_hint == 180


def test_from_reddit_applies_min_ups(monkeypatch):
    data = json.loads((FIXTURES / "sample_reddit.json").read_text())
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(data=data))
    cands = collect.from_reddit(["LocalLLaMA"], min_ups=100, now=NOW)
    assert [c.title for c in cands] == ["LLaMA 4 leaked"]
    assert cands[0].source == "reddit:LocalLLaMA"


def test_from_manual_reads_urls(tmp_path, monkeypatch):
    f = tmp_path / "fb.txt"
    f.write_text("# comment\nhttps://facebook.com/post/1\n\nhttps://facebook.com/post/2\n",
                 encoding="utf-8")
    monkeypatch.setattr(collect, "_extract", lambda url: ("full text", "https://img/x.jpg"))
    cands = collect.from_manual(f)
    assert [c.url for c in cands] == ["https://facebook.com/post/1", "https://facebook.com/post/2"]
    assert all(c.source == "manual" for c in cands)


def test_collect_dedupes_and_drops_seen(tmp_path, monkeypatch):
    xml = (FIXTURES / "sample_feed.xml").read_text(encoding="utf-8")
    hn = json.loads((FIXTURES / "sample_hn.json").read_text())

    def fake_get(url, params=None):
        return FakeResp(text=xml) if "feed" in url else FakeResp(data=hn)

    monkeypatch.setattr(collect, "_get", fake_get)
    monkeypatch.setattr(collect, "_extract", lambda url: ("body", "https://img/a.jpg"))
    sources = {"rss": [{"name": "OpenAI Blog", "url": "http://x/feed"}],
               "subreddits": [], "reddit_min_ups": 100, "hn_min_points": 50,
               "facebook_pages": [], "keywords": []}
    st = State(tmp_path)
    first = collect.collect(sources, {"rsshub_base": "http://rss"}, st, NOW)
    assert len(first) == 2
    st.seen_add_many([c.url_hash for c in first])
    second = collect.collect(sources, {"rsshub_base": "http://rss"}, st, NOW)
    assert second == []


_GNEWS_RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>OpenAI ra mắt mô hình mới - VnExpress</title>
<link>https://news.google.com/rss/articles/abc?oc=5</link>
<pubDate>Fri, 05 Sep 2026 06:00:00 GMT</pubDate>
<description>OpenAI công bố...</description></item>
</channel></rss>"""

_GNEWS_RSS_WITH_SOURCE = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>OpenAI ra mắt X - VnExpress</title>
<link>https://news.google.com/rss/articles/xyz?oc=5</link>
<pubDate>Fri, 05 Sep 2026 06:00:00 GMT</pubDate>
<source url="https://vnexpress.net">VnExpress</source>
<description>OpenAI công bố...</description></item>
</channel></rss>"""

def test_from_google_news_parses(monkeypatch):
    class R:
        text = _GNEWS_RSS
        def raise_for_status(self): pass
    monkeypatch.setattr(_collect_mod, "_get", lambda url, params=None: R())
    now = datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)
    cands = _collect_mod.from_google_news(["AI"], ["vi"], now)
    assert len(cands) == 1
    # no <source> element -> falls back to the query-tagged placeholder
    assert cands[0].source == "rss:Google News (AI)"
    assert "OpenAI" in cands[0].title
    assert cands[0].source_count == 1


def test_from_google_news_uses_real_publisher(monkeypatch):
    class R:
        text = _GNEWS_RSS_WITH_SOURCE
        def raise_for_status(self): pass
    monkeypatch.setattr(_collect_mod, "_get", lambda url, params=None: R())
    now = datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)
    cands = _collect_mod.from_google_news(["AI"], ["vi"], now)
    assert len(cands) == 1
    assert cands[0].source == "rss:VnExpress"
    assert cands[0].title == "OpenAI ra mắt X"


def test_collapse_similar_prefers_real_publisher_over_google_news():
    from pipeline.collect import _collapse_similar
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    a = Candidate(url="https://a/x", title="OpenAI launches GPT-6 today",
                  source="rss:Google News (AI)", published_at=now)
    b = Candidate(url="https://b/y", title="OpenAI launches GPT-6 today, sources say",
                  source="rss:VnExpress", published_at=now + timedelta(hours=1))
    out = _collapse_similar([a, b])
    assert len(out) == 1
    assert out[0].source == "rss:VnExpress"


def test_collect_skips_google_news_fulltext(tmp_path, monkeypatch):
    now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    calls: list[str] = []
    monkeypatch.setattr(collect, "_extract",
                        lambda url: (calls.append(url) or ("body text here", None)))
    monkeypatch.setattr(collect, "_collapse_similar", lambda cs: cs)
    monkeypatch.setattr(collect.time, "sleep", lambda *a, **k: None)
    gn = Candidate(url="https://news.google.com/rss/articles/CBMi123abc?oc=5",
                   title="AI story via Google News", source="rss:Google News (AI)",
                   published_at=now - timedelta(hours=1), summary="s")
    normal = Candidate(url="https://example.com/ai-story", title="AI story direct",
                       source="rss:Example", published_at=now - timedelta(hours=2),
                       summary="s")
    monkeypatch.setattr(collect, "from_rss", lambda *a, **k: [gn, normal])
    for name in ("from_google_news", "from_hn", "from_reddit", "from_facebook",
                 "from_manual"):
        monkeypatch.setattr(collect, name, lambda *a, **k: [])
    st = State(tmp_path)
    sources = {"rss": [], "google_news": {}, "subreddits": [], "facebook_pages": []}
    result = collect.collect(sources, {}, st, now)
    assert calls == ["https://example.com/ai-story"]  # google-news URL never extracted
    assert len(result) == 2                            # but it still survives as a candidate


def test_collapse_similar_merges_and_counts():
    from pipeline.collect import _collapse_similar
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    a = Candidate(url="https://a.com/x", title="OpenAI launches GPT-6 today",
                  source="rss:A", published_at=now)
    b = Candidate(url="https://b.com/y", title="OpenAI launches GPT-6 today, sources say",
                  source="rss:B", published_at=now)
    c = Candidate(url="https://c.com/z", title="Nvidia announces new GPU",
                  source="rss:C", published_at=now)
    out = _collapse_similar([a, b, c])
    assert len(out) == 2
    merged = [x for x in out if "OpenAI" in x.title][0]
    assert merged.source_count == 2
    # The representative must remember the OTHER outlet too, by name and
    # URL -- this is what lets the writer pull distinct numbers from more
    # than one source and lets the user see every source that fed a script,
    # not just the one it happened to be filed under.
    assert merged.also_reported_by == [{"name": "B", "url": "https://b.com/y"}]


def test_ensure_multi_source_text_merges_labeled_excerpts(monkeypatch):
    from pipeline.collect import ensure_multi_source_text
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    c = Candidate(url="https://a.com/x", title="OpenAI launches GPT-6", source="rss:A",
                 published_at=now, full_text="Bài gốc nguồn A.",
                 also_reported_by=[{"name": "B", "url": "https://b.com/y"}])

    def fake_extract(url):
        assert url == "https://b.com/y"
        return "Bài gốc nguồn B, có số liệu khác.", None

    monkeypatch.setattr("pipeline.collect._extract", fake_extract)
    ensure_multi_source_text(c)
    assert "[Nguồn 1 — rss:A]" in c.full_text
    assert "Bài gốc nguồn A." in c.full_text
    assert "[Nguồn 2 — B]" in c.full_text
    assert "Bài gốc nguồn B, có số liệu khác." in c.full_text


def test_ensure_multi_source_text_skips_a_failed_extra_source(monkeypatch):
    """One unreachable extra source must not cost the primary article --
    only the working sources are appended."""
    from pipeline.collect import ensure_multi_source_text
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    c = Candidate(url="https://a.com/x", title="t", source="rss:A", published_at=now,
                 full_text="Bài gốc nguồn A.",
                 also_reported_by=[{"name": "B", "url": "https://b.com/y"}])

    def boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr("pipeline.collect._extract", boom)
    ensure_multi_source_text(c)
    assert c.full_text == "Bài gốc nguồn A."


def test_ensure_multi_source_text_noop_without_extra_sources():
    from pipeline.collect import ensure_multi_source_text
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    c = Candidate(url="https://a.com/x", title="t", source="rss:A", published_at=now,
                 full_text="Bài gốc nguồn A.")
    ensure_multi_source_text(c)
    assert c.full_text == "Bài gốc nguồn A."


def _rss_response(entries_xml: str) -> str:
    return (
        "<?xml version='1.0'?><rss version='2.0'><channel>"
        f"{entries_xml}"
        "</channel></rss>"
    )


def test_from_rss_debug_logs_feed_counts(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_DEBUG", "1")
    now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    fresh_pub = "Sat, 05 Sep 2026 10:00:00 GMT"   # 2h old -> kept
    stale_pub = "Mon, 01 Sep 2026 10:00:00 GMT"   # way stale -> dropped
    xml = _rss_response(
        f"<item><title>Fresh item</title><link>https://x/1</link>"
        f"<pubDate>{fresh_pub}</pubDate></item>"
        f"<item><title>Stale item</title><link>https://x/2</link>"
        f"<pubDate>{stale_pub}</pubDate></item>"
    )
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(text=xml))
    with caplog.at_level(logging.INFO, logger="collect"):
        out = collect.from_rss([{"name": "Test Feed", "url": "https://feed"}], now)
    assert len(out) == 1 and out[0].title == "Fresh item"
    text = "\n".join(caplog.messages)
    assert "Test Feed" in text and "parsed=2" in text and "fresh=1" in text


def test_from_rss_debug_silent_by_default(monkeypatch, caplog):
    monkeypatch.delenv("ARTICLE_DEBUG", raising=False)
    now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    xml = _rss_response(
        "<item><title>Fresh item</title><link>https://x/1</link>"
        "<pubDate>Sat, 05 Sep 2026 10:00:00 GMT</pubDate></item>"
    )
    monkeypatch.setattr(collect, "_get", lambda url, params=None: FakeResp(text=xml))
    with caplog.at_level(logging.INFO, logger="collect"):
        collect.from_rss([{"name": "Test Feed", "url": "https://feed"}], now)
    assert not any("parsed=" in m for m in caplog.messages)


def test_ensure_fulltext_populates_full_text(monkeypatch):
    from pipeline.models import Candidate
    c = Candidate(url="https://example.com/a", title="t", source="rss:X",
                 published_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(collect, "_extract", lambda url: ("full article text here", "https://img/x.jpg"))
    collect.ensure_fulltext(c)
    assert c.full_text == "full article text here"
    assert c.top_image == "https://img/x.jpg"


def test_ensure_fulltext_skips_when_already_has_text(monkeypatch):
    from pipeline.models import Candidate
    c = Candidate(url="https://example.com/a", title="t", source="rss:X",
                 published_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
                 full_text="already here")
    called = []
    monkeypatch.setattr(collect, "_extract", lambda url: called.append(url) or ("new", None))
    collect.ensure_fulltext(c)
    assert c.full_text == "already here"
    assert called == []


def test_max_age_hours_is_96():
    assert collect.MAX_AGE_HOURS == 96


def test_fresh_keeps_80h_drops_100h():
    now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    from datetime import timedelta
    assert collect._fresh(now - timedelta(hours=80), now) is True
    assert collect._fresh(now - timedelta(hours=100), now) is False


def test_ensure_fulltext_skips_google_news_interstitial(monkeypatch):
    from pipeline.models import Candidate
    c = Candidate(url="https://news.google.com/rss/articles/xyz", title="t",
                 source="rss:Google News (x)",
                 published_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    called = []
    monkeypatch.setattr(collect, "_extract", lambda url: called.append(url) or ("new", None))
    collect.ensure_fulltext(c)
    assert c.full_text == ""
    assert called == []


def test_related_candidates_finds_shared_proper_nouns_despite_different_titles():
    """The exact incident this exists for: an OpenAI blog post titled
    "Perplexity improving accuracy with Astra" and a TechCrunch piece titled
    "TechCrunch: Astra powers Perplexity's new search mode" are plainly the
    same subject, but their titles score well under _collapse_similar's
    0.72 near-duplicate threshold -- they never cluster, so
    also_reported_by stays empty even though a second real source exists
    in the very same collected pool."""
    from pipeline.collect import related_candidates
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    primary = Candidate(url="https://openai.com/index/perplexity-improving-accuracy-with-astra",
                        title="Perplexity improving accuracy with Astra",
                        source="rss:OpenAI Blog", published_at=now)
    other = Candidate(url="https://techcrunch.com/astra-perplexity",
                      title="TechCrunch: Astra powers Perplexity's new search mode",
                      source="rss:TechCrunch AI", published_at=now)
    unrelated = Candidate(url="https://a.com/nvidia", title="Nvidia reveals Rubin GPU",
                          source="rss:A", published_at=now)
    from difflib import SequenceMatcher
    assert SequenceMatcher(None, primary.title.lower(), other.title.lower()).ratio() < 0.72

    got = related_candidates(primary, [primary, other, unrelated])
    assert got == [other]


def test_related_candidates_returns_empty_without_a_real_match():
    """Best-effort: when nothing else in the pool actually covers the
    subject, this must return nothing rather than grabbing an unrelated
    story just to pad the count."""
    from pipeline.collect import related_candidates
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    primary = Candidate(url="https://a.com/x", title="Perplexity improving accuracy with Astra",
                        source="rss:A", published_at=now)
    unrelated = Candidate(url="https://a.com/y", title="Nvidia reveals Rubin GPU",
                          source="rss:B", published_at=now)
    assert related_candidates(primary, [primary, unrelated]) == []


def test_related_candidates_caps_at_max_n_and_ranks_by_overlap():
    from pipeline.collect import related_candidates
    from pipeline.models import Candidate
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    primary = Candidate(url="https://a.com/x", title="Astra and Perplexity ship GPT-6 update",
                        source="rss:A", published_at=now)
    best = Candidate(url="https://a.com/1", title="GPT-6 Astra Perplexity report",
                     source="rss:B", published_at=now)   # 3 shared tokens
    ok = Candidate(url="https://a.com/2", title="Perplexity earnings today",
                   source="rss:C", published_at=now)     # 1 shared token
    weak1 = Candidate(url="https://a.com/3", title="Nvidia earnings beat estimates",
                      source="rss:D", published_at=now)
    weak2 = Candidate(url="https://a.com/4", title="Meta funding announced", source="rss:E",
                      published_at=now)
    weak3 = Candidate(url="https://a.com/5", title="Samsung partners with retailer",
                      source="rss:F", published_at=now)
    got = related_candidates(primary, [primary, weak1, ok, weak2, best, weak3], max_n=2)
    assert got == [best, ok]
