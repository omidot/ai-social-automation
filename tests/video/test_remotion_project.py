import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"

def test_project_present():
    assert (VIDEO / "package.json").is_file()
    assert (VIDEO / "src/Root.tsx").is_file()
    assert (VIDEO / "tools/align.mjs").is_file()
    assert (VIDEO / "tools/cards.manual.bak").is_file()
    assert (VIDEO / "tools/variants.manual.bak").is_file()

def test_composition_id_is_codexshort():
    assert "CodexShort" in (VIDEO / "src/Root.tsx").read_text(encoding="utf-8")

def test_single_fixed_background():
    """Task 2 (p2b): one fixed background video, per-chapter pool removed."""
    assert (VIDEO / "public/bg.mp4").is_file(), \
        "video/public/bg.mp4 must be committed (single fixed background)"
    src = (VIDEO / "src/BgVideo.tsx").read_text(encoding="utf-8")
    assert "'bg.mp4'" in src, "BgVideo.BG must reference bg.mp4"
    for old in ("bg-topo.mp4", "bg-navy.mp4", "bg-purple.mp4", "bg-red.mp4", "bg-grid.mp4"):
        assert old not in src, f"stale per-chapter pool reference left in BgVideo.tsx: {old}"

@pytest.mark.needs_node
def test_align_mjs_syntax_ok():
    r = subprocess.run(["node", "--check", "tools/align.mjs"], cwd=VIDEO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
