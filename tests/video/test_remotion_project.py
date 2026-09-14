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

def test_versus_card_moves_text_clear_of_the_logos():
    """The tiles occupy the upper half, so the card's own text is anchored
    low on those cards instead of overlapping them."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "anchor: 'low' as const, num: undefined" in src
    assert "<VersusMark card={cur} ff={fontFamily} />" in src

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

def test_narration_variants_show_only_the_active_line():
    """Regression: up to 3 lines of a card used to stack on screen at once
    (~15-20 words), which the reference never does -- it shows one short
    caption at a time. After cards are re-cut from real speech, even the
    rare hero/invert emphasis cards can end up with several lines, so all
    seven variants render only the line whose real timestamp is currently
    active, hiding the rest."""
    src = (VIDEO / "src/layouts.tsx").read_text(encoding="utf-8")
    assert src.count("if (i !== activeIdx) return null;") == 7

def test_narration_cards_anchor_to_the_bottom_like_a_caption():
    """The reference's spoken caption always sits near the bottom of the
    frame, never mid-screen. Hero/invert stay wherever variants.py put them
    (rare hook/closer moments); every other card is forced to anchor 'low'."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "isEmphasis ? card : { ...card, anchor: 'low' as const }" in src

def test_screenshot_is_full_bleed_not_a_floating_card():
    """The reference lets a real screenshot fill the whole vertical frame
    with a dark top/bottom vignette for legibility, not a rounded card
    floating with a drop shadow in the middle of the background."""
    src = (VIDEO / "src/Screenshot.tsx").read_text(encoding="utf-8")
    assert "borderRadius: 16" not in src
    assert "boxShadow" not in src
    assert "objectFit: 'cover'" in src
    assert "linear-gradient" in src

def test_headline_layer_carries_the_scripted_text():
    """The reference frames have TWO text layers: a big scripted headline
    up top that holds still for seconds (topic of the moment, last line in
    an accent-filled box), and a small spoken caption at the bottom that
    tracks the voice. Dropping the headline left a dead-black middle of
    frame, which the user reported with a screenshot."""
    assert (VIDEO / "src/Headline.tsx").is_file()
    src = (VIDEO / "src/Headline.tsx").read_text(encoding="utf-8")
    assert "export const Headline" in src
    assert "card.headline" in src
    ks = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "<Headline card={cur} ff={fontFamily} at={headStart} />" in ks

def test_headline_holds_still_across_caption_cards():
    """A headline that re-animated on every caption card would flicker
    several times a second. It keys off the first card sharing the same
    source script card, so it animates once and then holds."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "cards.find((c) => c.headlineAt === cur.headlineAt)" in src

def test_align_emits_headline_from_the_script_card():
    src = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "c.headline = CARDS[si]" in src
    assert "c.headlineAt = si" in src

def test_headline_layer_fills_the_frame_on_every_card():
    """The user's screenshot showed a near-empty black frame: one short
    caption at the bottom and nothing else. The reference always carries a
    big static headline (the SCRIPT's wording, not the running speech) in
    the upper third. It renders on every card except screenshot/versus
    cards, which already own the whole frame."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "import { Headline }" in src
    assert "const showHead = !cur.screenshotFile && !versusOf(cur);" in src
    assert (VIDEO / "src/Headline.tsx").is_file()

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

def test_chart_cards_still_show_the_spoken_caption():
    """Chart/screenshot cards drew no spoken words at all, so the viewer
    lost the thread whenever a visual was on screen."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const Caption" in src
    assert "hasVisual ? <Caption card={cur} activeIdx={capIdx} /> : null" in src

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
