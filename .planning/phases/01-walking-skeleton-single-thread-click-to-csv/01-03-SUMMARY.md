---
phase: 01-walking-skeleton-single-thread-click-to-csv
plan: 03
subsystem: infra
tags: [pandas, matplotlib-ginput, csv-schema]

requires:
  - phase: 01-01
    provides: "src/segment/naming.py parse_flat_path/parse_photo_path for session-key derivation"
provides:
  - "src/calibrate/ruler_scale.py: px_per_cm() pure math, write_calibration_csv(), calibrate_ruler()/calibrate_folder() interactive layer, Stage-3 CLI"
  - "src/join/build_final_csv.py: EXACT_R_SCRIPT_COLUMNS, build_final_csv() merge+mm-convert+exact-schema, Stage-4 CLI"
affects: [01-05]

tech-stack:
  added: []
  patterns: ["pure math split from interactive ginput collection, so calibration is unit-testable without a display", "hard-fail ValueError naming unmatched sessions instead of silent NaN/drop on join"]

key-files:
  created: [src/calibrate/ruler_scale.py, src/join/build_final_csv.py, tests/test_calibrate.py, tests/test_join.py]
  modified: []

key-decisions:
  - "write_calibration_csv(rows, out_csv) added as the pure/testable layer beneath calibrate_folder — plan's exact signature adjusted slightly to fully honor its own 'split pure math from interactive' instruction"
  - "Date rendered via manual int()-based M/D/YY formatting, not strftime, for Linux/Mac cross-platform identical output (no %-d portability issue)"

patterns-established:
  - "Fill missing batch with empty string on both frames before merge, to avoid NaN-key silent drops on the join"

requirements-completed: [CAL-01, CAL-02, CSV-01, CSV-02, CSV-03]

duration: 20min
completed: 2026-07-08
status: complete
---

# Phase 1 Plan 03: Calibration + CSV Assembly Summary

**Per-session pixels/cm calibration and the exact R-script-column CSV assembly, both hard-failing loudly on any missing/unmatched calibration factor rather than fabricating one.**

## Performance
- **Duration:** ~20 min
- **Tasks:** 2 completed
- **Files modified:** 4

## Accomplishments
- `px_per_cm()` pure math verified against known distances; calibration stored per (date,batch), never global
- `build_final_csv()` produces a byte-exact R-script header and correct mm conversion, verified against a hand-computed spot check
- Hard-fail on unmatched calibration proven by test (names the unmatched session in the error)

## Task Commits
1. **Task 1: ruler_scale.py** + **Task 2: build_final_csv.py** — `c8a7534` (feat, combined)

## Files Created/Modified
- `src/calibrate/ruler_scale.py` — px_per_cm, write_calibration_csv, calibrate_ruler, calibrate_folder, main()
- `src/join/build_final_csv.py` — EXACT_R_SCRIPT_COLUMNS, build_final_csv, main()
- `tests/test_calibrate.py` — 4 tests, headless (Agg backend, no ginput exercised)
- `tests/test_join.py` — 4 tests: exact-header, mm-conversion, Date-format, missing-calibration raise

## Decisions Made
- Added `write_calibration_csv` as an explicit pure-layer function beneath the interactive `calibrate_folder`, so the plan's own "split pure math from interactive ginput" instruction is honored at the CSV-writing layer too, not just at `px_per_cm`

## Deviations from Plan
None materially — one added helper function for testability, no behavior change from plan intent.

## Issues Encountered
None.

## User Setup Required
The interactive `ginput`-based click collection in `calibrate_ruler` is NOT exercised by the automated suite (requires a display) — validate by hand on the Mac tomorrow, per SKELETON.md's Mac morning-test plan.

## Next Phase Readiness
Ready for Plan 05's orchestrator to wire the interactive calibration call and the full join. No blockers.

---
*Phase: 01-walking-skeleton-single-thread-click-to-csv*
*Completed: 2026-07-08*
