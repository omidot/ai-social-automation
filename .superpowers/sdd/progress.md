# Phase 2C — Video Publish — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-09-phase2c-video-publish.md
Spec: docs/superpowers/specs/2026-09-09-phase2c-video-publish-design.md
Branch: feature/p2c-video-publish
Base: 3db71f8 (docs(p2c): implementation plan)
Prior phases: progress-p2b.md (2B, merged df91af1), progress-plan1/2.md

## Tasks
- Task 1: pending — assets.py: GitHub Release asset upload/delete
- Task 2: pending — youtube.py adapter + scripts/mint_youtube_token.py
- Task 3: pending — publish_pending orchestrator + config + render_run wiring
- Task 4: pending — handle_unpublish undo + expire_stale nudge + workflow env + README
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
