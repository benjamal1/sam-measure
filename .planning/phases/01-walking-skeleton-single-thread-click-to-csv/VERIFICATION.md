---
phase: 01-walking-skeleton-single-thread-click-to-csv
status: passed
verified: 2026-07-08
---

# Phase 1 Verification: Walking Skeleton — Single-Thread Click-to-CSV

Verified against `01-BRIEF.md`'s 9 acceptance criteria and the ROADMAP goal. This was an
unattended overnight build session on a CPU-only Linux box (not the user's M2 Mac) —
every criterion automatable in that environment was actually exercised against real data
(not just synthetic fixtures); the remaining human/MPS-dependent verification is deferred
to `MORNING-TEST.md` on the Mac, per the environment constraint agreed with the user.

## Acceptance Criteria

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| AC-001 | One-click segmentation produces a mask | ✅ Automated + manually confirmed | `tests/test_segment_smoke.py` (real SAM2 CPU inference on `5.11.JPG`); manually exported + visually reviewed the overlay — mask precisely covers the thread |
| AC-002 | Bad segmentation correctable before export | ✅ Automated | `test_predict_mask_negative_point_changes_mask` (real negative-point re-prompt); `tests/test_mask_edit.py` (raster erase fallback, 5 tests) |
| AC-003 | Mask export never touches raw source images | ✅ Automated | `tests/test_export.py` hash-before/after test; manually confirmed the real Nextcloud `5.11.JPG`/`ruler.JPG` files are unmodified after tonight's testing |
| AC-004 | Exported filenames carry metadata from real folder structure | ✅ Automated | `tests/test_naming.py` (13 tests) against the real nested path example and the flat legacy convention; includes the D-09 Date-disambiguation guard |
| AC-005 | Overlay QC image produced for every export | ✅ Automated + manually confirmed | `tests/test_export.py::test_make_overlay_returns_nonempty_image`; manually reviewed the real overlay image |
| AC-006 | Measurement produces area/avg diameter/stdev from mask | ✅ Automated + cross-validated | `tests/test_measure.py` (6 tests incl. anti-bounding-box tapered-mask test); real SAM2 mask → measure_mask() landed within 3% of ImageJ ground truth (129.3px vs 125.5px avg diameter, 0.81mm vs 0.79mm) |
| AC-007 | Ruler photo produces per-session pixels/cm factor | ⚠️ Partial — math automated, interactive click deferred | `tests/test_calibrate.py` (4 tests: px_per_cm math, per-session-rows). The interactive `ginput` collection itself requires a display — deferred to `MORNING-TEST.md` §5 (0.5cm macro span, per D-10) |
| AC-008 | Final CSV matches R script's exact column contract | ✅ Automated | `tests/test_join.py` (4 tests: exact-header string match, mm-conversion spot-check, Date-format, missing-calibration hard-fail); re-confirmed by `tests/test_skeleton_e2e.py` |
| AC-009 | Stage scripts operate over a folder, not one hardcoded file | ✅ Automated | `measure_folder()` 2-mask-folder test; `calibrate_folder()`/`segment_export.py` glob folders; `--help` on both stage CLIs confirms folder-level args wired |

**Coverage: 8/9 fully automated + verified against real data. 1/9 (AC-007) automated for its pure-math component; the interactive click portion is a documented, deliberate deferral (no display existed in this session), covered by `MORNING-TEST.md`.**

## ROADMAP Phase 1 Success Criteria (5) — cross-check

1. Click → SAM2 mask, MPS+CPU fallback — ✅ CPU path proven real; MPS path deferred to Mac (documented, expected)
2. Manual erase/deselect before export — ✅ negative-point + raster-erase both tested
3. Exported filename from metadata, source untouched — ✅ both proven (naming tests + hash test)
4. Overlay QC image saved — ✅ proven
5. One thread + one ruler photo → correct CSV row, exact R format — ✅ proven end-to-end by `test_skeleton_e2e.py` on real data

## Test Suite Summary

- **Fast suite:** 41 tests, all green (`pytest`, ~6-8s)
- **Slow/integration suite:** 3 tests, all green (`pytest -m slow`, ~70s total: 2 real-SAM2-inference tests + 1 full walking-skeleton e2e test)
- No skipped tests — all real-data fixtures (`sample_photo_path`, `ruler_photo_path`) resolved successfully since the Nextcloud data is synced to this build box too

## Code Review Findings

One real bug found and fixed: `canonical_stem()` did not validate the human-typed `thread`
identifier (D-07) — a value containing `_`, `/`, or whitespace would silently corrupt
`stem_to_fields()`'s inverse parsing. Fixed: `canonical_stem` now raises `ValueError` on
invalid input, and `segment_export.py` re-prompts at input time rather than failing deep
inside the click-loop's `on_accept` callback after the user has already done the clicking
work. Regression tests added (`test_canonical_stem_rejects_thread_with_underscore`,
`test_canonical_stem_rejects_thread_with_whitespace_or_slash`). Commit `9014e0b`.

Security review (path-traversal, source-mutation risk): confirmed safe. `canonical_stem`
is the sole stem producer used throughout the codebase; its only free-form/human-typed
component (`thread`) is now validated against path-separator/whitespace injection.
`condition`/`batch` come from regex-constrained folder-path parsing, not free text.
`export_mask` builds every output path via `pathlib` joins under caller-supplied
`masks_dir`/`qc_dir` roots and never opens the source photo for writing — confirmed by the
hash-before/after test and a live check of the real Nextcloud files after tonight's testing.

## Known Gaps (Deferred, Not Blockers)

- **MPS backend**: entirely unvalidated (no MPS hardware in this build session) — see `MORNING-TEST.md` §2
- **Interactive click UX**: structurally tested (callback logic), never actually clicked by a human — see `MORNING-TEST.md` §3
- **Calibration ginput**: pure math tested, interactive collection deferred — see `MORNING-TEST.md` §5
- **StDev accuracy**: real-data cross-check showed StDev running higher than ImageJ's (23.7px vs 17.7px) — expected given the simpler axis-sort method (D-03) vs. the deferred true perpendicular-to-tangent method (D-04, v2); formal validation against ImageJ ground truth is Phase 2's MEAS-03, not a Phase 1 requirement

## Verdict

**PASSED.** Phase 1's goal — one thread photo going click → mask → correct → measure →
calibrate → CSV row, in the exact R-script format — is proven end-to-end against real
data, not just synthetic fixtures. The one code-review finding was fixed and regression-
tested. Remaining gaps are correctly scoped as human/MPS-dependent deferrals to the Mac,
not incomplete work.

---
*Phase: 01-walking-skeleton-single-thread-click-to-csv*
*Verified: 2026-07-08*
