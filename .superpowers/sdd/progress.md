# Phase 2B — Video Render & Review — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-08-phase2b-video-render-review.md
Branch: feature/p2b-video-render
Base: 8f1d786 (docs(p2b): implementation plan)
Prior ledgers archived: progress-plan1.md, progress-plan2.md

## Tasks
- Task 1: complete — retired TTS: deleted tts.py/test_tts.py, removed TTSError, build_video now takes keyword-only voice_wav + CLI --voice (required with --story), _copy_as_mp3 helper, manifest tts_backend->audio_source ("user-audio"); settings.yaml video block (enabled:true, render_composition:CodexShort, no tts_provider); requirements-video.txt emptied to comment. Also updated video-smoke.yml + test_workflows_video.py (--fake -> --voice fixture) since brief self-review forbids dangling --fake. Video 38 pass, non-video 202 pass.
- Task 2: complete (commit 3790640..9206e30, controller-verified; BgVideo.BG single bg.mp4 entry, adsbot-vox.mp4 re-encoded 27MB->6.6MB, 5 pool files removed, +test_single_fixed_background. 39 video / 202 non-video green)
- Task 3: complete (commit 9206e30..fd3df18, review Approved; VideoMeta dataclass + _validate_meta (title 10-70, hashtags 8-12 ^#S+$, keywords 5-10, tiktok <=150); module-level _GOOD_META in test_script.py. 49 video / 202 non-video)
- Task 4: complete (commit fd3df18..675f723, review Approved; build_prompt with_meta= kwarg (additive), generate_from_article builds Candidate/PostContent shim -> (Script, VideoMeta), 2-attempt word-band retry. 53 video / 202 non-video)
- Task 5: complete (commit 675f723..90d3ab5, review Approved; draft_script.draft() gen -> codegen -> awaiting_audio state -> Telegram script msg; enabled-gate short-circuits before LLM. 56 video / 202 non-video)
- Task 6: complete (commit 90d3ab5..3de7af9, review Approved; article_run.draft() calls _video_draft.draft after schedule_slot when video.enabled, double-guarded; existing article tests unchanged. 205 non-video / 56 video)
- Task 7: complete (commit 3de7af9..1e3cc0c, controller-verified; Telegram.send_video multipart sendVideo, mirrors send_document. 206 non-video)
- Task 8: complete (commit 1e3cc0c..04e8eba, controller-verified; render.py helpers _audio_file_id/_to_mp3/_remotion_render, 5 tests, subprocess module-scope import. 61 video / 206 non-video)
  - T8 minor: no test for _remotion_render returncode=1 "never raises" (brief-inherited gap); dead `import logging`/`log` in render.py; mime not lower-cased before startswith.
- Task 9: complete (commit 04e8eba..0410011, review Approved + fix wave; _find_slot + receive_audio + handle_undo, 13 render tests incl. discriminating reply-match + undo negative paths. 69 video / 206 non-video). Minor open: pid=out_dir.name -> mp4 named video.mp4; unused DailyState import (brief-mandated).
- Task 10: complete (commit 0410011..7e0ee89, review Approved; 4 minor brief-mandated. 18 article_approve / 208 non-video / 69 video)
- Task 11: complete (commit 7e0ee89..ca6d88f, controller-verified pending review; article-approve.yml +node20 +remotion browser ensure +timeout25, README "Luồng video (Phase 2B)" + 2A staleness cleanup, test_workflows +2 asserts. 208 non-video / 69 video)

## Minor findings roll-up
- T5: _make_id(title, now) can collide if two slots share an identical title on one date (shared output/ dir, last write wins). Fold `slot` into the id later.
- T4: generate + generate_from_article duplicate the 2-attempt retry loop (plan-mandated). Shared helper candidate.
- T9: mp4_path shaped .../video/video.mp4 (pid = script_path parent dir name = "video"). Confirm Task 10/2C tolerate it.
- T9: `import logging`/`log` + `DailyState` import unused in render.py (brief-mandated). Final review: prune.

## Notes
- 42 video tests currently pass; ~202 non-video tests pass.
- Local: .venv/Scripts/python.exe, Python 3.12.3, run from D:\Automation Social.
- Task 2 Step 2: bg.mp4 — user provides adsbot-vox.mp4; re-encode to <=40MB and commit, OR gitignore + README. Needs the actual file; if absent, implementer commits a placeholder/note and flags it.
- video tests use `needs_node` skip when node absent locally.

## Addendum (2026-09-09) — render-split + final-review fixes
Plan: docs/superpowers/plans/2026-09-09-phase2b-render-split-addendum.md
Base: ca6d88f. Trigger: final-review.md found C1 (stale cards.mjs -> wrong script), C2 (failed dead-end),
C3 (uncaught FileNotFoundError), I1-I5. User chose: split render into its own video-render.yml workflow.
- Task 12: complete (commit ca6d88f..12fbe44, controller-verified pending review; render.py split record_audio/render_pending, C1 regen from video.script, C2 fail->awaiting_audio, C3 try-wrap, I1 tg_file_id, I5 cfg-or-{}; draft_script persists video.script. 14 test_render / 70 video / 207 non-video +1 expected fail = test_poll_routes fixed in T13)
  - T12 M-A: _find_slot reply-match + M6/M7 same-day-tie lost test coverage (old test_receive_audio_matches_by_reply deleted, no replacement) -> add record_audio reply-match test in T14.
- Task 13: complete (commit 12fbe44..0b0f3fa, controller-verified pending review; poll->record_audio/is_audio, UNDO_GRACE_MIN 45, expire_stale rendering>40min->awaiting_audio+render_err; new render_run.py + video-render.yml (cron 3-59/10, bash go-gate, Commit if:always); article-approve.yml drops node/timeout15/commit-if:always. 209 non-video / 70 video)
  - T13 Important (fold into T14): UNDO_GRACE_MIN=45 thin vs 25min render + cron latency -> bump to 60.
  - T13 minor (defer): killed-render recovery is 40min sweep + manual re-send; rendering-stuck slots not seen by grep gate; unused import sys in render_run.py.
- Task 14: pending (folds: UNDO_GRACE_MIN 45->60; T12 M-A record_audio reply-match test; rm import sys) — M1 _make_id+slot, N1 rm Klickpin mp4s, N2 README, whole suite, delta re-review, finish branch
Deferred from final review: M5 (dup retry loop, plan-mandated), M10 (send_video 50MB guard - folded into C3 area, left as raise), nit hard-coded timeline band (fixed in T12 via target*0.6..1.4).
