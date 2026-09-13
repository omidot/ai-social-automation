# Video Chart/Screenshot Cards — Subagent-Driven Execution Ledger

Plan: docs/superpowers/plans/2026-09-13-video-chart-screenshot-cards.md
Spec: docs/superpowers/specs/2026-09-13-video-chart-screenshot-cards-design.md
Base: a7543a9 (master tip at plan-execution start)

(A prior, unrelated plan's ledger — "News-First Content Refresh" — previously occupied
this file. That plan is fully merged to master; its history lives in git log, not here.
This file now tracks only the video-chart-screenshot-cards plan.)

## Tasks
- Task 1: complete (commit a7543a9..b3d0fae, review Approved; ChartSpec/ScreenshotSpec
  + Card.chart/screenshot/screenshot_file added to models.py, 4 new tests. 364 passed.)
- Task 2: complete (commit b3d0fae..0745bc4, review Approved; normalize()'s digit->numeral
  and section-final/last->invert/strike rules now skip cards with chart/screenshot set,
  2 new tests. 366 passed.)
- Task 3: complete (commit 0745bc4..814411f..385dd00, review Approved after 1 fix;
  build_prompt describes chart/screenshot card shapes, _validate() enforces
  num/chart/screenshot mutual exclusion + chart kind/item-count/value-type +
  screenshot query length, 9 new tests. Fix: shape-hint string was missing
  chart?/screenshot? (Important finding), fixed + 1 more test. 376 passed.)
  Minor findings deferred to final review: isinstance bool passes as numeric value
  (script.py ~104); mixed Vietnamese/English VideoScriptError message language.
- Task 4: complete (commit 385dd00..2dd807c, review Approved; render_variants_mjs
  emits 7-position rows [variant,anchor,num,motion_in,motion_out,chart,screenshot_file],
  golden fixture expected_variants.mjs updated, 1 new test. 377 passed.)
- Task 5: complete (commit 2dd807c..95d62ca, review Approved; align.mjs destructures
  the 2 new LAYOUT positions into c.chart/c.screenshotFile with truthy guards, 1 new
  test, node --check confirmed valid. 378 passed.)
- Task 6: complete (commit 95d62ca..92ecf39, review Approved; Pal.accent='#FF4D2E'
  added to both LIGHT/DARK in palette.ts, 1 new test. 379 passed.)
- Task 7: complete (commit 92ecf39..adca7f6, review Approved; Frame exported,
  Card type gains chart?/screenshotFile?, Stack/Stair/Strike retinted to pal.accent
  (Stair line190 vs Strike line256 verified distinct, not swapped), Numeral badge
  redesigned to bordered box, 3 new tests. 382 passed.)
- Task 8: complete (commit adca7f6..9eb5fd7, review Approved; media._shoot renamed
  to public capture_screenshot, screenshot()'s call site + 2 existing tests updated,
  1 new test, zero _shoot references remain. 383 passed.)
- Task 9: complete (commit 9eb5fd7..75a863c, review Approved; new
  src/pipeline/video/screenshot.py with ScreenshotError/search_top_url/
  search_and_capture (Google Custom Search + reuses media.capture_screenshot),
  5 new tests. 388 passed.) Minor finding deferred: unused `log` logger in
  screenshot.py (brief's own code, not implementer deviation).
- Task 10: complete (commit 75a863c..5f2c08c, review Approved; render_pending()
  now attempts screenshot capture per card before codegen.write, skips network
  entirely when secrets missing, falls back to plain card on ScreenshotError,
  3 new tests. Deviation (verified correct+harmless): hoisted `from . import
  codegen as _codegen` from function-local to module-level import so tests can
  monkeypatch render._codegen (brief's test code assumed this was already
  module-level; it wasn't). 391 passed.)
- Task 11: complete (commit 5f2c08c..33114e5..d778aa7, review Approved after 1 fix;
  new video/src/Chart.tsx (ChartCard: line/bar/hbar via SVG, pal.accent highlight),
  wired into KineticShort.tsx CardView before the variant switch, 2 new tests.
  Fix: guarded all 3 sub-components against empty items array + LineChart's
  single-item divide-by-zero (unreachable given Task 3's validation floor of
  2-3+ items, but defensive). 393 passed.)
- Task 12: complete (commit d778aa7..b7389da, review Approved; new
  video/src/Screenshot.tsx (ScreenshotCard: browser-chrome frame with 3 dots +
  Img via staticFile), wired into CardView after card.chart check / before
  variant switch, 2 new tests. No NaN-class fragility (single string, no array
  reduction) unlike Chart.tsx. 395 passed.) Minor findings deferred: FRAME_W vs
  Chart.tsx's W naming inconsistency; brief's prose mentioned a URL bar showing
  domain that its own code sample didn't include (doc inconsistency, not a bug).
- Task 13: complete (commit b7389da..e37ad4b, review Approved; video-render.yml
  installs Playwright chromium inside the existing go==1 gated step, adds
  GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX to Render+publish env. YAML parses, 395
  passed unchanged.)
- Task 14: complete (commit e37ad4b..2a381aa, review Approved; _FAKE_SCRIPT_JSON
  gains 1 chart card (bar, 2 items) + 1 pre-set screenshot_file card, new
  video/public/smoke-screenshot.png placeholder, 1 new test. word_count=162,
  cards=19, both in bounds. needs_node tests (13) pass on real Node v24.18.0.
  396 passed. ALL 14 TASKS COMPLETE.)

## Minor findings roll-up (for final whole-branch review to triage)
- T3: isinstance bool passes the chart-item numeric-value check (script.py ~104).
- T3: mixed Vietnamese/English VideoScriptError message language (dictated by
  test regexes, pre-existing pattern in the file already mixed).
- T9: unused `log` logger in screenshot.py (brief's own code).
- T12: Screenshot.tsx's `FRAME_W` vs Chart.tsx's `W` naming inconsistency for
  the identical 1080-T.PAD*2 computation.
- T12: plan's brief prose mentioned a URL-bar-with-domain for the screenshot
  card frame; the approved code sample never included one (doc inconsistency
  in the plan, not a bug -- 3-dot browser chrome only, no URL bar, matches
  global constraint's "optionally a URL bar" wording).
- T14: plan brief's inline rationale claimed the two smoke-fixture card
  replacements had equal word counts; actual delta is -4 words (23->19),
  harmless since the total (162) is still safely inside the 150-225 tolerance.

## Final whole-branch review (opus, range a7543a9..2a381aa, all 14 tasks)
Verdict: "Ready to merge with fixes." 0 Critical, 2 Important, 10 Minor. Full suite
396 passed + needs_node 13 pass on real Node v24.18.0 confirmed by the reviewer
directly (not just taken on report). Traced the full screenshot-failure path
end-to-end (script.py validate -> render.py capture-or-fallback -> codegen.py
serialize -> align.mjs thread -> Screenshot.tsx render) and confirmed no
field-name/shape mismatch and correct backward compatibility for pre-existing
5-element LAYOUT rows. Missing-secret path confirmed genuinely inert (no
network call, no side effect).

Important #1 (screenshot.py): `r.json()`/`.get`/`items[0]["link"]` could raise
JSONDecodeError/AttributeError/KeyError that escape ScreenshotError and crash
the WHOLE render instead of degrading one card -- violates the plan's own
"screenshot failure must never break a render" constraint. FIXED (self,
controller, not a subagent -- the dispatched fix-wave subagent hit a session
usage limit mid-run and produced no changes): wrapped in try/except, raises
ScreenshotError; 2 new tests.

Important #2 (video-render.yml): Playwright chromium install was unconditional
(on go==1) but NOT continue-on-error and NOT cached -- an optional feature's
installer could kill every render, including ones with zero screenshot cards
(the common case). FIXED: split into its own step with `continue-on-error:
true` + `actions/cache@v4` for `~/.cache/ms-playwright` (mirrors the existing
Remotion-browser cache pattern already in the same file).

Escalated plan/spec defect (was Minor T12 in per-task review, reviewer
correctly upgraded framing): the approved mockup (shown to and picked by the
user during brainstorming) had a URL bar showing the captured page's domain;
Task 12's approved code sample dropped it, and `render.py` was discarding the
URL `search_and_capture` already returns. FIXED properly (not just doc
amendment) since it was a real approved visual requirement: added
`Card.screenshot_url` end-to-end -- models.py (new field + roundtrip),
render.py (capture+store the URL), codegen.py (8th positional slot -> golden
fixture expected_variants.mjs updated), align.mjs (destructure `su` ->
`c.screenshotUrl`), layouts.tsx (Card type), Screenshot.tsx (renders the
domain, stripped of scheme, in a monospace url-bar div next to the 3 dots),
build_video.py smoke fixture (screenshot card now carries a real
screenshot_url too, so video-smoke.yml's real render exercises the url bar).

Also folded in 3 cheap Minor fixes while touching the same files: bool/non-
finite chart values now rejected (script.py, mirrors the `num` field's
documented `_coerce_num` lesson); capture_screenshot succeeding but leaving an
empty/missing file now raises ScreenshotError instead of deferring the crash
to Remotion's `<Img>` at render time; the previously-unused `log` logger in
screenshot.py now logs the resolved URL and the capture destination.

Deferred, not fixed (reviewer explicitly said "acceptable" / "optional
follow-up", not a blocker): T3's mixed VN/EN error message language; T9/T12's
naming nits (FRAME_W vs W, duplicated ChartItem type across layouts.tsx/
Chart.tsx -- no circular-import-free alternative was available at Task 7's
review point); Chart.tsx's `strokeDasharray={2000}` magic number (cosmetic,
`pathLength`-normalized rewrite would be cleaner but is pure polish); no
`tsc --noEmit` typecheck step exists in this repo for either video-smoke.yml
or CI generally (a real but pre-existing gap, out of scope for this plan);
T14's word-count-math inline comment inaccuracy (harmless, actual delta -4
not 0, total still safely in band).

After fixes: 400 passed (396 + 4: 2 malformed-search-response tests, 1 empty-
file test, 1 bool-chart-value test), needs_node 13/13 pass on real Node
(confirms the new 8-position LAYOUT format round-trips through the real
align.mjs + node --check). Fixed directly by the controller (no fix-wave
subagent re-dispatched after the first one hit a session usage limit with
zero commits landed) -- see commit immediately following this ledger entry.

## Notes
- Local: .venv/Scripts/python.exe, Python 3.12.3, run from D:\Automation Social.
- Baseline suite: 360 passed at a7543a9.
