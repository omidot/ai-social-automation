import json
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
