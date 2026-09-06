from pathlib import Path
import yaml

WF = Path(__file__).resolve().parents[1] / ".github/workflows"


def test_all_workflows_valid_yaml():
    for name in ("article-morning.yml", "article-evening.yml", "article-approve.yml",
                 "article-publish-ig.yml", "refresh-token.yml"):
        data = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
        assert True in data or "on" in data
        assert data["jobs"]


def test_old_workflows_removed():
    assert not (WF / "build.yml").exists()
    assert not (WF / "approve.yml").exists()


def test_morning_and_evening_crons_and_module():
    m = (WF / "article-morning.yml").read_text(encoding="utf-8")
    e = (WF / "article-evening.yml").read_text(encoding="utf-8")
    assert "cron: '0 0 * * *'" in m and "--slot morning" in m
    assert "cron: '0 10 * * *'" in e and "--slot evening" in e
    assert "playwright install" in m and "playwright install" in e
    assert "contents: write" in m


def test_approve_and_ig_crons_and_modules():
    a = (WF / "article-approve.yml").read_text(encoding="utf-8")
    g = (WF / "article-publish-ig.yml").read_text(encoding="utf-8")
    assert "python -m pipeline.article_approve" in a
    assert "*/10 * * * *" in a
    assert "playwright install" not in a
    assert "python -m pipeline.article_publish_ig" in g
    assert "0,15,30,45 4,5,12,13 * * *" in g
    assert "playwright install" not in g


def test_refresh_workflow_monthly():
    assert "cron: '0 2 1 * *'" in (WF / "refresh-token.yml").read_text(encoding="utf-8")
