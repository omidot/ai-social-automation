from __future__ import annotations
import json
import subprocess
from pathlib import Path

from . import CodegenError
from .models import Script

_HEADER = "// FILE TỰ SINH — đừng sửa tay. Nguồn: src/pipeline/video/codegen.py\n"


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def render_cards_mjs(s: Script) -> str:
    lines = [_HEADER, "export const CARDS = [\n"]
    for c in s.cards:
        inner = ", ".join(_q(l) for l in c.lines)
        lines.append(f"  [{inner}],\n")
    lines.append("];\n\nexport const SECTIONS = [\n")
    for sec in s.sections:
        lines.append(f"  [{sec.card_start}, {_q(sec.label)}],\n")
    lines.append("];\n")
    return "".join(lines)


def render_variants_mjs(s: Script) -> str:
    lines = [_HEADER, "export const LAYOUT = [\n"]
    for c in s.cards:
        num = "null" if c.num is None else str(c.num)
        lines.append(
            f"  [{_q(c.variant)}, {_q(c.anchor)}, {num}, "
            f"{_q(c.motion_in)}, {_q(c.motion_out)}],\n"
        )
    lines.append("];\n")
    return "".join(lines)


def write(s: Script, video_dir: Path) -> tuple[Path, Path]:
    tools = Path(video_dir) / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    a = tools / "cards.mjs"
    b = tools / "variants.mjs"
    a.write_text(render_cards_mjs(s), encoding="utf-8")
    b.write_text(render_variants_mjs(s), encoding="utf-8")
    return a, b


def node_check(video_dir: Path) -> None:
    for name in ("cards.mjs", "variants.mjs"):
        r = subprocess.run(["node", "--check", f"tools/{name}"],
                           cwd=str(video_dir), capture_output=True, text=True)
        if r.returncode != 0:
            raise CodegenError(f"node --check {name} failed: {r.stderr.strip()}")
