from __future__ import annotations
import logging, math, re
from datetime import datetime
from difflib import SequenceMatcher

from .models import Candidate

log = logging.getLogger("score")

# Short/ambiguous keyword tokens that must only be honoured when they hit the
# TITLE — never a bare summary match (they collide with ordinary words and
# accented names like "Hải"/"Mai" otherwise). Compared case-insensitively
# against the keyword string itself.
_STRICT = {"ai", "llm", "gpt"}


def _kw_hit(keyword: str, text: str) -> bool:
    """Word-boundary, case-insensitive, accent-preserving keyword match.

    ``(?<!\\w)…(?!\\w)`` keeps the bare token ``AI`` from matching inside
    ``Hải``/``OpenAI`` while still matching ``AI`` / ``A.I`` boundaries.
    """
    if not keyword or not text:
        return False
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.IGNORECASE) is not None


def is_ai_relevant(c: Candidate, keywords: list[str]) -> bool:
    """True iff at least one keyword matches the candidate's TITLE (word
    boundary, case-insensitive). Non-strict keywords (e.g. multi-word
    "trí tuệ nhân tạo") may also match the first ~300 chars of the summary;
    strict tokens (AI/LLM/GPT) are title-only.

    An empty keyword list means "cannot judge" -> relevant (don't filter).
    """
    if not keywords:
        return True
    title = c.title or ""
    summary_head = (c.summary or "")[:300]
    for k in keywords:
        if not k:
            continue
        if _kw_hit(k, title):
            return True
        if k.lower() in _STRICT:
            continue
        if _kw_hit(k, summary_head):
            return True
    return False


def has_body(c: Candidate, min_chars: int = 400) -> bool:
    """True iff the candidate carries enough prose to actually write about."""
    return (len((c.full_text or "").strip()) >= min_chars
            or len((c.summary or "").strip()) >= min_chars)


def _recency(c: Candidate, now: datetime) -> float:
    hours = max(0.0, (now - c.published_at).total_seconds() / 3600.0)
    return max(0.0, 40.0 * (1.0 - hours / 48.0))


def _popularity(c: Candidate) -> float:
    if c.raw_score_hint <= 0:
        return 0.0
    # log10(50)->~1.7 .. log10(5000)->~3.7 ; map ~[1.5,4.0] to [0,30]
    v = (math.log10(c.raw_score_hint) - 1.5) / (4.0 - 1.5)
    return max(0.0, min(1.0, v)) * 30.0


def _cross_source(c: Candidate, cohort: list[Candidate]) -> float:
    for other in cohort:
        if other is c or other.url == c.url:
            continue
        if SequenceMatcher(None, c.title.lower(), other.title.lower()).ratio() >= 0.6:
            return 20.0
    return 0.0


def _keyword_fit(c: Candidate, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    text = f"{c.title} {c.summary}"
    hits = sum(1 for k in keywords if _kw_hit(k, text))
    return min(1.0, hits / 3.0) * 10.0


def _source_spread(c: Candidate) -> float:
    return min(max(c.source_count - 1, 0), 4) * 5.0


def score_candidate(c: Candidate, now: datetime, cohort: list[Candidate],
                    keywords: list[str]) -> float:
    return round(_recency(c, now) + _popularity(c) + _cross_source(c, cohort)
                 + _keyword_fit(c, keywords) + _source_spread(c), 2)


def pick(cands: list[Candidate], min_score: float, now: datetime,
         keywords: list[str]) -> tuple[Candidate | None, float]:
    if not cands:
        return None, 0.0
    scored = [(score_candidate(c, now, cands, keywords), c) for c in cands]
    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best = scored[0]
    if best_score < min_score:
        return None, best_score
    return best, best_score


def pick_n(cands, n, min_score, now, keywords, exclude_titles=()):
    scored = [(score_candidate(c, now, cands, keywords), c) for c in cands]
    scored.sort(key=lambda t: t[0], reverse=True)
    picked: list[tuple[float, Candidate]] = []
    for sc, c in scored:
        if not is_ai_relevant(c, keywords):
            log.info("skip non-AI: %s", c.title)
            continue
        if sc < min_score:
            break
        blockers = list(exclude_titles) + [pc.title for _, pc in picked]
        if any(SequenceMatcher(None, c.title.lower(), b.lower()).ratio() >= 0.5
               for b in blockers):
            continue
        picked.append((sc, c))
        if len(picked) == n:
            break
    return picked
