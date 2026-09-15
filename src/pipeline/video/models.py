from __future__ import annotations
import re
from dataclasses import dataclass

VALID_VARIANTS = frozenset({"stack", "right", "hero", "invert", "mark", "stair", "numeral", "strike"})
VALID_ANCHORS = frozenset({"top", "mid", "low"})
VALID_MOTION_IN = frozenset({"rise", "fall", "slideR", "slideL", "wipe", "pop", "slam"})
VALID_MOTION_OUT = frozenset({"up", "down", "dissolve", "shrink", "wipeOut"})

_WORD = re.compile(r"\S+")
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _strip_tilde(line: str) -> str:
    return line[1:] if line.startswith("~") else line


def _coerce_num(num: object) -> int | float | None:
    """The LLM occasionally returns 'num' with a unit/currency attached (e.g.
    "50 USD", "2.5x") despite the prompt asking for a bare number — codegen
    writes this value verbatim into a JS array literal, so anything but a
    real number there breaks the generated variants.mjs. Extract the leading
    numeric value instead of letting a malformed one crash the render."""
    if num is None or isinstance(num, (int, float)):
        return num
    m = _NUM.search(str(num))
    if not m:
        return None
    text = m.group()
    return float(text) if "." in text else int(text)


@dataclass
class Card:
    lines: list[str]
    variant: str
    anchor: str
    motion_in: str
    motion_out: str
    num: int | float | None = None
    chart: ChartSpec | None = None
    screenshot: ScreenshotSpec | None = None
    screenshot_file: str | None = None
    screenshot_url: str | None = None

    @property
    def spoken(self) -> str:
        return " ".join(_strip_tilde(l).strip() for l in self.lines if _strip_tilde(l).strip())

    @property
    def displayed_words(self) -> int:
        return sum(len(_WORD.findall(l)) for l in self.lines if not l.startswith("~"))

    def to_dict(self) -> dict:
        return {"lines": list(self.lines), "variant": self.variant, "anchor": self.anchor,
                "motion_in": self.motion_in, "motion_out": self.motion_out, "num": self.num,
                "chart": self.chart.to_dict() if self.chart is not None else None,
                "screenshot": self.screenshot.to_dict() if self.screenshot is not None else None,
                "screenshot_file": self.screenshot_file, "screenshot_url": self.screenshot_url}

    @classmethod
    def from_dict(cls, d: dict) -> "Card":
        chart = ChartSpec.from_dict(d["chart"]) if d.get("chart") else None
        screenshot = ScreenshotSpec.from_dict(d["screenshot"]) if d.get("screenshot") else None
        return cls(lines=list(d["lines"]), variant=d["variant"], anchor=d["anchor"],
                   motion_in=d["motion_in"], motion_out=d["motion_out"],
                   num=_coerce_num(d.get("num")), chart=chart, screenshot=screenshot,
                   screenshot_file=d.get("screenshot_file"), screenshot_url=d.get("screenshot_url"))


@dataclass
class ChartSpec:
    kind: str
    items: list[dict]
    unit: str = ""
    # Nhãn ngắn nói khối số liệu này đo cái gì ("Giá đầu ra mỗi 1 triệu
    # token"). Bản tham chiếu luôn có dòng này phía trên các hộp số. Đây
    # KHÔNG phải câu thoại -- lời thoại chạy riêng ở caption dưới đáy.
    title: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "items": [dict(i) for i in self.items],
                "unit": self.unit, "title": self.title}

    @classmethod
    def from_dict(cls, d: dict) -> "ChartSpec":
        return cls(kind=d["kind"], items=[dict(i) for i in d["items"]],
                   unit=d.get("unit", ""), title=d.get("title", ""))


@dataclass
class ScreenshotSpec:
    query: str

    def to_dict(self) -> dict:
        return {"query": self.query}

    @classmethod
    def from_dict(cls, d: dict) -> "ScreenshotSpec":
        return cls(query=d["query"])


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


@dataclass
class VideoMeta:
    title: str
    description: str
    hashtags: list[str]
    keywords: list[str]
    tiktok_caption: str

    def to_dict(self) -> dict:
        return {"title": self.title, "description": self.description,
                "hashtags": list(self.hashtags), "keywords": list(self.keywords),
                "tiktok_caption": self.tiktok_caption}

    @classmethod
    def from_dict(cls, d: dict) -> "VideoMeta":
        return cls(title=d["title"], description=d["description"],
                   hashtags=list(d["hashtags"]), keywords=list(d["keywords"]),
                   tiktok_caption=d["tiktok_caption"])
