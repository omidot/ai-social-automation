# P1.5 — Article Image Style Variety — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-07-article-style-variety.md
Branch: feature/p1-style-variety
Base: c8928cc (merge of feature/p1-style-autopublish)
Plan-1 ledger archived at .superpowers/sdd/progress-plan1.md

## Tasks
- Task 1: complete (commits a4913d8..49b1ec9, review Approved; plan had to be fixed first — pick_style is now a positional cursor. FOLLOW-UP for Task 2: add a dup-name StyleError test)
- Task 2: complete (commits 49b1ec9..27b370f, all 7 font downloads OK, 12 ttf, +dup-name test, 169 green; verified files are real TrueType by controller)
- Task 3: complete (commits 27b370f..a2c80be, review Needs-fixes -> fixed; no rename (plan corrected), _via_fallback reuses _render_*_slide; +hermetic tests +selection asserts; 173 green)
- Task 4: complete (commits a2c80be..8ad3425, review Approved; +fix: lockup box-unpack guarded, _mono_logo logs, +5 coverage tests chip/mono/hook_logos; 182 green)
- Task 5: complete (commits 8ad3425..e62de50, review Approved; 3 existing build_images tests edited legitimately — default style is now centered=real layout not stub; hook suppresses bar/none accent; nits: item/close ~30-line dup, _fit_lines not refactored, body not hard-capped at 7 lines, pre-existing _legacy_fallback IndexError on sources==[])
- Task 6: pending — _layout_left_rail
- Task 7: pending — _layout_bottom_bar
- Task 8: pending — _layout_split
- Task 9: pending — _layout_magazine
- Task 10: pending — _layout_ticket
- Task 11: pending — wire pick_style into article_run.draft() + store style name
- Task 12: pending — sample-render script + full suite + visual QA

## Minor findings roll-up
(none yet)

## Notes
- Plan 1 (auto-publish) merged to local master as c8928cc; local master ahead 16 / behind 2
  of origin (behind = pipeline state-commits from Actions). NOT pushed — needs user.
- Layout tasks 5-10 have manual visual-QA steps; controller renders samples and surfaces to user.

## Deferred from Task 4 review (for final review / magazine layout task)
- F2: _logo_lockup brand name is always Be Vietnam Pro Bold (no fonts param). editorial/mono/rounded styles show a Lora/JetBrains/Nunito headline beside a BVP wordmark. Resolve if magazine layout needs the style face (add a font param) — else it's an intentional brand-consistency choice.
- F3: _hook_logos drops individually-failed logos for `tile` but keeps a glyph for chip/mono; add one docstring line.
