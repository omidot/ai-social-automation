from pathlib import Path
import yaml

WF = Path(__file__).resolve().parents[1] / ".github/workflows"


def test_all_workflows_valid_yaml():
    for name in ("build.yml", "approve.yml", "refresh-token.yml"):
        data = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
        assert True in data or "on" in data  # 'on' key may parse as bool True
        assert data["jobs"]


def test_build_workflow_runs_pipeline_and_commits():
    text = (WF / "build.yml").read_text(encoding="utf-8")
    assert "python -m pipeline.run" in text
    assert "cron: '0 1 * * *'" in text
    assert "contents: write" in text
    assert "playwright install" in text


def test_approve_workflow_cron_and_module():
    text = (WF / "approve.yml").read_text(encoding="utf-8")
    assert "python -m pipeline.approve_poll" in text
    assert "*/10 * * * *" in text


def test_refresh_workflow_monthly():
    text = (WF / "refresh-token.yml").read_text(encoding="utf-8")
    assert "cron: '0 2 1 * *'" in text
