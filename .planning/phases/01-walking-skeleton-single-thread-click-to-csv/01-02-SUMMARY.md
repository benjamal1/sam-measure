---
phase: 01-walking-skeleton-single-thread-click-to-csv
plan: 02
subsystem: infra
tags: [skimage, scipy, skeletonize, distance-transform, pandas]

requires:
  - phase: 01-01
    provides: "src/segment/naming.py stem_to_fields() for recovering CSV columns from mask filenames"
provides:
  - "src/measure/measure_masks.py: measure_mask() (area/diameter/stdev via skeleton+distance-transform), measure_folder() Stage-2 CLI"
affects: [01-05]

tech-stack:
  added: []
  patterns: ["skeletonize + distance_transform_edt + axis-sort endpoint-trim for width sampling", "pure-function + thin-CLI-wrapper split so measurement is independently testable"]

key-files:
  created: [src/measure/measure_masks.py, tests/test_measure.py]
  modified: []

key-decisions:
  - "Used skimage 0.26 non-deprecated API (closing/max_size) instead of the plan's literal binary_closing/min_size, which are deprecated in this scikit-image version — same behavior, no warnings"

patterns-established:
  - "Per-point skeleton width sampling (never bounding-box) enforced by a tapered-mask test that would fail under a bbox/minAreaRect implementation"

requirements-completed: [MEAS-01, MEAS-02]

duration: 15min
completed: 2026-07-08
status: complete
---

# Phase 1 Plan 02: Measurement Engine Summary

**skimage skeletonize + distance-transform width sampling turns a mask into area/diameter/stdev, validated on real SAM2 output within 3% of ImageJ ground truth (129.3px vs 125.5px avg diameter).**

## Performance
- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `measure_mask()` correctly measures a known-width synthetic strip, rejects bounding-box shortcuts (tapered-mask test), guards empty input, and trims frayed endpoints
- `measure_folder()` Stage-2 CLI globs a mask directory and writes schema-exact `measurements.csv`
- Cross-checked against real SAM2 output from plan 01-04 on the actual `5.11.JPG` ground-truth photo: 129.3px vs ImageJ's 125.5px avg diameter (within 3%), 0.81mm vs 0.79mm ImageJ ground truth

## Task Commits
1. **Task 1: measure_mask() TDD** + **Task 2: Stage-2 CLI** — `fc2f7b6` (feat, combined)

## Files Created/Modified
- `src/measure/measure_masks.py` — measure_mask, measure_folder, main()
- `tests/test_measure.py` — 6 tests: strip, empty-guard, tapered (anti-bbox), frayed-endpoint, no-heavy-import, folder-CLI

## Decisions Made
- Swapped the plan's literal `binary_closing`/`min_size` calls for scikit-image 0.26's current `closing`/`max_size` API (the old calls are deprecated in this env's pinned version) — identical behavior, zero warnings in the test run

## Deviations from Plan
None materially — API name swap only, same semantics.

## Issues Encountered
None.

## User Setup Required
None.

## Next Phase Readiness
Ready for Plan 05's end-to-end orchestrator to call `measure_mask`/`measure_folder` directly. StDev runs higher than ImageJ's (23.7 vs 17.7px on the real sample) — expected given the simpler axis-sort method vs true perpendicular measurement (D-04, deferred to v2); flag for Phase 2's MEAS-03 validation pass.

---
*Phase: 01-walking-skeleton-single-thread-click-to-csv*
*Completed: 2026-07-08*
