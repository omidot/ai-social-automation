from datetime import datetime, timezone
from pipeline.models import PostContent
from pipeline import review


def _post():
    return PostContent(angle="tin-tuc", caption_fb="Nội dung dài.\n\nNguồn: X — https://x/y",
                       caption_ig="ngắn", hashtags=["#AI", "#OpenAI"],
                       thumbnail_prompt="p", thumbnail_title="T", youtube_title="yt",
                       youtube_desc="desc", tiktok_caption="tt",
                       source_url="https://x/y", source_name="X")


NOW = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)


def test_build_pending_schema():
    p = review.build_pending(_post(), ["a.jpg", "b.jpg", "c.jpg"], "2026-09-03-x", False, NOW)
    assert p["id"] == "2026-09-03-x"
    assert p["created_at"] == "2026-09-03T01:00:00+00:00"
    assert p["images"] == ["a.jpg", "b.jpg", "c.jpg"]
    assert p["youtube"]["title"] == "yt" and p["tiktok"]["caption"] == "tt"
    assert p["source"]["url"] == "https://x/y"
    assert p["low_media"] is False


class FakeTG:
    def __init__(self):
        self.msgs = []
        self.groups = []

    def send_media_group(self, imgs, caption=""):
        self.groups.append((imgs, caption))

    def send_message(self, text, buttons=None):
        self.msgs.append((text, buttons))


def test_send_preview_sends_group_and_buttons():
    tg = FakeTG()
    p = review.build_pending(_post(), ["a.jpg", "b.jpg", "c.jpg"], "pid1", False, NOW)
    review.send_preview(p, tg)
    assert tg.groups and tg.groups[0][0] == ["a.jpg", "b.jpg", "c.jpg"]
    text, buttons = tg.msgs[0]
    assert [b[1] for b in buttons] == ["approve:pid1", "edit:pid1", "reject:pid1"]
    assert "⚠️" not in text


def test_send_preview_low_media_warning():
    tg = FakeTG()
    p = review.build_pending(_post(), ["a.jpg"], "pid2", True, NOW)
    review.send_preview(p, tg)
    assert "⚠️" in tg.msgs[0][0]
