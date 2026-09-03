from __future__ import annotations
import math
from datetime import datetime
from difflib import SequenceMatcher

from .models import Candidate


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
    text = f"{c.title} {c.summary}".lower()
    hits = sum(1 for k in keywords if k.lower() in text)
    return min(1.0, hits / 3.0) * 10.0


def score_candidate(c: Candidate, now: datetime, cohort: list[Candidate],
                    keywords: list[str]) -> float:
    return round(_recency(c, now) + _popularity(c) + _cross_source(c, cohort)
                 + _keyword_fit(c, keywords), 2)


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
