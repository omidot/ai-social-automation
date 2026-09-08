import json
from pathlib import Path

import pytest
from pipeline import styles
from pipeline.styles import Style, StyleError

REPO = Path(__file__).resolve().parents[1]


def _write_real_config(dst):
    src = (REPO / "config" / "styles.yaml").read_text("utf-8")
    (dst / "config" / "styles.yaml").write_text(src, encoding="utf-8")


def test_load_styles_returns_24_valid(tmp_path):
    (tmp_path / "config").mkdir()
    _write_real_config(tmp_path)
    st = styles.load_styles(tmp_path)
    assert len(st) == 24
    names = [s.name for s in st]
    assert len(set(names)) == 24
    for s in st:
        assert s.layout in styles.LAYOUT_NAMES
        assert s.palette in styles.PALETTE_NAMES
        assert s.font in styles.FONT_NAMES
        assert s.texture in styles.TEXTURE_NAMES
        assert s.accent_shape in styles.ACCENT_SHAPES
        assert s.logo in styles.LOGO_TREATMENTS
    # every layout and every palette is exercised at least once
    assert {s.layout for s in st} == set(styles.LAYOUT_NAMES)
    assert {s.palette for s in st} == set(styles.PALETTE_NAMES)


def test_load_styles_rejects_bad_count(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "styles.yaml").write_text(
        "styles:\n  - {name: a, layout: centered, palette: ink-on-white, "
        "font: grotesk, texture: dots, accent_shape: none, logo: tile}\n",
        encoding="utf-8")
    with pytest.raises(StyleError):
        styles.load_styles(tmp_path)


def test_load_styles_rejects_bad_field(tmp_path):
    (tmp_path / "config").mkdir()
    rows = "\n".join(
        f"  - {{name: s{i}, layout: centered, palette: ink-on-white, font: grotesk, "
        f"texture: dots, accent_shape: none, logo: tile}}" for i in range(23))
    (tmp_path / "config" / "styles.yaml").write_text(
        "styles:\n" + rows +
        "\n  - {name: bad, layout: NOPE, palette: ink-on-white, font: grotesk, "
        "texture: dots, accent_shape: none, logo: tile}\n", encoding="utf-8")
    with pytest.raises(StyleError):
        styles.load_styles(tmp_path)


def test_load_styles_rejects_duplicate_name(tmp_path):
    (tmp_path / "config").mkdir()
    rows = "\n".join(
        "  - {name: dup, layout: centered, palette: ink-on-white, font: grotesk, "
        "texture: dots, accent_shape: none, logo: tile}" for _ in range(24))
    (tmp_path / "config" / "styles.yaml").write_text("styles:\n" + rows + "\n", encoding="utf-8")
    with pytest.raises(StyleError):
        styles.load_styles(tmp_path)


def test_pick_style_cycles_without_repeat_in_15(tmp_path):
    (tmp_path / "config").mkdir()
    _write_real_config(tmp_path)                     # helper: copy repo styles.yaml
    seen = []
    for _ in range(24):
        seen.append(styles.pick_style(tmp_path).name)
    assert len(set(seen)) == 24                      # all distinct across one full cycle
    nxt = styles.pick_style(tmp_path).name
    assert nxt == seen[0]                            # 25th == 1st (cycle)
    cur = json.loads((tmp_path / "data" / "style_cursor.json").read_text("utf-8"))
    assert len(cur["recent"]) <= 15
    assert cur["recent"][0] == nxt


def test_pick_style_no_repeat_in_last_15(tmp_path):
    (tmp_path / "config").mkdir()
    _write_real_config(tmp_path)
    picks = [styles.pick_style(tmp_path).name for _ in range(40)]
    for i in range(15, len(picks)):
        assert picks[i] not in picks[i - 15:i]


def test_palette_for_merges_brand_override(tmp_path):
    s = Style("x", "centered", "ink-on-white", "grotesk", "dots", "none", "tile")
    p = styles.palette_for(s, {"accent": "#FF0000", "irrelevant": "z"})
    assert p["accent"] == "#FF0000"
    assert p["bg"] == styles.PALETTES["ink-on-white"]["bg"]


def test_font_paths_always_exist(tmp_path):
    for key in styles.FONT_NAMES:
        fp = styles.font_paths(key)
        for role in ("regular", "bold", "black", "italic"):
            assert fp[role].exists()


def test_bold_faces_are_actually_bold(tmp_path):
    # the vendored Lora/JetBrains/Nunito families were variable fonts; if the
    # static-instance step regressed, PIL would render Regular/ExtraLight and the
    # bold roles would be indistinguishable from regular.
    from PIL import ImageFont
    for key in ("editorial", "mono", "rounded"):
        fp = styles.font_paths(key)
        for role in ("bold", "black"):
            sub = ImageFont.truetype(str(fp[role]), 40).getname()[1]
            assert sub not in ("Regular", "ExtraLight"), f"{key}/{role} -> {sub}"
