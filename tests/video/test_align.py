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
