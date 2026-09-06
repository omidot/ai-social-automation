import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import article_run
from pipeline.models import Candidate, ArticleContent
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.media = []; self.msgs = []
    def send_media_group(self, paths, caption=""): self.media.append(list(paths))
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))


@pytest.fixture
def wired(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text("google_news: {queries: [], langs: []}\nkeywords: [AI]\n", encoding="utf-8")
    (tmp_path / "config" / "voice.yaml").write_text(
        "xung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ngiong: vui\ncam_ky: []\nten_kenh: A Hít\n", encoding="utf-8")
    (tmp_path / "config" / "settings.yaml").write_text(
        "articles:\n  slots: {morning: '11:30', evening: '19:45'}\n  min_score: 10\n"
        "  format_deep_margin: 12\n  roundup_min: 3\n  roundup_max: 5\n"
        "images:\n  style_prompt: x\n  size: '1080x1350'\n  raw_base: https://raw/base\n", encoding="utf-8")
    cand = Candidate(url="https://o/x", title="OpenAI ships GPT-6", source="rss:OpenAI",
                     published_at=datetime(2026, 9, 6, 6, tzinfo=timezone.utc),
                     summary="big", full_text="big news", raw_score_hint=900, source_count=3)
    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [cand])
    art = ArticleContent(format="deep", caption_fb="body\n\nCTA", caption_ig="ig",
                         hashtags=["#AI"], cover_title="GPT-6", cover_brief="core",
                         image_briefs=["a", "b"], sources=[{"name": "OpenAI", "url": "https://o/x"}])
    monkeypatch.setattr(article_run.write, "write_deep", lambda *a, **k: art)
    monkeypatch.setattr(article_run.write, "write_roundup", lambda *a, **k: art)
    monkeypatch.setattr(article_run.images, "build_images",
                        lambda *a, **k: [str(tmp_path / "01_cover.jpg"), str(tmp_path / "02.jpg")])
    return tmp_path, cand


def test_draft_writes_state_and_preview(wired):
    root, _ = wired
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    slot = article_run.draft("morning", root, now, tg=tg)
    assert slot["status"] == "draft"
    assert slot["format"] == "deep"
    ds = DailyState(root / "data")
    assert ds.get("2026-09-06", "morning")["title"] == "OpenAI ships GPT-6"
    assert tg.media and tg.msgs
    _, buttons = tg.msgs[-1]
    assert [b[1] for b in buttons] == ["art:2026-09-06:morning:now",
                                       "art:2026-09-06:morning:sched",
                                       "art:2026-09-06:morning:drop"]


def test_draft_evening_excludes_morning_title(wired, monkeypatch):
    root, cand = wired
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", title="OpenAI ships GPT-6 today")
    seen = {}
    monkeypatch.setattr(article_run.score, "pick_n",
                        lambda *a, **k: seen.setdefault("ex", k.get("exclude_titles")) and [])
    tg = FakeTG()
    now = datetime(2026, 9, 6, 10, 5, tzinfo=timezone.utc)
    out = article_run.draft("evening", root, now, tg=tg)
    assert out["status"] == "none"
    assert "OpenAI ships GPT-6 today" in seen["ex"]


def test_draft_roundup_routing(wired, monkeypatch):
    root, cand = wired
    cand2 = Candidate(url="https://o/y", title="Anthropic ships Claude 5", source="rss:Anthropic",
                      published_at=datetime(2026, 9, 6, 6, tzinfo=timezone.utc),
                      summary="also big", full_text="also big news", raw_score_hint=880, source_count=2)
    # two scores within format_deep_margin (12) of each other -> roundup branch
    monkeypatch.setattr(article_run.score, "pick_n", lambda *a, **k: [(50.0, cand), (48.0, cand2)])
    called = {}
    roundup_art = ArticleContent(format="roundup", caption_fb="body\n\nCTA", caption_ig="ig",
                                 hashtags=["#AI"], cover_title="Round-up", cover_brief="core",
                                 image_briefs=["a", "b"],
                                 sources=[{"name": "OpenAI", "url": "https://o/x"}])

    def fake_roundup(cands, *a, **k):
        called["roundup"] = list(cands)
        return roundup_art

    def fake_deep(*a, **k):
        raise AssertionError("write_deep must not be called on the roundup path")

    monkeypatch.setattr(article_run.write, "write_roundup", fake_roundup)
    monkeypatch.setattr(article_run.write, "write_deep", fake_deep)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    slot = article_run.draft("morning", root, now, tg=tg)
    assert slot["status"] == "draft"
    assert slot["format"] == "roundup"
    assert "roundup" in called and len(called["roundup"]) == 2


def test_main_notifies_on_draft_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(article_run, "draft", boom)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")

    sent = []

    class FakeTelegram:
        def __init__(self, *a, **k):
            pass

        def send_message(self, text, *a, **k):
            sent.append(text)

    monkeypatch.setattr(article_run, "Telegram", FakeTelegram)
    rc = article_run.main(["--slot", "morning", "--root", "."])
    assert rc == 1
    assert sent and "Pipeline lỗi" in sent[-1]


def test_draft_reports_collect_failure(wired, monkeypatch):
    root, _ = wired

    def boom(*a, **k):
        raise article_run.collect.CollectError("all sources down")

    monkeypatch.setattr(article_run.collect, "collect", boom)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg)
    assert out == {"slot": "morning", "status": "error"}
    assert tg.msgs and "Gom tin lỗi hết nguồn" in tg.msgs[-1][0]
    assert "morning" in tg.msgs[-1][0]
