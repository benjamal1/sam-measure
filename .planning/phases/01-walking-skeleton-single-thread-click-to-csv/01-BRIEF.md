# Acceptance Brief: Phase 1 — Walking Skeleton, Single-Thread Click-to-CSV

**Status:** Draft
**Depth:** Quick Capture (local research tool, no auth/compliance/external-cost risk)

## Goal

A researcher can point the pipeline at a real thread photo and a real ruler photo and get back a correct CSV row, in the exact format the existing R script expects, having only clicked to segment and (if needed) corrected the mask.

## Scope

**In scope**
- SAM2 click-to-segment (M2 MPS with CPU fallback) via a bespoke matplotlib/OpenCV loop
- Manual mask correction (negative-point re-prompt first, pixel/polygon erase fallback)
- Mask export named from metadata parsed out of the real Nextcloud folder path
- Overlay QC image saved alongside each mask
- Skeleton + distance-transform width sampling → area, avg diameter(px), stdev(px)
- Ruler-photo → pixels/cm calibration, one factor per session (date/batch)
- Join by date/batch, unit conversion, CSV in the exact R-script column order
- Stage-per-script architecture, each script operating over a folder of inputs (not hardcoded to one file)

**Out of scope**
- Idempotent re-export skip, ImageJ ground-truth validation, hard-fail safety nets, run manifest (all Phase 2)
- Historical folder cleanup tooling (Phase 3)
- True perpendicular ray-cast measurement, outlier flagging, keyboard-driven review queue (v2)

## Context

**Discovered facts**
- No existing code — greenfield project.
- Research (`research/STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md`) already selected the stack and flagged the two live risks: SAM2-on-MPS is "preliminary" support, and naive width measurement mis-measures curved threads.
- R script's exact expected CSV columns (verbatim): `Thread, Batch, Condition, Date, Conversion (pixels/cm), Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm)`.

**Product/business constraints (from user)**
- Must run fully locally on the user's M2 Mac — no cloud GPU/API dependency.
- R script itself is not to be modified — pipeline output must conform to it exactly.
- Raw source photos on Nextcloud must never be modified or moved.

**Assumptions**
- One ruler photo exists per session (date/batch) the pipeline needs to calibrate — if not, Phase 1 can fail loudly (hard-fail is formally a Phase 2 requirement, but Phase 1 shouldn't silently fabricate a factor either).
- The folder-path parser (D-07) only needs to handle the path shapes the user has actually shown (e.g. `Batch 8 04-24-26/Poststretch/D12 05-11-26/IMG_8092.JPG`) — full historical-mess coverage is Phase 3's job.

**Dependencies and constraints**
- PyTorch with MPS backend, facebookresearch/sam2 (source install), scikit-image, OpenCV, pandas — per `research/STACK.md`.

## Risk Review

| Risk area | Applies? | Required handling |
| --- | --- | --- |
| Security/privacy | No | Local-only, no network calls, no PII beyond research photos |
| Persistent data/migration | No | No database, no schema; CSV is the only durable output |
| External effects/cost | No | No paid APIs, no cloud calls |
| Compatibility/API | Yes | Output CSV must match the R script's column contract exactly — this is the one hard compatibility boundary |
| UX/accessibility | Partial | Single-user CLI/click tool; correctness of the click/correct loop matters more than polish |

## Acceptance Criteria

### AC-001: One-click segmentation produces a mask
- **Scenario:** A real thread photo, SAM2 loaded (MPS if available, else CPU)
- **Action:** User clicks once on the thread in the image
- **Expected:** A segmentation mask is displayed/saved covering the thread region
- **Must not:** Crash or silently produce an empty mask with no error
- **Verification:** Manual run against a real sample photo; visual inspection of the mask overlay
- **Priority:** Required

### AC-002: Bad segmentation can be corrected before export
- **Scenario:** SAM2 mask incorrectly includes the needle
- **Action:** User adds a negative point on the needle region, or manually erases that part of the mask
- **Expected:** Final exported mask covers only the thread
- **Must not:** Require editing the raw source photo to fix
- **Verification:** Manual run on a known problem photo (needle-adjacent thread), visual check of exported mask
- **Priority:** Required

### AC-003: Mask export never touches raw source images
- **Scenario:** Any segmentation run against a Nextcloud-synced photo
- **Action:** Run the segmentation/export script
- **Expected:** Source photo file is byte-identical before and after; mask + overlay written to a separate output directory
- **Must not:** Modify, move, or rename anything under the Nextcloud source tree
- **Verification:** Automated check — hash source file before/after a run
- **Priority:** Required

### AC-004: Exported filenames carry metadata parsed from the real folder structure
- **Scenario:** A source photo at a real nested path (e.g. `Batch 8 04-24-26/Poststretch/D12 05-11-26/IMG_8092.JPG`)
- **Action:** Run the export step
- **Expected:** Exported mask filename encodes date, batch, condition, and thread number
- **Must not:** Depend on the original filename (`IMG_8092.JPG`) carrying any of that info
- **Verification:** Unit test against 2-3 real example paths from PROJECT.md/CONTEXT.md
- **Priority:** Required

### AC-005: Overlay QC image is produced for every export
- **Scenario:** Any successful mask export
- **Action:** Run the export step
- **Expected:** An overlay image (mask drawn over the original photo) is saved alongside the mask
- **Must not:** Silently skip overlay generation on success
- **Verification:** Manual check — overlay file exists and visually matches the mask
- **Priority:** Required

### AC-006: Measurement produces area, avg diameter, and stdev from a mask
- **Scenario:** A valid exported mask
- **Action:** Run the measurement script
- **Expected:** Output includes pixel area, average width (px) from skeleton+distance-transform sampling, and stdev (px) of those per-point widths
- **Must not:** Use bounding-box/min-area-rect width as a stand-in
- **Verification:** Unit test against a synthetic mask with a known/hand-computed expected width and area
- **Priority:** Required

### AC-007: Ruler photo produces a per-session pixels/cm factor
- **Scenario:** A ruler photo for a given date/batch
- **Action:** Run the calibration script (two-click distance against a known cm span)
- **Expected:** A pixels/cm conversion factor is computed and stored keyed to that date/batch
- **Must not:** Apply as a global constant across all sessions
- **Verification:** Manual run against a real ruler photo; sanity-check the resulting factor against a hand calculation
- **Priority:** Required

### AC-008: Final CSV matches the R script's exact column contract
- **Scenario:** At least one measured thread and its matching calibration factor exist
- **Action:** Run the CSV-build script
- **Expected:** Output CSV has header `Thread, Batch, Condition, Date, Conversion (pixels/cm), Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm)` in that exact order, with correct mm-converted values
- **Must not:** Reorder, rename, add, or drop columns relative to the existing R script's expectation
- **Verification:** Automated test comparing generated header row against the literal expected header string; manual value spot-check against hand-computed mm conversion
- **Priority:** Required

### AC-009: Stage scripts operate over a folder of inputs, not one hardcoded file
- **Scenario:** A folder containing more than one already-exported mask, or more than one ruler photo
- **Action:** Run the measurement or calibration script without a single-file argument
- **Expected:** All matching files in the folder are processed
- **Must not:** Require re-invoking the script per file
- **Verification:** Manual run against a small real folder of 2+ files
- **Priority:** Important

## Blocking Decisions

None — Phase 1 has no unresolved decision that would create material safety/correctness risk if left as scoped. (SAM2-on-MPS viability is a known open risk per PITFALLS.md, but the CPU fallback in SEG-03/AC-001 already covers it; it doesn't block starting implementation.)

## Verification Plan

| Criterion | Verification evidence | Status |
| --- | --- | --- |
| AC-001 | Manual run + visual mask check | Pending |
| AC-002 | Manual run on needle-adjacent sample | Pending |
| AC-003 | Automated hash-before/after check | Pending |
| AC-004 | Unit test, real example paths | Pending |
| AC-005 | Manual overlay existence/visual check | Pending |
| AC-006 | Unit test, synthetic mask w/ known width | Pending |
| AC-007 | Manual run + hand-calc sanity check | Pending |
| AC-008 | Automated header-match test + manual value spot-check | Pending |
| AC-009 | Manual multi-file folder run | Pending |
