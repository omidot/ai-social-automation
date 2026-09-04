import json, subprocess
from pathlib import Path
import pytest
from pipeline.video.models import Script
from pipeline.video import codegen, CodegenError

FX = Path(__file__).resolve().parents[1] / "fixtures" / "video"

def _script():
    return Script.from_dict(json.loads((FX / "norm_script.json").read_text(encoding="utf-8")))

def test_cards_mjs_matches_golden():
    got = codegen.render_cards_mjs(_script())
    assert got == (FX / "expected_cards.mjs").read_text(encoding="utf-8")

def test_variants_mjs_matches_golden():
    got = codegen.render_variants_mjs(_script())
    assert got == (FX / "expected_variants.mjs").read_text(encoding="utf-8")

def test_write_creates_both(tmp_path):
    (tmp_path / "tools").mkdir()
    a, b = codegen.write(_script(), tmp_path)
    assert a.read_text(encoding="utf-8").startswith("// FILE TỰ SINH")
    assert "export const LAYOUT" in b.read_text(encoding="utf-8")

@pytest.mark.needs_node
def test_node_check_passes(tmp_path):
    (tmp_path / "tools").mkdir()
    codegen.write(_script(), tmp_path)
    codegen.node_check(tmp_path)  # must not raise

@pytest.mark.needs_node
def test_node_check_raises_on_garbage(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/cards.mjs").write_text("export const CARDS = [ ( ;", encoding="utf-8")
    (tmp_path / "tools/variants.mjs").write_text("export const LAYOUT = [];", encoding="utf-8")
    with pytest.raises(CodegenError):
        codegen.node_check(tmp_path)
