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
- Task 6: complete (commits e2ec0db..27e0df5, review Approved + fix; accent rail L, bar->underline downgrade, ghost number; fix: _handle_line gained left= kwarg so handle clears the rail. 186 green)
- Task 7: complete (commits 27e0df5..9100f93, review Needs-fixes -> fixed; accent bar bottom 45%, shadowed-palette recolour for handle/swipe on bar; fix: bulleted-item body capped 3 lines (measured all faces), _bottom_bar_close delegates to _centered_close. 189 green)
- Task 8: complete (commits 9100f93..cc7839d, review Approved; 14% tint band top half + 3px divider, close delegates to _centered_close; minors: no fits-above-lockup test, left-aligned body/bullets dup across layouts 6/7/8)
- Task 9: complete (commit be5af3d; _layout_magazine — forced editorial serif, 110px margins, tracked kicker, headline boxed by 2 hairline rules + accent_shape (underline/bracket only), body -> 2 columns when >6 col-width lines else 1, accent drop-cap hung in left gutter (first char sliced, no reflow), item lockup forced "mono", close -> _centered_close. 191 -> 194 green, no existing test edited. + fix 80b9d9c (review Needs-fixes): _logo_lockup gained name_font= kwarg, magazine passes serif fonts["bold"] so brand name matches; +_mag_wrap_body content_w param. 195 green. minors: drop-cap invisible-as-accent on mono-contrast (accent==ink); bracket/underline can sit near lower rule — Task 12 QA; left-aligned body/bullet dup now across layouts 6/7/8/9)
- Task 10: complete (commits 80b9d9c..9e39505, review Approved; inset dashed card over textured ground, perforation dots -> left content/right stub, ghost number in stub, close -> _centered_close; concerns for Task 12 QA: item body 6-line cap truncates mid-sentence on mono (bump to ~8-9), handle low-contrast in card footer)
- Task 11: complete (commit 34afe88, diff verified by controller — pick_style before build_images, style= kwarg, style_name in ds.put, failure -> "default"; 198 green)
- Task 12: complete (commit 3b48db4; all 24 rendered 1080x1350 no crash; caps raised: ticket body 12, bottom-bar block 52%+cap 5, left-rail/split 9; +test_no_layout_truncates_a_45_word_body; 199 green. 23/24 clean, mono-bar clips ~2 words of a 60+word body (cosmetic, real bodies 40-70w)). ALL 12 TASKS COMPLETE.

## Minor findings roll-up
(none yet)

## Notes
- Plan 1 (auto-publish) merged to local master as c8928cc; local master ahead 16 / behind 2
  of origin (behind = pipeline state-commits from Actions). NOT pushed — needs user.
- Layout tasks 5-10 have manual visual-QA steps; controller renders samples and surfaces to user.

## Deferred from Task 4 review (for final review / magazine layout task)
- F2: _logo_lockup brand name is always Be Vietnam Pro Bold (no fonts param). editorial/mono/rounded styles show a Lora/JetBrains/Nunito headline beside a BVP wordmark. Resolve if magazine layout needs the style face (add a font param) — else it's an intentional brand-consistency choice.
- F3: _hook_logos drops individually-failed logos for `tile` but keeps a glyph for chip/mono; add one docstring line.

## Shared-helper evolution (for final review awareness)
- Task 5 added: _pill, _fit_lines_font, _centre_lines, _centered_body_fill (local to images.py).
- Task 6 added: _handle_line gained `left: int = 80` kwarg (used by left-rail).
- Duplication watch: 34->30->28 body-shrink loop + bullet ellipse/wrap/text loop are near-identical across _centered_item and _left_rail_item (differ only by anchor). Candidate for one shared alignment-parameterised helper — deferred cleanup.

## Final whole-branch review (opus) — 3 rounds
R1 (eb5fa41..00ceebe): "With fixes" — Critical: (#1) settings.yaml images.brand's v4 accent/ink/muted overrode EVERY palette -> 12/24 styles invisible; (#2) Lora/JetBrains/Nunito vendored as variable fonts -> hairline headlines. Important: (#3) tools-less hook = 40% empty canvas; (#4) ticket handle straddles card border; (#5) no test on the production brand path.
Fix df921c4: #1 (drop 3 keys from settings.yaml), #2 (fontTools instancer -> static weights + OFL-NOTICE), #3 (_hook_marks helper), #4 (bottom= kwarg), #5 (test_production_config_every_style_is_legible), bonus _mono_logo opaque-favicon -> glyph.
R2 (00ceebe..df921c4): "No" — #3/#4 not actually closed: _draw_icon_fan ignored its box (fan painted over by bottom-bar block = 0px; straddled ticket perforation); ticket bottom=_TICKET_M+30 overshot -> dashed frame struck through footer text.
Fix 4541f63: _draw_icon_fan honours box=; ticket bottom=_TICKET_M+5; +test_toolless_hook_draws_a_visible_fallback_on_every_layout (fails on old tree with the 0px bottom-bar signature).
R3 (df921c4..4541f63): "Yes" — both criticals closed, verified by measurement. 244 tests. Minor follow-ups: fan test asserts visibility not placement; b.get("tile_icon","#1F2937") literal; warm-editorial muted/bg 3.46:1 (pre-existing); JetBrainsMono/Nunito italic not vendored (falls back to BVP).

ALL DONE — Plan 2 ready to merge. 24 styles, 6 layouts, auto-rotated per post, brand furniture identical across all, degrades to v4 on any failure.
