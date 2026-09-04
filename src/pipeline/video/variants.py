from __future__ import annotations
import copy
import re

from .models import (Card, Script, VALID_VARIANTS, VALID_ANCHORS,
                     VALID_MOTION_IN, VALID_MOTION_OUT)

_MI_ORDER = ["rise", "slideL", "wipe", "fall", "slideR", "pop", "slam"]
_ANCHOR_CYCLE = ["mid", "top", "low"]
_DIGIT = re.compile(r"\d[\d.,]*")


def _first_int(text: str) -> int | None:
    m = _DIGIT.search(text)
    if not m:
        return None
    try:
        return int(m.group(0).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _section_final_indices(s: Script) -> set[int]:
    starts = sorted(sec.card_start for sec in s.sections)
    finals = {st - 1 for st in starts if st - 1 >= 0}
    finals.add(len(s.cards) - 1)
    return finals


def normalize(s: Script) -> Script:
    s = copy.deepcopy(s)
    n = len(s.cards)
    finals = _section_final_indices(s)

    for i, c in enumerate(s.cards):
        # 1. defaults for invalid enum values
        if c.variant not in VALID_VARIANTS:
            c.variant = "stack"
        if c.anchor not in VALID_ANCHORS:
            c.anchor = "mid"
        if c.motion_in not in VALID_MOTION_IN:
            c.motion_in = "rise"
        if c.motion_out not in VALID_MOTION_OUT:
            c.motion_out = "up"

        # 2. digit card -> numeral
        joined = " ".join(l for l in c.lines if not l.startswith("~"))
        if _DIGIT.search(joined):
            if c.num is None:
                c.num = _first_int(joined)
            c.variant = "numeral"

        # 3. section-final / last-card variants
        if i == n - 1:
            c.variant = "invert"
        elif i in finals and c.variant in {"stack", "right"}:
            c.variant = "strike"

    # 4. anchor: no 3 in a row
    for i in range(2, n):
        a = s.cards
        if a[i].anchor == a[i - 1].anchor == a[i - 2].anchor:
            nxt = _ANCHOR_CYCLE[(_ANCHOR_CYCLE.index(a[i].anchor) + 1) % 3]
            a[i].anchor = nxt

    # 5. motion_in: differ from previous card
    for i in range(1, n):
        if s.cards[i].motion_in == s.cards[i - 1].motion_in:
            for cand in _MI_ORDER:
                if cand != s.cards[i - 1].motion_in:
                    s.cards[i].motion_in = cand
                    break

    # 6. closer cards exit hard
    for c in s.cards:
        if c.variant in {"invert", "strike"} and c.motion_out == "up":
            c.motion_out = "wipeOut"

    return s
