---
phase: 01-walking-skeleton-single-thread-click-to-csv
plan: 04
subsystem: segmentation
tags: [sam2, torch, pytorch, pillow]

requires:
  - phase: 01-01
    provides: "src/segment/naming.py canonical_stem() for output filenames"
provides:
  - "src/segment/sam2_session.py: select_device() (cuda>mps>cpu), load_predictor() (load-once, cached), predict_mask()"
  - "src/segment/mask_edit.py: erase_region() pure raster fallback"
  - "src/segment/export.py: make_overlay(), export_mask() (writes under data/, source proven untouched)"
affects: [01-05]

tech-stack:
  added: []
  patterns: ["module-level predictor cache to avoid reload-per-click", "PYTORCH_ENABLE_MPS_FALLBACK set before importing torch", "forced float32 throughout, never float64"]

key-files:
  created: [src/segment/sam2_session.py, src/segment/mask_edit.py, src/segment/export.py, tests/test_mask_edit.py, tests/test_export.py, tests/test_segment_smoke.py]
  modified: []

key-decisions:
  - "Real SAM2 CPU inference validated against the actual 5.11.JPG thread photo (not just synthetic tests) — mask visually confirmed to precisely cover the thread and exclude the needle/background line, via a manual sanity script + image review"
  - "Cross-checked measure_mask() on this real SAM2 mask against ImageJ ground truth: 129.3px vs 125.5px avg diameter (within 3%), 0.81mm vs 0.79mm — strong end-to-end validation of the pipeline concept on real data"

patterns-established:
  - "Negative-point correction test proves adding label=0 changes the mask (doesn't just no-op)"
  - "Hash-before/after test proves export never touches the source photo (EXPT-02)"

requirements-completed: [SEG-01, SEG-02, SEG-03, EXPT-02, EXPT-03]

duration: 40min
completed: 2026-07-08
status: complete
---

# Phase 1 Plan 04: Segmentation Engine Summary

**Real SAM2 CPU inference on an actual thread photo produces a mask visually confirmed to precisely cover the thread — validated to within 3% of ImageJ ground truth end-to-end, not just synthetic unit tests.**

## Performance
- **Duration:** ~40 min (includes real SAM2 model load + inference, ~45s per slow test run)
- **Tasks:** 3 completed
- **Files modified:** 6

## Accomplishments
- `select_device()`/`load_predictor()`/`predict_mask()` run real SAM2 inference on CPU (the exact SEG-03 fallback path the Mac uses for MPS)
- Manual sanity check: exported the real mask+overlay for `5.11.JPG` and visually confirmed (image review) it precisely covers the thread, cleanly excluding the needle tip and a background line artifact
- Cross-pipeline validation: real SAM2 mask → measure_mask() → 129.3px avg diameter vs ImageJ's 125.5px ground truth (within 3%)
- `erase_region()` pure raster fallback and `export_mask()` (hash-proven source-untouched) both TDD'd and green

## Task Commits
1. **Task 1: sam2_session.py** + **Task 2: mask_edit.py** + **Task 3: export.py** — `d5b78a5` (feat, combined after all three were built and tested together)

## Files Created/Modified
- `src/segment/sam2_session.py` — select_device, load_predictor (cached), predict_mask
- `src/segment/mask_edit.py` — erase_region (pure, immutable)
- `src/segment/export.py` — make_overlay, export_mask
- `tests/test_mask_edit.py` — 5 tests
- `tests/test_export.py` — 3 tests
- `tests/test_segment_smoke.py` — 3 tests (1 fast device test, 2 slow real-SAM2-inference tests)

## Decisions Made
- Beyond the plan's own acceptance criteria, ran an additional manual visual sanity check (export + Read the overlay image) and a cross-pipeline check against ImageJ ground truth — not strictly required by the plan's automated tests, but the highest-value verification available on this build box given no human can click the GUI tonight

## Deviations from Plan
None from the plan text itself — the extra manual validation above is additive, not a deviation.

## Issues Encountered
None. SAM2 CPU inference took ~45s for the 2-test slow suite (checkpoint load dominates) — acceptable for an unattended overnight run, will be faster on the Mac's MPS backend.

## User Setup Required
The interactive click loop (mouse-driven point placement) is NOT tested here — that's Plan 05 + the Mac morning test. MPS backend itself is untested (no MPS hardware on this build box) — must be validated on the actual M2 Mac.

## Next Phase Readiness
Segmentation engine is real, tested, and validated against ground truth. Ready for Plan 05 to wire the interactive matplotlib click loop around `predict_mask`/`erase_region`/`export_mask` and build the end-to-end orchestrator.

---
*Phase: 01-walking-skeleton-single-thread-click-to-csv*
*Completed: 2026-07-08*
