from pipeline.daily_state import DailyState

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
