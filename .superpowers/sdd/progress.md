# Phase 2A — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-03-phase2a-script-voice-timeline.md
Branch: feature/phase2a-video
Base: 7c4b291 (Add Phase 2A implementation plan)

## Tasks
- Task 1: DEFERRED (spike — needs user's assets/voice/sample.wav + 2GB model download; do last)
- Task 2: complete (commits c799d0a..5334520, review clean)
- Task 3: complete (commits 230c9cd..a4f4ed5, review clean — Approved)
- Task 4: complete (commits b5692a4..5028903, review Approved + fix pass for 2 Important coverage gaps; re-verified by controller — 78 suite green)
- Task 5: complete (commits cf00a86..59a623e, review Approved)
- Task 6: complete (commits d813abc..28cc8bb, review Approved)
- Task 7: complete (commits 1e15b92..d5cc5f6, review Approved; deviation: +encoding="utf-8",errors="replace" on subprocess calls — Windows cp1252/Vietnamese fix, confirmed sound)
- Task 8: complete (commits 784cdef..8abaf76, review Approved; deviation: os.close() the mkstemp fd — Windows PermissionError fix, sound)
- Task 9: complete (commits 24d0f19..3ed62fc, review Approved; cross-task fix: tts._fake_wav emits quiet tone not pure silence so _to_mp3 silenceremove doesn't strip it — fake-path only, real-TTS untouched, Task 8 tests unaffected)
- Task 10: complete (commits 6929d28..d92c620, review Approved)
- Task 11: complete (commits 9f26ea9..6eb94f4, review Approved — no issues)

ALL CODE TASKS (2-11) COMPLETE. Task 1 (spike) deferred — needs user's assets/voice/sample.wav.
Final whole-branch review (opus) done → "No, with fixes": 2 Critical, 7 Important.
Fix wave dispatched (one subagent). Then re-verify + finishing-a-development-branch.

## Final review findings (fix wave)
- C1 build_video.py main(): `cfg.setdefault("enabled", True)` never overrides settings' False → CLI + CI smoke are vacuous no-ops. FIX: `cfg["enabled"] = True` + test driving main().
- C2 video/src/KineticShort.tsx:112 plays `voice-adsbot.mp3` not generated `voice.mp3` → every render has wrong desynced audio. FIX: staticFile('voice.mp3') + commit placeholder.
- I1 run.py:127 video `_notify` fires during --dry-run (above the dry_run guard). FIX: `if not dry_run:`.
- I2 run.py:118/122 malformed `video: true` scalar → AttributeError before try/except. FIX: `vcfg = settings.get("video") or {}` + isinstance guard.
- I3 regenerated video/ files tracked & churned; voice.mp3 untracked+unignored. FIX: gitignore video/ref/silence.txt + assets/voice/sample.txt; keep cards.mjs/variants.mjs/timeline.json/voice.mp3 tracked as Studio seed + README "git checkout -- video/ after local runs".
- I4 faster-whisper+gradio-client in requirements.txt install on ALL workflows incl approve.yml (every 10min) — cost regression + breaks py3.14 local. FIX: requirements-video.txt, installed only in video-smoke.yml.
- I5 tts._to_mp3 check=True → CalledProcessError escapes main()'s `except VideoError`. FIX: wrap→TTSError; move _to_mp3 out of backend loop in non-fake path.
- I6 encoding="utf-8",errors="replace" only on align.py; missing on tts._run_script, tts._to_mp3, codegen.node_check, build_video render-smoke. FIX: add to all 4.
- I7 tts._hfspace sleeps 60s after final attempt. FIX: `if attempt < 2:` + hoist import time.
- Minors: ruff F401/F841 (unused json/field/re/subprocess/_SIL/_wav_seconds/tmp_path); strengthen test_synthesize_falls_through_backends to assert on mp3; struct.pack splat + _run_script argv size = final polish / Task 1 concern.

## Minor findings roll-up (for final review)
- Task 2: unused `json` import in tests/video/test_remotion_project.py:1 (from plan text; harmless)
- Task 2: ffmpeg-static postinstall warning was benign — video/node_modules/ffmpeg-static/ffmpeg.exe (82MB) IS present. Task 7 unblocked.
- Task 3: unused `field` import in src/pipeline/video/models.py (from plan text; harmless) — clean up at final review
- Task 4: `_validate(data, cfg)` — `cfg` param unused (plan-mandated shape); "unreachable" guard is dead-but-defensible type hint; raw_script.json = 108 displayed words (below 110-140 target, inside 95-155 test band). All for final-review triage.
- Task 5: unused `re` import in tests/video/test_variants.py (from plan text). No explicit test that normalize() does not mutate its input (deepcopy on line 1 makes it self-evident).
- Task 6: unused `subprocess` import in tests/video/test_codegen.py (from plan text). Golden fixtures bootstrapped from impl — triangulated by node_check + downstream align.mjs (Task 7).
- Task 7: dead `_SIL` regex in align.py:11 (from plan text); unused `tmp_path` in test_align.py:48; align.py validation branches (missing timeline / bad JSON / empty cards) not directly covered — only returncode!=0 path is. `needs_node` has no conftest auto-skip → hard-fails on machines without node/ffmpeg (fine for CI which has both; add skip hook in Task 11 or final).
- Task 8: FIX-AT-FINAL — `_hfspace` in tts.py sleeps 60s even after the last retry attempt (guard with `if attempt < 2:`); move `import time` out of loop; drop unused `_wav_seconds` test helper; `test_synthesize_all_fail_raises` should assert the TTSError message names the backends; dead `not Path(out_wav).exists()` guard in `_run_script` (latent); `_to_mp3` returns input-wav duration not trimmed-mp3 duration (add comment).
- Task 9: `tts._fake_wav` uses `struct.pack("<%dh" % n, *gen)` — ~700k-arg splat for long text; works, cosmetic (final-review: array/bytes assembly cleaner).
- Task 10: README links `docs/superpowers/notes/2026-09-03-tts-spike.md` which does not exist yet (Task 1 spike creates it) — broken link meanwhile. `_CFG_DEFAULTS` merge has no e2e test. `run.py:118/122` mixed access: a malformed scalar `video: true` in settings.yaml would AttributeError before the try — optional `isinstance(...)` hardening (plan-snippet issue).
