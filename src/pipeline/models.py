from __future__ import annotations
import hashlib, re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


def _normalise_url(url: str) -> str:
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"/+$", "", u)
    return u


@dataclass
class Candidate:
    url: str
    title: str
    source: str
    published_at: datetime
    raw_score_hint: float = 0.0
    summary: str = ""
    full_text: str = ""
    top_image: str | None = None
    source_count: int = 1

    @property
    def url_hash(self) -> str:
        return hashlib.sha1(_normalise_url(self.url).encode()).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = self.published_at.astimezone(timezone.utc).isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        d = dict(d)
        pa = d["published_at"]
        if isinstance(pa, str):
            d["published_at"] = datetime.fromisoformat(pa.replace("Z", "+00:00"))
        return cls(**d)


@dataclass
class PostContent:
    angle: str
    caption_fb: str
    caption_ig: str
    hashtags: list[str]
    thumbnail_prompt: str
    thumbnail_title: str
    youtube_title: str
    youtube_desc: str
    tiktok_caption: str
    source_url: str
    source_name: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PostContent":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class ArticleContent:
    format: str                 # always "share" now (single-topic knowledge piece)
    caption_fb: str
    caption_ig: str
    hashtags: list[str]
    cover_title: str
    # A storyboard of 5 to 7 dicts, one rendered slide each. Shape:
    #   {"role": str, "headline": str, "body": str,
    #    "tool": {"name": str, "domain": str} | None}
    # slides[0]["role"] == "hook" (the curiosity hook), slides[-1]["role"] ==
    # "close", every middle slide "role" == "item". "tool" is set ONLY when the
    # slide is genuinely about one named product; "domain" is that product's
    # official root domain (e.g. "openai.com", "canva.com") used to fetch its
    # real logo. Omitted / None otherwise.
    slides: list[dict]
    sources: list[dict]
    risk: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ArticleContent":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})
