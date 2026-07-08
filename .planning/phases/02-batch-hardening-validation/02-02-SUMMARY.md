---
phase: 02-batch-hardening-validation
plan: 02
subsystem: testing
tags: [pandas, hard-fail, data-integrity, csv-join, pytest]

# Dependency graph
requires:
  - phase: 01-walking-skeleton-single-thread-click-to-csv
    provides: "build_final_csv (Stage-4 merge/mm-convert/exact-R-columns) and frozen intermediate CSV schema"
provides:
  - "Hardened CAL-03/CSV-04 hard-fail contract in build_final_csv.py: unmatched-guard message names both the unmatched (date,batch) session and the affected thread id(s)"
  - "Empty/missing calibration.csv treated as zero calibration rows, producing a clear ValueError instead of a bare pandas EmptyDataError"
  - "No-stale-output guarantee: a hard-failed run unlinks any pre-existing output_csv before raising"
  - "Requirement-ID-labeled regression suite (tests/test_hard_fail_calibration.py) covering session-missing, row-unmatched, empty-calibration, stale-output-removal, and multi-thread happy-path scenarios"
affects: [batch-hardening-validation, join, csv-assembly]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hard-fail-before-write: unmatched-guard raise happens strictly before the only to_csv call on real output, guaranteeing atomic all-or-nothing final.csv"
    - "Empty-file-as-zero-rows: catch pd.errors.EmptyDataError at the read boundary and normalize to an empty DataFrame with the expected columns, so downstream logic (and its error messages) stays uniform regardless of whether calibration.csv is missing rows or missing entirely"

key-files:
  created:
    - tests/test_hard_fail_calibration.py
  modified:
    - src/join/build_final_csv.py

key-decisions:
  - "CAL-03 and CSV-04 share one code path (the post-merge NaN px_per_cm check) rather than two separate guards, since both requirements describe the same underlying failure (a session with no matching calibration row) viewed from two angles (session-level vs thread-row-level traceability) — the single error message now names both."
  - "An empty calibration.csv is normalized to a zero-row DataFrame with the expected columns at the read boundary (_read_calibration), so it flows through the existing unmatched-guard and produces the same clear, named ValueError as any other missing-session case, rather than adding a second bespoke error path."
  - "Task 2's full requirement-ID-labeled test suite (5 named tests) was written as Task 1's TDD RED step, since the plan's Task 2 <behavior> spec was fully known in advance and needed to exist to drive Task 1's implementation. Task 2 required no additional commit — its acceptance criteria were already satisfied by the RED/GREEN commits."

patterns-established:
  - "Requirement-ID test naming: test_CAL_03_* / test_CSV_04_* prefixes make hard-fail contracts greppable and regression-proof (grep -nE 'CAL_03|CSV_04' tests/)."

requirements-completed: [CAL-03, CSV-04]

# Metrics
duration: 25min
completed: 2026-07-08
status: complete
---

# Phase 02 Plan 02: Hard-Fail Calibration Contract Summary

**Hardened build_final_csv's CAL-03/CSV-04 unmatched-calibration guard to name both session and thread id, treat empty calibration.csv as a clear hard-fail instead of a bare pandas error, and unlink any stale final.csv on failure — backed by a 5-test requirement-ID-labeled regression suite.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-08T19:34:00Z (approx.)
- **Completed:** 2026-07-08T19:58:48Z
- **Tasks:** 2 (2 completed)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `build_final_csv` now raises a single ValueError naming BOTH the unmatched (date,batch) session(s) (CAL-03) AND the affected thread id(s) (CSV-04), before any output write.
- Empty or zero-byte `calibration.csv` no longer raises a bare `pandas.errors.EmptyDataError` — it's normalized to zero calibration rows and flows through the same named hard-fail path.
- On hard-fail, any pre-existing `output_csv` from a prior run is unlinked before the raise, so a failed run can never leave a stale `final.csv` that looks current (Pitfall 4).
- `tests/test_hard_fail_calibration.py` adds 5 requirement-ID-labeled tests (`test_CAL_03_*`, `test_CSV_04_*`, plus a multi-thread happy-path proof) — full fast suite grew from 52 to 57 passing tests with zero regressions.

## Task Commits

Both tasks were TDD (`tdd="true"`); Task 2's full deliverable was produced as part of Task 1's RED step (see Decisions Made below), so there is no separate Task 2 commit — its acceptance criteria were already satisfied.

1. **Task 1: Harden build_final_csv hard-fail contract (CAL-03 + CSV-04)**
   - `6059959` (test) — add failing CAL-03/CSV-04 hard-fail contract tests (RED: 3 of 5 new tests failed against the pre-hardening implementation)
   - `97c1410` (feat) — harden CAL-03/CSV-04 hard-fail contract in build_final_csv (GREEN: all 5 new tests + 4 existing test_join.py tests pass)
2. **Task 2: Requirement-ID-labeled hard-fail test suite** — no additional commit; `tests/test_hard_fail_calibration.py` already contained the full 5-test suite specified in this task's `<behavior>` (written during Task 1's RED step). Verified via `pytest tests/test_hard_fail_calibration.py -q` (5 passed) and `grep -nE "CAL_03|CSV_04"` (4 matches, both requirement IDs present).

**Plan metadata:** (pending — see Final Commit below)

## Files Created/Modified
- `src/join/build_final_csv.py` — added `_read_calibration` (EmptyDataError → zero-row frame), `_unmatched_hard_fail_message` (names session + thread ids), hoisted `output_csv = Path(output_csv)` to function top, and unlinks a pre-existing `output_csv` before raising on hard-fail. `EXACT_R_SCRIPT_COLUMNS`, the mm-conversion math, and `_render_date` are unchanged.
- `tests/test_hard_fail_calibration.py` (new) — 5 tests: `test_CAL_03_session_without_ruler_calibration_hard_fails`, `test_CSV_04_unmatched_thread_row_hard_fails_no_partial_output`, `test_CAL_03_empty_calibration_file_hard_fails_clearly`, `test_CSV_04_hard_fail_removes_stale_final_csv`, `test_happy_path_multi_thread_still_writes`.

## Decisions Made
- CAL-03 and CSV-04 are implemented as one code path (see key-decisions above) — a single hard-fail message serves both requirement angles rather than duplicating the guard.
- Empty calibration.csv is normalized at the read boundary rather than special-cased at the raise site, keeping the raise logic single-sourced.
- Task 2's full test suite was written during Task 1's RED phase because its exact test names/behavior were already fully specified in the plan and were needed to drive Task 1's GREEN implementation correctly (TDD requires the tests to exist before the fix). This is noted as a deviation from the literal task-by-task commit sequencing, not a scope change — all acceptance criteria for both tasks are met.

## Deviations from Plan

### Auto-fixed Issues

None — no Rule 1/2/3/4 auto-fixes were needed. The only note is the RED-phase sequencing above (Task 2's test file content landed in Task 1's `test(...)` commit), which is a TDD-ordering consequence, not an unplanned code change, security fix, or architectural decision.

---

**Total deviations:** 0 auto-fixed
**Impact on plan:** None. Both tasks' acceptance criteria are fully met; no scope creep; no untested code paths added.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CAL-03 and CSV-04 hard-fail contracts are now formalized, requirement-ID-labeled, and regression-proof for the batch-hardening phase.
- No blockers for plans 02-01 (EXPT-04/CSV-05, already merged) or 02-03 (MEAS-03) — this plan's file scope (`src/join/build_final_csv.py`, `tests/test_hard_fail_calibration.py`) does not overlap either.

---
*Phase: 02-batch-hardening-validation*
*Completed: 2026-07-08*

## Self-Check: PASSED
- FOUND: src/join/build_final_csv.py
- FOUND: tests/test_hard_fail_calibration.py
- FOUND: commit 6059959 (test)
- FOUND: commit 97c1410 (feat)
