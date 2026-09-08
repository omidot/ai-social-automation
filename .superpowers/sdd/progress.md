# Phase 2B — Video Render & Review — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-08-phase2b-video-render-review.md
Branch: feature/p2b-video-render
Base: 8f1d786 (docs(p2b): implementation plan)
Prior ledgers archived: progress-plan1.md, progress-plan2.md

## Tasks
- Task 1: complete — retired TTS: deleted tts.py/test_tts.py, removed TTSError, build_video now takes keyword-only voice_wav + CLI --voice (required with --story), _copy_as_mp3 helper, manifest tts_backend->audio_source ("user-audio"); settings.yaml video block (enabled:true, render_composition:CodexShort, no tts_provider); requirements-video.txt emptied to comment. Also updated video-smoke.yml + test_workflows_video.py (--fake -> --voice fixture) since brief self-review forbids dangling --fake. Video 38 pass, non-video 202 pass.
- Task 2: pending — single fixed background video/public/bg.mp4 + BgVideo.tsx
- Task 3: pending — VideoMeta model + _validate_meta
- Task 4: pending — script.generate_from_article
- Task 5: pending — video/draft_script.py
- Task 6: pending — wire draft_script into article_run.draft()
- Task 7: pending — Telegram.send_video
- Task 8: pending — render.py helpers (_audio_file_id, _to_mp3, _remotion_render)
- Task 9: pending — render.receive_audio + handle_undo
- Task 10: pending — article_approve.poll routing + expire_stale video sweep
- Task 11: pending — article-approve.yml + full suite + README

## Minor findings roll-up
(none yet)

## Notes
- 42 video tests currently pass; ~202 non-video tests pass.
- Local: .venv/Scripts/python.exe, Python 3.12.3, run from D:\Automation Social.
- Task 2 Step 2: bg.mp4 — user provides adsbot-vox.mp4; re-encode to <=40MB and commit, OR gitignore + README. Needs the actual file; if absent, implementer commits a placeholder/note and flags it.
- video tests use `needs_node` skip when node absent locally.
