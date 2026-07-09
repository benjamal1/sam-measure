---
phase: 02-batch-hardening-validation
plan: 04
subsystem: pipeline
tags: [pandas, matplotlib, sam2, iqr-outliers, calibration]

# Dependency graph
requires:
  - phase: 02-batch-hardening-validation (plan 02-02)
    provides: CAL-03/CSV-04 hard-fail contract in build_final_csv (unmatched-calibration guard, no-stale-output)
provides:
  - Recursive Condition/Batch/Day folder walk in segment_export (no per-photo CLI restart)
  - Manual condition/thread entry as authoritative over path-parsed guesses
  - Multi-thread-per-photo labeling loop (click_loop return-value-driven reclick/advance)
  - resolve_calibration_factor: same-batch earlier-date calibration fallback (CAL-02)
  - mad_px (median absolute deviation) in measure_masks, additive alongside area/diameter/stdev
  - flag_outliers: IQR-based outlier flagging within (date,batch,condition) groups (QOL-02)
  - final.csv extended with area_px/area_mm2/mad_px/mad_mm/flag/flag_reason after the frozen R-script columns
affects: [phase-3-batch-cleanup, v2-qol-features]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Explicit override > path-parsed guess > interactive prompt resolution order (_resolve_field), applied consistently for condition/thread"
    - "click_loop on_accept return-value contract: truthy=advance (state.done), falsy=reclick same photo"
    - "Per-mask idempotency/thread resolution deferred into on_accept for photos with no pre-loop thread guess (multi-mask support)"

key-files:
  created:
    - src/validate/__init__.py
    - src/validate/outliers.py
    - tests/test_segment_export.py
    - tests/test_outliers.py
  modified:
    - src/segment/naming.py
    - src/segment/segment_export.py
    - src/segment/click_loop.py
    - src/calibrate/ruler_scale.py
    - src/measure/measure_masks.py
    - src/join/build_final_csv.py
    - tests/test_naming.py (unchanged behaviorally — no edits ended up needed)
    - tests/test_click_loop.py
    - tests/test_calibrate.py
    - tests/test_measure.py
    - tests/test_join.py
    - tests/test_hard_fail_calibration.py

key-decisions:
  - "Task 1's condition/thread resolution keeps flat-legacy/explicit-override paths fully non-interactive (preserves existing EXPT-04 idempotency/--force tests verbatim); true per-photo/per-mask interactive prompting only fires for genuinely unknown (nested-path) values"
  - "Multi-mask-per-photo (Task 2) required consequential changes to segment_export.py's on_accept closure (not just click_loop.py) so each accept resolves its own thread and idempotency-checks independently — documented as necessary follow-through, not scope creep"
  - "build_final_csv keeps the SAME returned DataFrame object as what's written to final.csv (9 exact columns + 6 appended), rather than returning a stripped-down 9-column object — required updating two literal exact-column-count assertions in tests/test_hard_fail_calibration.py (outside this task's declared file scope) since they are structurally incompatible with the plan's own must-have of appending columns; the underlying CAL-03/CSV-04 hard-fail guarantees in that file are fully intact and untouched"
  - "area_mm2 uses px_per_cm/10 squared (area scales with the square of the linear pixel-to-cm factor) — documented inline as a distinct conversion from the linear AvgDiameter(mm)/StDev(mm)/mad_mm formula"

requirements-completed: [EXPT-01, MEAS-01, MEAS-02, CAL-01, CAL-02, QOL-02]

# Metrics
duration: 15min
completed: 2026-07-09
status: complete
---

# Phase 2 Plan 4: Batch UX Redesign + Area/MAD/Outlier Measurement Columns Summary

**Recursive Condition/Batch/Day folder walk with manual-entry-authoritative labeling, multi-thread-per-photo click loop, same-batch date-fallback ruler calibration, and MAD/area/IQR-outlier columns appended to final.csv without touching the frozen R-script column contract.**

## Performance

- **Duration:** ~15 min (across 6 task commits)
- **Started:** 2026-07-09T00:26Z (first task commit)
- **Completed:** 2026-07-09T04:39Z
- **Tasks:** 6/6 completed
- **Files modified:** 12 (6 source, 6 test — plus 2 new source files, 2 new test files)

## Accomplishments

- `segment_export.export_folder` now recursively discovers photos under any depth of nesting (`Condition/Batch/Day`), excludes `ruler_*`/`Ruler_*` photos case-insensitively, and treats manually-supplied condition/thread as authoritative over path-parsed guesses.
- `click_loop.py` supports multiple labeled masks per photo: `on_accept`'s return value (truthy=advance, falsy=reclick) drives a new `state.done` flag; click-state resets after every accept (a new reset trigger alongside the existing per-new-photo reset) with a dedicated regression test proving no cross-contamination between two accepts on the same photo (Pitfall-2 guard).
- `resolve_calibration_factor` resolves exact `(date,batch)` matches first, else the closest strictly-earlier same-batch date, never crossing batches even when a different-batch row is closer in date.
- `measure_mask`/`measure_folder` gained `mad_px` (median absolute deviation), additive after the existing `area_px`/`avg_diameter_px`/`stdev_px` columns.
- New `src/validate/outliers.py::flag_outliers` — pure IQR-based flagging within `(date,batch,condition)` groups, skipping groups under 4 rows.
- `build_final_csv` now resolves calibration row-wise via `resolve_calibration_factor` (preserving the full CAL-03/CSV-04 hard-fail contract from plan 02-02) and appends `area_px, area_mm2, mad_px, mad_mm, flag, flag_reason` after the unchanged, 9-column `EXACT_R_SCRIPT_COLUMNS`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Recursive folder walk + manual condition/thread entry** — `2bf5b4e` (feat)
2. **Task 2: Multi-thread-per-photo label loop (click_loop + segment_export wiring)** — `2bc62d4` (feat)
3. **Task 3: Ruler date-matching with same-batch fallback** — `c160e7b` (feat)
4. **Task 4: area_mm2 + MAD in measure_masks** — `a03aa53` (feat)
5. **Task 5: Outlier flagging module** — `5fad5e2` (feat)
6. **Task 6: Wire calibration date-fallback + area/MAD/outlier into build_final_csv** — `56bc8af` (feat)

**Plan metadata:** (this commit, docs: complete plan)

_All 6 tasks were TDD-executed (RED test written and confirmed failing, then GREEN implementation) within their own commits rather than split into separate test/feat commits — each commit's diff includes both the new/updated tests and the implementation that makes them pass._

## Files Created/Modified

- `src/segment/naming.py` — docstring updated to frame `parse_photo_path`/`parse_flat_path` as advisory-only guesses (EXPT-01 revised); no behavioral change
- `src/segment/segment_export.py` — recursive `rglob`-based discovery, ruler exclusion, `_resolve_field` (explicit override > guess > prompt), multi-mask `on_accept` restructuring, `--thread` CLI flag
- `src/segment/click_loop.py` — `ClickLoopState.done` flag, `on_accept` return-value-driven reclick/advance, `run_click_loop` closes the window on `state.done`
- `src/calibrate/ruler_scale.py` — new `resolve_calibration_factor` (pure, same-batch date-fallback)
- `src/measure/measure_masks.py` — `mad_px` added to `measure_mask` and `_CSV_COLUMNS`/`measure_folder`
- `src/validate/__init__.py` — new (package didn't yet exist; plan 02-03 normally originates it, hasn't run in this session)
- `src/validate/outliers.py` — new, `flag_outliers` pure IQR flagging
- `src/join/build_final_csv.py` — row-wise calibration resolution via `resolve_calibration_factor`, `area_mm2`/`mad_mm`/`flag`/`flag_reason` appended after `EXACT_R_SCRIPT_COLUMNS`
- `tests/test_segment_export.py` — new; recursive discovery, ruler exclusion, manual-override-wins, multi-mask, legacy-no-prompt regression coverage
- `tests/test_click_loop.py` — extended with 7 new tests for the multi-mask reclick/advance/reset contract
- `tests/test_calibrate.py` — extended with `resolve_calibration_factor` coverage (plan named `tests/test_ruler_scale.py`, which does not exist in this repo)
- `tests/test_measure.py` — extended with `mad_px` coverage (plan named `tests/test_measure_masks.py`, which does not exist in this repo)
- `tests/test_outliers.py` — new, `flag_outliers` coverage
- `tests/test_join.py` — extended with date-fallback-success, cross-batch-rejection, area/MAD/outlier-column coverage; two pre-existing assertions widened from exact-equality to prefix-equality (see Decisions)
- `tests/test_hard_fail_calibration.py` — two literal exact-column assertions in `test_happy_path_multi_thread_still_writes` widened to prefix checks (see Deviations); all 4 CAL-03/CSV-04/no-stale-output hard-fail tests pass completely unchanged

## Decisions Made

See `key-decisions` in frontmatter. In short: kept the existing non-interactive/idempotent code paths byte-for-byte compatible wherever a value is already knowable without prompting (flat-legacy convention, explicit overrides), and only introduced real interactivity where the data is genuinely unknown until a human looks at the photo — consistent with the plan's "manual entry authoritative, not a fallback" framing without breaking the pre-existing batch/CI-friendly test surface.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created `src/validate/__init__.py`**
- **Found during:** Task 5 (outlier flagging module)
- **Issue:** Task 5's own read_first references `src/validate/__init__.py` as an "existing package, pure-module convention from plan 02-03" — but plan 02-03 has not executed in this session, so `src/validate/` didn't exist yet, blocking Task 5 entirely.
- **Fix:** Created an empty `src/validate/__init__.py`. Compatible with whatever plan 02-03 adds later (it will not conflict or need to overwrite this file's content).
- **Files modified:** `src/validate/__init__.py`
- **Committed in:** `5fad5e2` (Task 5 commit)

**2. [Rule 2 - Missing Critical] Restructured `segment_export.py`'s `on_accept` for real multi-mask support (Task 2 follow-through)**
- **Found during:** Task 2 (click_loop.py's own declared file scope is `click_loop.py`/`tests/test_click_loop.py` only, but Task 2's own action text says the post-accept prompt is "driven by segment_export")
- **Issue:** Without updating `segment_export.py`'s `on_accept` closure to resolve its own thread per accept (instead of reusing one pre-computed value for the whole photo), the multi-thread-per-photo feature described in the plan's `must_haves.truths` would be unreachable dead code — two accepts on the same nested-path photo would collide on an identical stem and silently overwrite each other's mask.
- **Fix:** `on_accept` now resolves `mask_thread` fresh on every call (short-circuiting to a pre-known value only when the thread is already fully known via override/flat-legacy-guess, to avoid any prompt calls in those cases), independently idempotency-checks each resulting stem, and returns `not prompt_more_threads(...)` to drive the reclick/advance decision — except when the thread was already fully known pre-loop, in which case it auto-advances without asking (preserving exact pre-multi-mask behavior and non-interactive test compatibility for that case).
- **Files modified:** `src/segment/segment_export.py`, `tests/test_segment_export.py`
- **Committed in:** `2bc62d4` (Task 2 commit)

**3. [Rule 1 - Bug/structural incompatibility] Widened two literal column-equality assertions in `tests/test_hard_fail_calibration.py`**
- **Found during:** Task 6 (wiring area/MAD/outlier columns into `build_final_csv`)
- **Issue:** `test_happy_path_multi_thread_still_writes` (in a file outside Task 6's declared `<files>` scope) hard-codes `list(df.columns) == EXACT_R_SCRIPT_COLUMNS` and `header_line == EXACT_HEADER` — both strict 9-column equality checks that are structurally incompatible with the plan's own explicit must-have of appending 6 new columns after `EXACT_R_SCRIPT_COLUMNS`. Any implementation satisfying the plan's stated objective would fail this specific assertion.
- **Fix:** Widened both assertions to prefix checks (`df.columns[:len(EXACT_R_SCRIPT_COLUMNS)] == EXACT_R_SCRIPT_COLUMNS` and `header_line.startswith(EXACT_HEADER + ",")`), preserving the actual guarantee under test (frozen columns come first, unchanged name/order) without weakening it. All other assertions in this file, and all 4 of its CAL-03/CSV-04/no-stale-output hard-fail tests, are byte-for-byte unchanged and pass.
- **Files modified:** `tests/test_hard_fail_calibration.py`
- **Verification:** `pytest tests/test_hard_fail_calibration.py tests/test_join.py -q` — 14/14 passed.
- **Committed in:** `56bc8af` (Task 6 commit)

**4. [Documentation] Extended actual existing test modules instead of creating plan-named files that don't exist in this repo**
- **Found during:** Tasks 3 and 4
- **Issue:** The plan's frontmatter lists `tests/test_ruler_scale.py` and `tests/test_measure_masks.py` as files to modify — neither exists in this repository; the actual modules are `tests/test_calibrate.py` and `tests/test_measure.py`.
- **Fix:** Extended the actual existing test files rather than creating new parallel files with the plan's assumed names (which would split coverage of the same production modules across two files pointlessly).
- **Files modified:** `tests/test_calibrate.py`, `tests/test_measure.py`
- **Committed in:** `c160e7b`, `a03aa53`

---

**Total deviations:** 4 (1 blocking-issue fix, 1 missing-critical-functionality fix, 1 structural-incompatibility test fix, 1 documentation/naming note)
**Impact on plan:** All auto-fixes were necessary for the plan's own stated must-haves to be reachable/testable at all. No scope creep beyond what each task's behavior required.

## Issues Encountered

None beyond the deviations above — all resolved inline during TDD execution, no unresolved blockers.

## User Setup Required

None — no external service configuration required.

## What Still Needs Hands-On Mac Validation

Per the plan's own `<verification>` note (same pattern as Phase 1's MORNING-TEST.md): Task 2's actual interactive multi-mask click-loop UX (does "label another thread on this photo?" feel natural, does the window genuinely stay open and re-render correctly between accepts, does SAM2/MPS behave as expected across two rapid re-clicks on the same loaded image) is **not verifiable headlessly**. The Agg-backend unit tests in `tests/test_click_loop.py` and the DI-stubbed tests in `tests/test_segment_export.py` prove the underlying state machine and wiring are correct (no click-state leakage, correct stem resolution, correct idempotency), but the actual on-screen feel of accept → prompt → reclick-or-advance needs a hands-on pass on the user's M2 Mac with real SAM2 inference and a real nested `Condition/Batch/Day` folder, ideally including at least one genuinely multi-thread photo.

## Next Phase Readiness

- All 6 tasks complete; full fast suite green (84 passed, 3 skipped [real-data-dependent, no Nextcloud mount on this build machine], 4 deselected [slow/integration], 0 failed) — zero regressions against the pre-existing 57ish passing baseline from plan 02-02.
- `src/validate/__init__.py` now exists ahead of plan 02-03 — when 02-03 executes, it should find the package already present and simply add `imagej_validation.py` alongside `outliers.py` without conflict.
- The real-world validation pass (multi-thread photo, full nested tree, real ruler date-fallback) should happen on the user's actual reorganized Nextcloud folder once Mac-side hands-on testing is done.

---
*Phase: 02-batch-hardening-validation*
*Completed: 2026-07-09*

## Self-Check: PASSED

All 15 claimed created/modified files confirmed present on disk; all 6 task commit hashes
(`2bf5b4e`, `2bc62d4`, `c160e7b`, `a03aa53`, `5fad5e2`, `56bc8af`) confirmed in `git log`.
