from __future__ import annotations
import re
from dataclasses import dataclass

VALID_VARIANTS = frozenset({"stack", "right", "hero", "invert", "mark", "stair", "numeral", "strike"})
VALID_ANCHORS = frozenset({"top", "mid", "low"})
VALID_MOTION_IN = frozenset({"rise", "fall", "slideR", "slideL", "wipe", "pop", "slam"})
VALID_MOTION_OUT = frozenset({"up", "down", "dissolve", "shrink", "wipeOut"})

_WORD = re.compile(r"\S+")


def _strip_tilde(line: str) -> str:
    return line[1:] if line.startswith("~") else line


@dataclass
class Card:
    lines: list[str]
    variant: str
    anchor: str
    motion_in: str
    motion_out: str
    num: int | None = None

    @property
    def spoken(self) -> str:
        return " ".join(_strip_tilde(l).strip() for l in self.lines if _strip_tilde(l).strip())

    @property
    def displayed_words(self) -> int:
        return sum(len(_WORD.findall(l)) for l in self.lines if not l.startswith("~"))

    def to_dict(self) -> dict:
        return {"lines": list(self.lines), "variant": self.variant, "anchor": self.anchor,
                "motion_in": self.motion_in, "motion_out": self.motion_out, "num": self.num}

    @classmethod
    def from_dict(cls, d: dict) -> "Card":
        return cls(lines=list(d["lines"]), variant=d["variant"], anchor=d["anchor"],
                   motion_in=d["motion_in"], motion_out=d["motion_out"], num=d.get("num"))


@dataclass
class SectionMark:
    label: str
    card_start: int

    def to_dict(self) -> dict:
        return {"label": self.label, "card_start": self.card_start}

    @classmethod
    def from_dict(cls, d: dict) -> "SectionMark":
        return cls(label=d["label"], card_start=int(d["card_start"]))


@dataclass
class Script:
    cards: list[Card]
    sections: list[SectionMark]

    @property
    def spoken_text(self) -> str:
        return "\n".join(c.spoken for c in self.cards)

    @property
    def word_count(self) -> int:
        return sum(c.displayed_words for c in self.cards)

    def to_dict(self) -> dict:
        return {"cards": [c.to_dict() for c in self.cards],
                "sections": [s.to_dict() for s in self.sections]}

    @classmethod
    def from_dict(cls, d: dict) -> "Script":
        return cls(cards=[Card.from_dict(c) for c in d["cards"]],
                   sections=[SectionMark.from_dict(s) for s in d["sections"]])
