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

def test_subtitle_track_is_the_spoken_words_verbatim(stage):
    """The narrator paraphrases: they add words, swap words, drop words. The
    subtitle layer is the one that must follow the voice exactly, so it
    carries the transcript verbatim rather than the scripted wording."""
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    # Script says "một hai ba" / "bốn năm sáu" / "bảy tám chín" (see `stage`),
    # but the speaker paraphrased: kept some words, swapped others, added one.
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

    assert [w["text"] for w in tl["subtitle"]] == [s["w"] for s in spoken]
    assert [w["start"] for w in tl["subtitle"]] ==         [pytest.approx(s["start"], abs=1e-6) for s in spoken]
    # The slide layer keeps the scripted wording -- it is a designed headline.
    assert "ba" in " ".join(l["text"] for c in tl["cards"] for l in c["lines"])


def test_no_subtitle_when_real_timing_is_unavailable(stage):
    """Without a usable transcript the words on screen would be guesses, not
    what was said -- showing nothing beats showing wrong captions."""
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))
    assert tl["subtitle"] == []


def test_long_speech_does_not_bloat_the_slide_layer(stage):
    """A real recording carries far more words than the (deliberately terse)
    kinetic script -- 502 vs 166 in the incident that prompted this. Routing
    the narration into the slides produced a 21-line card shrunk to
    unreadable, so the slides stay scripted and the speech goes to the
    subtitle."""
    dur = align.make_silence_txt(FX / "voice_fixture.wav", stage / "ref/silence.txt",
                                 video_dir=VIDEO)
    spoken = [{"w": f"từ{i}", "start": i * 0.04, "end": i * 0.04 + 0.03} for i in range(120)]
    (stage / "ref/words.json").write_text(json.dumps(spoken, ensure_ascii=False), encoding="utf-8")
    tl = json.loads(align.run_aligner(stage, dur).read_text(encoding="utf-8"))

    assert len(tl["cards"]) == 3, "slides stay one-per-scripted-card"
    assert all(len(c["lines"]) <= 3 for c in tl["cards"])
    assert len(tl["subtitle"]) == 120, "every spoken word still reaches the subtitle"


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
