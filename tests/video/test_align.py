import json, shutil
from pathlib import Path
import pytest
from pipeline.video import align, AlignError

ROOT = Path(__file__).resolve().parents[2]
FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"
VIDEO = ROOT / "video"

pytestmark = pytest.mark.needs_node

@pytest.fixture
def stage(tmp_path):
    """A minimal video/ dir: real align.mjs + node_modules, generated cards/variants."""
    d = tmp_path / "video"
    (d / "tools").mkdir(parents=True)
    (d / "src").mkdir()
    (d / "ref").mkdir()
    shutil.copy(VIDEO / "tools/align.mjs", d / "tools/align.mjs")
    # align.mjs imports autoviz.mjs (biểu đồ dựng từ chính lời nói)
    shutil.copy(VIDEO / "tools/autoviz.mjs", d / "tools/autoviz.mjs")
    # 3 cards so align maps onto the 3 speech bursts of the fixture
    (d / "tools/cards.mjs").write_text(
        'export const CARDS = [["một hai ba"],["bốn năm sáu"],["bảy tám chín"]];\n'
        'export const SECTIONS = [[0,"A"]];\n', encoding="utf-8")
    (d / "tools/variants.mjs").write_text(
        'export const LAYOUT = [["stack","mid",null,"rise","up"],'
        '["stack","top",null,"fall","down"],'
        '["invert","mid",null,"pop","wipeOut"]];\n', encoding="utf-8")
    # symlink/copy node_modules for ffmpeg-static + node builtin only (align.mjs uses node:fs only)
    return d

def test_make_silence_txt_finds_gaps(stage):
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    txt = (stage / "ref/silence.txt").read_text(encoding="utf-8")
    assert "silence_start" in txt and "silence_end" in txt
    assert 4.5 <= dur <= 6.5

def test_run_aligner_builds_timeline(stage):
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    out = align.run_aligner(stage, dur)
    tl = json.loads(out.read_text(encoding="utf-8"))
    assert len(tl["cards"]) == 3
    starts = [c["start"] for c in tl["cards"]]
    assert starts == sorted(starts)
    assert 4.0 <= tl["duration"] <= 7.0

def test_run_aligner_raises_without_cards(stage):
    (stage / "tools/cards.mjs").unlink()
    with pytest.raises(AlignError):
        align.run_aligner(stage, 5.0)

def test_run_aligner_uses_real_words_when_present(stage):
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    words = [
        {"w": "một", "start": 0.10, "end": 0.30}, {"w": "hai", "start": 0.30, "end": 0.50},
        {"w": "ba", "start": 0.50, "end": 0.70},
        {"w": "bốn", "start": 1.00, "end": 1.20}, {"w": "năm", "start": 1.20, "end": 1.40},
        {"w": "sáu", "start": 1.40, "end": 1.60},
        {"w": "bảy", "start": 2.00, "end": 2.20}, {"w": "tám", "start": 2.20, "end": 2.40},
        {"w": "chín", "start": 2.40, "end": 2.60},
    ]
    (stage / "ref/words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    out = align.run_aligner(stage, dur)
    tl = json.loads(out.read_text(encoding="utf-8"))
    # Mốc thật phải được dùng nguyên văn -- không bị đoán lại theo khoảng lặng.
    assert tl["cards"][0]["start"] == pytest.approx(0.10, abs=1e-6)
    # Mỗi TỪ phải có mốc riêng (không chỉ mốc cả dòng) -- đây là điều kiện để
    # chữ hiện ra đúng từng từ, không phải cả câu hiện cùng lúc.
    flat = [w for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert [w["text"] for w in flat] == [w["w"] for w in words]
    assert [w["start"] for w in flat] == [pytest.approx(w["start"], abs=1e-6) for w in words]

def test_run_aligner_falls_back_when_words_dont_match(stage):
    """words.json ASR gibberish that shares nothing with the script -> the
    low match-ratio guard must discard it and use the silence heuristic,
    not silently poison the timeline with meaningless timestamps."""
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    garbage = [{"w": "xyz", "start": 0.0, "end": 0.1}, {"w": "qwe", "start": 0.1, "end": 0.2}]
    (stage / "ref/words.json").write_text(json.dumps(garbage), encoding="utf-8")
    out = align.run_aligner(stage, dur)
    tl = json.loads(out.read_text(encoding="utf-8"))
    assert len(tl["cards"]) == 3
    starts = [c["start"] for c in tl["cards"]]
    assert starts == sorted(starts)


NL = chr(10)
JS_FABLE = ('export const CARDS = [["Fable thắng rồi"]];' + NL
            + 'export const SECTIONS = [[0,"A"]];' + NL)
JS_LAYOUT1 = 'export const LAYOUT = [["stack","mid",null,"rise","up"]];' + NL


def test_slides_carry_the_SCRIPTED_words_timed_to_the_voice(stage):
    """Chữ lấy từ KỊCH BẢN, giờ lấy từ GIỌNG NÓI.

    Hai lần trước đều hỏng ở một trong hai nửa. Hiện chữ kịch bản rồi tự
    đoán giờ -> chữ chạy trước tiếng cả chục giây. Hiện thẳng chữ nhận
    diện được -> đúng giờ nhưng SAI CHÍNH TẢ ngay trên màn hình (máy nghe
    "Perplexity" ra "Proplexity", "GPT-6" ra "GP6").

    Căn chỉnh quy hoạch động ghép từng từ kịch bản vào mốc giờ của từ
    tương ứng trong giọng đọc, nên lấy được cả hai nửa đúng."""
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [
        {"w": "mọt", "start": 0.10, "end": 0.30},       # nghe sai "một"
        {"w": "hai", "start": 0.30, "end": 0.50},
        {"w": "ba", "start": 0.50, "end": 0.70},
        {"w": "bốn", "start": 1.00, "end": 1.20},
        {"w": "lăm", "start": 1.20, "end": 1.40},       # nghe sai "năm"
        {"w": "sáu", "start": 1.40, "end": 1.60},
        {"w": "bảy", "start": 2.00, "end": 2.20},
        {"w": "tám", "start": 2.20, "end": 2.40},
        {"w": "chín", "start": 2.40, "end": 2.60},
    ]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    flat = [w for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    # CHÍNH TẢ của kịch bản thắng: "một"/"năm", không phải "mọt"/"lăm"
    assert [w["text"] for w in flat] == ["một", "hai", "ba", "bốn", "năm", "sáu",
                                         "bảy", "tám", "chín"]
    # GIỜ của giọng đọc thắng: từng từ giữ đúng mốc thật của nó
    assert [w["start"] for w in flat] == [
        pytest.approx(x["start"], abs=1e-6) for x in spoken]


def test_brand_names_are_right_because_the_script_supplies_them(stage):
    """Từng phải có hẳn một lớp dò Levenshtein để sửa tên riêng bị nghe
    nhầm ("Fable" -> "Facebook"), và chính lớp đó đã có lần sửa nhầm chữ
    "Đừng" thành "Fable". Lấy chữ từ kịch bản thì vấn đề biến mất từ gốc,
    nên lớp sửa đã được gỡ -- test này giữ cho nó không quay lại."""
    (stage / "tools/cards.mjs").write_text(JS_FABLE, encoding="utf-8")
    (stage / "tools/variants.mjs").write_text(JS_LAYOUT1, encoding="utf-8")
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [
        {"w": "Facebook", "start": 0.10, "end": 0.40},   # nghe nhầm "Fable"
        {"w": "thắng", "start": 0.40, "end": 0.70},
        {"w": "nhé", "start": 0.70, "end": 0.90},        # đọc khác kịch bản
    ]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    shown = [w["text"] for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert shown == ["Fable", "thắng", "rồi"]
    assert "function lev(" not in (VIDEO / "tools/align.mjs").read_text(encoding="utf-8"),         "lớp sửa tên thương hiệu đã thừa -- đừng để nó quay lại"


def test_caption_lines_stay_short_enough_to_read(stage):
    """Bản tham chiếu chỉ để 2-4 từ dưới đáy mỗi lúc. Dài hơn là người xem
    phải ĐỌC thay vì NGHE, và chữ co nhỏ tới mức khó nhìn trên điện thoại."""
    long_script = " ".join("từ%d" % i for i in range(120))
    (stage / "tools/cards.mjs").write_text(
        'export const CARDS = [["%s"]];%sexport const SECTIONS = [[0,"A"]];%s'
        % (long_script, NL, NL), encoding="utf-8")
    (stage / "tools/variants.mjs").write_text(JS_LAYOUT1, encoding="utf-8")
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [{"w": "từ%d" % i, "start": i * 0.04, "end": i * 0.04 + 0.03} for i in range(120)]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    assert all(len(c["lines"]) == 1 for c in tl["cards"]), "một dòng một lúc"
    assert all(len(l["text"]) <= 22 for c in tl["cards"] for l in c["lines"])
    shown = [w["text"] for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert shown == ["từ%d" % i for i in range(120)], "không được rơi mất chữ nào"
    assert all(c["variant"] and c["section"] for c in tl["cards"])
