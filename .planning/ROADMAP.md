# Roadmap: Thread Compaction Analysis (Auto)

## Overview

The journey starts with a walking skeleton: prove that one thread photo can travel all the way from a single SAM2 click through segmentation, measurement, and calibration to a correct CSV row in the exact shape the existing R script expects. That end-to-end slice, even rough, retires the biggest project risks (SAM2-on-MPS viability, the naming convention as join key, and the measurement/calibration/CSV math) before any effort goes into scaling. Phase 2 then hardens that same pipeline for real batch use across the full multi-session dataset — validating measurement accuracy against ImageJ ground truth, adding hard-fail safety nets on missing calibration, guarding against duplicate re-runs, and producing an audit manifest. Phase 3 is the deliberately separate, per-batch historical folder cleanup track, decoupled from the automated pipeline per the project's own scoping decision.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Walking Skeleton — Single-Thread Click-to-CSV** - One thread photo can go from a single SAM2 click through to a correct CSV row, proving the whole pipeline shape end-to-end
- [ ] **Phase 2: Batch Hardening & Validation** - The same pipeline runs reliably and safely across the full multi-session dataset, with validated measurement accuracy and hard-fail safety nets
- [ ] **Phase 3: Historical Folder Cleanup** - Per-batch tool flattens messy nested legacy folders into the pipeline's naming convention, safely and with human review

## Phase Details

### Phase 1: Walking Skeleton — Single-Thread Click-to-CSV
**Goal**: For one thread photo, a user can click to segment, correct if needed, and get a correct CSV row in the exact R-script format — proving the full pipeline shape end-to-end before scaling to a full batch.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: SEG-01, SEG-02, SEG-03, EXPT-01, EXPT-02, EXPT-03, MEAS-01, MEAS-02, CAL-01, CAL-02, CSV-01, CSV-02, CSV-03
**Success Criteria** (what must be TRUE):
  1. User can click once on a thread in a photo and see a SAM2-generated segmentation mask, running on the M2's MPS backend with an explicit CPU fallback when MPS fails or produces bad output
  2. User can manually erase/deselect bad mask regions (e.g. a needle picked up alongside the thread) before the mask is exported
  3. The exported mask file is named using identifying metadata (date, batch, condition, thread number) derived at export time, and the original source photo on Nextcloud is never modified or moved
  4. An overlay QC image (mask drawn over the original photo) is saved alongside the exported mask for visual audit
  5. Running the pipeline on that one thread plus one ruler photo produces a single CSV row with correct pixel area, average diameter/stdev, and mm-converted values, in the exact column names/order the existing R script expects
**Plans**: 5 plans (waves: 1 → [2 parallel] → 3)
- [ ] 01-01-PLAN.md — Scaffold + folder-path metadata/naming parser (TDD) [wave 1]
- [ ] 01-02-PLAN.md — Measurement engine: skeleton+distance-transform area/diameter/stdev (TDD) [wave 2]
- [ ] 01-03-PLAN.md — Ruler calibration + join/CSV assembly in exact R schema (TDD) [wave 2]
- [ ] 01-04-PLAN.md — Segmentation engine: SAM2 device-fallback + export + raster erase [wave 2]
- [ ] 01-05-PLAN.md — Click-loop UI + end-to-end orchestrator + skeleton integration test + Mac morning-test doc [wave 3]

### Phase 2: Batch Hardening & Validation
**Goal**: The pipeline built in Phase 1 can be trusted to run across the full multi-session historical dataset — measurement accuracy is validated against ImageJ ground truth, re-runs are safe, missing calibration hard-fails loudly, and every run leaves an audit trail.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: EXPT-04, MEAS-03, CAL-03, CSV-04, CSV-05
**Success Criteria** (what must be TRUE):
  1. Re-running mask export on already-processed photos does not duplicate or clobber existing masks (idempotent/skippable)
  2. Measurement output (average diameter, stdev) has been validated against existing ImageJ output on a shared sample set before being trusted on new data
  3. Processing a thread whose session has no matching ruler calibration hard-fails with a clear error instead of silently defaulting or skipping
  4. A thread row that can't be matched to a calibration factor during CSV assembly hard-fails the run instead of being silently skipped or nulled out
  5. Each pipeline run produces a manifest/log recording every input processed, every output written, and which conversion factor was applied to which thread
**Plans**: TBD

### Phase 3: Historical Folder Cleanup
**Goal**: User can turn a messy, deeply-nested folder of legacy thread photos into flat, informative filenames — inspected and run per-batch, since the historical mess isn't uniform across batches.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CLN-01, CLN-02, CLN-03
**Success Criteria** (what must be TRUE):
  1. User can run a per-batch tool that flattens a messy nested folder of images into flat, informative filenames (date/batch/condition/thread number), reusing the same naming convention established in Phase 1
  2. The tool shows the full old-name to new-name mapping in a dry run before any file is touched
  3. The tool hard-fails on any rename collision (two source files mapping to the same target name) rather than silently overwriting a file
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Walking Skeleton — Single-Thread Click-to-CSV | 5/5 | Complete (verified passed) | 2026-07-08 |
| 2. Batch Hardening & Validation | 0/TBD | Not started | - |
| 3. Historical Folder Cleanup | 0/TBD | Not started | - |
</content>
