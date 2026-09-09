from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.video import draft_script
from pipeline.daily_state import DailyState


class FakeTG:
    def __init__(self): self.msgs = []
    def send_message(self, text, buttons=None):
        self.msgs.append(text)
        return {"result": {"message_id": 900 + len(self.msgs)}}


def _wire(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "video:\n  enabled: true\n  target_seconds: 40\n  words_min: 110\n"
        "  words_max: 140\n  render_composition: CodexShort\n", encoding="utf-8")
    (tmp_path / "config" / "voice.yaml").write_text(
        "ten_kenh: A Hít\ngiong: vui\nxung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ncam_ky: []\n",
        encoding="utf-8")
    (tmp_path / "video" / "tools").mkdir(parents=True)
    return tmp_path


def _fake_gen_ok(system, user, provider="auto"):
    import json
    cards = [{"lines": [f"Câu {i}", "vài từ nữa cho đủ chữ"], "variant": "stack",
              "anchor": "mid", "motion_in": "rise", "motion_out": "up"} for i in range(12)]
    return json.dumps({
        "sections": [{"label": "MỞ", "card_start": 0}, {"label": "GIỮA", "card_start": 6}],
        "cards": cards,
        "publish": {"title": "AI vừa có một bước nhảy lớn hôm nay",
                    "description": "Mô hình mới ra mắt. Theo dõi kênh nhé.",
                    "hashtags": ["#AI", "#congnghe", "#tudonghoa", "#ainews", "#chatgpt",
                                 "#automation", "#ahitofficial", "#vietnam"],
                    "keywords": ["ai", "tự động hoá", "công nghệ", "mô hình", "chatgpt"],
                    "tiktok_caption": "AI vừa nhảy vọt #AI #congnghe #fyp"},
    }, ensure_ascii=False)


def test_draft_writes_video_record_and_sends_script(tmp_path):
    root = _wire(tmp_path)
    tg = FakeTG()
    now = datetime(2026, 9, 8, 0, 5, tzinfo=timezone.utc)
    v = draft_script.draft("morning", root, title="OpenAI ra mắt mô hình video",
                           source_url="https://openai.com/x", body_text="Bài gốc dài",
                           caption_fb="Caption.", angle="chia sẻ", now=now,
                           generate=_fake_gen_ok, tg=tg)
    assert v["status"] == "awaiting_audio"
    assert v["meta"]["title"].startswith("AI vừa")
    assert v["spoken_text"]
    assert v["script_msg_id"] == 901
    saved = DailyState(root / "data").get_safe("2026-09-08", "morning")
    assert saved["video"]["status"] == "awaiting_audio"
    assert (root / "video" / "tools" / "cards.mjs").exists()
    assert any("Kịch bản video morning" in m for m in tg.msgs)


def test_draft_gen_failure_warns_no_state(tmp_path):
    root = _wire(tmp_path)
    tg = FakeTG()
    def boom(system, user, provider="auto"):
        return '{"cards": [], "sections": []}'          # fails _validate (card count)
    out = draft_script.draft("evening", root, title="x" * 20, source_url="", body_text="b",
                             caption_fb="c", angle="a", now=datetime(2026, 9, 8, tzinfo=timezone.utc),
                             generate=boom, tg=tg)
    assert out == {"status": "error"}
    assert any("Kịch bản video evening lỗi" in m for m in tg.msgs)
    assert DailyState(root / "data").get_safe("2026-09-08", "evening") is None


def test_draft_skipped_when_video_disabled(tmp_path):
    root = _wire(tmp_path)
    (root / "config" / "settings.yaml").write_text(
        "video:\n  enabled: false\n", encoding="utf-8")
    calls = []
    out = draft_script.draft("morning", root, title="t" * 20, source_url="", body_text="b",
                             caption_fb="c", angle="a",
                             now=datetime(2026, 9, 8, tzinfo=timezone.utc),
                             generate=lambda *a, **k: calls.append(1) or "{}", tg=FakeTG())
    assert out == {"skipped": True}
    assert calls == []
