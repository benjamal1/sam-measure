# Project Research Summary

**Project:** thread-compaction-analysis-auto
**Domain:** Local SAM2-based interactive image segmentation + batch scientific measurement pipeline (bioelectric thread compaction analysis), single-user, Apple Silicon Mac
**Researched:** 2026-07-08
**Confidence:** MEDIUM

## Executive Summary

This project replaces a manual ImageJ workflow with a local, SAM2-powered click-to-segment pipeline that measures thread diameter from photos and produces a CSV feeding an existing (unmodified) R analysis script. Experts building this kind of tool split it into a human-in-the-loop interactive segmentation stage (click + manual erase correction, using napari + a SAM2 plugin) and a fully automated, headless batch measurement stage, connected only by mask files on disk, never a shared process. A separate ruler-calibration stage produces a per-session pixels-per-cm factor that is joined to thread measurements by date/batch key. This mask-file-as-interface pattern is the dominant approach across published bioimaging pipelines (MCMICRO, CellProfiler, IMC Segmentation Pipeline) and fits here because it decouples slow, error-prone human clicking from fast, deterministic, unit-testable measurement math.

The recommended stack is Python 3.11/3.12 + PyTorch (MPS backend) + facebookresearch/sam2 (source-installed) for segmentation, napari + napari-sam as the interactive review UI, and scikit-image + OpenCV + pandas for measurement, calibration, and CSV assembly. Confidence on the measurement/CSV tooling is HIGH; confidence on SAM2-on-MPS is MEDIUM-LOW because Apple Silicon support is officially "preliminary" with an open, unresolved upstream GitHub issue (RuntimeError on MPS device placement). This must be validated hands-on early, with an explicit CPU fallback path built in from day one, not bolted on later.

The two biggest risks are both silent-failure-of-correctness risks rather than crashes: (1) naive skeleton/distance-transform diameter measurement systematically mis-measures curved thread segments compared to ImageJ's true perpendicular-edge-tracing method, and (2) a wrong or stale ruler-to-thread calibration join silently corrupts every downstream measurement with no error thrown. Both must be treated as first-class correctness requirements, validated against real ImageJ ground-truth data and hard-failed (never silently defaulted) on missing/mismatched joins, not deferred as polish.

## Key Findings

### Recommended Stack

Python 3.11/3.12 with PyTorch (MPS backend, no CUDA/cloud) running facebookresearch/sam2 installed from source is the core segmentation engine, wrapped by napari + the napari-sam plugin for the interactive click/correct UI. Measurement (mask to diameter/area statistics) uses scikit-image's skeletonize/medial-axis plus a distance transform; calibration uses OpenCV mouse-click ruler measurement; final CSV assembly uses pandas for its merge/groupby capability needed to join measurements to calibration factors by date.

**Core technologies:**
- PyTorch (MPS backend) + facebookresearch/sam2 (source install): the click-to-segment engine, official `SAM2ImagePredictor` API matches "click once on the thread" directly, but MPS support is "preliminary" per upstream docs
- napari + napari-sam plugin: interactive click/correct UI, real desktop viewer with native Labels paintbrush/eraser tools, avoids building a custom GUI
- scikit-image (0.26.x): mask to skeleton to distance-transform to diameter statistics, standard way to approximate ImageJ's perpendicular edge-tracing measurement
- pandas (2.x, pin below 3.x): builds the exact-column final CSV via `to_csv` and handles the date-keyed merge between measurements and calibration

### Expected Features

Table stakes for this domain center on trustworthy, auditable output: every CSV row must be traceable back to its source photo and mask, and no silent data corruption is acceptable. Differentiators are workflow speed (keyboard-driven review) and QC (outlier flagging). Several tempting features are explicitly anti-features given the single-user, local-only, deliberately-manual-correction scope.

**Must have (table stakes):**
- Raw source images never modified, read-only source tree, all writes to a separate output directory
- Derived-filename mask export (date/batch/condition/thread#) as the join key across all stages
- Overlay QC image saved alongside every mask
- Per-run manifest/log (inputs, outputs, timestamps, model version, conversion factor used)
- Explicit, per-session pixel-to-cm conversion factor, hard-fail if missing for a date
- Manual erase/correction step before mask export (non-negotiable given SAM2's needle-grabbing failure mode)
- CSV output matching the existing R script's exact columns
- Basic per-mask sanity checks (non-empty, plausible area) before entering the CSV

**Should have (competitive):**
- Keyboard-shortcut-driven review queue (click-through speed across hundreds of images)
- Implicit resume via output-existence check
- Statistical outlier flagging on the final CSV (flag, don't delete)
- Skeletonize + medial-axis width measurement (more faithful to ImageJ's perpendicular measurement than area-only)

**Defer (v2+):**
- True perpendicular ray-casting width measurement can start as skeleton+distance-transform if timeline is tight, upgraded later without changing CSV schema
- Any cleanup automation beyond simple per-batch scripted rename helpers, deliberately scoped as manual/inspected, not automated

### Architecture Approach

The pipeline is four sequential stages plus one decoupled utility stage: (1) interactive segmentation producing mask files with metadata-encoded filenames, (2) fully automated headless batch measurement reading only masks, (3) a parallel ruler-calibration stage producing one px-per-cm factor per session, and (4) a join/finalize stage that merges measurements to calibration by date/batch key and writes the R-script-exact CSV. A separate, deliberately-manual historical folder-cleanup stage feeds into the same Stage 1 naming convention but is never part of the automated chain.

**Major components:**
1. Segmentation tool (napari + SAM2), human clicks/corrects, exports mask with derived filename; hard interface boundary, never shares a process with measurement code
2. Batch measurement (scikit-image/OpenCV/numpy), headless, pure function of mask files, fully re-runnable and unit-testable against ImageJ ground truth
3. Ruler calibration, small standalone click-based tool producing one factor per session, stored keyed by date/batch, never a global constant
4. Join/CSV finalizer (pandas merge), the single place the R script's fixed column contract lives; must hard-fail on any missing calibration match rather than defaulting

### Critical Pitfalls

1. **MPS backend numerical/precision quirks** — SAM2 on Apple Silicon MPS is not numerically CUDA-equivalent (documented op-level bugs, no float64 support); force float32 explicitly, validate on real photos before trusting output, build an explicit CPU fallback rather than assuming MPS "just works."
2. **Naive skeleton/distance-transform diameter measurement breaks on curved threads** — over/under-estimates width on curvature and is corrupted by mask boundary noise; implement true perpendicular-to-tangent ray casting, smooth mask boundaries first, trim skeleton endpoint spurs, validate against real ImageJ measurements before trusting it on a full batch.
3. **Single/global pixels-per-cm factor is wrong across sessions** — camera distance/angle varies per shoot; require exactly one ruler photo per session, hard-fail (never silently default) if missing, store calibration keyed by date/batch, never as a pipeline-wide constant.
4. **Silent join mismatch between thread measurements and calibration factor** — inconsistent date/batch string formats across batches make ad hoc key matching dangerous; define one canonical session-key format up front, hard-fail the join on any unmatched thread row, carry raw-image provenance through every intermediate artifact.
5. **Batch folder-cleanup collisions/silent skips** — two differently-named source files can flatten to the same target name; always dry-run with a full old-to-new mapping, hard-fail on any collision, never rename/write into the Nextcloud-synced original tree.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: SAM2 + Segmentation Tool Spike
**Rationale:** Highest-risk unknown (MPS support is "preliminary," open unresolved upstream bug) must be validated before any other stage is built on top of it; also the stage with the least prior art for this specific tool combination (napari-sam vs napari-segment-anything vs sam2-studio).
**Delivers:** A working local click-to-segment-and-correct loop on real sample thread photos, with a confirmed MPS-or-CPU-fallback device path and a chosen interactive UI (napari plugin or fallback custom loop).
**Addresses:** Click-to-segment with SAM2 running locally; manual erase/correction step (P1 table stakes from FEATURES.md)
**Avoids:** Pitfall 1 (MPS numerical/precision quirks), validated hands-on with real images, float32 enforced explicitly, before building further

### Phase 2: Mask Export + Naming Convention
**Rationale:** The derived-filename convention is the join key for every later stage; must be built and stabilized right after segmentation works, before measurement/calibration/join code exists to depend on it.
**Delivers:** Mask export with date/batch/condition/thread#-encoded filenames, overlay QC image generation, shared `naming.py` module (also usable by later cleanup work), idempotent skip-if-already-masked check.
**Uses:** napari + napari-sam plugin export hooks; OpenCV/PIL for overlay drawing
**Implements:** Segmentation to Measurement boundary (mask file as the hard interface, per ARCHITECTURE.md Pattern 1)

### Phase 3: Batch Measurement (Diameter/Area)
**Rationale:** Pure, deterministic, headless code that can be built and unit-tested independently of the GUI, but is the single highest-risk correctness pitfall in the whole project (Pitfall 2), must be validated against real ImageJ ground truth before trusting it on a full batch.
**Delivers:** `measure_masks.py` producing pixel-area/diameter/stdev per mask via perpendicular-to-tangent width sampling (or skeleton+distance-transform as an acceptable v1 fallback), with golden-file tests against known ImageJ output.
**Addresses:** Batch pixel-area/diameter computation (P1); Skeletonize/medial-axis diameter (P2, promote to P1 scope if feasible)
**Avoids:** Pitfall 2 (curvature/boundary-noise measurement bias), validated against real ImageJ baseline, not synthetic test images

### Phase 4: Ruler Calibration
**Rationale:** Structurally independent of measurement (no runtime dependency per ARCHITECTURE.md), can be built in parallel or right after Phase 3, but must enforce hard-fail-on-missing discipline before Phase 5 depends on it.
**Delivers:** Standalone ruler-photo to px-per-cm tool, one factor per session, stored keyed by canonical date/batch, with plausibility-range sanity checks on the derived factor.
**Addresses:** Explicit, logged pixel-to-cm conversion factor per session (P1 table stakes)
**Avoids:** Pitfall 3 (global/stale calibration factor), hard-fail if no ruler photo exists for a session being processed

### Phase 5: Join + Final CSV
**Rationale:** Depends on both Phase 3 and Phase 4 outputs; this is the actual deliverable (the R script's input) and the highest-consequence silent-failure point in the pipeline, so it comes last and gets the most validation attention.
**Delivers:** `build_final_csv.py`, pandas merge of measurements to calibration by canonical session key, unit conversion, exact R-script column mapping, hard-fail on any unmatched join key.
**Addresses:** Correct date-based join (P1); CSV output matching R script's exact columns (P1); run manifest/provenance log (P1)
**Avoids:** Pitfall 4 (silent join mismatch / lost provenance), canonical key format defined once, raw-image path carried through intermediate artifacts, hard-fail on unmatched rows

### Phase 6 (separate track, as-needed): Historical Folder Cleanup
**Rationale:** Deliberately decoupled from the main pipeline per PROJECT.md's own decision, per-batch, human-inspected, not a global automated pass. Can be built any time after Phase 2's `naming.py` exists, since cleanup must produce output in the same convention.
**Delivers:** Small reusable per-batch rename primitive with mandatory dry-run + collision hard-fail, reusing `naming.py` from Phase 2.
**Avoids:** Pitfall 5 (silent rename collisions/data loss), dry-run mapping review and hard collision-fail before any file operation; never writes into the Nextcloud-synced original tree

### Phase Ordering Rationale

- Segmentation (Phase 1) must come first because it's both the highest-uncertainty stage (MPS support) and the upstream producer for everything else's input (masks).
- Mask export/naming (Phase 2) must immediately follow segmentation and precede measurement/calibration/join, since the filename convention is the shared join key every later stage depends on.
- Measurement (Phase 3) and calibration (Phase 4) have no runtime dependency on each other per ARCHITECTURE.md and can be built in either order or in parallel, but both must land before Phase 5.
- Join/final CSV (Phase 5) is last because it's the only stage that needs both other outputs, and it's where the two most catastrophic silent-failure pitfalls (curvature bias feeding into wrong numbers, calibration join mismatch) converge into the actual deliverable, it needs the most validation once its inputs are trustworthy.
- Folder cleanup (Phase 6) is intentionally a separate, later, as-needed track, explicitly scoped out of the automated main chain per PROJECT.md and only needs `naming.py` to exist first.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (SAM2 + Segmentation Tool Spike):** MPS support is officially "preliminary" with an open unresolved upstream bug (facebookresearch/sam2#687); napari-sam vs napari-segment-anything vs sam2-studio choice needs a hands-on spike before committing.
- **Phase 3 (Batch Measurement):** True perpendicular-to-tangent width measurement (vs. naive skeleton/distance-transform) has no off-the-shelf library function, needs custom implementation and validation against ImageJ ground truth; this is genuinely novel territory (no direct prior art found for SAM2-based thread/fiber diameter measurement).

Phases with standard patterns (skip research-phase):
- **Phase 2 (Mask Export + Naming):** Straightforward filename-parsing and file I/O, well-understood pattern from FEATURES.md/ARCHITECTURE.md research.
- **Phase 4 (Ruler Calibration):** Standard OpenCV two-click pixel-distance calibration, well-documented community pattern (PyImageSearch-style).
- **Phase 5 (Join + Final CSV):** Standard pandas merge/to_csv pattern, well-documented.
- **Phase 6 (Folder Cleanup):** Standard dry-run/rename pattern, already scoped by explicit project decisions in PROJECT.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Measurement/CSV libraries (scikit-image, pandas, OpenCV) are HIGH-confidence stable choices; SAM2-on-MPS specifics are the weak point (single GitHub issue, "preliminary" official support) |
| Features | MEDIUM | Cross-verified against multiple published napari-SAM annotation tools and one adjacent fiber-diameter measurement paper, but no direct prior art exists for this exact domain (thread diameter via SAM2) |
| Architecture | MEDIUM | Component-boundary pattern (interactive stage + automated stage, mask-file interface) cross-verified across multiple independent published bioimaging pipelines; SAM2-on-Mac tooling specifics remain a phase-level research risk |
| Pitfalls | MEDIUM | Web search only, no MCP doc providers used for this project's research; findings cross-corroborated across multiple independent sources per topic but not verified against this project's actual hardware/data yet |

**Overall confidence:** MEDIUM

### Gaps to Address

- SAM2 MPS reliability on the actual target M2 Mac is unverified, must be validated in Phase 1 before any further phase depends on it; budget explicit time for a CPU-fallback path.
- No direct prior art exists for "SAM2 applied to thread/fiber diameter measurement," the perpendicular-to-tangent width measurement algorithm (Phase 3) will need to be built and validated from scratch against ImageJ ground truth, not adapted from an existing library function.
- napari-sam vs napari-segment-anything vs sam2-studio: which actually supports SAM2 (not just SAM1) cleanly is unconfirmed, resolve via a short Phase 1 spike before committing.
- pandas 3.x line was seen appearing on PyPI during stack research, pin explicitly to `pandas>=2.2,<3` and re-verify current stable release at implementation time.

## Sources

### Primary (HIGH confidence)
- `/facebookresearch/sam2` (Context7), installation, MPS device-selection pattern, `SAM2ImagePredictor` API
- `/scikit-image/scikit-image` (Context7) + official skeletonize example gallery, skeleton/distance-transform width measurement pattern
- Live PyPI JSON API, current stable versions of scikit-image, pandas, numpy, opencv-python, torch, napari

### Secondary (MEDIUM confidence)
- GitHub facebookresearch/sam2 issue #687, unresolved MPS RuntimeError on Apple Silicon
- Published bioimaging pipeline docs (MCMICRO, CellProfiler/Cell Painting Gallery, IMC Segmentation Pipeline), mask-file-interface architecture pattern
- napari-sam / napari-SAMV2 / napari-sam2long / napari-vos-sam2 / FrancisCrickInstitute napari_sam2, interactive SAM2 annotation UX prior art
- PMC11398094 (Deep Learning Distance Map Fiber Diameter), closest adjacent prior art for automated fiber width measurement

### Tertiary (LOW confidence)
- Individual PyTorch/MPS bug reports (index_select, torch.var, AvgPool2d, float64 support), cross-corroborated across multiple issues but not verified on this project's own hardware
- Single-source claims on Nextcloud sync/locking race conditions, plausible but not tested against this project's actual Nextcloud setup

---
*Research completed: 2026-07-08*
*Ready for roadmap: yes*
