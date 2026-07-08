# Architecture Research

**Domain:** Small scientific-image-processing pipeline (interactive segmentation → batch measurement → calibration → CSV join), single-user, local-first, Apple Silicon Mac
**Researched:** 2026-07-08
**Confidence:** MEDIUM (component-boundary pattern cross-verified across multiple published pipelines; SAM2-on-Mac tooling specifics are LOW confidence and flagged as a phase-level research risk)

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│  STAGE 0 — SOURCE (read-only)                                         │
│  Nextcloud-synced raw images (untouched, never written to)            │
└───────────────────────────┬─────────────────────────────────────────-┘
                             │ (path glob / manifest, read-only)
┌───────────────────────────▼─────────────────────────────────────────-┐
│  STAGE 1 — INTERACTIVE SEGMENTATION (human-in-the-loop)               │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │  napari + SAM2 plugin: click prompt → mask → manual erase/   │     │
│  │  paint correction → export                                    │     │
│  └───────────────────────────┬─────────────────────────────────┘     │
│  Output: mask file + metadata-bearing filename (date/batch/           │
│  condition/thread#), written to project-owned masks/ folder           │
│  Never overwrites raw source; idempotent via "already has a mask"     │
│  skip check                                                            │
└───────────────────────────┬───────────────────────────────────────────┘
                             │ (mask file = the interface)
┌───────────────────────────▼─────────────────────────────────────────-┐
│  STAGE 2 — BATCH MEASUREMENT (fully automated, no human input)        │
│  mask → pixel area, diameter (mean of width along length), stdev      │
│  + QC overlay image (mask boundary drawn over source thumbnail)       │
│  Output: measurements.csv (px units) + qc/*.png                       │
└───────────────────────────┬───────────────────────────────────────────┘
                             │
┌───────────────────────────▼─────────────────────────────────────────-┐
│  STAGE 3 — RULER CALIBRATION (separate, parallel branch)              │
│  ruler photo → 2-click line selection → px-per-cm factor per session  │
│  Output: calibration.csv (date/session → px_per_cm)                   │
└───────────────────────────┬───────────────────────────────────────────┘
                             │ (joined by date/session key)
┌───────────────────────────▼─────────────────────────────────────────-┐
│  STAGE 4 — JOIN / FINAL CSV                                           │
│  measurements.csv ⨝ calibration.csv on (date/session)                 │
│  → px → mm conversion → column rename/reorder to R script's schema    │
│  Output: final.csv (exact columns the R script expects)               │
└─────────────────────────────────────────────────────────────────────-┘

  (separate, decoupled, one-time-per-batch, NOT part of the above chain)
┌─────────────────────────────────────────────────────────────────────-┐
│  STAGE X — HISTORICAL CLEANUP (manual-triggered, per-batch script     │
│  invocation, inspected not automated end-to-end)                      │
│  messy nested Nextcloud folder → flat informative filenames           │
│  Writes into the SAME Stage-1-input convention so cleaned batches     │
│  flow through Stage 1+ identically to newly-shot batches               │
└─────────────────────────────────────────────────────────────────────-┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Segmentation tool (Stage 1) | Human clicks thread once, corrects mask, exports labeled mask file | napari + a SAM2 plugin (or a thin custom Python/Qt or napari-based UI wrapping `facebookresearch/sam2` inference); MPS backend for Apple Silicon |
| Filename/metadata deriver | Turns per-image context (folder path segments, or user input during segmentation session) into a structured identifier (date, batch, condition, thread#) baked into the mask filename | Small pure-Python parsing module, shared by Stage 1 export and Stage X cleanup, not duplicated |
| Batch measurement (Stage 2) | Reads mask, computes area (px²), diameter samples along thread length, mean/stdev — same statistic definition as the current ImageJ macro | scikit-image / OpenCV / numpy on mask arrays; runs headless, no GUI, fully scriptable and testable |
| QC overlay generator | Draws mask boundary over the source image for visual sanity-check without re-opening the interactive tool | Part of Stage 2, writes to `qc/` — cheap add-on, high value for catching bad masks in bulk |
| Ruler calibration (Stage 3) | Converts a ruler photo into a px-per-cm factor for one shoot/session | Small standalone script/tool — 2-point click or line-length input, same "click, don't guess" philosophy as Stage 1 but far simpler (single interaction per session, not per thread) |
| Join/CSV finalizer (Stage 4) | Matches every thread measurement row to the correct session's conversion factor by date/session key, converts units, emits final schema-exact CSV | pandas merge on a normalized date/session key; this is the only place the R script's fixed column contract lives |
| Historical cleanup (Stage X) | One-time, per-batch/day inspection-driven renaming of old inconsistent folders into the same flat naming convention Stage 1 consumes | Interactive/semi-interactive script invoked per batch, not a single global automated pass — deliberately out of the main pipeline's dependency chain |

## Recommended Project Structure

```
thread-compaction-analysis-auto/
├── src/
│   ├── segment/                 # Stage 1: interactive SAM2 tool
│   │   ├── app.py                # napari launcher / SAM2 plugin wiring
│   │   └── naming.py             # shared metadata→filename deriver (also used by cleanup/)
│   ├── measure/                  # Stage 2: batch measurement (fully automated, headless)
│   │   ├── measure_masks.py      # mask → area/diameter/stdev
│   │   └── qc_overlay.py         # mask boundary overlay PNGs
│   ├── calibrate/                # Stage 3: ruler → px-per-cm
│   │   └── ruler_scale.py
│   ├── join/                     # Stage 4: merge + final CSV
│   │   └── build_final_csv.py    # schema-exact output for the R script
│   └── cleanup/                  # Stage X: one-time historical folder flattening
│       └── flatten_batch.py      # invoked per-batch, human-inspected, uses naming.py
├── data/                          # NOT the Nextcloud source — pipeline's own working area
│   ├── masks/                    # Stage 1 output: <date>_<batch>_<condition>_<thread>.png (or .npy/.tif)
│   ├── qc/                       # Stage 2 output: overlay PNGs, one per mask, same stem
│   ├── calibration/               # Stage 3 output + the ruler photos' derived factors
│   │   └── calibration.csv       # session_date, px_per_cm
│   └── csv/
│       ├── measurements.csv      # Stage 2 output (px units, pre-join)
│       └── final.csv             # Stage 4 output (matches R script schema exactly)
└── tests/
    ├── test_measure.py           # golden-file tests against known ImageJ output
    ├── test_naming.py
    └── test_join.py
```

### Structure Rationale

- **`src/` split mirrors the pipeline stages 1:1** (segment / measure / calibrate / join / cleanup) so each stage stays independently runnable, independently testable, and swappable (e.g. swapping the SAM2 plugin later doesn't touch measurement code).
- **`data/masks/` is the hard interface boundary.** Nothing downstream of Stage 1 ever touches the Nextcloud source images again — Stage 2+ only reads masks and (for QC) thumbnails/paths recorded in the mask filename or a lightweight sidecar. This is what makes re-runs safe: Stage 2 can be re-run on all masks any time without re-touching Stage 1's human effort.
- **`data/` is pipeline-owned, not the Nextcloud folder.** Raw images stay wherever Nextcloud syncs them, read-only; the repo's own `data/` holds only things this pipeline creates. Never conflate "the sync folder" with "pipeline working storage" — that's how raw data gets accidentally mutated.
- **`naming.py` is shared, not duplicated,** between Stage 1 (segmentation export) and Stage X (historical cleanup) — both stages produce filenames that must obey the exact same date/batch/condition/thread convention, since Stage 2 onward can't tell (and shouldn't need to know) whether a mask came from a freshly-shot photo or a cleaned-up historical one.
- **`calibration.csv` is intentionally tiny and separate from `measurements.csv`** — one row per imaging session, not per thread — because the join in Stage 4 is a many-to-one merge (many thread measurements per session, one calibration factor per session).

## Architectural Patterns

### Pattern 1: Interactive stage, separate automated stage, mask-file interface

**What:** The human-in-the-loop segmentation tool and the fully automated batch measurement script are two separate programs that never run in the same process. The only thing that crosses the boundary is a mask file (plus its filename-encoded metadata).
**When to use:** Any time one stage requires a human judgment call (SAM2 sometimes segments the needle instead of the thread) and the next stage is pure, deterministic math (pixel counting) that benefits from being scriptable, batchable, and testable independently of the GUI.
**Trade-offs:** Slight duplication of "what counts as this thread's identity" logic if not centralized (mitigated by the shared `naming.py`). In exchange: Stage 2 can be re-run instantly and repeatedly (e.g. after fixing a diameter-averaging bug) without re-doing any of the manual segmentation work, and Stage 2 is trivially unit-testable against fixed mask fixtures — including against masks hand-derived from the existing ImageJ ground truth.

This is the dominant pattern across published bioimaging pipelines (MCMICRO, CellProfiler/Cell Painting Gallery, Batch-Mask, IMC Segmentation Pipeline) — they all separate an interactive/curated segmentation stage from an automated quantification stage using saved mask/label files as the sole interface, plus a QC-overlay stage generated from those same masks. [MEDIUM confidence — cross-verified across independent published pipeline docs]

### Pattern 2: Metadata rides in the filename, not in a side database

**What:** Date, batch, condition, and thread number are encoded directly into the mask filename at export time (e.g. `2026-04-24_batch8_poststretch_day12_thread05.png`), rather than tracked in a separate lookup table keyed by opaque IDs.
**When to use:** Small, single-user pipelines where the "database" would be massive overkill, and where a human will regularly `ls` the masks folder and needs to understand what each file is at a glance.
**Trade-offs:** Filenames become long/rigid and any renaming logic needs a single canonical parser/formatter (this is why `naming.py` must be shared, not duplicated). In exchange: every downstream stage (measurement, QC, join) can derive its join keys by parsing the filename alone — no separate metadata store to keep in sync, no risk of a mask and its metadata drifting apart, and the CSV output is one `parse-filename-into-columns` step away.

### Pattern 3: Join by session key, not by shared filename convention

**What:** Ruler calibration produces one row per imaging session (date/batch), and thread measurements have many rows per session. The final CSV join is a many-to-one `pandas.merge` on a normalized `(date, batch)` or `(date)` key — not a 1:1 filename match.
**When to use:** Whenever one measurement type is per-item (thread) and another is per-batch/session (calibration) — a very common shape in imaging pipelines that mix object-level and scene-level measurements.
**Trade-offs:** Requires a strict, validated key normalization (e.g. dates must parse identically from both the mask filenames and the ruler-photo session folder/filename) — a silent key mismatch produces `NaN` conversion factors that are easy to miss if not explicitly checked. In exchange: calibration only needs to be shot and processed once per session regardless of how many threads are in that session, matching how the ruler photo is actually taken in the field.

**Example (join logic):**
```python
# join/build_final_csv.py
measurements = pd.read_csv("data/csv/measurements.csv")   # one row per thread
calibration = pd.read_csv("data/calibration/calibration.csv")  # one row per session

merged = measurements.merge(calibration, on=["date", "batch"], how="left")
missing = merged[merged["px_per_cm"].isna()]
assert missing.empty, f"No calibration factor for sessions: {missing[['date','batch']].drop_duplicates()}"

merged["AvgDiameter(mm)"] = merged["avg_diameter_px"] / merged["px_per_cm"] * 10
merged["StDev(mm)"] = merged["stdev_px"] / merged["px_per_cm"] * 10

final = merged.rename(columns={...})[EXACT_R_SCRIPT_COLUMNS]
final.to_csv("data/csv/final.csv", index=False)
```

## Data Flow

### End-to-end flow, raw image to final CSV row

```
Nextcloud raw image (path encodes batch/condition/day)
    ↓ (Stage 1: user opens image in napari+SAM2, clicks thread, corrects, exports)
mask file, filename = date_batch_condition_thread.png
    ↓ (Stage 2: automated, reads mask only)
one row in measurements.csv: {date, batch, condition, thread, area_px, avg_diameter_px, stdev_px}
    ↓ (Stage 4: merge on date+batch against calibration.csv)
                                                              ↑
                                          ruler photo (Stage 3, same session)
                                              ↓
                                          one row in calibration.csv: {date, batch, px_per_cm}
    ↓
one row in final.csv, exact R-script schema:
Thread, Batch, Condition, Date, Conversion(px/cm), AvgDiameter(px), StDev(px), AvgDiameter(mm), StDev(mm)
```

### Key Data Flows

1. **Metadata propagation:** date/batch/condition/thread# is captured *once*, at Stage 1 export time (parsed from the source folder path or entered by the user during segmentation), embedded in the mask filename, and every downstream stage (measurement, QC, join) re-derives its identifying columns purely by parsing that filename — there is no separate metadata database to keep in sync.
2. **Calibration join:** ruler photos are processed independently and produce a small session-keyed table; the join step is the *only* place calibration and thread data meet, and it must hard-fail (not silently NaN) if a session's calibration factor is missing.
3. **Idempotent re-run:** Stage 1 checks "does a mask already exist for source image X" before opening the interactive tool (skip already-segmented images); Stage 2/3/4 are pure functions of their inputs and safe to re-run in full every time — cheap because they're not doing GPU inference, so no need for per-file skip logic there, just re-generate `measurements.csv`, `calibration.csv`, `final.csv` wholesale on every run.

## Scaling Considerations

This is explicitly a single-user, local, small-N pipeline (tens to low hundreds of threads per batch, single Mac). "Scaling" here means "keeps working as batch count grows over years," not concurrent users.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current (single user, batches over time) | Flat file-based interface (masks + CSVs) is sufficient; no database needed |
| Years of accumulated batches | `naming.py`'s filename convention must stay a stable, backward-compatible contract — treat it like a schema; add a version prefix if it ever needs to change, so old masks remain parseable |
| If segmentation volume grows large (thousands of threads) | Stage 1 gains the most from a "skip already-masked images" check (already planned); Stage 2-4 stay cheap regardless since they're pure CPU array math over small masks |

### Scaling Priorities

1. **First bottleneck:** Human segmentation time (Stage 1) — this is the actual bottleneck of the whole system, which is exactly why it's the one stage kept interactive/manual rather than the batch stages. No architectural fix needed beyond making re-runs skip already-done images.
2. **Second bottleneck (much smaller):** Filename convention drift across years of batches — mitigated by centralizing parsing/formatting in one shared module and testing it against real historical examples from Stage X cleanup.

## Anti-Patterns

### Anti-Pattern 1: One monolithic script/tool doing segmentation and measurement together

**What people do:** Build a single interactive tool that segments *and* immediately computes/writes final measurements in the same session, because it feels convenient to "do it all in one pass."
**Why it's wrong:** Couples a human-paced, GUI-driven, error-prone-and-needs-correction stage to a deterministic, fast, easily-testable stage. You lose the ability to re-run measurement logic (e.g. after fixing a diameter-averaging bug) without re-doing hours of manual clicking, and you lose the ability to unit-test the measurement math against fixed mask fixtures (including the existing ImageJ ground truth) independent of the GUI.
**Do this instead:** Keep the mask file as the hard interface. Stage 1 exports masks and nothing else; Stage 2 is a separate, headless, re-runnable script.

### Anti-Pattern 2: Deriving thread identity from ImageJ-style shot order or frame position

**What people do:** Try to auto-derive thread number/condition from the position of the photo in a sequence (e.g. "5th photo of the day = thread 5"), since that's superficially how the data was shot.
**Why it's wrong:** The project's own context is explicit that shot order/labeling convention differs by batch and sometimes by day — a global positional rule will silently mis-tag threads in every batch that doesn't follow the assumed convention, and errors here are the worst kind (wrong CSV row, not a crash).
**Do this instead:** Derive identity from explicit signals per batch — folder path segments where available, or user-entered/confirmed metadata at segmentation time — and treat the historical cleanup pass (Stage X) as deliberately per-batch/manual for exactly this reason, never as a single global heuristic.

### Anti-Pattern 3: Auto-resolving ambiguous SAM2 masks (e.g. needle vs. thread) instead of flagging for correction

**What people do:** Add a heuristic (largest connected component, aspect-ratio filter, etc.) to auto-pick the "real" thread when SAM2 grabs the needle too, to avoid the manual correction step.
**Why it's wrong:** Explicitly out of scope per this project's own constraints — needle and thread can overlap or be similar in scale, so a heuristic will occasionally silently pick the wrong region and produce a plausible-looking but wrong measurement, which is worse than requiring a manual fix every time.
**Do this instead:** Keep manual erase/correction in the interactive tool as the only mechanism for resolving ambiguous segments.

### Anti-Pattern 4: Renaming or writing into the Nextcloud-synced raw folder

**What people do:** Run the cleanup/rename pass (or any pipeline stage) directly on the synced source folder to "tidy it up in place."
**Why it's wrong:** Nextcloud sync means any write can propagate/conflict across devices, and there is no undo for a botched batch rename applied directly to the only copy of irreplaceable source photos.
**Do this instead:** Cleanup (Stage X) and all pipeline stages only *read* from the Nextcloud path; every write (masks, CSVs, even a "flattened copy" if cleanup needs one) goes to the pipeline's own `data/` directory, never back into the synced source tree.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Nextcloud sync folder | Local filesystem read, by path, no API | Treat exactly like any other local folder that happens to be externally synced — read-only from this pipeline's perspective; do not assume real-time consistency if a sync is in progress |
| SAM2 model (Meta) | Local Python inference (`facebookresearch/sam2` or a wrapping plugin), MPS backend on Apple Silicon | No cloud dependency; model checkpoint downloaded once and run locally. Apple Silicon/MPS support is community-reported, not officially documented for SAM2 — flag as a phase-level research risk before committing to a specific plugin/wrapper [LOW confidence, verify hands-on early] |
| Existing R compaction-analysis script | Consumes `final.csv` by fixed column contract | This pipeline's only obligation to the R script is the exact column names/order — no other coupling; changing that schema is the one change that would require touching the R script too |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Segmentation (Stage 1) ↔ Measurement (Stage 2) | Mask files on disk, filename-encoded metadata | Hard boundary — Stage 2 never imports SAM2/napari code, Stage 1 never imports measurement math |
| Measurement (Stage 2) ↔ Calibration (Stage 3) | None directly — both write independent CSVs | These two stages have zero runtime dependency on each other and can be built/tested in either order |
| Measurement + Calibration ↔ Join (Stage 4) | Two CSVs on disk, merged by date/batch key | Join is the only stage that needs to know both schemas; keep the R-script's exact column contract isolated here so it's the single place that changes if the R script's expectations ever shift |
| Cleanup (Stage X) ↔ Segmentation (Stage 1) | Shared `naming.py` module + shared output-filename convention | Stage X's output must be indistinguishable, to Stage 1 and beyond, from a freshly-shot and freshly-named batch |

## Sources

- [SAM2Long napari plugin — napari-hub.org](https://napari-hub.org/plugins/napari-sam2long.html)
- [Interactive Medical-SAM2 GUI (napari-based semi-automatic annotation) — arXiv 2602.22649](https://arxiv.org/abs/2602.22649)
- [napari-vos-sam2 — GitHub](https://github.com/ledvic/napari-vos-sam2)
- [FrancisCrickInstitute/napari_sam2 — GitHub](https://github.com/FrancisCrickInstitute/napari_sam2)
- [napari-segment-anything — napari-hub.org](https://napari-hub.org/plugins/napari-segment-anything)
- [SKKU-IBE/Medical-SAM2GUI — GitHub](https://github.com/SKKU-IBE/Medical-SAM2GUI)
- [Meta SAM2 official announcement](https://ai.meta.com/research/sam2/)
- [facebookresearch/sam2 — GitHub](https://github.com/facebookresearch/sam2)
- [Batch-Mask: Automated Image Segmentation — PMC9617216](https://pmc.ncbi.nlm.nih.gov/articles/PMC9617216/)
- [SPACEc: streamlined interactive Python workflow for multiplexed image processing — Nature Communications](https://www.nature.com/articles/s41467-025-65658-3)
- [IMC Segmentation Pipeline — bodenmillergroup.github.io](https://bodenmillergroup.github.io/ImcSegmentationPipeline/)
- [Cell Painting Gallery folder structure — Broad Institute docs](https://broadinstitute.github.io/cellpainting-gallery/data_structure.html)
- [A Set of FMRI Quality Control Tools in AFNI — MIT Press Imaging Neuroscience](https://direct.mit.edu/imag/article/doi/10.1162/imag_a_00246/123633/A-Set-of-FMRI-Quality-Control-Tools-in-AFNI)
- [ImageJ Set Scale / spatial calibration guide](https://www.toolify.ai/ai-news/master-image-calibration-set-scale-bar-in-imagej-77842)
- [ImageJ User Guide — Analyze Menu](https://imagej.net/ij/docs/menus/analyze.html)

---
*Architecture research for: small scientific-image-processing pipeline (SAM2 segmentation → batch measurement → calibration → CSV join)*
*Researched: 2026-07-08*
