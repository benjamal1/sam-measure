# Requirements: Thread Compaction Analysis (Auto)

**Defined:** 2026-07-08
**Core Value:** Turn a folder of thread photos (however messy) into the exact CSV shape the existing R script already consumes — with one click per thread instead of manual edge-tracing in ImageJ.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Segmentation

- [ ] **SEG-01**: User can click once on a thread in a photo (SAM2, running locally on M2 Mac) to get a segmentation mask
- [ ] **SEG-02**: User can manually erase/deselect bad regions of a mask before export (e.g. needle picked up alongside thread)
- [ ] **SEG-03**: SAM2 inference runs on the M2's MPS backend where viable, with an explicit CPU fallback path when MPS fails or produces bad output

### Mask Export & Naming

- [ ] **EXPT-01**: Exported masks are named using identifying metadata (date, batch, condition, thread number) derived from context at export time — not from the original nested folder structure
- [ ] **EXPT-02**: Raw source images on Nextcloud are never modified or moved by the export process
- [ ] **EXPT-03**: An overlay QC image (mask drawn over original photo) is saved alongside each exported mask for visual audit
- [ ] **EXPT-04**: Re-running export on already-processed images does not duplicate or clobber existing masks (idempotent/skippable)

### Batch Measurement

- [ ] **MEAS-01**: A batch script computes pixel area for every exported mask
- [ ] **MEAS-02**: A batch script computes average diameter and standard deviation (px) per thread from its mask, using a method comparable to the existing ImageJ perpendicular edge-tracing output (not simple bounding-box width)
- [ ] **MEAS-03**: Measurement logic is validated against existing ImageJ output on a shared sample set before being trusted on new data

### Calibration

- [ ] **CAL-01**: User can process a photo of a ruler to derive a pixels-per-cm conversion factor
- [ ] **CAL-02**: Conversion factor is computed and stored per session (date/batch), not as one global constant
- [ ] **CAL-03**: Pipeline hard-fails (does not silently default or skip) when a thread's session has no matching ruler calibration

### CSV Assembly

- [ ] **CSV-01**: Pipeline joins each thread's pixel measurements to its session's conversion factor by date/batch key
- [ ] **CSV-02**: Pipeline converts pixel measurements to mm/cm units using the matched conversion factor
- [ ] **CSV-03**: Final CSV output matches the existing R script's exact columns and order: `Thread, Batch, Condition, Date, Conversion (pixels/cm), Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm)` — no R script changes required
- [ ] **CSV-04**: Pipeline hard-fails (does not silently skip or null out) on any thread row that can't be matched to a calibration factor
- [ ] **CSV-05**: Each pipeline run produces a manifest/log recording inputs processed, outputs written, and which conversion factor was applied to which thread

### Historical Cleanup

- [ ] **CLN-01**: User has a per-batch rename/flatten tool to turn a messy nested folder of images into flat, informative filenames (date/batch/condition/thread number)
- [ ] **CLN-02**: Cleanup tool runs in dry-run mode first, showing the full old-name → new-name mapping before any file is touched
- [ ] **CLN-03**: Cleanup tool hard-fails on any rename collision (two source files mapping to the same target name) rather than silently overwriting

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Workflow Quality-of-Life

- **QOL-01**: Keyboard-shortcut-driven review queue for clicking through many images quickly
- **QOL-02**: Statistical outlier flagging on the final CSV (flag suspect measurements, don't auto-delete)
- **QOL-03**: Resume support that explicitly tracks progress through a batch (beyond simple output-exists skip)

### Measurement Refinement

- **MEAS-04**: True perpendicular-to-tangent ray-cast width measurement (upgrade from skeleton+distance-transform, if that proves insufficiently accurate against ImageJ ground truth)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Automatic needle/thread disambiguation without user correction | SAM2 sometimes grabs the needle; manual erase step is deliberately kept rather than building fragile auto-detection |
| Single global script to rename all historical images at once | Folder/naming conventions vary by batch and day; cleanup is inspected and run per-batch instead |
| Rewriting the existing R compaction-analysis script | Pipeline conforms its CSV output to the R script's existing format instead |
| Cloud-hosted SAM2 / cloud GPU dependency | Must run locally on the user's M2 Mac |
| Multi-user support, web app, or hosted service | Single-user local research tool |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEG-01 | Phase 1 | Pending |
| SEG-02 | Phase 1 | Pending |
| SEG-03 | Phase 1 | Pending |
| EXPT-01 | Phase 2 | Pending |
| EXPT-02 | Phase 2 | Pending |
| EXPT-03 | Phase 2 | Pending |
| EXPT-04 | Phase 2 | Pending |
| MEAS-01 | Phase 3 | Pending |
| MEAS-02 | Phase 3 | Pending |
| MEAS-03 | Phase 3 | Pending |
| CAL-01 | Phase 4 | Pending |
| CAL-02 | Phase 4 | Pending |
| CAL-03 | Phase 4 | Pending |
| CSV-01 | Phase 5 | Pending |
| CSV-02 | Phase 5 | Pending |
| CSV-03 | Phase 5 | Pending |
| CSV-04 | Phase 5 | Pending |
| CSV-05 | Phase 5 | Pending |
| CLN-01 | Phase 6 | Pending |
| CLN-02 | Phase 6 | Pending |
| CLN-03 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-08*
*Last updated: 2026-07-08 after initial definition*
