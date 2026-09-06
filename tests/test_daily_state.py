from pipeline.daily_state import DailyState


def test_load_safe_returns_none_on_corrupt(tmp_path):
    ds = DailyState(tmp_path)
    (tmp_path / "daily").mkdir(parents=True, exist_ok=True)
    (tmp_path / "daily" / "2026-09-06.json").write_text("{ not json", encoding="utf-8")
    assert ds.load_safe("2026-09-06") is None
    # a good file next to the corrupt one still loads fine
    ds.put("2026-09-07", "morning", status="draft")
    assert ds.load_safe("2026-09-07")["posts"]["morning"]["status"] == "draft"

def test_put_and_get(tmp_path):
    ds = DailyState(tmp_path)
    ds.put("2026-09-06", "morning", status="draft", format="deep", text_fb="hi")
    slot = ds.get("2026-09-06", "morning")
    assert slot["status"] == "draft" and slot["text_fb"] == "hi"
    ds.put("2026-09-06", "morning", fb_post_id="123")
    assert ds.get("2026-09-06", "morning")["fb_post_id"] == "123"
    assert ds.get("2026-09-06", "evening") is None

def test_one_way_status(tmp_path):
    ds = DailyState(tmp_path)
    ds.put("2026-09-06", "morning", status="draft")
    assert ds.set_status("2026-09-06", "morning", "scheduled") is True
    assert ds.set_status("2026-09-06", "morning", "posted") is True
    assert ds.set_status("2026-09-06", "morning", "discarded") is False
    assert ds.get("2026-09-06", "morning")["status"] == "posted"
