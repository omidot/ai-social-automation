from datetime import datetime, timezone
from pathlib import Path
from pipeline.models import Candidate, PostContent
from pipeline.state import State

def _cand():
    return Candidate(url="https://x.com/a?b=1", title="T", source="rss:x",
                     published_at=datetime(2026,9,3,tzinfo=timezone.utc),
                     raw_score_hint=10.0, summary="s", full_text="", top_image=None)

def test_candidate_roundtrip_and_hash():
    c = _cand()
    assert c.url_hash == Candidate.from_dict(c.to_dict()).url_hash
    # trailing slash / scheme differences normalise to same hash
    c2 = Candidate.from_dict({**c.to_dict(), "url": "http://x.com/a?b=1/"})
    assert c2.url_hash == c.url_hash

def test_postcontent_roundtrip():
    p = PostContent(angle="tin-tuc", caption_fb="a", caption_ig="b", hashtags=["#AI"],
                    thumbnail_prompt="p", thumbnail_title="t", youtube_title="y",
                    youtube_desc="d", tiktok_caption="tk", source_url="u", source_name="n")
    assert PostContent.from_dict(p.to_dict()) == p

def test_seen_add_and_check(tmp_path):
    s = State(tmp_path)
    assert not s.seen_has("h1")
    s.seen_add_many(["h1", "h2"])
    assert s.seen_has("h1") and s.seen_has("h2")
    s2 = State(tmp_path)  # reload from disk
    assert s2.seen_has("h2")

def test_pending_lifecycle(tmp_path):
    s = State(tmp_path)
    p = s.pending_add({"id": "p1", "created_at": "2026-09-03T00:00:00Z"})
    assert p.exists()
    assert [r["id"] for r in s.pending_list()] == ["p1"]
    s.pending_remove("p1")
    assert s.pending_list() == []

def test_offset(tmp_path):
    s = State(tmp_path)
    assert s.offset_load() == 0
    s.offset_save(42)
    assert State(tmp_path).offset_load() == 42
