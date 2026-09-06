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


def test_common_workflow_boilerplate():
    """Assert common boilerplate elements present in all article workflows."""
    for name in ("article-morning.yml", "article-evening.yml", "article-approve.yml",
                 "article-publish-ig.yml"):
        text = (WF / name).read_text(encoding="utf-8")
        assert "bash scripts/commit_state.sh" in text, f"{name} missing commit_state.sh"
        assert "workflow_dispatch:" in text, f"{name} missing workflow_dispatch"
        assert "concurrency:" in text, f"{name} missing concurrency"
        assert "fetch-depth: 0" in text, f"{name} missing fetch-depth: 0"
        assert "contents: write" in text, f"{name} missing contents: write"
        assert "python-version: '3.12'" in text, f"{name} missing python-version: '3.12'"


def test_workflow_secret_blocks():
    """Assert required secrets are declared in each workflow."""
    morning_text = (WF / "article-morning.yml").read_text(encoding="utf-8")
    evening_text = (WF / "article-evening.yml").read_text(encoding="utf-8")
    approve_text = (WF / "article-approve.yml").read_text(encoding="utf-8")
    ig_text = (WF / "article-publish-ig.yml").read_text(encoding="utf-8")

    # Morning and evening need: CLAUDE_CODE_OAUTH_TOKEN, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    for secret in ("CLAUDE_CODE_OAUTH_TOKEN", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert secret in morning_text, f"article-morning.yml missing {secret}"
        assert secret in evening_text, f"article-evening.yml missing {secret}"

    # Approve and IG need: META_PAGE_ID, META_PAGE_TOKEN, IG_BUSINESS_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    for secret in ("META_PAGE_ID", "META_PAGE_TOKEN", "IG_BUSINESS_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert secret in approve_text, f"article-approve.yml missing {secret}"
        assert secret in ig_text, f"article-publish-ig.yml missing {secret}"
