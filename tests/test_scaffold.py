import subprocess, sys
from pathlib import Path
import yaml

def test_package_imports():
    import pipeline
    assert isinstance(pipeline.__version__, str)

def test_config_files_present_and_valid():
    root = Path(__file__).resolve().parents[1]
    settings = yaml.safe_load((root / "config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["approval_mode"] in {"telegram", "auto"}
    assert settings["min_score"] == 45
    assert "rsshub_base" in settings
    sources = yaml.safe_load((root / "config/sources.yaml").read_text(encoding="utf-8"))
    assert isinstance(sources["rss"], list) and sources["rss"]
    assert isinstance(sources["subreddits"], list)
    voice = yaml.safe_load((root / "config/voice.yaml").read_text(encoding="utf-8"))
    assert "xung_ho" in voice and "cam_ky" in voice

def test_requirements_pinned():
    root = Path(__file__).resolve().parents[1]
    lines = [l for l in (root / "requirements.txt").read_text().splitlines() if l and not l.startswith("#")]
    assert all("==" in l for l in lines), "every dependency must be pinned"

def test_article_content_roundtrip():
    from pipeline.models import ArticleContent
    a = ArticleContent(format="deep", caption_fb="x", caption_ig="y", hashtags=["#AI"],
                       cover_title="TIÊU ĐỀ",
                       slides=[{"headline": "a", "sub": "x"}, {"headline": "b", "sub": "y"}],
                       sources=[{"name": "hn", "url": "http://h"}])
    b = ArticleContent.from_dict({**a.to_dict(), "junk": 1})
    assert b == a
    assert b.risk is False
