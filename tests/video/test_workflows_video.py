from pathlib import Path
import yaml

WF = Path(__file__).resolve().parents[2] / ".github/workflows/video-smoke.yml"

def test_workflow_valid_and_targeted():
    data = yaml.safe_load(WF.read_text(encoding="utf-8"))
    assert data["jobs"]
    text = WF.read_text(encoding="utf-8")
    assert "npm ci" in text
    assert "pipeline.video.build_video --fake" in text
    assert "render-smoke" in text
    assert "video/**" in text
