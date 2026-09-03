import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import collect
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
