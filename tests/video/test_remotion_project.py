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

def test_static_background_no_video():
    """Background is a flat static backdrop (matches the ainius.net-style
    reference), not moving video footage -- replaces the two-segment
    bg1/bg2 video design."""
    for stale in ("public/bg.mp4", "public/bg1.mp4", "public/bg2.mp4"):
        assert not (VIDEO / stale).exists(), f"stale background video should be removed: {stale}"
    src = (VIDEO / "src/BgVideo.tsx").read_text(encoding="utf-8")
    assert "OffthreadVideo" not in src and "staticFile" not in src, \
        "BgVideo must no longer render video footage"
    for old in (".mp4", "bg-topo", "bg-navy", "bg-purple", "bg-red", "bg-grid"):
        assert old not in src, f"stale video-background reference left in BgVideo.tsx: {old}"

def test_align_mjs_threads_chart_and_screenshot_file():
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "c.chart = ch" in src
    assert "c.screenshotFile = sf" in src
    assert "c.screenshotUrl = su" in src

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

def test_align_mjs_emits_per_word_timestamps():
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "words: u.words.map" in src

def test_accent_line_is_measured_in_the_case_it_is_drawn_in():
    """Stack's accent line is uppercased at paint time. Measuring the
    lower-case string and then uppercasing it made the widest lines run off
    the right edge of the 1080px frame."""
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "role === 'accent' ? l.text.toUpperCase() : l.text" in src

def test_chart_tsx_exists_and_exports_chartcard():
    assert (VIDEO / "src/Chart.tsx").is_file()
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "export const ChartCard" in src

def test_chart_is_rows_not_plotted_axes():
    """The reference never plots axes -- it lists rows (label left, value
    right, a rounded bar beneath) that land one at a time as each number is
    spoken. Plotted SVG charts read as tiny and generic on a 1080x1920
    phone frame."""
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "<svg" not in src, "axes-style plotting should be gone"
    assert "borderRadius: 28" in src, "bars are fully rounded rails"
    assert "const Row" in src

def test_frame_chrome_matches_the_reference():
    """Reference chrome: slide counter top-left, brand logo top-right."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const Counter" in src
    assert "<Counter index={cur.index} total={cards.length} />" in src
    assert "<BrandMark card={cur} />" in src

def test_chart_dims_rows_already_passed():
    """Only the row being talked about stays bright; earlier rows sink to
    grey so the eye tracks the number currently being said."""
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "const dim = !active" in src
    assert "#8A8A88" in src

def test_kineticshort_renders_chart_before_variant_switch():
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "ChartCard" in src
    assert "card.chart" in src

def test_screenshot_tsx_exists_and_exports_screenshotcard():
    assert (VIDEO / "src/Screenshot.tsx").is_file()
    src = (VIDEO / "src/Screenshot.tsx").read_text(encoding="utf-8")
    assert "export const ScreenshotCard" in src
    assert "staticFile" in src

def test_screenshot_card_has_no_fake_browser_chrome_or_source_line():
    """The reference lets the captured image stand on its own. A mock
    browser bar, a fake URL field and a printed source line all read as
    cheap, so none of them may come back."""
    src = (VIDEO / "src/Screenshot.tsx").read_text(encoding="utf-8")
    assert "card.screenshotUrl" not in src, "no fake address bar"
    for dot in ("#ff5f57", "#febc2e", "#28c840"):
        assert dot not in src, f"traffic-light browser dot left in Screenshot.tsx: {dot}"

def test_kineticshort_renders_screenshot_before_variant_switch():
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "ScreenshotCard" in src
    assert "card.screenshotFile" in src

def test_legacy_decoration_layers_are_gone():
    """Cutouts (paper-cutout icons), Sfx (sound cues) and Shots (a
    hardcoded screenshot stamped with a source line) all predate the
    reference-matched design. Shots in particular was still printing
    'CLAUDE.COM/PRODUCT/CLAUDE-CODE' over a capture after the source line
    was removed from ScreenshotCard, so the files are deleted outright
    rather than merely unmounted."""
    for gone in ("Cutouts.tsx", "Sfx.tsx", "Shots.tsx"):
        assert not (VIDEO / "src" / gone).exists(), f"{gone} should be deleted"
    for src_name in ("KineticShort.tsx", "layouts.tsx"):
        src = (VIDEO / "src" / src_name).read_text(encoding="utf-8")
        for dead in ("Cutouts", "Sfx", "Shots", "shotPushAt"):
            assert dead not in src, f"{dead} still referenced in {src_name}"

def test_slide_text_is_revealed_word_by_word():
    """Measured regression: with scripted wording on the slides, the text ran
    up to ten seconds ahead of the voice (20.1s showed "USD cho mot tac vu"
    while the narrator was still on "vuot xa 40%"). Slides carry the spoken
    words again, each appearing on its own timestamp."""
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "export const WordFade" in src
    assert src.count("<WordFade line={l} />") == 6
    assert "{l.text}</span>" not in src

def test_no_separate_subtitle_layer():
    """With the spoken words back on the slides, a subtitle would print the
    same text twice on screen."""
    assert not (VIDEO / "src/Subtitle.tsx").exists()
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "Subtitle" not in src

def test_brand_mark_is_large_enough_to_read():
    """A 64px logo tucked in a small white chip was not legible at phone
    size; the reference shows the brand mark far larger."""
    src = (VIDEO / "src/BrandMark.tsx").read_text(encoding="utf-8")
    assert "width: 92, height: 92" in src
