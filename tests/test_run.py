import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline import run
from pipeline.models import Candidate

NOW = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def project(tmp_path):
    root = tmp_path
    (root / "config").mkdir()
    (root / "config/settings.yaml").write_text(
        "approval_mode: telegram\nmin_score: 45\nposts_per_day: 1\n"
        "rsshub_base: http://rss\npending_ttl_hours: 12\n", encoding="utf-8")
    (root / "config/sources.yaml").write_text(
        "rss: []\nsubreddits: []\nhn_min_points: 50\nreddit_min_ups: 100\n"
        "facebook_pages: []\nkeywords: [AI, OpenAI, mô hình]\n", encoding="utf-8")
    (root / "config/voice.yaml").write_text(
        "xung_ho: {nguoi_noi: mình, nguoi_nghe: bạn}\ngiong: thân thiện\n"
        "cam_ky: [không giật tít sai]\nten_kenh: A Hít Official\n"
        "mo_bai_mau: [Có tin hay nè]\ncta_mau: [Bạn nghĩ sao]\n", encoding="utf-8")
    return root


def _fake_candidate():
    return Candidate(url="https://openai.com/blog/new-model",
                     title="OpenAI ra mô hình AI mới cực mạnh",
                     source="rss:OpenAI Blog", published_at=NOW, raw_score_hint=900,
                     summary="OpenAI ra mô hình AI mới",
                     full_text="Chi tiết mô hình AI mới của OpenAI.")


LLM_JSON = json.dumps({
    "angle": "tin-tuc", "caption_fb": "Bài dài về AI.", "caption_ig": "ngắn",
    "hashtags": ["#AI", "#OpenAI", "#congnghe"], "thumbnail_prompt": "neural core",
    "thumbnail_title": "OPENAI RA MODEL MỚI", "youtube_title": "YT", "youtube_desc": "D",
    "tiktok_caption": "TT"}, ensure_ascii=False)


def _touch(p: Path) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return str(p)


def test_build_dry_run_produces_output(project, monkeypatch):
    monkeypatch.setattr(run.collect, "collect", lambda *a, **k: [_fake_candidate()])
    monkeypatch.setattr(run.media, "build_media",
                        lambda cand, post, outdir, channel: (
                            [_touch(Path(outdir) / "img/01_thumbnail.jpg")], True))
    pending = run.build(project, NOW, dry_run=True, local=False,
                        generate=lambda s, u, **k: LLM_JSON)
    assert pending["id"].startswith("2026-09-03-")
    out_dir = project / "output" / "2026-09-03" / pending["id"]
    assert (out_dir / "caption_fb.txt").exists()
    assert (out_dir / "meta.json").exists()


def test_build_no_story_returns_none(project, monkeypatch):
    monkeypatch.setattr(run.collect, "collect", lambda *a, **k: [])
    sent = []
    monkeypatch.setattr(run, "_notify", lambda msg: sent.append(msg))
    assert run.build(project, NOW, dry_run=False, local=False) is None
    assert sent and "không có tin" in sent[0].lower()


def test_make_id_slugifies():
    c = _fake_candidate()
    assert run.make_id(c, NOW) == "2026-09-03-openai-ra-mo-hinh-ai-moi-cuc-manh"[:53]
