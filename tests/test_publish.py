from pathlib import Path
import pytest
from pipeline import publish


def _pending(imgs):
    return {"id": "2026-09-03-x", "angle": "tin-tuc",
            "caption_fb": "FB caption\n\nNguồn: X — https://x/y",
            "caption_ig": "IG caption", "hashtags": ["#AI", "#OpenAI"],
            "images": imgs,
            "youtube": {"title": "YT title", "desc": "YT desc"},
            "tiktok": {"caption": "TT caption"},
            "source": {"url": "https://x/y", "name": "X"}, "low_media": False}


class FakeMeta:
    def __init__(self, fail=None):
        self.fail = fail or set()

    def fb_upload_photo(self, p):
        if "fb" in self.fail:
            raise RuntimeError("fb upload down")
        return "fbid-" + Path(p).stem

    def fb_create_post(self, msg, ids):
        if "fb" in self.fail:
            raise RuntimeError("fb post down")
        return {"id": "100_200", "url": "https://facebook.com/100_200"}

    def ig_upload_temp(self, p):
        return "https://tmpfiles.org/dl/1/" + Path(p).name

    def ig_create_item(self, url):
        if "ig" in self.fail:
            raise RuntimeError("ig item down")
        return "c-" + url[-5:]

    def ig_create_carousel(self, ids, cap):
        return "caro"

    def ig_publish(self, cid):
        return {"id": "ig-media-1"}


def test_publish_happy_path(tmp_path):
    imgs = []
    for i in range(3):
        p = tmp_path / f"{i}.jpg"
        p.write_bytes(b"x")
        imgs.append(str(p))
    rec = publish.publish(_pending(imgs), FakeMeta(), tmp_path)
    assert rec["facebook"]["ok"] and rec["facebook"]["url"].endswith("100_200")
    assert rec["instagram"]["ok"] and rec["instagram"]["media_id"] == "ig-media-1"
    yt = (tmp_path / "youtube.txt").read_text(encoding="utf-8")
    assert "YT title" in yt and "YT desc" in yt
    assert (tmp_path / "tiktok.txt").read_text(encoding="utf-8").strip().startswith("TT caption")


def test_publish_ig_fails_fb_ok(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"x")
    rec = publish.publish(_pending([str(p)]), FakeMeta(fail={"ig"}), tmp_path)
    assert rec["facebook"]["ok"] is True
    assert rec["instagram"]["ok"] is False and "ig item down" in rec["instagram"]["error"]


def test_publish_both_fail_raises(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"x")
    with pytest.raises(publish.PublishError):
        publish.publish(_pending([str(p)]), FakeMeta(fail={"fb", "ig"}), tmp_path)
