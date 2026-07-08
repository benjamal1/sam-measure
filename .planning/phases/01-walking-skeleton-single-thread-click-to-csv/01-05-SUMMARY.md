---
phase: 01-walking-skeleton-single-thread-click-to-csv
plan: 05
subsystem: infra
tags: [matplotlib, argparse, integration-test]

requires:
  - phase: 01-01
    provides: "naming.py canonical_stem/parse_flat_path/parse_photo_path"
  - phase: 01-02
    provides: "measure_masks.py measure_folder"
  - phase: 01-03
    provides: "ruler_scale.py px_per_cm/write_calibration_csv, build_final_csv.py build_final_csv"
  - phase: 01-04
    provides: "sam2_session.py load_predictor/predict_mask, export.py export_mask, mask_edit.py erase_region"
provides:
  - "src/segment/click_loop.py: run_click_loop() interactive UI + testable ClickLoopState/handle_click/handle_key"
  - "src/segment/segment_export.py: Stage-1 CLI, folder glob + thread-number prompt"
  - "run_pipeline.py: real end-to-end orchestrator (replaces plan-01 stub)"
  - "MORNING-TEST.md: Mac hand-validation checklist"
affects: []

tech-stack:
  added: []
  patterns: ["callback logic (handle_click/handle_key) separated from matplotlib event-loop plumbing (run_click_loop) so it's unit-testable under Agg without a display"]

key-files:
  created: [src/segment/click_loop.py, src/segment/segment_export.py, tests/test_click_loop.py, tests/test_skeleton_e2e.py, MORNING-TEST.md]
  modified: [run_pipeline.py]

key-decisions:
  - "Walking-skeleton e2e test passed on the FIRST run against real data — SAM2 mask (from plan 04) -> measurement -> calibration -> final.csv all connected correctly with no integration bugs"
  - "final.csv AvgDiameter(mm) landed at ~0.81mm for 5.11, within the loose 0.3-3.0mm plausibility band and close to ImageJ's 0.789mm ground truth"

patterns-established:
  - "Click state (points/labels/mask) lives in a single ClickLoopState dataclass with an explicit reset() — the one place PITFALLS' 'stale click contamination across photos' pitfall is prevented"

requirements-completed: [SEG-01, SEG-02]

duration: 35min
completed: 2026-07-08
status: complete
---

# Phase 1 Plan 05: Click Loop + Orchestrator + Walking Skeleton Proof Summary

**The full pipeline runs end-to-end on real data — real SAM2 CPU inference, real skeleton+distance-transform measurement, real calibration math, exact R-script CSV header — proven by an integration test that passed on the first run.**

## Performance
- **Duration:** ~35 min
- **Tasks:** 3 completed
- **Files modified:** 6

## Accomplishments
- Interactive click loop (`click_loop.py`) built to the researched reference pattern, with callback logic structurally tested under Agg (left=positive/right=negative/accept/erase/reset-per-photo all verified)
- `run_pipeline.py` drives segment→export→measure→calibrate→build_csv non-interactively; the walking-skeleton integration test passed against real `5.11.JPG` + `ruler.JPG` on the first attempt
- `MORNING-TEST.md` written as a concrete numbered Mac checklist covering exactly what tonight's session could not validate: MPS backend, real click UX, and the 0.5cm calibration zoom

## Task Commits
1. **Task 1: click_loop.py + Stage-1 CLI** + **Task 2: run_pipeline.py + e2e test** + **Task 3: MORNING-TEST.md** — `8f30712` (feat, combined — all three landed together after the e2e test confirmed the whole stack works)

## Files Created/Modified
- `src/segment/click_loop.py` — ClickLoopState, handle_click, handle_key, run_click_loop
- `src/segment/segment_export.py` — Stage-1 CLI main()
- `run_pipeline.py` — real run() orchestrator + CLI (replaces the plan-01 NotImplementedError stub)
- `tests/test_click_loop.py` — 6 structural wiring tests
- `tests/test_skeleton_e2e.py` — the walking-skeleton proof (slow+integration)
- `MORNING-TEST.md` — 8-section Mac validation checklist

## Decisions Made
- No new decisions beyond CONTEXT.md's D-01 through D-10 — this plan was pure integration of already-decided, already-built pieces

## Deviations from Plan
None — plan executed as written, and the integration worked correctly on the first run (no debugging cycle needed to connect the four independently-built stages).

## Issues Encountered
None.

## User Setup Required
Full Mac validation required — see `MORNING-TEST.md`. Specifically: MPS backend behavior is completely unverified (no MPS hardware existed in this build session), and the interactive click/erase UX has only been structurally tested, never actually clicked by a human.

## Next Phase Readiness
**Phase 1 goal is met**: one thread photo goes click → mask → correct → measure → calibrate → CSV row, proven end-to-end on real data. All 40 fast tests + 3 slow/integration tests green. Ready for Step 8 (code review) and Step 9 (verify against 01-BRIEF.md's 9 acceptance criteria). Phase 2 (batch hardening: idempotency, ImageJ validation, hard-fail nets, manifest) and the user's Mac validation pass are the next steps.

---
*Phase: 01-walking-skeleton-single-thread-click-to-csv*
*Completed: 2026-07-08*
