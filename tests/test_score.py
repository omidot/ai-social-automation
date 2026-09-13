import logging
import math
from datetime import datetime, timedelta, timezone
from pipeline.models import Candidate
from pipeline import score
from pipeline.score import pick_n

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
KW = ["AI", "mô hình", "OpenAI"]


def test_pick_n_debug_logs_component_breakdown(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_DEBUG", "1")
    cand = _c("OpenAI ships GPT-6", hint=0)
    with caplog.at_level(logging.INFO, logger="score"):
        pick_n([cand], 1, min_score=1000, now=datetime(2026, 9, 5, 8, tzinfo=timezone.utc),
              keywords=["AI", "GPT"])
    text = "\n".join(caplog.messages)
    assert "OpenAI ships GPT-6" in text
    assert "recency=" in text and "total=" in text
    assert "below min_score" in text  # min_score=1000 rejects everything


def test_pick_n_debug_silent_by_default(monkeypatch, caplog):
    monkeypatch.delenv("ARTICLE_DEBUG", raising=False)
    cand = _c("OpenAI ships GPT-6", hint=0)
    with caplog.at_level(logging.INFO, logger="score"):
        pick_n([cand], 1, min_score=1000, now=datetime(2026, 9, 5, 8, tzinfo=timezone.utc),
              keywords=["AI", "GPT"])
    assert not any("recency=" in m for m in caplog.messages)


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


def _c(title, hint=0.0, sc=1, url=None):
    return Candidate(url=url or f"https://x/{title[:8]}", title=title, source="rss:X",
                     published_at=datetime(2026, 9, 5, 6, tzinfo=timezone.utc),
                     raw_score_hint=hint, summary=title, source_count=sc)


def test_pick_n_returns_distinct_topics():
    now = datetime(2026, 9, 5, 8, tzinfo=timezone.utc)
    cands = [_c("OpenAI ships GPT-6", hint=800, sc=3),
             _c("OpenAI ships GPT-6 model", hint=200, sc=1),
             _c("Nvidia reveals Rubin GPU", hint=500, sc=2),
             _c("Google DeepMind protein news", hint=120)]
    picked = pick_n(cands, 2, min_score=20, now=now, keywords=["AI", "GPT", "GPU"])
    assert len(picked) == 2
    titles = [c.title for _, c in picked]
    assert "OpenAI ships GPT-6" in titles[0]
    assert "Nvidia" in titles[1]  # 2nd pick skips the near-duplicate OpenAI item


def test_is_ai_relevant_word_boundary():
    kw = ["AI", "trí tuệ nhân tạo"]
    # the real production failure: a non-AI story must not pass the gate
    assert not score.is_ai_relevant(mk("Bác sĩ đỡ đẻ trên máy bay", 1, 0), kw)
    # a genuine AI title passes
    assert score.is_ai_relevant(mk("AI tạo video từ một câu lệnh", 1, 0), kw)
    # bare "AI" must not match inside accented words like "Mai"/"Hải"
    assert not score.is_ai_relevant(
        mk("Nguyễn Văn Hải và Mai mở quán phở mới", 1, 0), kw)
    # a multi-word keyword may match the summary head, not only the title
    assert score.is_ai_relevant(
        mk("Chuyện công nghệ hôm nay", 1, 0,
           summary="Bài viết bàn về trí tuệ nhân tạo trong ngành y."), kw)
    # strict tokens (AI) are title-only: summary mention alone is not enough
    assert not score.is_ai_relevant(
        mk("Tin thời tiết cuối tuần", 1, 0, summary="đoạn này có nhắc tới AI"), kw)


def test_pick_n_skips_non_ai():
    # non-AI story is the freshest (max recency) but must be skipped for the
    # lower-scoring, older AI story.
    non_ai = mk("Bác sĩ đỡ đẻ trên máy bay", 0, 0, url="https://a/plane")
    ai = mk("AI tạo video từ giọng nói", 30, 0, url="https://a/ai")
    picked = pick_n([non_ai, ai], 2, min_score=10, now=NOW,
                    keywords=["AI", "trí tuệ nhân tạo"])
    assert [c.url for _, c in picked] == ["https://a/ai"]


def test_source_tier_recognises_tier1_and_tier2():
    assert score._source_tier(mk("x", 0, 0, src="rss:OpenAI Blog")) == 15.0
    assert score._source_tier(mk("x", 0, 0, src="rss:Google DeepMind")) == 15.0
    assert score._source_tier(mk("x", 0, 0, src="rss:Anthropic News")) == 15.0
    assert score._source_tier(mk("x", 0, 0, src="rss:TechCrunch AI")) == 8.0
    assert score._source_tier(mk("x", 0, 0, src="rss:The Verge AI")) == 8.0
    assert score._source_tier(mk("x", 0, 0, src="reddit:artificial")) == 0.0
    assert score._source_tier(mk("x", 0, 0, src="hn")) == 0.0


def test_single_source_tier1_news_clears_new_gate():
    # the exact failure mode from production: one first-party blog post, one
    # source, 30h old, no reddit/HN signal.
    cand = mk("OpenAI ra tính năng mới cho agent", 30, 0, src="rss:OpenAI Blog")
    sc = score.score_candidate(cand, NOW, [cand], KW)
    assert sc >= 20  # config/settings.yaml articles.min_score after this task


def test_breaking_cross_posted_story_still_outranks_single_source():
    # NOTE: distinct urls are required here — _c's default url derives from
    # title[:8], and these two titles share the prefix "OpenAI s", which would
    # otherwise collide and make _cross_source's `other.url == c.url` guard
    # treat them as the same candidate (masking the bonus this test checks).
    breaking = [
        _c("OpenAI ships GPT-6 today", hint=0, sc=1, url="https://x/breaking1"),
        _c("OpenAI ships GPT-6 model today", hint=0, sc=1, url="https://x/breaking2"),
    ]
    single = _c("OpenAI shares a minor blog update", hint=0, sc=1)
    breaking_scores = [score.score_candidate(c, NOW, breaking + [single], KW)
                       for c in breaking]
    single_score = score.score_candidate(single, NOW, breaking + [single], KW)
    assert min(breaking_scores) > single_score


def test_pick_n_respects_exclude_titles():
    now = datetime(2026, 9, 5, 8, tzinfo=timezone.utc)
    cands = [_c("OpenAI ships GPT-6", hint=800, sc=3),
             _c("Nvidia reveals Rubin GPU", hint=500, sc=2)]
    picked = pick_n(cands, 1, min_score=20, now=now, keywords=["AI", "GPT", "GPU"],
                    exclude_titles=["OpenAI ships GPT-6 today"])
    assert len(picked) == 1
    assert "Nvidia" in picked[0][1].title
