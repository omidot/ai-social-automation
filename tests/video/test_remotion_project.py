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
    assert "<Chip" not in src, "no centre label in the reference"
    # Logo hãng KHÔNG còn nép góc phải trên: người dùng chỉ rõ nó quá nhỏ,
    # không ai thấy. Giờ nhắc tới hãng nào thì logo hãng đó hiện GIỮA KHUNG.
    assert "BrandMark" not in src
    assert "BrandScreen" in src

def test_chart_dims_rows_already_passed():
    """Only the row being talked about stays bright; earlier rows sink to
    grey so the eye tracks the number currently being said."""
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "const dim = !active" in src
    assert "#8A8A88" in src


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



def test_gauge_and_chip_elements_exist():
    """Two more of the reference's illustration types: a gauge with an
    arrow parked at the score reached ("98.6 / 100"), and name chips for
    when a card lists new products rather than figures."""
    src = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "const Gauge" in src and "const Chips" in src
    assert "chart.kind === 'gauge'" in src and "chart.kind === 'chips'" in src
    assert "borderTop: `26px solid ${accent}`" in src, "gauge needs its arrow"


# ---------- Thiết kế hiện tại: chỉ MỘT lớp chữ, phần còn lại là HÌNH ----------


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


# ---------- Kiến trúc hiện tại: mỗi CHƯƠNG một màn hình chiếm khung ----------

def test_every_chapter_gets_a_screen():
    """Điểm sai gốc của các bản trước: nền đen + chữ chạy là mặc định, hình
    chỉ thỉnh thoảng mới chèn, nên phần lớn thời lượng màn hình trống. Video
    mẫu chia bài thành chương và MỖI CHƯƠNG có đúng một màn hình chiếm khung
    đứng yên suốt chương đó."""
    src = (VIDEO / "tools/screens.mjs").read_text(encoding="utf-8")
    assert "export function assignScreens" in src
    for kind in ("'hook'", "'panel'", "'shot'", "'statement'", "'cards'", "'element'"):
        assert kind in src, kind
    # chương mở đầu luôn là hook, không được để bảng biểu chiếm chỗ
    assert "if (ci === 0) {" in src


def test_screens_are_timed_to_when_their_content_is_spoken():
    """Yêu cầu trực tiếp: "nói tới đâu hiện tới đó, không hiện trước".

    Cách cũ gán mỗi chương một màn rồi bật từ đầu chương -- đo thật: bộ thẻ
    liệt kê bật ở giây 12.2 trong khi người đọc nói câu đó ở giây 7. Giờ mỗi
    màn tự khai giờ nó được nói ra và cả bộ được sắp theo giờ."""
    src = (VIDEO / "tools/screens.mjs").read_text(encoding="utf-8")
    assert "export function buildTimeline" in src
    assert "export function findSpokenTime" in src
    # khớp phải liền mạch: bản đầu cho nhảy tuỳ ý nên mọi màn đều trả về giây 0.46
    assert "const SKIP = 3;" in src
    assert "flat[i].n !== want[0]" in src, "phải bắt đầu đúng từ đầu cụm"


def test_numbers_roll_and_land_on_the_spoken_moment():
    """Yêu cầu trực tiếp: số chạy rồi dừng đúng con số, khớp giọng nói.
    Biểu đồ do kịch bản gắn tay không có mốc thời gian, nên giờ đọc của
    từng con số được dò ngược từ chính bản ghi lời nói."""
    src = (VIDEO / "tools/screens.mjs").read_text(encoding="utf-8")
    assert "export function timeChartItems" in src
    panel = (VIDEO / "src/Panel.tsx").read_text(encoding="utf-8")
    assert "const Rolling" in panel
    assert "runFor" in panel, "thời lượng chạy nhận từ ngoài, không đặt cứng"
    chart = (VIDEO / "src/Chart.tsx").read_text(encoding="utf-8")
    assert "const rollFor" in chart and "const spokenAt" in chart


def test_person_screen_cuts_out_and_enters_diagonally():
    """Yêu cầu trực tiếp: nhân vật tách nền, viền trắng, hiện chéo từ góc
    phải, kèm text kiểu người đó đang nói."""
    src = (VIDEO / "src/Screens.tsx").read_text(encoding="utf-8")
    assert "export const PersonScreen" in src
    assert "vào chéo" in src
    port = (ROOT / "src/pipeline/video/portrait.py").read_text(encoding="utf-8")
    assert "def find_person_names" in port
    assert "from rembg import remove" in port
    assert "def _outline" in port, "viền trắng quanh hình đã tách"
    # ảnh người thật -> chỉ lấy từ nguồn có giấy phép rõ ràng, luôn ghi công
    assert "wikipedia_image" in port
    assert "credit" in port


def test_exactly_one_screen_is_drawn_at_a_time():
    """Nguyên nhân THẬT của cái "nhấp nháy miết": màn hình từng được gắn vào
    mỗi thẻ caption, mà nhiều thẻ cùng hiện một lúc -- cùng một màn bị dựng
    chồng nhiều lần với mốc giờ khác nhau nên hiệu ứng chạy lại liên tục.
    Giờ màn hình là một dòng thời gian riêng ở mức gốc của timeline, và chỗ
    dựng hình chọn ra ĐÚNG MỘT cái."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const ScreenView" in src
    assert "screens.filter((x) => t >= (x.at ?? 0)).slice(-1)[0]" in src
    assert "visible.map" not in src, "không được vẽ lại màn theo từng thẻ nữa"
    align = (VIDEO / "tools/align.mjs").read_text(encoding="utf-8")
    assert "screens: SCREENS" in align
    assert "const Caption" in src
    assert "Headline" not in src, "người dùng đã yêu cầu bỏ tiêu đề"


def test_screens_fade_in_and_out():
    """Yêu cầu trực tiếp: hình xuất hiện và biến mất phải có chuyển, không
    bật/tắt phựt."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "const IN = 9, OUT = 11;" in src
    assert "if (fade <= 0) return null;" in src


def test_brands_get_a_centred_screen_when_named():
    """Người dùng chỉ rõ: nhắc "GPT-6 Astra" hay "Claude Fable 5" thì hiện
    đúng logo hai bên ở GIỮA kèm chú thích, không phải một ô bé nép góc."""
    src = (VIDEO / "src/Screens.tsx").read_text(encoding="utf-8")
    assert "export const BrandScreen" in src
    tools = (VIDEO / "tools/screens.mjs").read_text(encoding="utf-8")
    assert "kind: 'brandpair'" in tools and "kind: 'brand'" in tools


def test_source_screenshots_reject_bot_walls():
    """Đo thật trên 4 nguồn của một bài: openai.com dựng Cloudflare
    'Verify you are human', engadget.com trả 403. Không vượt các chặn đó --
    nhưng BẮT BUỘC phải loại ảnh hỏng, vì một khung 'Verify you are human'
    lọt vào video đã xuất bản còn tệ hơn là không có ảnh nào."""
    src = (ROOT / "src/pipeline/video/sourceshot.py").read_text(encoding="utf-8")
    assert "verify you are human" in src
    assert "403 error" in src
    assert "_is_mostly_blank" in src
    # dải cookie bị ẩn bằng CSS, không bấm nút "Đồng ý" thay người dùng
    assert "_HIDE_CSS" in src
    assert "click" not in src.lower().split("_HIDE_CSS")[0].split("def capture")[-1]


def test_list_cards_come_from_real_enumerations_only():
    """Thẻ nhỏ cắt nguyên văn từ câu liệt kê trong lời nói. Chỉ nhận khi các
    vế THỰC SỰ song song (cùng từ mở đầu) -- nếu không thì câu nào có dấu
    phẩy cũng bị xé thành thẻ vô nghĩa."""
    src = (VIDEO / "tools/listcards.mjs").read_text(encoding="utf-8")
    assert "export function listItemsOf" in src
    assert "topCount < 2" in src, "phải có ít nhất hai vế song song"
    assert "MAX_ITEMS" in src


def test_auto_loop_diagram_connects_and_labels_its_nodes():
    """Yêu cầu trực tiếp: sơ đồ tự vận hành phải có ĐƯỜNG KẺ NỐI lõi ra các
    chấm và CHÚ THÍCH từng chấm -- bản trước chỉ có mấy chấm trôi lơ lửng,
    nhìn thì có hình nhưng không hiểu đang nói gì."""
    src = (VIDEO / "src/Elements.tsx").read_text(encoding="utf-8")
    assert "const AutoLoop" in src
    assert "<line x1={CX} y1={CY}" in src, "đường kẻ nối lõi ra chấm"
    assert "chú thích cho từng chấm" in src


def test_portrait_refuses_a_same_name_stranger():
    """Đo thật: bài nhắc "Johnny Ho, đồng sáng lập Perplexity", nhưng trên
    Wikidata "Johnny Ho" là một nhà nghiên cứu và một nghệ sĩ saxophone --
    người khác hoàn toàn. Dán mặt nhầm một người THẬT lên video còn tệ hơn
    hẳn là không có ảnh, nên khi bài có nêu bối cảnh thì bối cảnh đó phải
    xuất hiện trong phần tóm tắt của trang mới được nhận."""
    src = (ROOT / "src/pipeline/video/portrait.py").read_text(encoding="utf-8")
    assert "def _verify" in src
    assert "if hit and not _verify(hit[0], name, extra_terms):" in src


def test_portrait_prefers_a_hand_placed_file():
    """Người không đủ nổi tiếng thì không nguồn tự động nào có ảnh đúng.
    Đường thoát: đặt tay một file vào thư mục portraits, và nó phải được
    ưu tiên trên mọi nguồn tự tìm."""
    src = (ROOT / "src/pipeline/video/portrait.py").read_text(encoding="utf-8")
    assert "def local_portrait" in src
    assert "local = local_portrait(name, out_path.parent)" in src
    # phải đứng TRƯỚC nhánh Wikipedia
    assert src.index("local_portrait(name, out_path.parent)") < src.index("hit = wikipedia_image(name)")


def test_editorial_person_has_several_typographic_looks():
    """Ba ảnh mẫu người dùng gửi mỗi cái một kiểu chữ: khối báo đầy đủ, tít
    khổng lồ tràn mép, và khối đỏ đóng dấu. Dùng chung một khuôn cho mọi màn
    nhân vật thì tới màn thứ hai người xem đã thấy lặp."""
    src = (VIDEO / "src/Editorial.tsx").read_text(encoding="utf-8")
    assert "export type EdVariant" in src
    for v in ("'masthead'", "'bleed'", "'stamp'", "'quote'"):
        assert v in src, v
    # bút dạ vàng, chip ngày đỏ, nền giấy -- các dấu hiệu của phong cách này
    assert "marker:" in src and "PaperBg" in src
    tools = (VIDEO / "tools/screens.mjs").read_text(encoding="utf-8")
    assert "ED_VARIANTS" in tools, "kiểu chữ phải xoay vòng giữa các màn"


def test_person_screens_fire_on_every_mention_of_the_name():
    """Người dùng nói rõ: cứ nhắc "Johnny Ho" là ảnh Johnny Ho phải lên --
    không chỉ lần đầu trong chương. Màn nhân vật giờ bật ở MỌI lần tên được
    nói ra."""
    src = (VIDEO / "tools/screens.mjs").read_text(encoding="utf-8")
    assert "export function findAllSpokenTimes" in src
    assert "const hits = findAllSpokenTimes(cards, pr.name);" in src


def test_caption_moves_aside_on_person_screens():
    """Người chiếm nửa phải khung; caption căn giữa như thường sẽ nằm đè lên
    mặt -- đúng chỗ người dùng chỉ ra trên khung hình."""
    src = (VIDEO / "src/KineticShort.tsx").read_text(encoding="utf-8")
    assert "asideOf" in src
    assert "right: asideOf ? '48%' : 0" in src
    assert "<Caption card={cur} activeIdx={capIdx} asideOf={onPaper} />" in src


def test_brand_plus_stepping_cards_screen_exists():
    """Dạng người dùng mô tả đích danh: "logo OpenAI và chữ tiêu đề dưới là
    card nhỏ từng cái một hiện lên"."""
    src = (VIDEO / "src/Screens.tsx").read_text(encoding="utf-8")
    assert "export const BrandCardsScreen" in src
    assert "const StepIn" in src, "mỗi card vào lệch nhịp, không bật cả cụm"
    tools = (VIDEO / "tools/screens.mjs").read_text(encoding="utf-8")
    assert "kind: 'brandcards'" in tools


def test_bust_crop_removes_the_leftover_block():
    """Ảnh chân dung để nguyên thân dài thì mảng áo phẳng thành một khối đặc
    ở đáy khung, và viền chạy quanh biến nó thành hình chữ nhật thừa -- đúng
    chỗ người dùng chỉ ra. Cắt còn đầu và vai, cạnh dưới để hở."""
    src = (ROOT / "src/pipeline/video/portrait.py").read_text(encoding="utf-8")
    assert "def _bust" in src
    assert "keep: float = 0.86" in src, "0.62 cắt đúng cằm, chỉ còn cái đầu trôi nổi"
    assert "im.height + pad)" in src, "cạnh dưới không chừa lề -> viền chạy ra khỏi mép"
