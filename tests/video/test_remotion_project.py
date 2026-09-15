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
    """Reference chrome: a CHAPTER counter top-left ("03 / 09"), the brand
    logo top-right, and a segmented chapter rail down the left edge. The
    counter deliberately counts chapters, not caption lines -- counting
    lines produced "76 / 132", a number that scrolls past meaninglessly.
    There is no centre title: the reference has nothing at top-centre."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const Counter" in src
    assert "<Counter index={chapIdx} total={chapters.length} />" in src
    assert "const ChapterRail" in src
    assert "<BrandMark card={cur} />" in src
    assert "<Chip" not in src, "no centre label in the reference"

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

def test_versus_card_shows_both_brand_logos():
    """When the narration says two brands "fight" ("GPT-6 Astra dau Claude
    Fable"), words alone undersell it -- the viewer has to see the two
    logos facing off, as the reference does with its model tiles."""
    assert (VIDEO / "src/Versus.tsx").is_file()
    src = (VIDEO / "src/Versus.tsx").read_text(encoding="utf-8")
    assert "export const versusOf" in src
    assert "export const VersusMark" in src
    assert "'dau'" in src, "the Vietnamese 'dau' (versus) must trigger it"
    assert "brandsOf" in src, "both brands come from the shared registry"


def test_numeral_badge_hidden_when_there_is_no_number():
    """Suppressing card.num on a versus card left the badge's empty red
    outline floating beside the logos -- the frame must go with it."""
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert "card.num === undefined || card.num === null ? null : (" in src

def test_stat_block_element_exists():
    """A video of nothing but words is dull. The 'stat' chart kind renders
    the reference's stat blocks -- rounded box, small label left, large
    number right -- for figures that share no common scale, where drawing a
    bar would be meaningless."""
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "const StatRow" in src
    assert "chart.kind === 'stat'" in src

def test_versus_tiles_mark_winner_and_loser():
    """The reference crosses out the beaten models and crowns the winner."""
    src = (VIDEO / "src/Versus.tsx").read_text(encoding="utf-8")
    assert "export const hasWinner" in src
    assert "verdict === 'lose'" in src and "verdict === 'win'" in src
    assert "👑" in src
    assert "grayscale(1)" in src


def test_screenshot_is_full_bleed_not_a_floating_card():
    """The reference lets a real screenshot fill the whole vertical frame
    with a dark top/bottom vignette for legibility, not a rounded card
    floating with a drop shadow in the middle of the background."""
    src = (VIDEO / "src/Screenshot.tsx").read_text(encoding="utf-8")
    assert "borderRadius: 16" not in src
    assert "boxShadow" not in src
    assert "objectFit: 'cover'" in src
    assert "linear-gradient" in src



def test_align_emits_headline_from_the_script_card():
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "c.headline = CARDS[si]" in src
    assert "c.headlineAt = si" in src


def test_visuals_persist_across_the_whole_script_card():
    """Measured: charts attached only to the FIRST re-cut card of a script
    card, so a chart flashed for ~3s and the next dozen cards were bare --
    5% of runtime had any visual. They now attach to every card of the
    group, animating from the group's own start so the build-in does not
    restart on each caption change."""
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "groupStart" in src
    assert "c.visualAt = groupStart.get(si)" in src
    assert "if (ch) c.chart = ch;" in src, "chart must attach to every card of the group"
    for comp in ("src/Chart.tsx", "src/Screenshot.tsx"):
        assert "card.visualAt ?? card.start" in (VIDEO / comp).read_text(encoding="utf-8"), comp


def test_bare_narration_cards_get_a_presence_dot():
    """Cards with no chart/screenshot/versus still left the middle of the
    frame dead black. A breathing glow dot is not a hand-drawn per-topic
    illustration, but it beats an empty frame."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const Presence" in src
    assert "bare ? <Presence /> : null" in src

def test_gauge_and_chip_elements_exist():
    """Two more of the reference's illustration types: a gauge with an
    arrow parked at the score reached ("98.6 / 100"), and name chips for
    when a card lists new products rather than figures."""
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "const Gauge" in src and "const Chips" in src
    assert "chart.kind === 'gauge'" in src and "chart.kind === 'chips'" in src
    assert "borderTop: `26px solid ${accent}`" in src, "gauge needs its arrow"


# ---------- Thiết kế hiện tại: chỉ MỘT lớp chữ, phần còn lại là HÌNH ----------

def test_caption_is_the_only_text_layer():
    """Người dùng yêu cầu dứt khoát: không tiêu đề, chỉ một dòng ngắn chạy
    theo giọng. Trước đây mỗi biến thể tự vẽ chữ ở một chỗ riêng cộng thêm
    lớp tiêu đề, nên chữ nhảy lung tung và chồng lên hình."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const Caption" in src
    assert "<Caption card={cur} activeIdx={capIdx} />" in src
    assert "Headline" not in src, "người dùng đã yêu cầu bỏ tiêu đề"
    # CardView chỉ còn dựng hình
    assert "if (card.chart) return <ChartCard" in src
    assert "if (card.screenshotFile) return <ScreenshotCard" in src
    assert "return null;" in src


def test_caption_highlights_the_word_being_spoken():
    """Bản tham chiếu tô màu nhấn đúng từ đang được đọc -- vừa đẹp vừa là
    bằng chứng nhìn thấy được rằng chữ khớp tiếng."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const on = t >= w.start - 0.02 && t < w.end + 0.06;" in src
    assert "color: on ? pal.accent : pal.ink" in src


def test_caption_only_appears_once_its_first_word_is_spoken():
    """Chống tái phát lỗi 'text đi trước nói sau'."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "interpolate(t - line.start, [0, 0.14], [0, 1]," in src


def test_panel_elements_match_the_reference_shapes():
    """Bản tham chiếu dựng mọi đoạn bằng HỘP BO TRÒN nền mờ: nhãn nhỏ +
    số to, hoặc số thứ tự + tiêu đề + mô tả, hoặc nhãn/giá trị nằm trên
    một thanh chạy hết ngang."""
    assert (VIDEO / "src/Panel.tsx").is_file()
    src = (VIDEO / "src/Panel.tsx").read_text(encoding="utf-8")
    for comp in ("PanelTitle", "StatBox", "StepBox", "BarRow"):
        assert "export const %s" % comp in src, comp
    assert "borderRadius: 22" in src, "hộp bo tròn"
    assert "rgba(255,255,255,0.045)" in src, "nền mờ nhạt"


def test_visuals_hold_on_screen_instead_of_flashing():
    """Đo thật: hình chỉ hiện đúng khoảng câu chứa con số -> loé vài giây
    rồi cả đoạn sau trống (5% thời lượng có hình). Bản tham chiếu để một
    tấm số liệu đứng yên cả chục giây trong khi caption chạy bên dưới."""
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "const HOLD = 14;" in src
    assert "if (c.chart || c.screenshotFile) break;" in src


def test_duplicate_charts_are_suppressed():
    """Kịch bản và autoviz có thể dựng cùng một bảng số, hiện hai lần cách
    nhau vài giây (đo thật: 90.7s và 94.3s cùng là 45/225/900)."""
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "const valueKey" in src
    assert "if (dup) continue;" in src
