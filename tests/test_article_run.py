import logging
from datetime import datetime, timezone
import pytest
from pipeline import article_run
from pipeline.models import ArticleContent
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.media = []; self.msgs = []
    def send_media_group(self, paths, caption=""): self.media.append(list(paths))
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
        "google_news: {queries: [], langs: []}\nkeywords: [AI, GPT, OpenAI]\n", encoding="utf-8")
    (tmp_path / "config" / "voice.yaml").write_text(
        "xung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ngiong: vui\ncam_ky: []\nten_kenh: A Hít\n",
        encoding="utf-8")
    (tmp_path / "config" / "settings.yaml").write_text(
        "articles:\n  slots: {morning: '11:30', evening: '19:45'}\n  min_score: 10\n"
        "images:\n  size: '1080x1350'\n  raw_base: https://raw/base\n", encoding="utf-8")
    (tmp_path / "config" / "topics.yaml").write_text(
        "seeds: ['5 công cụ AI dựng video']\nthemes: ['dựng video ngắn']\n"
        "formats: ['Top {n} công cụ AI để {viec}']\nrecent_window_days: 45\n", encoding="utf-8")

    monkeypatch.setattr(article_run.topics, "propose_topic",
                        lambda *a, **k: {"topic": "5 công cụ AI dựng video",
                                         "angle": "giúp bạn ra video nhanh hơn"})
    monkeypatch.setattr(article_run.write, "write_topic_post", lambda *a, **k: _art())
    monkeypatch.setattr(article_run.images, "build_images",
                        lambda *a, **k: [str(tmp_path / f"{i:02d}.jpg") for i in range(1, 6)])
    return tmp_path, None


def test_draft_writes_state_and_preview(wired):
    root, _ = wired
    tg = FakeTG()
    now = datetime(2026, 9, 6, 0, 5, tzinfo=timezone.utc)
    slot = article_run.draft("morning", root, now, tg=tg)
    assert slot["status"] == "draft"
    assert slot["format"] == "share"
    ds = DailyState(root / "data")
    saved = ds.get("2026-09-06", "morning")
    assert saved["title"] == "5 công cụ AI dựng video"
    assert saved["sources"] == []
    assert saved["angle"] == "giúp bạn ra video nhanh hơn"
    assert tg.media and tg.msgs
    _, buttons = tg.msgs[-1]
    assert [b[1] for b in buttons] == ["art:2026-09-06:morning:now",
                                       "art:2026-09-06:morning:sched",
                                       "art:2026-09-06:morning:drop"]
    assert "5 công cụ AI dựng video" in tg.msgs[-1][0]


def _preview_art(caption_fb):
    return ArticleContent(format="share", caption_fb=caption_fb, caption_ig="ig",
                          hashtags=["#AI", "#ml"], cover_title="T",
                          slides=[{"role": "hook", "headline": "a", "body": "x"}],
                          sources=[])


def test_send_preview_sends_full_caption_in_one_message():
    tg = FakeTG()
    body = "Câu đầu tiên. " * 40  # ~560 chars, well under the split threshold
    article_run.send_preview(_preview_art(body), ["a.jpg"], "morning",
                             "2026-09-06", tg, "11:30", "Chủ đề mẫu")
    assert len(tg.msgs) == 1
    text, buttons = tg.msgs[0]
    assert body in text                       # nothing truncated
    assert "…" not in text
    assert "💡 Chủ đề mẫu" in text
    assert [b[1] for b in buttons] == ["art:2026-09-06:morning:now",
                                       "art:2026-09-06:morning:sched",
                                       "art:2026-09-06:morning:drop"]


def test_send_preview_splits_when_over_telegram_limit():
    tg = FakeTG()
    body = "x" * 4200  # forces the two-message split
    article_run.send_preview(_preview_art(body), ["a.jpg"], "morning",
                             "2026-09-06", tg, "11:30", "Chủ đề mẫu")
    assert len(tg.msgs) == 2
    assert body in tg.msgs[0][0] and tg.msgs[0][1] is None      # body first, no buttons
    assert "#AI #ml" in tg.msgs[1][0]                           # hashtags carry the buttons
    assert [b[1] for b in tg.msgs[1][1]] == ["art:2026-09-06:morning:now",
                                             "art:2026-09-06:morning:sched",
                                             "art:2026-09-06:morning:drop"]


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
    assert out["status"] == "draft"
    assert "Chủ đề buổi sáng" in seen["recent"]


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
