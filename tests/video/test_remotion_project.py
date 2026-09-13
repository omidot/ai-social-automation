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

def test_two_segment_background():
    """Two background videos in sequence (bg1 0-30s, bg2 30s+), replacing the
    single-fixed-background design from Task 2 (p2b)."""
    assert (VIDEO / "public/bg1.mp4").is_file(), \
        "video/public/bg1.mp4 must be committed (first background segment)"
    assert (VIDEO / "public/bg2.mp4").is_file(), \
        "video/public/bg2.mp4 must be committed (second background segment)"
    assert not (VIDEO / "public/bg.mp4").exists(), \
        "stale single-background bg.mp4 should be removed"
    src = (VIDEO / "src/BgVideo.tsx").read_text(encoding="utf-8")
    assert "'bg1.mp4'" in src and "'bg2.mp4'" in src, \
        "BgVideo.BG must reference both bg1.mp4 and bg2.mp4"
    for old in ("bg-topo.mp4", "bg-navy.mp4", "bg-purple.mp4", "bg-red.mp4", "bg-grid.mp4"):
        assert old not in src, f"stale per-chapter pool reference left in BgVideo.tsx: {old}"

def test_align_mjs_threads_chart_and_screenshot_file():
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "c.chart = ch" in src
    assert "c.screenshotFile = sf" in src

@pytest.mark.needs_node
def test_align_mjs_syntax_ok():
    r = subprocess.run(["node", "--check", "tools/align.mjs"], cwd=VIDEO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

def test_palette_has_accent_color():
    src = (VIDEO / "src/palette.ts").read_text(encoding="utf-8")
    assert src.count("#FF4D2E") == 2  # once in LIGHT, once in DARK
    assert "accent: string;" in src

def test_layouts_export_frame():
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "export const Frame" in src

def test_layouts_stack_accent_uses_brand_color():
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "role === 'accent' ? pal.accent" in src

def test_layouts_numeral_badge_uses_accent_border():
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "border: `4px solid ${pal.accent}`" in src

def test_chart_tsx_exists_and_exports_chartcard():
    assert (VIDEO / "src/Chart.tsx").is_file()
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "export const ChartCard" in src
    assert "'line'" in src and "'bar'" in src and "'hbar'" in src

def test_kineticshort_renders_chart_before_variant_switch():
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "ChartCard" in src
    assert "card.chart" in src

def test_screenshot_tsx_exists_and_exports_screenshotcard():
    assert (VIDEO / "src/Screenshot.tsx").is_file()
    src = (VIDEO / "src/Screenshot.tsx").read_text(encoding="utf-8")
    assert "export const ScreenshotCard" in src
    assert "staticFile" in src

def test_kineticshort_renders_screenshot_before_variant_switch():
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "ScreenshotCard" in src
    assert "card.screenshotFile" in src
