import math
from datetime import datetime, timedelta, timezone
from pipeline.models import Candidate
from pipeline import score

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
KW = ["AI", "mô hình", "OpenAI"]


def mk(title, hours_old, hint, url="https://a.com/x", src="hn", summary=""):
    return Candidate(url=url, title=title, source=src,
                     published_at=NOW - timedelta(hours=hours_old),
                     raw_score_hint=hint, summary=summary or title)


def test_recency_component_decays():
    fresh = score.score_candidate(mk("AI model", 0, 0), NOW, [], KW)
    old = score.score_candidate(mk("AI model", 48, 0), NOW, [], KW)
    assert fresh > old
    assert fresh <= 100 and old >= 0


def test_popularity_is_log_scaled():
    low = score.score_candidate(mk("AI", 0, 50), NOW, [], KW)
    high = score.score_candidate(mk("AI", 0, 5000), NOW, [], KW)
    assert high > low
    assert (high - low) < 30  # log, not linear blow-up


def test_cross_source_bonus():
    a = mk("OpenAI ra GPT-5", 1, 100, url="https://openai.com/gpt5", src="hn")
    b = mk("OpenAI ra GPT-5", 1, 0, url="https://theverge.com/gpt5", src="rss:The Verge AI")
    solo = score.score_candidate(a, NOW, [a], KW)
    paired = score.score_candidate(a, NOW, [a, b], KW)
    assert paired - solo >= 15


def test_keyword_fit():
    on = score.score_candidate(mk("OpenAI ra mô hình AI mới", 1, 0), NOW, [], KW)
    off = score.score_candidate(mk("Chuyện thời tiết hôm nay", 1, 0), NOW, [], KW)
    assert on > off


def test_pick_respects_threshold():
    weak = [mk("Tin nhạt", 47, 0, summary="abc")]
    best, sc = score.pick(weak, min_score=45, now=NOW, keywords=KW)
    assert best is None and sc < 45


def test_pick_returns_top():
    cands = [mk("AI nhạt", 40, 5, url="https://a/1"),
             mk("OpenAI ra mô hình AI cực mạnh", 1, 900, url="https://a/2")]
    best, sc = score.pick(cands, min_score=45, now=NOW, keywords=KW)
    assert best.url == "https://a/2" and sc >= 45
