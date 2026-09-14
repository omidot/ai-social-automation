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


def test_slides_carry_the_spoken_words_not_the_script(stage):
    """The narrator paraphrases: they add words, swap words, drop words.
    Keeping the scripted wording on screen put the text up to ten seconds
    out of step with the voice, so the slides are rebuilt from what was
    actually said."""
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    # Script says "một hai ba" / "bốn năm sáu" / "bảy tám chín" (see `stage`).
    spoken = [
        {"w": "một", "start": 0.10, "end": 0.30},
        {"w": "hai", "start": 0.30, "end": 0.50},
        {"w": "nghìn", "start": 0.50, "end": 0.70},      # added, not in script
        {"w": "bốn", "start": 1.00, "end": 1.20},
        {"w": "lăm", "start": 1.20, "end": 1.40},        # said instead of "năm"
        {"w": "sáu", "start": 1.40, "end": 1.60},
        {"w": "bảy", "start": 2.00, "end": 2.20},
        {"w": "tám", "start": 2.20, "end": 2.40},
        {"w": "chín", "start": 2.40, "end": 2.60},
    ]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    flat = [w for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert [w["text"] for w in flat] == [s["w"] for s in spoken]
    # Each word keeps its own real timestamp, so nothing can appear early.
    assert [w["start"] for w in flat] ==         [pytest.approx(s["start"], abs=1e-6) for s in spoken]


def test_long_speech_never_overflows_a_slide(stage):
    """A real recording carries far more words than the (deliberately terse)
    kinetic script -- 502 vs 166 in the incident that prompted this. Packing
    it into the script's own card slots gave a 21-line card shrunk to
    unreadable, so slides are re-cut from the speech."""
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [{"w": f"từ{i}", "start": i * 0.04, "end": i * 0.04 + 0.03} for i in range(120)]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    assert all(len(c["lines"]) <= 3 for c in tl["cards"])
    assert all(len(l["text"]) <= 26 for c in tl["cards"] for l in c["lines"])
    shown = [w["text"] for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert shown == [s["w"] for s in spoken], "no spoken word may be dropped"
    assert all(c["variant"] and c["section"] for c in tl["cards"])


def test_misheard_brand_names_are_corrected_from_the_script(stage):
    """Speech recognition mangles brand names -- the narrator said "Fable"
    and it came back "Facebook", putting the wrong company on screen. The
    word keeps its (correct) timestamp but borrows the script's spelling.

    Matching is done straight against the logo registry, not via the
    script alignment: measured on the real recording, the aligner paired
    "Fable" with "vi", "nam" and "dung" -- far too loose to trust."""
    (stage / "tools/cards.mjs").write_text(
        'export const CARDS = [["Fable thắng rồi"]];\n'
        'export const SECTIONS = [[0,"A"]];\n', encoding="utf-8")
    (stage / "tools/variants.mjs").write_text(
        'export const LAYOUT = [["stack","mid",null,"rise","up"]];\n', encoding="utf-8")
    (stage / "src").mkdir(exist_ok=True)
    (stage / "src/logos.json").write_text(
        json.dumps({"fable": {"label": "Anthropic", "file": "logos/fable.png"}}),
        encoding="utf-8")
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [
        {"w": "Facebook", "start": 0.10, "end": 0.40},   # misheard "Fable"
        {"w": "thắng", "start": 0.40, "end": 0.70},
        {"w": "nhé", "start": 0.70, "end": 0.90},        # said instead of "rồi"
    ]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    flat = [w for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert [w["text"] for w in flat] == ["Fable", "thắng", "nhé"]
    assert flat[0]["start"] == pytest.approx(0.10, abs=1e-6), "timing untouched"


def test_unrelated_words_are_never_rewritten_to_a_brand(stage):
    """Guard on the rule above: a stray alignment must not let a brand name
    overwrite a word that merely happens to line up with it."""
    (stage / "tools/cards.mjs").write_text(
        'export const CARDS = [["Fable thắng rồi"]];\n'
        'export const SECTIONS = [[0,"A"]];\n', encoding="utf-8")
    (stage / "tools/variants.mjs").write_text(
        'export const LAYOUT = [["stack","mid",null,"rise","up"]];\n', encoding="utf-8")
    (stage / "src").mkdir(exist_ok=True)
    (stage / "src/logos.json").write_text(
        json.dumps({"fable": {"label": "Anthropic", "file": "logos/fable.png"}}),
        encoding="utf-8")
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [
        {"w": "Đừng", "start": 0.10, "end": 0.40},   # nothing like "Fable"
        {"w": "thắng", "start": 0.40, "end": 0.70},
        {"w": "rồi", "start": 0.70, "end": 0.90},
    ]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    shown = [w["text"] for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert shown[0] == "Đừng", "a different word must survive untouched"


def test_brand_correction_is_reported_and_bounded(stage):
    """Only close misspellings of a registered brand are rewritten. A word
    that merely starts with the same letter must survive as spoken."""
    (stage / "tools/cards.mjs").write_text(
        'export const CARDS = [["Claude thắng rồi"]];\n'
        'export const SECTIONS = [[0,"A"]];\n', encoding="utf-8")
    (stage / "tools/variants.mjs").write_text(
        'export const LAYOUT = [["stack","mid",null,"rise","up"]];\n', encoding="utf-8")
    (stage / "src").mkdir(exist_ok=True)
    (stage / "src/logos.json").write_text(
        json.dumps({"claude": {"label": "Anthropic", "file": "logos/claude.png"}}),
        encoding="utf-8")
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [
        {"w": "Cloud", "start": 0.10, "end": 0.40},    # misheard "Claude"
        {"w": "chuyện", "start": 0.40, "end": 0.70},   # same initial, unrelated
        {"w": "rồi", "start": 0.70, "end": 0.90},
    ]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    shown = [w["text"] for c in tl["cards"] for l in c["lines"] for w in l["words"]]
    assert shown == ["Claude", "chuyện", "rồi"]
