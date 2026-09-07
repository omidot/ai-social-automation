import logging
from datetime import datetime, timezone
import pytest
from pipeline import article_run
from pipeline.models import ArticleContent
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.media = []; self.msgs = []; self.captions = []
    def send_media_group(self, paths, caption=""):
        self.media.append(list(paths)); self.captions.append(caption)
    def send_message(self, text, buttons=None): self.msgs.append((text, buttons))


def _art(cover="One topic"):
    roles = ["hook", "what", "why", "how", "close"]
    return ArticleContent(format="share", caption_fb="body\n\nCTA", caption_ig="ig",
                          hashtags=["#AI"], cover_title=cover,
                          slides=[{"role": r, "headline": f"h{r}", "body": f"b{r}"}
                                  for r in roles],
                          sources=[])


@pytest.fixture
def wired(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text(
        "rss: []\ngoogle_news: {queries: [], langs: []}\nkeywords: [AI, GPT, OpenAI]\n",
        encoding="utf-8")
    (tmp_path / "config" / "voice.yaml").write_text(
        "xung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ngiong: vui\ncam_ky: []\nten_kenh: A Hít\n",
        encoding="utf-8")
    (tmp_path / "config" / "settings.yaml").write_text(
        "articles:\n  slots: {morning: '11:30', evening: '19:45'}\n  min_score: 10\n"
        "images:\n  size: '1080x1350'\n  raw_base: https://raw/base\n", encoding="utf-8")
    (tmp_path / "config" / "topics.yaml").write_text(
        "seeds: ['5 công cụ AI dựng video']\nthemes: ['dựng video ngắn']\n"
        "formats: ['Top {n} công cụ AI để {viec}']\nrecent_window_days: 45\n", encoding="utf-8")

    # by default no news candidates -> every test flows through the topic bank
    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [])
    monkeypatch.setattr(article_run.topics, "propose_topic",
                        lambda *a, **k: {"topic": "5 công cụ AI dựng video",
                                         "angle": "giúp bạn ra video nhanh hơn"})
    monkeypatch.setattr(article_run.write, "write_topic_post", lambda *a, **k: _art())
    monkeypatch.setattr(article_run.images, "build_images",
                        lambda *a, **k: [str(tmp_path / f"{i:02d}.jpg") for i in range(1, 6)])
    # keep the flow tests off the live Graph API: stub both the lazy Meta
    # builder and schedule_slot so draft()'s `meta or _meta()` never calls
    # Meta.from_env() (which would KeyError without META_* env vars).
    monkeypatch.setattr(article_run, "_meta", lambda: object())
    monkeypatch.setattr(article_run.publish, "schedule_slot",
                        lambda ds, meta, root, date, slot, now, tg:
                            (ds.set_status(date, slot, "scheduled"),
                             f"scheduled:{date}:{slot}")[1])
    return tmp_path, None


def test_draft_writes_state_and_schedules(wired):
    root, _ = wired
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    slot = article_run.draft("morning", root, now, tg=tg, meta=object())
    assert slot["status"] == "scheduled"
    assert slot["format"] == "share"
    ds = DailyState(root / "data")
    saved = ds.get("2026-09-06", "morning")
    assert saved["title"] == "5 công cụ AI dựng video"
    assert saved["sources"] == []
    assert saved["angle"] == "giúp bạn ra video nhanh hơn"
    # media still previewed to Telegram before scheduling
    assert tg.media


def test_draft_excludes_recent_and_other_slot(wired, monkeypatch):
    root, _ = wired
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", title="Chủ đề buổi sáng")
    seen = {}

    def fake_propose(topics_cfg, recent, voice, generate):
        seen["recent"] = list(recent)
        return {"topic": "Chủ đề buổi tối", "angle": "abc"}

    monkeypatch.setattr(article_run.topics, "propose_topic", fake_propose)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 10, 5, tzinfo=timezone.utc)
    out = article_run.draft("evening", root, now, tg=tg)
    assert out["status"] == "scheduled"
    assert "Chủ đề buổi sáng" in seen["recent"]


def _news_cand(title="OpenAI ships Sora 2 video model", url="https://openai.com/blog/sora-2"):
    from pipeline.models import Candidate
    return Candidate(url=url, title=title, source="rss:OpenAI Blog",
                     published_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
                     summary="s", full_text="x" * 800)


def test_draft_prefers_news_candidate(wired, monkeypatch):
    root, _ = wired
    cand = _news_cand()
    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [cand])
    seen = {}

    def fake_write_share(c, voice, generate=None):
        seen["cand"] = c
        return _art(c.title)

    monkeypatch.setattr(article_run.write, "write_share", fake_write_share)
    monkeypatch.setattr(article_run.topics, "propose_topic",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("topic bank must not run")))
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg)
    assert out["status"] == "scheduled"
    saved = DailyState(root / "data").get("2026-09-06", "morning")
    assert saved["title"] == cand.title
    assert saved["sources"] and saved["sources"][0]["url"] == cand.url
    assert seen["cand"].url == cand.url
    assert any("📰" in c for c in tg.captions)   # news marker


def test_draft_falls_back_to_topic_bank(wired, monkeypatch):
    root, _ = wired
    monkeypatch.setattr(article_run.collect, "collect", lambda *a, **k: [_news_cand()])

    def always_fail(*a, **k):
        raise article_run.write.WriteError("model returned junk")

    monkeypatch.setattr(article_run.write, "write_share", always_fail)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg)
    assert out["status"] == "scheduled"
    saved = DailyState(root / "data").get("2026-09-06", "morning")
    assert saved["title"] == "5 công cụ AI dựng video"
    assert saved["sources"] == []
    assert any("💡" in c for c in tg.captions)   # topic-bank marker


def test_draft_falls_back_when_collect_fails(wired, monkeypatch):
    root, _ = wired

    def boom(*a, **k):
        raise article_run.collect.CollectError("all sources down")

    monkeypatch.setattr(article_run.collect, "collect", boom)
    monkeypatch.setattr(article_run.write, "write_share",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("write_share must not run when collect fails")))
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg)  # must NOT raise
    assert out["status"] == "scheduled"
    assert DailyState(root / "data").get("2026-09-06", "morning")["title"] == \
        "5 công cụ AI dựng video"


def test_draft_schedule_failure_marks_draft_and_notifies(wired, monkeypatch):
    root, _ = wired

    def boom(*a, **k):
        raise RuntimeError("(190) token expired")

    monkeypatch.setattr(article_run.publish, "schedule_slot", boom)
    notes = []
    monkeypatch.setattr(article_run, "_notify_failure",
                        lambda slot, e: notes.append((slot, str(e))))
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg, meta=object())
    assert out == {"slot": "morning", "status": "error"}
    assert DailyState(root / "data").get("2026-09-06", "morning")["status"] == "draft"
    assert notes and "token expired" in notes[0][1]


def test_draft_risk_flagged_even_when_schedule_raises(wired, monkeypatch):
    root, _ = wired
    risky = ArticleContent(format="share", caption_fb="body", caption_ig="ig",
                           hashtags=["#AI"], cover_title="X",
                           slides=[{"role": r, "headline": "h", "body": "b"}
                                   for r in ("hook", "item", "close")],
                           sources=[], risk=True)
    monkeypatch.setattr(article_run.write, "write_topic_post", lambda *a, **k: risky)
    monkeypatch.setattr(article_run.publish, "schedule_slot",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("(190) token")))
    monkeypatch.setattr(article_run, "_notify_failure", lambda *a, **k: None)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg, meta=object())
    assert out == {"slot": "morning", "status": "error"}
    # the risk flag must reach Telegram even though scheduling blew up and the
    # slot fell back to "draft" for retry_unscheduled (which sends no risk notice)
    assert any("nhạy cảm" in t for t, _ in tg.msgs)
    assert DailyState(root / "data").get("2026-09-06", "morning")["status"] == "draft"


def test_fake_llm_smoke_passes_noop_meta_not_real(monkeypatch, tmp_path):
    """The --fake-llm offline smoke must never construct a real Meta: main()
    hands draft() a _NoopMeta, so draft()'s `meta or _meta()` never calls _meta."""
    seen = {}

    def fake_draft(slot, root, now, *, generate=None, tg=None, meta=None):
        seen["meta"] = meta
        return {"slot": slot, "status": "dry"}

    monkeypatch.setattr(article_run, "draft", fake_draft)
    monkeypatch.setattr(article_run, "_meta",
                        lambda: (_ for _ in ()).throw(AssertionError("real Meta built")))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    rc = article_run.main(["--slot", "morning", "--root", str(tmp_path), "--fake-llm"])
    assert rc == 0
    assert isinstance(seen["meta"], article_run._NoopMeta)


def test_draft_skips_committed_slot(wired, monkeypatch):
    root, _ = wired
    ds = DailyState(root / "data")
    ds.put("2026-09-06", "morning", status="scheduled", title="already committed")

    def boom(*a, **k):
        raise AssertionError("must not run when the slot is already committed")

    monkeypatch.setattr(article_run.topics, "propose_topic", boom)
    monkeypatch.setattr(article_run.write, "write_topic_post", boom)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg)
    assert out == {"slot": "morning", "status": "skipped"}
    assert tg.msgs and "bỏ qua" in tg.msgs[-1][0]
    assert "scheduled" in tg.msgs[-1][0]
    assert ds.get("2026-09-06", "morning")["status"] == "scheduled"


def test_draft_reports_topic_failure(wired, monkeypatch):
    root, _ = wired

    def boom(*a, **k):
        raise article_run.topics.TopicError("LLM đề xuất hỏng")

    monkeypatch.setattr(article_run.topics, "propose_topic", boom)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg)  # must NOT raise
    assert out == {"slot": "morning", "status": "error"}
    assert tg.msgs and "Không đề xuất được chủ đề" in tg.msgs[-1][0]
    assert "morning" in tg.msgs[-1][0]


def test_draft_reports_write_failure(wired, monkeypatch):
    root, _ = wired

    def boom(*a, **k):
        raise article_run.write.WriteError("chủ đề không viết được: x")

    monkeypatch.setattr(article_run.write, "write_topic_post", boom)
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    out = article_run.draft("morning", root, now, tg=tg)  # must NOT raise
    assert out == {"slot": "morning", "status": "error"}
    assert tg.msgs and "Không viết được bài" in tg.msgs[-1][0]
    assert "5 công cụ AI dựng video" in tg.msgs[-1][0]


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


def test_main_logs_traceback_on_failure(monkeypatch, caplog):
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
    with caplog.at_level(logging.ERROR):
        rc = article_run.main(["--slot", "morning", "--root", "."])
    assert rc == 1
    assert "boom" in caplog.text
    assert "draft(morning) failed" in caplog.text
    assert sent and "RuntimeError" in sent[-1]
