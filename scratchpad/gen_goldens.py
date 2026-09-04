import json
from pathlib import Path
from pipeline.video.models import Script
from pipeline.video import codegen
FX = Path("tests/fixtures/video")
s = Script.from_dict(json.loads((FX/"norm_script.json").read_text(encoding="utf-8")))
(FX/"expected_cards.mjs").write_text(codegen.render_cards_mjs(s), encoding="utf-8")
(FX/"expected_variants.mjs").write_text(codegen.render_variants_mjs(s), encoding="utf-8")
print("=== expected_cards.mjs ===")
print((FX/"expected_cards.mjs").read_text(encoding="utf-8"))
print("")
print("=== expected_variants.mjs ===")
print((FX/"expected_variants.mjs").read_text(encoding="utf-8"))
