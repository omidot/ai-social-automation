# Phase 2C — Video Publish — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-09-phase2c-video-publish.md
Spec: docs/superpowers/specs/2026-09-09-phase2c-video-publish-design.md
Branch: feature/p2c-video-publish
Base: 3db71f8 (docs(p2c): implementation plan)
Prior phases: progress-p2b.md (2B, merged df91af1), progress-plan1/2.md

## Tasks
- Task 1: complete (commit 3db71f8..5ff3a9b, controller-verified pending review; assets.py upload/delete Release asset, _client module-level for MockTransport, 4 tests. 78 video / 209 non-video)
  - T1 minor (fold later): delete_release_asset raises httpx.HTTPStatusError not AssetError on non-404; _repo_token bare KeyError on unset env.
- Task 2: complete (commit 5ff3a9b..edd3418, controller-verified pending review; youtube.py adapter _access_token/upload/delete + scripts/mint_youtube_token.py, 5 tests. 83 video / 209 non-video)
  - T2 minor (fold later): mint script no exit on OAuth access_denied; httpx.Client never closed in __init__; delete() extra token round-trip.
- Task 3: complete (commit edd3418..9709d06, controller-verified pending review; publish_pending orchestrator + _PLATFORMS{youtube} + _Ctx + render_run wiring + settings video.publish block. 6 orchestrator tests, 89 video / 209 non-video)
  - T3 minor: youtube_category at video.publish.* not honored (_do_youtube passes video block; upload reads flat). value==default so masked. FIX IN T4.
  - T3 minor: dead `timezone` import in publish/__init__.py.
- Task 4: complete (commit 9709d06..003b108, controller-verified pending review; handle_unpublish undo + poll vid:*:unpub routing + expire_stale publishing>6h nudge + video-render.yml gate/env + README. Folded: youtube_category merge fix + dead timezone import. 92 video / 211 non-video)
- Task 5: pending — Meta.fb_publish_reel + register fb_reel
- Task 6: pending — Meta.ig_publish_reel + register ig_reel
- Task 7: pending — tiktok.py + refresh-token rotation + register tiktok

## Pre-flight notes (fold into the relevant task, not plan contradictions)
- T3: `_publish_one` draft has publish_started_at written 3x — collapse to one `patch.setdefault(...)`.
- T4: plan adds `from ...publish import slot_unix` to publish/__init__.py but handle_unpublish uses published_at, not slot time — drop the unused import.

## Notes
- Local: .venv/Scripts/python.exe, Python 3.12.3, run from D:\Automation Social.
- Baseline suites: 74 video / 209 non-video green at 3db71f8.
- Repo is PUBLIC -> Actions free/unlimited; NEVER commit a token.
