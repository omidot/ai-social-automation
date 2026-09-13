# News-First Content Refresh — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-09-news-first-content-refresh.md
Spec: docs/superpowers/specs/2026-09-09-news-first-content-refresh-design.md
Branch: feature/news-first-content-refresh
Base: 53a9c94 (docs: implementation plan)
Prior phases: progress-p2c.md, progress-p2b.md, progress-plan1/2.md

## Tasks
- Task 1: pending — ARTICLE_DEBUG diagnostic logging in collect + score
- Task 2: pending — fix scoring gate (_source_tier, recency denom, min_score, MAX_AGE_HOURS)
- Task 3: pending — write_share broadened + ANGLES + ArticleContent.angle + storyboard relax
- Task 4: pending — replace listicle fallback bank (topics.yaml, propose_topic, write_take)
- Task 5: pending — article_run wiring (angle propagation + sibling-angle hint)

## Controller note
Between Task 1 and Task 2: run ARTICLE_DEBUG=1 live once (network) to confirm root-cause
numbers before dispatching Task 2's threshold changes.

## Notes
- Local: .venv/Scripts/python.exe, Python 3.12.3, run from D:\Automation Social.
- Baseline suites: 209 non-video / 100 video green at 53a9c94 (approx — recheck at Task 1 start).
- Root cause confirmed by controller: 8/8 posts 2026-09-06..09 sources=[] (100% fallback,
  all listicle). score.py min_score=45 gate mathematically unreachable by single-source
  first-party RSS news (popularity=0, cross_source=0, source_spread=0 for a lone item).
