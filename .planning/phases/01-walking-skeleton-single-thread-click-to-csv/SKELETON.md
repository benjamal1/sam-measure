# Walking Skeleton — Thread Compaction Analysis (Auto)

**Phase:** 1
**Generated:** 2026-07-08

## Capability Proven End-to-End

Given one real thread photo, a segmentation click point, and one real ruler photo,
the pipeline produces `data/csv/final.csv` with a single row in the exact R-script
column order and plausible mm-converted diameter values — with the segmentation click
supplied programmatically (headless build box) and the interactive click UI wired but
validated by hand on the Mac.

**Phase user story** (derived from ROADMAP `**Goal:**` + BRIEF Goal; the ROADMAP goal
line is prose, not strict `As a / I want to / so that` keyword form — story below is a
faithful restatement, not new intent):

**As a** thread-compaction researcher, **I want to** click once to segment a thread photo,
correct the mask if SAM2 grabs the needle, and run the pipeline against a ruler photo,
**so that** I get a correct CSV row in the exact column format my existing R script
consumes — without manual ImageJ edge-tracing.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.12, `.venv/` (already provisioned) | Required by SAM2/PyTorch/scikit-image; env pre-built and import-verified this session |
| Segmentation engine | `facebookresearch/sam2` 2.1 (`sam2.1_hiera_small.pt`), editable install from `vendor/sam2/` | Locked by project (SEG-01); small checkpoint chosen for interactive latency |
| Device policy | `cuda > mps > cpu` selection + `PYTORCH_ENABLE_MPS_FALLBACK=1`, forced `float32` | D-02 / SEG-03. Build box is CPU-only (legit exercise of the fallback path); Mac targets MPS |
| Interactive UI | Bespoke matplotlib click loop (left=positive, right=negative), NOT napari | D-01 — zero third-party SAM2-plugin risk |
| Mask correction | SAM2 negative point (`label=0`) first; pure raster `erase_region` fallback | D-08 / SEG-02 |
| Measurement | skimage `skeletonize` + `scipy.ndimage.distance_transform_edt`, endpoint-trim, mean/stdev | D-03. True perpendicular ray-cast deferred to v2 per D-04 |
| Calibration | Two-click `plt.ginput(2)` over a known cm span, one factor per (date,batch) session | CAL-01/02, D-10 (span is 0–0.5 cm macro ruler, not 0–10 cm) |
| CSV assembly | pandas `merge` on `[date,batch]` + `to_csv(columns=EXACT_R_SCRIPT_COLUMNS, index=False)` | CSV-01/02/03, D-05 |
| CSV `Date` value | day/measurement-folder date, formatted `M/D/YY` for the R column | D-09 (day date, not batch-start date) |
| Directory layout | `src/{segment,measure,calibrate,join}/` per stage; `data/` pipeline-owned; `tests/` mirrors stages | ARCHITECTURE.md — mask file is the stage-1→stage-2 interface |
| Source photos | Read-only; every pipeline write lands under repo `data/`, never back into Nextcloud | EXPT-02 / ARCHITECTURE Anti-Pattern 4 |
| Import mechanism | pytest `pythonpath = ["src"]` + a `sys.path` shim in CLI entry points | Avoids a new editable install of local code; env stays frozen |

## Directory Layout Contract (established Phase 1, stable for Phase 2/3)

```
src/
├── segment/
│   ├── sam2_session.py    # device fallback + load-once predictor + predict_mask()  (SEG-01/03, D-02)
│   ├── mask_edit.py        # pure erase_region() + GUI drag wrapper                  (SEG-02, D-08)
│   ├── export.py           # write mask + overlay, source untouched                  (EXPT-01/02/03)
│   ├── click_loop.py       # matplotlib interactive click UI                         (D-01, SEG-01/02)
│   ├── segment_export.py   # Stage-1 CLI: glob folder, per-photo click+export        (D-05)
│   └── naming.py           # path→PhotoMetadata parser + canonical_stem()            (EXPT-01, D-07/09)
├── measure/
│   └── measure_masks.py    # measure_mask() + Stage-2 CLI → measurements.csv         (MEAS-01/02, D-03)
├── calibrate/
│   └── ruler_scale.py      # px_per_cm math + two-click GUI + Stage-3 CLI            (CAL-01/02, D-10)
└── join/
    └── build_final_csv.py  # Stage-4 merge + mm convert + exact R columns           (CSV-01/02/03, D-05/09)
run_pipeline.py             # non-interactive end-to-end orchestrator (skeleton proof)
data/                        # gitignored: masks/ qc/ calibration/ csv/
tests/                       # test_naming, test_measure, test_calibrate, test_join, test_export, test_mask_edit, test_skeleton_e2e
```

## Intermediate Data Schema Contract (frozen in Phase 1 — both Wave-2 plans depend on it)

**`data/csv/measurements.csv`** (Stage-2 output, px units):
`source_path, date, batch, condition, thread, area_px, avg_diameter_px, stdev_px`
- `date` = ISO `YYYY-MM-DD`; `batch` = string, `""` when absent; `condition` = string, `""` when absent; `thread` = string (e.g. `5.11` or `05`).

**`data/calibration/calibration.csv`** (Stage-3 output):
`date, batch, px_per_cm, ruler_source_path`
- `date` ISO, `batch` string (`""` when absent) — join key must byte-match measurements.

**`data/csv/final.csv`** (Stage-4 output — R-script schema, exact order, DO NOT change):
`Thread, Batch, Condition, Date, Conversion (pixels/cm), Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm)`
- `Date` rendered `M/D/YY` (no leading zeros, 2-digit year) to match the pasted ImageJ sample (`8/1/25`).
- `AvgDiameter(mm) = avg_diameter_px / px_per_cm * 10`; `StDev(mm) = stdev_px / px_per_cm * 10`.

**Mask/overlay filenames** (Stage-1 output): `data/masks/<stem>.png`, `data/qc/<stem>_overlay.png`
- `<stem>` = `canonical_stem(meta, thread)`; nested data → `2026-05-11_batch8_poststretch_thread05`; flat data (no batch/condition) → `2025-08-03_thread5.11` (empty segments omitted).

## Stack Touched in Phase 1

- [x] Project scaffold (pyproject.toml pytest config, requirements.txt frozen from env, .gitignore, package layout)
- [x] Routing — five stage CLIs + one end-to-end orchestrator (`run_pipeline.py`)
- [x] Persistence — real mask/overlay PNG writes AND real CSV writes under `data/`
- [x] UI — matplotlib click loop wired to `predict_mask` + `export_mask` (interactive validation deferred to Mac)
- [x] Full-stack run — documented `run_pipeline.py` command + `pytest -m slow` skeleton integration test on real data

## Out of Scope (Deferred to Later Slices)

Deferred to **Phase 2** (batch trust): idempotent re-export skip (EXPT-04), ImageJ ground-truth
validation (MEAS-03), hard-fail on missing calibration (CAL-03), hard-fail on join mismatch (CSV-04),
run manifest/log (CSV-05). Deferred to **Phase 3**: historical folder cleanup (CLN-01/02/03).
Deferred to **v2**: true perpendicular ray-cast measurement (MEAS-04), outlier flagging, keyboard review queue.

Phase 1 still fails *loudly* (raises) on unparseable paths and on a thread with no matching calibration —
it just doesn't yet carry the formal Phase-2 safety-net contracts or the audit manifest.

## Subsequent Slice Plan

- **Phase 2:** harden this same pipeline for full-batch runs — idempotency, ImageJ validation, hard-fail
  safety nets, audit manifest — reusing every module below unchanged.
- **Phase 3:** per-batch historical folder cleanup (`flatten_batch.py`) that emits the same
  `canonical_stem` filenames Stage 1 consumes, so cleaned batches flow through identically.
