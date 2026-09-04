import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pipeline.video import build_video, VideoScriptError

ROOT = Path(__file__).resolve().parents[2]
FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"
NOW = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)
CFG = {"enabled": True, "target_seconds": 40, "words_min": 110, "words_max": 140,
       "tts_provider": "auto"}

pytestmark = pytest.mark.needs_node  # align.mjs + ffmpeg-static


def _story():
    return build_video._load_story(FX / "story.json")


def test_load_story_roundtrips():
    cand, post = _story()
    assert cand.title.startswith("OpenAI") and post.angle == "phan-tich"


def test_build_fake_writes_all_artefacts(tmp_path, monkeypatch):
    # isolated repo copy: video/ + assets + config + tests fixtures reachable
    repo = tmp_path
    (repo / "video").mkdir()
    for sub in ("tools", "src", "ref", "public", "node_modules"):
        (repo / "video" / sub).mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(ROOT / "video/tools/align.mjs", repo / "video/tools/align.mjs")
    shutil.copytree(ROOT / "video/node_modules/ffmpeg-static",
                    repo / "video/node_modules/ffmpeg-static", dirs_exist_ok=True)

    raw = (FX / "raw_script.json").read_text(encoding="utf-8")
    voice = {"xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "giong": "thân thiện",
             "cam_ky": [], "ten_kenh": "A Hít Official"}
    monkeypatch.setattr(build_video, "_load_voice", lambda root: voice)

    cand, post = _story()
    man = build_video.build(repo, cand, post, NOW, CFG, fake=True,
                            llm=lambda s, u, **k: raw)
    assert (repo / "video/tools/cards.mjs").exists()
    assert (repo / "video/tools/variants.mjs").exists()
    assert (repo / "video/public/voice.mp3").exists()
    assert (repo / "video/src/timeline.json").exists()
    vdir = repo / "output/2026-09-03" / man["id"] / "video"
    assert (vdir / "script.json").exists() and (vdir / "timeline.json").exists()
    assert man["word_count"] >= 95 and man["cards"] == 14
    assert man["tts_backend"] == "fake"


def test_build_disabled_returns_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(build_video, "_load_voice", lambda root: {})
    cand, post = _story()
    man = build_video.build(tmp_path, cand, post, NOW, {"enabled": False}, fake=True)
    assert man.get("skipped")


def test_build_propagates_script_error(tmp_path, monkeypatch):
    monkeypatch.setattr(build_video, "_load_voice", lambda root: {
        "xung_ho": {"nguoi_noi": "mình", "nguoi_nghe": "bạn"}, "cam_ky": [], "ten_kenh": "X"})
    cand, post = _story()
    with pytest.raises(VideoScriptError):
        build_video.build(tmp_path, cand, post, NOW, CFG, fake=True,
                          llm=lambda s, u, **k: '{"cards": [], "sections": []}')
