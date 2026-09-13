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
- Task 2: complete (commit 1c0ba48..0900fbc, controller-verified pending review; collect.ensure_fulltext() extracted from collect()'s loop (preserves original try/except + time.sleep(0.5) rate-limit not captured in the plan brief, correctly discovered+preserved); article_run.py calls ensure_fulltext on picked candidates lacking body before has_body filter. Deviation: test_article_run.py addition used the file's real fixtures (wired/FakeTG), not the brief's assumed NOW/FakeTelegram/FakeMeta. 219 non-video / 111 video)  [review Approved]
- Task 3: complete (commit 0900fbc..4fb8121, controller-verified pending review; _source_tier/_TIER1/_TIER2 in score.py, recency denom 96, ARTICLE_DEBUG log line updated with source_tier field, MAX_AGE_HOURS 96, settings.yaml articles.min_score 20. Deviation: _c() test helper default URL truncates title[:8] causing a collision/false-tie in the new cross-posted-outranks test - added optional url= param, distinct URLs for that test only, no prod logic touched. 224 non-video / 111 video)  [review Approved]
- Task 4: complete (commit 4fb8121..6c5a641, controller-verified pending review; ANGLES frozenset, build_share_prompt+write_share sibling_angle param + angle validation, _STORYBOARD_SPEC toolless-slide sentence, ArticleContent.angle field, fixture gains angle key, 10 new tests. Self-caught+fixed an edit slip clipping a pre-existing test line before running suite. Note for Task 6: sibling_angle sits before generate positionally, current call site uses generate= kwarg so safe. 234 non-video / 111 video)  [review: Important vacuous-test fixed by controller (commit 870f191); Minor duplicate-test finding deferred]
- Task 5: complete (commit 6c5a641..870f191..c21903e, controller-verified pending review; config/topics.yaml replaced (takes/shifts), propose_topic returns {topic,angle,why} + sibling_angle param, write_take/build_take_prompt replace write_topic_post/build_topic_prompt. Note: tests/test_write.py edits landed split across controller commit 870f191 (accidental concurrent-edit scoop, see earlier ledger note) + this commit - net diff correct, no duplication/loss, agent self-detected and handled it. Also fixed stale comment + an unbriefed pre-existing test (test_propose_topic_parses_and_validates) needing schema update. KNOWN EXPECTED GAP: test_article_run.py has 16 AttributeError (write_topic_post removed) - Task 6 fixes. 217 non-video (+16 known errors) / 111 video)  [review Approved; concurrency-incident split confirmed clean, 0% overlap]
- Task 6: complete (commit c21903e..232481d, controller-verified pending review; sibling_angle computed once after `other`, threaded into write_share (positional) + propose_topic (kwarg); news angle now article.angle (was hard-coded ""); fallback angle = spec["angle"] (required key). Fixed all 16 write_topic_post AttributeErrors + 3 new tests + 1 unbriefed fallout (test_draft_excludes_recent_and_other_slot fake_propose needed sibling_angle kwarg). 236 non-video / 111 video — ALL 6 TASKS COMPLETE)  [review Approved]

## Notes
- Local: .venv/Scripts/python.exe, Python 3.12.3, run from D:\Automation Social.
- Baseline suites: 215 non-video / 111 video green at 1c0ba48.
- ARTICLE_DEBUG in score.py/collect.py is a zero-arg function _DEBUG(), NOT a bool
  constant (frozen-at-import bools can't observe monkeypatch.setenv in tests).

## Live sanity check after Task 2 (2026-09-09, controller-run)
picked_after_score=4 -> picked_after_has_body=2 (was 0 pre-Task-2). write_share attempt
1/2 actually invoked for the first time this session. Both rejected only because
--fake-llm's canned payload isn't shaped for write_share's schema (expected artifact of
the smoke-test fake, not a real defect) -> correctly fell through to topic-bank
fallback. Root cause #2 (extraction targeting) CONFIRMED FIXED live.

## Minor findings roll-up (for final whole-branch review to triage)
- T3: microsoft in tier-1 (15.0) - odd categorization per brief's literal spec, not currently a real feed source, harmless.
- T3: all 3 titles in test_breaking_cross_posted_story_still_outranks_single_source collide on title[:8] in _c()'s default url - pre-existing test-infra debt, worked around locally for the new test only.
- T4: test_write_share_accepts_a_non_launch_source_via_fixture duplicates test_write_share_returns_validated_angle.
- T5: no test directly asserts "hook.tools PHẢI là []/item.tool PHẢI là null" prompt text presence (traces to brief's own test list, implementation is compliant by inspection).
- T6: no test exercises write_share receiving a non-empty sibling_angle (only propose_topic/fallback path tested with a real value) - mirrors a gap in the brief's own test spec.
- General: data/seen.json locally polluted by controller's live diagnostic runs (--root . instead of a tmp dir) - to be reverted before merge, not part of any commit.

## ALL 6 TASKS COMPLETE — ready for final whole-branch review
