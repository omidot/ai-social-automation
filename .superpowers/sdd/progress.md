# News-First Content Refresh — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-09-news-first-content-refresh.md
Spec: docs/superpowers/specs/2026-09-09-news-first-content-refresh-design.md
Branch: feature/news-first-content-refresh
Base: 53a9c94 (docs: implementation plan, pre-renumber)
Prior phases: progress-p2c.md, progress-p2b.md, progress-plan1/2.md

## Live diagnostic findings (2026-09-09, controller-run against real feeds)
1. Root cause #1 (spec §1, confirmed): quiet days, single-source tier-1 AI news scores
   well under min_score=45 (no cross_source/source_spread/popularity bonus available).
2. Root cause #2 (spec §1a, NEW — found live, not anticipated in original spec):
   pick_n DID select 4 distinct candidates >=45 on the day tested (a viral cross-posted
   Anthropic story inflated scores), but ALL 4 had full_text=0 + summary <400 chars ->
   has_body() zeroed picked to 0 -> write_share never called. Cause: collect() extracts
   fulltext for top-8-by-RECENCY, not top-4-by-SCORE that pick_n returns. GPT-6 Astra
   candidate WAS present in feed (rss:OpenAI, 0.5h old, score 46.2 - barely over 45).
   -> Plan revised: inserted new Task 2 (fulltext extraction targeting) before the
   scoring-gate task (now Task 3). Spec updated with §1a + §4.2a. Both fixes needed
   together for the news path to visibly fire.
   Raw diagnostic output: see conversation history / re-run `ARTICLE_DEBUG=1
   .venv/Scripts/python.exe -m pipeline.article_run --slot morning --root . --fake-llm`
   to reproduce.

## Tasks
- Task 1: complete (commit 53a9c94..12da364..1c0ba48, review Approved; ARTICLE_DEBUG()
  fn (not const, monkeypatch-safe) in collect.py+score.py + article_run.py picked/
  has_body funnel logging (controller-added after live diagnostic, commit 1c0ba48).
  Deviations: test_collect.py pre-existed (appended not overwrote); _DEBUG const->fn.
  215 non-video / 111 video)
- Task 2: pending — target fulltext extraction at picked candidates (collect.ensure_fulltext)
- Task 3: pending — fix scoring gate (_source_tier, recency denom, min_score, MAX_AGE_HOURS)
- Task 4: pending — write_share broadened + ANGLES + ArticleContent.angle + storyboard relax
- Task 5: pending — replace listicle fallback bank (topics.yaml, propose_topic, write_take)
- Task 6: pending — article_run wiring (angle propagation + sibling-angle hint)

## Notes
- Local: .venv/Scripts/python.exe, Python 3.12.3, run from D:\Automation Social.
- Baseline suites: 215 non-video / 111 video green at 1c0ba48.
- ARTICLE_DEBUG in score.py/collect.py is a zero-arg function _DEBUG(), NOT a bool
  constant (frozen-at-import bools can't observe monkeypatch.setenv in tests).
