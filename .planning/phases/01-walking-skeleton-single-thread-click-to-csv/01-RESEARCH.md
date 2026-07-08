# Phase 1: Walking Skeleton — Single-Thread Click-to-CSV - Research

**Researched:** 2026-07-08
**Domain:** SAM2 interactive point-prompt segmentation (bespoke matplotlib loop) + skimage skeleton/distance-transform measurement + OpenCV ruler calibration + pandas CSV assembly, macOS/Apple Silicon
**Confidence:** MEDIUM (library APIs are HIGH/MEDIUM-confidence, verified via Context7 against official facebookresearch/sam2 and scikit-image/pandas docs; the click-loop/parser/test *implementation shapes* below are synthesized patterns, not copy-pasted from a single canonical source, and are flagged accordingly)

## Summary

This phase composes four already-selected libraries (SAM2, scikit-image, OpenCV/matplotlib, pandas — see `research/STACK.md`) into one vertical slice. The main planning risk isn't picking a library, it's getting four small implementation shapes right: (1) the SAM2 point-prompt call sequence and how to keep one loaded model/predictor alive across an interactive matplotlib click session, (2) the click-loop event-handling pattern itself, (3) the skeleton→distance-transform→mean/stdev width pipeline including mask cleanup and endpoint trimming, and (4) the two-date-per-path metadata parser where the CSV's "Date" column must be the day/measurement date, not the batch-start date embedded one level up — this is a real ambiguity flagged in CONTEXT.md and this research resolves it to a specific recommendation with an explicit confirmation flag.

Verified via Context7 against the official `facebookresearch/sam2` repo docs: `SAM2ImagePredictor(build_sam2(model_cfg, checkpoint, device=device))`, `predictor.set_image(image)` once per photo, then `predictor.predict(point_coords, point_labels, multimask_output=False)` per click, with `label=1` for a positive (thread) click and `label=0` for a negative (exclude-needle) click. The predictor is instantiated once and reused for the whole session — `set_image()` is the only per-photo cost, not a full model reload. A public GitHub issue on the same repo (facebookresearch/sam2#421) describes almost exactly the bespoke click-loop D-01 already locked in: a sub-110-line matplotlib script using `fig.canvas.mpl_connect("button_press_event", on_click)`, left-click = positive point, right-click = negative point, mask redrawn via `fig.canvas.draw_idle()` after every click.

The measurement pipeline (mask → clean up → skeletonize → distance-transform → per-point width list → mean/stdev) is confirmed via Context7 against scikit-image's own docs and cross-checked against project PITFALLS.md's own warning about boundary-roughness and endpoint spurs — the recommendation is to keep this simple (morphological cleanup + skeletonize + `distance_transform_edt` + fixed-margin endpoint trim) rather than reaching for the heavier `skan` graph-analysis library, which is unnecessary for a single elongated thread shape.

**Primary recommendation:** Build one shared `sam2_session.py` (load-once predictor + device fallback), one `naming.py` (path-segment regex parser that treats the day-folder date as canonical "Date" and prompts the user for thread number at click time — filenames never carry it), one `measure.py` (cleanup → skeletonize → distance-transform → trim-and-average), one `calibrate.py` (two-click OpenCV or `plt.ginput(2)` ruler distance), and one `build_csv.py` (pandas merge-on-`[date,batch]` + `to_csv(columns=EXACT_LIST, index=False)`) — each independently unit-testable per the project's own `src/` stage split in ARCHITECTURE.md.

## User Constraints

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Build a bespoke click-to-segment + erase-correction loop (matplotlib/OpenCV), not a napari+SAM2 plugin. Chosen over napari-sam/napari-segment-anything specifically to avoid depending on a third-party plugin's SAM2 (vs SAM1) support being solid — more code now, zero external plugin risk.
- **D-02:** SAM2 inference targets the M2's MPS backend with an explicit CPU fallback (per SEG-03) — the click loop itself is UI-only and doesn't change based on device.
- **D-03:** Use skeleton + Euclidean-distance-transform width sampling (research's STACK.md recommendation) as the Phase 1 measurement method. This single method produces BOTH the average diameter (mean width across skeleton points) AND StDev (spread of per-point widths) directly from the mask.
- **D-04:** True perpendicular-to-tangent ray-cast width measurement (MEAS-04, more accurate on curved threads) stays deferred to v2 — Phase 1 uses skeleton+distance-transform as-is, validated against ImageJ ground truth in Phase 2 (MEAS-03), not Phase 1.
- **D-05:** One CLI script per pipeline stage: a segmentation/export script, a ruler-calibration script, and a measure+match+CSV-build script. Each stage script operates over a folder/set of inputs (not hardcoded to exactly one image). Matching thread measurements to calibration factors happens by date (batch is the secondary key if date alone collides).
- **D-06:** Phase 1 running "for real" against more than one thread is not scope creep. What stays out of Phase 1 (deferred to Phase 2): idempotent re-export skip (EXPT-04), ImageJ validation (MEAS-03), hard-fail on missing calibration (CAL-03), hard-fail on join mismatch (CSV-04), and the run manifest (CSV-05).
- **D-07:** Build the real folder-path metadata parser now (date, batch, condition, thread number from the nested Nextcloud path), not CLI-typed metadata. Note: thread-number-within-a-session identification still needs a human decision at click time (the user knows which physical thread they're clicking on), not automatic inference from shot order — the parser handles date/batch/condition from the path only.
- **D-08:** No lightweight existing package beats OpenCV+matplotlib for the bespoke click/erase loop (D-01) — confirmed standard minimal SAM2 interactive-correction pattern. SAM2's own point-prompt API natively supports negative points (`label=0`); try that first, fall back to manual polygon/pixel erase only if a negative point doesn't cleanly separate thread from needle.

### Claude's Discretion

- Exact skeleton/distance-transform implementation details (skimage function calls, mask cleanup/smoothing before skeletonization) — left to research/planning.
- CSV intermediate file layout between the three stage scripts (e.g., a measurements.csv + a calibration.csv joined by build_csv.py) — implementation detail, not a user-facing decision.

### Deferred Ideas (OUT OF SCOPE)

- Automatic needle/thread disambiguation without manual correction — explicitly out of scope per PROJECT.md.
- True perpendicular ray-cast diameter measurement (MEAS-04) — v2 only, if skeleton+distance-transform proves insufficiently accurate against ImageJ ground truth in Phase 2.
- Keyboard-shortcut review queue, outlier flagging, explicit resume tracking (QOL-01/02/03) — v2.
- Historical folder cleanup tooling — Phase 3, separate track.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEG-01 | Click once on a thread (SAM2, local M2) to get a mask | Code Examples #1-#2: `SAM2ImagePredictor` load-once pattern, click-loop pattern |
| SEG-02 | Manually erase/deselect bad mask regions before export | Code Examples #2-#3: negative-point re-prompt first, manual raster erase fallback |
| SEG-03 | SAM2 runs on MPS where viable, explicit CPU fallback | Code Example #1: `cuda > mps > cpu` device selection + `PYTORCH_ENABLE_MPS_FALLBACK`; Pitfall carry-forward from project PITFALLS.md Pitfall 1 |
| EXPT-01 | Exported masks named from metadata parsed at export time | Code Example #4: folder-path regex parser + user-prompted thread number |
| EXPT-02 | Raw source images never modified/moved | Architecture Patterns: read-only source access pattern (already established in project ARCHITECTURE.md, reaffirmed here) |
| EXPT-03 | Overlay QC image saved alongside each exported mask | Code Example #2 extension: overlay generation is a one-line addition to the export step |
| MEAS-01 | Batch script computes pixel area for every mask | Code Example #5: `mask.sum()` alongside the width pipeline |
| MEAS-02 | Batch script computes avg diameter + stdev (px), comparable to ImageJ | Code Example #5: skeletonize + distance-transform + endpoint-trim + mean/stdev |
| CAL-01 | Process a ruler photo to derive px/cm | Code Example #6: two-click distance calibration |
| CAL-02 | Conversion factor stored per session (date/batch), not global | Code Example #7: calibration.csv keyed by (date, batch); Pitfall 3 carry-forward |
| CSV-01 | Join thread measurements to session's conversion factor by date/batch | Code Example #7: `pd.merge(..., on=["date","batch"], how="left")` |
| CSV-02 | Convert px measurements to mm/cm using matched factor | Code Example #7: `avg_diameter_px / px_per_cm * 10` |
| CSV-03 | Final CSV matches R script's exact columns/order | Code Example #7: `to_csv(path, columns=EXACT_R_SCRIPT_COLUMNS, index=False)` |
</phase_requirements>

## Architectural Responsibility Map

This is a single-process-per-stage CLI pipeline, not a multi-tier web app — "tiers" here map to pipeline stages, not client/server layers.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Interactive SAM2 click segmentation + correction | Segmentation stage (Stage 1, local process) | — | Human-in-the-loop, GPU/MPS inference; must stay a separate process from batch math per ARCHITECTURE.md Anti-Pattern 1 |
| Metadata parsing (date/batch/condition from path) | Shared `naming.py` module | Segmentation stage (calls it at export) | Must be identical logic whether called from Stage 1 export or the future Stage X cleanup — a shared pure-Python module, not duplicated per stage |
| Mask → area/diameter/stdev measurement | Measurement stage (Stage 2, headless) | — | Pure deterministic array math; must be independently re-runnable/testable without re-touching Stage 1's human effort (ARCHITECTURE.md Pattern 1) |
| Ruler → px/cm calibration | Calibration stage (Stage 3) | — | Independent of measurement; only meets it at the join |
| Join + unit conversion + final CSV | Join/CSV stage (Stage 4) | — | Only place the R-script's exact column contract lives; isolates that coupling to one file |
| Raw Nextcloud photo storage | External/read-only source | — | Never written to by any stage (EXPT-02); not part of this pipeline's own tiers at all |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11 or 3.12 | Runtime | Confirmed by project STACK.md; matches SAM2/PyTorch macOS arm64 wheel targeting |
| torch | latest 2.x with MPS wheel (`>=2.3.1` floor per SAM2 README) [CITED: github.com/facebookresearch/sam2] | SAM2's tensor runtime | PyPI confirms `2.12.1` current stable [VERIFIED: pip index versions, run this session] — always re-verify the actual floor against SAM2's README at install time since both move independently |
| facebookresearch/sam2 (2.1) | source install, pin a commit/tag | Click-to-segment engine | No numbered PyPI release; `sam2` *does* exist as a PyPI name but is a different, unrelated package — do not `pip install sam2` expecting Meta's model [ASSUMED — confirm PyPI `sam2` is not the intended package before any `pip install sam2` invocation appears in a plan] |
| scikit-image | 0.26.x | Mask → skeleton → distance-transform → diameter stats | PyPI confirms `0.26.0` current stable [VERIFIED: pip index versions, run this session]; `skeletonize`/`medial_axis` dtype handling stabilized in 0.25+ [CITED: scikit-image release notes 0.25, via Context7] |
| opencv-python | pin a tested 4.x (e.g. `4.13.0.92`), NOT the new `5.x` line | Ruler image I/O, two-click mouse calibration | PyPI confirms `5.0.0.93` is now the newest release with `4.13.0.92` the newest 4.x [VERIFIED: pip index versions, run this session] — the 4→5 major jump is very recent; project STACK.md's caution to pin 4.x unless 5.x is explicitly verified against the rest of this stack still applies, and this research did not verify 5.x compatibility |
| pandas | pin `>=2.2,<3` unless 3.x is deliberately verified | Final CSV assembly, session-key merge | PyPI confirms `3.0.3` is now current stable, `2.3.3` newest 2.x [VERIFIED: pip index versions, run this session] — `merge()`/`to_csv(columns=..., index=False)` API surface used here is unaffected by pandas 3.0's headline changes (default string dtype, copy-on-write), but this was not independently re-verified against pandas 3.0's actual release notes this session; treat pandas-3.x adoption as a planner decision, not a default |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| matplotlib | latest 3.x | Click-loop UI (D-01), overlay rendering, optional `ginput()` ruler calibration | Primary UI surface for the bespoke segmentation loop per D-01/D-08 |
| Pillow | latest | `np.array(Image.open(path))` for `SAM2ImagePredictor.set_image()` | Simpler than OpenCV's BGR handling for feeding SAM2 |
| NumPy | whatever torch/scikit-image/opencv jointly resolve to | Array plumbing | Implicit dependency, no separate pin needed |
| pytest | latest | Unit tests for `naming.py` and `measure.py` | Per `python-testing` project skill; TDD is the mandated workflow (project CLAUDE.md + rules) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Bespoke matplotlib click loop (D-01, locked) | napari + napari-sam plugin | Rejected by user decision (D-01) specifically to avoid third-party SAM2-support risk — not re-litigated here |
| `skeletonize` + `distance_transform_edt` (2 stdlib-ish calls) | `skan` (full skeleton-graph library) | `skan` gives proper branch/junction/endpoint classification, which is overkill for a single elongated thread shape; adds a new dependency for a problem PITFALLS.md already has a cheap fix for (fixed-margin endpoint trim). Revisit only if endpoint-spur trimming proves fragile in practice |
| `skeletonize` + `distance_transform_edt` | `medial_axis(mask, return_distance=True)` | One-call convenience (returns skeleton + distance together); `skeletonize` is preferred by project STACK.md for producing a thinner, less-branchy result on a single elongated shape — keep `medial_axis` as a documented fallback, not the default |
| OpenCV `cv2.setMouseCallback` two-click ruler calibration | `plt.ginput(2)` | Both are ~2-4 lines; `ginput` avoids opening a second GUI toolkit if the segmentation loop is already matplotlib-based (D-01) — **recommend `plt.ginput(2)` over introducing an OpenCV window specifically to reduce the number of GUI event loops the codebase has to manage, since D-01 already committed to matplotlib** |

**Installation:**
```bash
python3.11 -m venv .venv
source .venv/bin/activate

pip install "torch>=2.3.1" torchvision   # MPS wheel is automatic on macOS arm64

git clone https://github.com/facebookresearch/sam2.git
cd sam2 && pip install -e . && cd ..
cd sam2/checkpoints && ./download_ckpts.sh && cd ../..   # downloads all 4 sizes; interactive use targets sam2.1_hiera_small.pt

pip install "scikit-image>=0.25" "opencv-python>=4.10,<5" "pandas>=2.2,<3" pillow matplotlib pytest
```

**Version verification performed this session:**
- `scikit-image` → `0.26.0` current [VERIFIED: `pip index versions scikit-image`]
- `pandas` → `3.0.3` current, `2.3.3` newest 2.x [VERIFIED: `pip index versions pandas`]
- `opencv-python` → `5.0.0.93` current, `4.13.0.92` newest 4.x [VERIFIED: `pip index versions opencv-python`]
- `torch` → `2.12.1` current [VERIFIED: `pip index versions torch`]
- `sam2` (Meta's model) has no PyPI release; a PyPI package literally named `sam2` does exist but is unrelated — install from source per above, never `pip install sam2` [ASSUMED, carried forward from project STACK.md — re-confirm at implementation time]

## Package Legitimacy Audit

All packages checked are long-established, high-profile ecosystem-standard libraries (numpy, pandas, matplotlib, pytest, torch, torchvision, pillow, opencv-python, scikit-image). The legitimacy checker flagged every one of them `SUS`, but every single reason given is `too-new` (meaning: most recent *release* is recent — these are actively maintained libraries with frequent releases, not new/unproven packages) and/or `unknown-downloads`/`no-repository` (the checker's registry query didn't return a download-count or repo-URL field for that package name, not that one doesn't exist). This is a known false-positive pattern for high-velocity, high-trust libraries and does **not** indicate slopsquatting risk — these are all packages every Python data/ML developer would recognize by name, independently confirmed via Context7 official docs (torch/scikit-image/pandas) and training knowledge (numpy/matplotlib/pytest/pillow/opencv-python).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| scikit-image | PyPI | 15+ yrs (checker only saw latest release date) | not returned by checker (unknown) | not returned by checker (project is at github.com/scikit-image/scikit-image) | SUS (too-new/unknown-downloads/no-repo signals — false positive) | Approved |
| opencv-python | PyPI | 10+ yrs | not returned | github.com/opencv/opencv-python | SUS (false positive) | Approved |
| pandas | PyPI | 15+ yrs | not returned | not returned (project is github.com/pandas-dev/pandas) | SUS (false positive) | Approved |
| torch | PyPI | 10+ yrs | not returned | pytorch.org | SUS (false positive) | Approved |
| torchvision | PyPI | 10+ yrs | not returned | github.com/pytorch/vision | SUS (false positive) | Approved |
| pillow | PyPI | 15+ yrs | not returned | github.com/python-pillow/Pillow | SUS (false positive) | Approved |
| matplotlib | PyPI | 20+ yrs | not returned | matplotlib.org | SUS (false positive) | Approved |
| pytest | PyPI | 15+ yrs | not returned | github.com/pytest-dev/pytest | SUS (false positive) | Approved |
| numpy | PyPI | 15+ yrs | not returned | not returned | SUS (false positive) | Approved |
| sam2 (Meta model) | source install, not PyPI | n/a | n/a | github.com/facebookresearch/sam2 | Not applicable to the checker (source install) | Approved — install from source per README, do not `pip install sam2` |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** all nine PyPI packages above were flagged `SUS`, but this research assesses all nine as false positives from a checker that lacks download-count/repo telemetry for these entries, not genuine legitimacy risk — see rationale above. **Per protocol, the planner should still gate the actual `pip install` step behind a single `checkpoint:human-verify` (one checkpoint covering the whole `requirements.txt`/`pip install` line is sufficient — nine near-identical individual checkpoints for numpy/pandas/pytest etc. would be checkpoint fatigue for zero added safety), where the human visually confirms the resolved package names/versions before the install actually runs.**

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Nextcloud-synced raw photos (read-only)                         │
│  .../Batch 8 04-24-26/Poststretch/D12 05-11-26/IMG_8092.JPG     │
└───────────────────────────┬───────────────────────────────────-┘
                             │ path glob (segment_export.py --input-dir)
                             ▼
                 ┌───────────────────────┐
                 │ naming.py: parse path │───▶ (batch, batch_start_date,
                 │ segments via regex    │       condition, day, DATE=day_date)
                 └───────────┬───────────┘
                             │  + thread_number (prompted from user at click time,
                             │    NOT derivable from path/filename)
                             ▼
        ┌─────────────────────────────────────────┐
        │ sam2_session.py: load predictor ONCE     │
        │  (device = cuda>mps>cpu, PYTORCH_ENABLE_ │
        │   MPS_FALLBACK=1)                        │
        └───────────────────┬───────────────────────┘
                             │  per photo: set_image() once
                             ▼
        ┌─────────────────────────────────────────┐
        │ click_loop.py (matplotlib):              │
        │  left-click → positive point (label=1)   │
        │  right-click → negative point (label=0)  │
        │  each click → predictor.predict(...)     │
        │  key press → accept & export, or         │
        │              manual raster erase fallback│
        └──────────────┬──────────────┬─────────────┘
                        │              │
                mask (.png/.npy)   overlay QC (.png)
                        │              │
                        ▼              ▼
                 data/masks/     data/qc/
                        │
                        ▼
        ┌─────────────────────────────────────────┐
        │ measure.py (headless, per mask):         │
        │  binary_closing → remove_small_objects   │
        │  → skeletonize → distance_transform_edt  │
        │  → trim endpoints → per-point widths     │
        │  → area, mean(width), stdev(width)       │
        └───────────────────┬───────────────────────┘
                             ▼
                 data/csv/measurements.csv
                 {date,batch,condition,thread,area_px,
                  avg_diameter_px,stdev_px}

  (parallel branch, same session key)
┌─────────────────────────────────────────────────┐
│ ruler photo → calibrate.py:                      │
│  plt.ginput(2) on known cm span → px_per_cm       │
└───────────────────┬───────────────────────────────┘
                     ▼
         data/calibration/calibration.csv
         {date, batch, px_per_cm}
                     │
                     ▼
        ┌─────────────────────────────────────────┐
        │ build_csv.py:                            │
        │  pd.merge(measurements, calibration,     │
        │           on=["date","batch"], how="left")│
        │  → mm conversion → EXACT_R_SCRIPT_COLUMNS│
        └───────────────────┬───────────────────────┘
                             ▼
                     data/csv/final.csv
       (Thread, Batch, Condition, Date, Conversion (pixels/cm),
        Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm))
```

### Recommended Project Structure

Matches project ARCHITECTURE.md's `src/` layout exactly — this phase implements it, doesn't redesign it:

```
src/
├── segment/
│   ├── sam2_session.py     # load-once predictor + device fallback (SEG-03)
│   ├── click_loop.py       # matplotlib click-to-prompt UI (D-01/SEG-01/SEG-02)
│   └── naming.py           # path parser + canonical filename (EXPT-01, shared with future Stage X)
├── measure/
│   ├── measure_masks.py    # skeleton+distance-transform → area/diameter/stdev (MEAS-01/02)
│   └── qc_overlay.py       # mask boundary overlay PNG (EXPT-03)
├── calibrate/
│   └── ruler_scale.py      # two-click px/cm (CAL-01/02)
└── join/
    └── build_final_csv.py  # merge + exact-schema CSV (CSV-01/02/03)
tests/
├── test_naming.py          # AC-004: real example paths → correct (date,batch,condition)
├── test_measure.py         # AC-006: synthetic known-width mask
└── test_join.py            # AC-008: header-match + mm conversion spot-check
```

### Pattern 1: Load the SAM2 predictor once, reuse across every click and every photo in the session

**What:** Instantiate `SAM2ImagePredictor(build_sam2(...))` exactly once at script startup; call `.set_image(new_photo_array)` each time the user moves to a new photo (cheap — recomputes embeddings for that image only); call `.predict(...)` for every click within that photo (cheap — reuses the cached embedding).
**When to use:** Always, for any interactive multi-photo session. Reloading the model checkpoint per image is a documented performance trap (project PITFALLS.md, Performance Traps table) that turns an interactive tool into an unusable one across a real photo backlog.
**Example:**
```python
# Source: Context7 /facebookresearch/sam2 (README.md, image_predictor_example.ipynb)
import os
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"  # set BEFORE importing torch
import torch
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

def select_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

device = select_device()
checkpoint = "./sam2/checkpoints/sam2.1_hiera_small.pt"
model_cfg = "configs/sam2.1/sam2.1_hiera_s.yaml"
sam2_model = build_sam2(model_cfg, checkpoint, device=device)
predictor = SAM2ImagePredictor(sam2_model)   # <-- instantiate ONCE

# per photo in the session loop:
predictor.set_image(image_array)             # cheap-ish, once per photo

# per click within that photo:
masks, scores, logits = predictor.predict(
    point_coords=point_coords,   # accumulated (x,y) array, positive + negative
    point_labels=point_labels,   # 1 = thread (positive), 0 = exclude e.g. needle (negative)
    multimask_output=False,
)
```
Per project PITFALLS.md Pitfall 1 (MPS numerical quirks) and SAM2's own device-selection notebook code [CITED: github.com/facebookresearch/sam2/blob/main/notebooks/image_predictor_example.ipynb via Context7], always force `float32` explicitly and treat "gave a mask" and "mask is good enough" as separate human-verified steps — do not silently trust MPS output without the manual correction step already locked in by D-01/SEG-02.

### Pattern 2: matplotlib click-loop event handling (adapt, don't invent)

**What:** A single `mpl_connect("button_press_event", on_click)` callback that branches on `event.button` (left=1 positive, right=3 negative), re-runs `predictor.predict()` with the accumulated point set after every click, and redraws via `draw_idle()`.
**When to use:** This is the concrete shape of D-01's bespoke loop. A near-identical reference implementation already exists as a public GitHub issue on the same repo the project depends on — adapt it rather than designing the event loop from first principles.
**Example:**
```python
# Source: pattern described in facebookresearch/sam2 issue #421
# (https://github.com/facebookresearch/sam2/issues/421) — a <110-line matplotlib
# interactive point-prompt GUI using the exact predictor API from Pattern 1.
# [CITED: GitHub issue text, fetched via WebFetch this session — no runnable
#  code block was present in the issue itself, this is a description of its
#  approach, not a verbatim quote; treat as MEDIUM confidence, verify hands-on]

import matplotlib.pyplot as plt
import numpy as np

positive_points, negative_points = [], []

fig, ax = plt.subplots()
ax.imshow(image_array)

def redraw(mask):
    ax.clear()
    ax.imshow(image_array)
    ax.imshow(mask, alpha=0.5, cmap="Blues")  # blue-tint overlay
    if positive_points:
        pts = np.array(positive_points)
        ax.scatter(pts[:, 0], pts[:, 1], c="lime", marker="s")
    if negative_points:
        pts = np.array(negative_points)
        ax.scatter(pts[:, 0], pts[:, 1], c="red", marker="s")
    fig.canvas.draw_idle()

def on_click(event):
    if event.inaxes != ax:
        return
    if event.button == 1:      # left click = positive (thread)
        positive_points.append((event.xdata, event.ydata))
    elif event.button == 3:    # right click = negative (e.g. needle)
        negative_points.append((event.xdata, event.ydata))
    else:
        return

    coords = np.array(positive_points + negative_points)
    labels = np.array([1] * len(positive_points) + [0] * len(negative_points))
    masks, scores, _ = predictor.predict(
        point_coords=coords, point_labels=labels, multimask_output=False
    )
    redraw(masks[0])

cid = fig.canvas.mpl_connect("button_press_event", on_click)
plt.show()
# on a key press (e.g. 'a' = accept), save masks[0] + overlay, disconnect, move to next photo
```
**Fallback path (SEG-02):** if a negative point doesn't cleanly separate thread from needle, fall back to manual raster erase — the simplest version is a second mouse-drag mode that sets `mask[y, x] = False` along the dragged path before export; this doesn't need SAM2 involvement at all, it's pixel editing on the accepted mask array.

### Pattern 3: Mask → width statistics (skeleton + distance transform, with cleanup and endpoint trim)

**What:** Clean the mask boundary lightly, skeletonize it, sample the distance transform along the skeleton, discard a margin near both skeleton endpoints, then take mean/stdev of the remaining per-point widths.
**When to use:** MEAS-01/MEAS-02, every exported mask, fully automated (no human input at this stage).
**Example:**
```python
# Source: Context7 /scikit-image/scikit-image (release notes 0.25) +
# project PITFALLS.md Pitfall 2's own prescribed mitigation (endpoint trim,
# boundary smoothing) — synthesized pattern, [ASSUMED — validate against
# ImageJ ground truth in Phase 2 per MEAS-03, not this phase]
import numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize, binary_closing, remove_small_objects, disk

def measure_mask(mask: np.ndarray, endpoint_trim_px: int = 5) -> dict:
    # 1. Cleanup: close small boundary gaps, drop spurious tiny blobs
    cleaned = binary_closing(mask, footprint=disk(2))
    cleaned = remove_small_objects(cleaned, min_size=50)

    area_px = int(cleaned.sum())

    # 2. Skeleton (centerline) + distance transform (distance to nearest boundary)
    skeleton = skeletonize(cleaned)
    distance = ndi.distance_transform_edt(cleaned)

    # 3. Sample width = 2 * distance at skeleton pixels
    ys, xs = np.nonzero(skeleton)
    widths = 2.0 * distance[ys, xs]

    # 4. Trim a fixed pixel margin off both ends of the skeleton path to discard
    #    endpoint-spur artifacts (PITFALLS.md Pitfall 2's prescribed mitigation).
    #    Order points along the skeleton's principal axis as a simple proxy for
    #    "along the thread's length" (adequate for a roughly-straight single
    #    thread; a full graph-ordered walk via `skan` is the upgrade path if
    #    this proves too crude on curved threads).
    order = np.argsort(xs) if (xs.max() - xs.min()) >= (ys.max() - ys.min()) else np.argsort(ys)
    widths_ordered = widths[order]
    trimmed = widths_ordered[endpoint_trim_px:-endpoint_trim_px] if len(widths_ordered) > 2 * endpoint_trim_px else widths_ordered

    return {
        "area_px": area_px,
        "avg_diameter_px": float(np.mean(trimmed)),
        "stdev_px": float(np.std(trimmed, ddof=1)) if len(trimmed) > 1 else 0.0,
    }
```
**Note on the endpoint-trim/ordering shortcut above:** sorting skeleton pixels by their dominant axis coordinate is a simplification, not a true skeleton-graph walk — it is adequate for a single, roughly-straight thread segment (which is what SAM2 + manual correction should produce per-photo) but will misorder a strongly curved or self-overlapping skeleton. If Phase 2's ImageJ validation (MEAS-03) shows this producing systematically wrong stdev, the fix is either the `skan` library's proper branch/path ordering, or upgrading to MEAS-04's ray-cast method already deferred to v2 — do not silently patch this function further without re-validating.

### Pattern 4: Folder-path metadata parser — segment-by-segment regex, not fixed-depth split

**What:** Walk each path segment independently and test it against per-field regexes (batch, condition, day) rather than assuming a fixed folder depth — matches ARCHITECTURE.md's own warning that folder naming isn't perfectly uniform even within Phase 1's real-data scope.
**When to use:** EXPT-01, called once per exported mask.
**Example:**
```python
# Source: designed against the real example path in CONTEXT.md/PROJECT.md —
# [ASSUMED — only validated against the 1-2 example paths supplied in
#  CONTEXT.md; the AC-004 unit test must exercise real examples, not just this one]
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

BATCH_RE = re.compile(r"^Batch\s+(?P<batch>\d+)\s+(?P<batch_date>\d{2}-\d{2}-\d{2})$", re.IGNORECASE)
DAY_RE = re.compile(r"^D(?P<day>\d+)\s+(?P<day_date>\d{2}-\d{2}-\d{2})$", re.IGNORECASE)
CONDITION_RE = re.compile(r"^(Prestretch|Poststretch)$", re.IGNORECASE)

@dataclass(frozen=True)
class PhotoMetadata:
    batch: str
    batch_start_date: date   # from the Batch-folder segment; NOT the CSV "Date" column
    condition: str
    day: str
    date: date                # from the Day-folder segment; THIS is the CSV "Date" column
    source_path: Path

def _parse_mmddyy(s: str) -> date:
    mm, dd, yy = (int(p) for p in s.split("-"))
    return date(2000 + yy, mm, dd)

def parse_photo_path(photo_path: Path, nextcloud_root: Path) -> PhotoMetadata:
    segments = photo_path.relative_to(nextcloud_root).parts
    batch = batch_date = condition = day = day_date = None
    for seg in segments:
        if (m := BATCH_RE.match(seg)):
            batch, batch_date = m.group("batch"), _parse_mmddyy(m.group("batch_date"))
        elif (m := DAY_RE.match(seg)):
            day, day_date = m.group("day"), _parse_mmddyy(m.group("day_date"))
        elif CONDITION_RE.match(seg):
            condition = seg
    if None in (batch, batch_date, condition, day, day_date):
        raise ValueError(f"Could not parse required metadata from path: {photo_path}")
    return PhotoMetadata(
        batch=batch, batch_start_date=batch_date, condition=condition,
        day=day, date=day_date, source_path=photo_path,
    )
```
**Thread number is deliberately NOT parsed from the path** (per D-07's own note) — `click_loop.py` must prompt the user for it at click/export time (e.g. a simple `input("Thread number: ")` in the CLI, or a matplotlib text box), since shot order/thread-numbering convention varies by batch/day per PROJECT.md.

### Anti-Patterns to Avoid

- **Reloading the SAM2 checkpoint inside the per-photo or per-click loop:** turns an interactive tool into an unusable one across a real backlog — load once at script startup (Pattern 1). [CITED: project PITFALLS.md Performance Traps]
- **Assuming a fixed folder depth for the path parser:** the real data already has two conventions (nested `Batch.../Poststretch/D12.../IMG_8092.JPG` vs. older ad hoc `5.11.JPG`) — a positional/fixed-index parser will silently break on the second convention. Use segment-by-segment regex matching (Pattern 4), and hard-fail loudly (`raise ValueError`) rather than silently returning partial metadata, per project PITFALLS.md Pitfall 5's own warning about silent skip/collision.
- **Treating the batch-start date as the CSV "Date" column:** see Open Question #1 below — this is the single highest-risk ambiguity in this phase's metadata handling.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SAM2 point-prompt inference | A custom PyTorch forward-pass wrapper around SAM2's internals | `SAM2ImagePredictor.predict()` | It's already a 3-line official wrapper API (`set_image` + `predict`) — there is nothing to hand-roll here |
| Skeleton/centerline extraction | A custom thinning algorithm | `skimage.morphology.skeletonize` | Textbook, well-tested, exactly matches project STACK.md's own recommendation |
| Distance-to-boundary per pixel | A hand-rolled nearest-boundary search | `scipy.ndimage.distance_transform_edt` | O(n) exact Euclidean distance transform; a hand-rolled version would be slower and more bug-prone for zero benefit |
| Full skeleton-graph branch/endpoint classification | A bespoke graph-walk over skeleton pixels | `skan` (only if Pattern 3's axis-sort proxy proves insufficient) | Deliberately deferred — not needed for Phase 1's single-thread case per Alternatives Considered above; don't build this preemptively (YAGNI) |
| Exact-column CSV writing | Manual string-joining / `csv.writer` row-by-row | `pandas.DataFrame.to_csv(path, columns=EXACT_LIST, index=False)` | One declarative line guarantees byte-for-byte column control; project STACK.md already made this call |

**Key insight:** every piece of this phase's "hard" math (skeleton, distance transform, point-prompt segmentation, CSV column control) is already a one-to-three-line call in an existing, well-tested library. The actual engineering work in Phase 1 is gluing these calls together correctly (predictor lifecycle, click-loop state, path-segment parsing, join keys) — not reimplementing any of the math itself.

## Common Pitfalls

*(Carried forward and sharpened from project-level `research/PITFALLS.md`; only phase-1-relevant sharpening is repeated here — see that file for the full catalogue including Phase 2/3-scoped pitfalls like idempotent skip and folder-cleanup collisions.)*

### Pitfall 1: Ambiguous "Date" column — batch-start date vs. day/measurement date

**What goes wrong:** The real folder path carries two dates: the batch-start date embedded in the `Batch 8 04-24-26` segment, and the day/measurement date embedded in the `D12 05-11-26` segment. CONTEXT.md explicitly flags that the R script's existing sample CSV used per-thread dates like `8/1/25` — which reads as a specific day's date, not a batch-start date — but this research has **not** seen the actual R-script sample CSV or its source data to confirm which folder-date those sample rows came from.
**Why it happens:** Both dates are syntactically identical (`MM-DD-YY`) and both are plausible candidates for "the date this thread was measured" — a parser that grabs "the first date-looking string in the path" will silently pick the wrong one.
**How to avoid:** This research's recommendation (implemented in Pattern 4) is: **use the day-folder date (`D12 05-11-26` → `05-11-26`) as the CSV `Date` column**, since that's the date the photo was actually taken/measured, which is the more natural reading of a per-thread "Date" column in a measurement CSV. Keep the batch-start date available on `PhotoMetadata` (as `batch_start_date`) for provenance/debugging, but do not use it as the CSV `Date` value.
**Warning signs:** If a human spot-check of AC-008's final CSV shows dates that don't match the day the photo was actually shot (per the day-folder), the parser picked the wrong field.
**Phase to address:** Phase 1 (EXPT-01/CSV-03) — this must be resolved before the first real CSV row is produced, not discovered later during Phase 2 validation. **Flagged in Assumptions Log (A1) — recommend confirming with the user against a real R-script sample CSV row before locking this into the plan as unquestioned.**

### Pitfall 2: Confusing "predictor state" with "click state" across photos

**What goes wrong:** If the click loop's `positive_points`/`negative_points` lists (Pattern 2) aren't reset when moving to a new photo, the next photo's SAM2 call gets contaminated with the previous photo's click coordinates (which are meaningless in the new image's pixel space) — SAM2 won't error, it'll just silently produce garbage prompts at the wrong pixel locations.
**Why it happens:** The predictor itself is correctly persistent (Pattern 1) — it's easy to conflate "keep the predictor alive" with "keep all click state alive," when only the former should survive a photo transition.
**How to avoid:** Explicitly clear `positive_points`, `negative_points`, and any accepted-but-uncommitted mask state at the start of each new photo's session, immediately after `predictor.set_image()`.
**Warning signs:** A mask that looks like it's segmenting something in a completely wrong location relative to the currently-displayed photo.
**Phase to address:** Phase 1 (SEG-01/SEG-02) — this is a per-session bug class, not a batch-scale one; catch it in the first multi-photo manual test run (AC-009).

### Pitfall 3: pandas 3.0 is now current stable — don't silently pick it up via an unpinned install

**What goes wrong:** This research confirmed `pandas 3.0.3` is the current PyPI release (project STACK.md's own "What NOT to Use" section had already flagged this as a live risk when it saw an early 3.x signal). An unpinned `pip install pandas` today would install 3.0.3, not the 2.x line most existing pandas tutorials/examples (including this research's own Context7 lookups) are written against.
**Why it happens:** Default `pip install pandas` always grabs latest.
**How to avoid:** Pin `pandas>=2.2,<3` in `requirements.txt` per the Standard Stack table above, unless the planner deliberately decides to verify and adopt 3.x.
**Warning signs:** `to_csv`/`merge` behaving identically (their core API is unaffected) but other pandas code elsewhere in the pipeline hitting the copy-on-write or default-string-dtype changes unexpectedly.
**Phase to address:** Phase 1, at environment setup — a one-line pin, not a code change.

## Runtime State Inventory

Not applicable — this is a greenfield phase (no existing code, no rename/refactor/migration in scope per PROJECT.md and CONTEXT.md's `<code_context>` section, which explicitly states "Greenfield project — no existing code, no codebase maps"). Skipped per the trigger condition in the verification protocol.

## Code Examples

See Architecture Patterns 1-4 above for the full annotated examples (SAM2 predictor lifecycle, click-loop, measurement pipeline, path parser). Two additional examples not shown above:

### Two-click ruler calibration (matplotlib `ginput`, per Alternatives Considered)
```python
# Source: standard PyImageSearch-style reference-object calibration pattern
# [CITED: project STACK.md + WebSearch this session, cross-confirmed pattern —
#  no single canonical official doc for this specific technique since it's a
#  general computer-vision idiom, not a library API]
import matplotlib.pyplot as plt
import numpy as np

def calibrate_px_per_cm(ruler_image: np.ndarray, known_cm_span: float) -> float:
    fig, ax = plt.subplots()
    ax.imshow(ruler_image)
    ax.set_title(f"Click two points spanning exactly {known_cm_span} cm")
    points = plt.ginput(2, timeout=0)  # blocks until 2 clicks
    plt.close(fig)
    (x1, y1), (x2, y2) = points
    pixel_distance = float(np.hypot(x2 - x1, y2 - y1))
    return pixel_distance / known_cm_span
```

### Final CSV assembly with exact column contract
```python
# Source: Context7 /websites/pandas_pydata (merging.html) — merge-on-multiple-keys
# pattern; to_csv(columns=...) is standard pandas API, not phase-specific
import pandas as pd

EXACT_R_SCRIPT_COLUMNS = [
    "Thread", "Batch", "Condition", "Date", "Conversion (pixels/cm)",
    "Avg diameter(px)", "StDev(px)", "AvgDiameter(mm)", "StDev(mm)",
]

def build_final_csv(measurements_csv: str, calibration_csv: str, output_csv: str) -> None:
    measurements = pd.read_csv(measurements_csv)   # one row per thread
    calibration = pd.read_csv(calibration_csv)     # one row per (date, batch) session

    merged = measurements.merge(calibration, on=["date", "batch"], how="left")
    missing = merged[merged["px_per_cm"].isna()]
    if not missing.empty:
        # Phase 1: loud failure is acceptable even though CAL-03's formal hard-fail
        # contract is Phase 2 scope — don't silently fabricate a factor either way.
        raise ValueError(
            f"No calibration factor for sessions: "
            f"{missing[['date', 'batch']].drop_duplicates().to_dict('records')}"
        )

    merged["AvgDiameter(mm)"] = merged["avg_diameter_px"] / merged["px_per_cm"] * 10
    merged["StDev(mm)"] = merged["stdev_px"] / merged["px_per_cm"] * 10

    final = merged.rename(columns={
        "thread": "Thread", "batch": "Batch", "condition": "Condition", "date": "Date",
        "px_per_cm": "Conversion (pixels/cm)", "avg_diameter_px": "Avg diameter(px)",
        "stdev_px": "StDev(px)",
    })[EXACT_R_SCRIPT_COLUMNS]
    final.to_csv(output_csv, index=False)
```

### Synthetic-mask test fixture for AC-006 (per `python-testing` skill conventions)
```python
# Source: standard pattern for testing width-measurement functions against a
# hand-computable ground truth — [ASSUMED shape, synthesized from general
# fiber-diameter-measurement testing conventions found via WebSearch this
# session; adapt exact tolerance to real skeleton-endpoint behavior observed
# once measure_mask() is actually implemented]
import numpy as np
import pytest
from measure.measure_masks import measure_mask

def test_measure_mask_straight_strip_known_width():
    """A straight rectangular strip of known width W should measure close to W."""
    mask = np.zeros((100, 120), dtype=bool)
    mask[40:60, 10:110] = True   # 20px-wide, 100px-long horizontal strip

    result = measure_mask(mask, endpoint_trim_px=5)

    assert result["area_px"] == 20 * 100
    assert result["avg_diameter_px"] == pytest.approx(20.0, abs=1.5)
    assert result["stdev_px"] == pytest.approx(0.0, abs=1.0)  # uniform width → low spread

def test_measure_mask_empty_raises_or_returns_zero():
    """Guard against a degenerate/empty mask reaching the measurement stage."""
    mask = np.zeros((50, 50), dtype=bool)
    with pytest.raises(ValueError):
        measure_mask(mask)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual ImageJ perpendicular edge-tracing (the project's own prior workflow) | SAM2 click-to-segment + skeleton/distance-transform | This project, Phase 1 | Trades a fully-manual, high-precision method for a semi-automated, "comparable but not identical" method — MEAS-03's ImageJ validation (Phase 2) is what confirms the tradeoff is acceptable, not this phase |
| SAM1 (`SamPredictor`) | SAM2 (`SAM2ImagePredictor`) point-prompt API | SAM2 release (2024) | Newer decoder, video-capable (unused here), officially still calls MPS support "preliminary" [CITED: facebookresearch/sam2 notebook device-selection code, via Context7] — this is why SEG-03's CPU fallback exists |
| `skimage.morphology.skeletonize_3d` | `skimage.morphology.skeletonize` (unified) | scikit-image 0.25.0 (2024-12-13) [CITED: scikit-image release notes 0.25, via Context7] | `skeletonize_3d` is fully removed as of 0.25 — do not follow any tutorial that still references it |

**Deprecated/outdated:**
- `skimage.morphology.skeletonize_3d`: removed in scikit-image 0.25.0, replaced by unified `skeletonize`. [CITED: Context7 scikit-image release notes]
- pandas 1.x/early-2.x-era `DataFrame.append()`: not used in any example above (merge/to_csv only), but worth flagging since older pandas tutorials still reference it — do not let it appear in generated code.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The CSV "Date" column should use the day/measurement-folder date (`D12 05-11-26`), not the batch-start date (`Batch 8 04-24-26`) | Pattern 4, Pitfall 1 | If wrong, every CSV row's Date column is off by however many days/weeks separate batch-start from that specific measurement day — a silent, systematic data-correctness bug that would only surface when someone cross-checks against the R script's downstream analysis. **Recommend explicit user confirmation against a real R-script sample CSV row before this is locked into the plan as settled.** |
| A2 | `configs/sam2.1/sam2.1_hiera_s.yaml` is the correct config filename for the small checkpoint | Standard Stack, Code Example #1 | Low risk — `_l.yaml`/`_t.yaml` are directly confirmed [CITED], `_s.yaml` is inferred by consistent naming convention; if wrong, it's an immediate, loud `FileNotFoundError` at model-load time, not a silent data bug |
| A3 | The GitHub issue #421 click-loop description (no runnable code block was retrievable) accurately reflects a working implementation shape | Pattern 2 | Low-medium risk — the event-handling shape (mpl_connect/button/draw_idle) is standard matplotlib regardless of whether this specific issue's code is exactly right; verify hands-on in the first spike session before trusting the accept/erase key-binding details |
| A4 | Ruler photos live in the same Nextcloud folder tree and can reuse (or trivially adapt) the same path parser for their session key | Open Question #1 | Medium risk — if ruler photos are stored ad hoc (not in the batch/day folder structure), `calibrate.py` needs its own metadata-entry mechanism instead of relying on `naming.py`; affects CAL-02's session-keying implementation, not just a detail |
| A5 | The axis-sort endpoint-ordering shortcut in Pattern 3 (sort skeleton pixels by dominant axis instead of a true graph walk) is adequate for Phase 1's real thread photos | Pattern 3 | Medium risk on curved threads specifically — this is exactly the shape of PITFALLS.md's Pitfall 2 (curvature bias); Phase 2's MEAS-03 ImageJ validation is the designed catch for this, so it is an acceptable Phase-1-only risk, not a blocker |

## Open Questions

1. **Where do ruler photos live in the real folder structure, and what identifies their session (date/batch)?**
   - What we know: threads live in `Batch N <date>/<Condition>/D<day> <date>/IMG_xxxx.JPG`; CAL-02 requires one calibration factor per session keyed the same way.
   - What's unclear: whether a ruler photo sits inside the same per-day folder (and can reuse `parse_photo_path`), or lives in a separate ruler-specific folder/convention not yet described anywhere in CONTEXT.md/PROJECT.md.
   - Recommendation: confirm with the user during planning; if unconfirmed, design `calibrate.py` to accept either a folder it can run the same parser against, or an explicit `--date --batch` CLI override per ruler photo, so the script isn't blocked on this being resolved before Phase 1 starts.

2. **Does the R script's actual sample CSV confirm the day-date-not-batch-date assumption (A1)?**
   - What we know: CONTEXT.md itself already flags this as something "the planner must get right," citing sample dates like `8/1/25`.
   - What's unclear: this research had no access to the actual R-script sample CSV or its source photos to cross-check which folder-date those sample dates came from.
   - Recommendation: the planner should treat this as a discuss-phase-worthy confirmation point if not already resolved, or accept A1's recommendation with a note that Phase 1's AC-008 manual value spot-check is the safety net that would catch this being wrong.

## Security Domain

Required per `security_enforcement: true` in `.planning/config.json` (ASVS level 1). This is a single-user, local-only, offline research tool (per BRIEF.md's own Risk Review: "Security/privacy: No — Local-only, no network calls, no PII beyond research photos"), so most ASVS categories are not applicable — the relevant slice is input validation on file-path/filename handling and data-integrity guarantees (EXPT-02's "never modify raw source" requirement), not authn/authz/crypto.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Single local user, no accounts, no login surface |
| V3 Session Management | No | No web session/cookie concept in a local CLI pipeline |
| V4 Access Control | No | No multi-user access boundary exists |
| V5 Input Validation | Yes | Folder-path parsing (Pattern 4) must `raise ValueError` on unparseable segments rather than silently proceeding with partial/wrong metadata — this is the pipeline's actual "untrusted input" surface (real-world folder-naming inconsistency, not an adversarial user) |
| V6 Cryptography | No | No secrets, no encrypted data, no crypto operations anywhere in this phase |
| V12 File & Resources (ASVS 4.x numbering; "V8 Data Protection" in some 3.x mappings) | Yes | EXPT-02's "never modify raw source" requirement is this phase's actual data-integrity control — enforce via read-only file access patterns (open-then-close, never opening the source path in a write mode) and verify with AC-003's automated hash-before/after check |

### Known Threat Patterns for this stack

Not a web-facing stack, so classic STRIDE web patterns (injection, CSRF, XSS) largely don't apply. The two realistic failure classes are data-integrity, not security in the adversarial sense:

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Accidental write/rename into the Nextcloud-synced raw-photo tree | Tampering (accidental, not adversarial) | Read-only access pattern for all source-path reads; every pipeline write target lives under the repo's own `data/` directory, never back into the synced source path (already established in project ARCHITECTURE.md Anti-Pattern 4) |
| Path-traversal-shaped bug from unvalidated folder segments (e.g. a malformed path producing a write outside `data/`) | Tampering / Elevation of privilege (theoretical, not a realistic adversary here, but still a correctness bug class) | Construct all output paths via `pathlib.Path` joins against a fixed `data/` root, never by string-concatenating raw path segments into a write target |

## Sources

### Primary (HIGH confidence)
- `/facebookresearch/sam2` (Context7) — `SAM2ImagePredictor` point-prompt API (`set_image`/`predict`), `build_sam2` local-checkpoint loading, device-selection (`cuda`/`mps`/`cpu`) pattern, MPS-preliminary-support warning text, checkpoint size/FPS table. [VERIFIED: Context7 query against official repo docs this session]
- `pip index versions` live queries this session for `scikit-image`, `pandas`, `opencv-python`, `torch` — current stable version numbers. [VERIFIED: registry query this session]

### Secondary (MEDIUM confidence)
- `/scikit-image/scikit-image` (Context7) — `skeletonize_3d` removal in 0.25.0, `skeletonize` dtype-handling clarification. [CITED: Context7 query against official release notes this session]
- `/websites/pandas_pydata` (Context7) — `pd.merge(..., on=[...], how=...)`, `DataFrame.to_csv(columns=..., index=False)`. [CITED: Context7 query against official pandas docs this session]
- GitHub `facebookresearch/sam2` issue #421 — described (not verbatim-quoted, no retrievable code block) matplotlib click-loop shape. [CITED: WebFetch this session]
- WebSearch: matplotlib `mpl_connect`/`button_press_event` official event-handling docs. [CITED: matplotlib.org, via WebSearch this session]
- WebSearch: `skan` skeleton-graph-analysis library existence/purpose (considered and deliberately not adopted — see Alternatives Considered). [CITED: skeleton-analysis.org, via WebSearch this session]

### Tertiary (LOW confidence)
- WebSearch: OpenCV `cv2.setMouseCallback` two-click ruler-calibration pattern — general community idiom, no single canonical source. [LOW confidence, marked for hands-on validation]
- WebSearch: synthetic-mask pytest fixture shape for fiber/thread width testing — synthesized from general fiber-diameter-measurement literature, not a copy-pasted test. [LOW confidence, adapt tolerance values once `measure_mask()` is actually implemented against real data]
- Package Legitimacy Audit `SUS` verdicts for numpy/pandas/matplotlib/pytest/torch/torchvision/pillow/opencv-python/scikit-image — assessed as false positives by this research based on general knowledge of these being long-established libraries; not independently re-verified against a download-count API this session. [LOW confidence on the raw checker signal itself, but the packages' legitimacy is not genuinely in question]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every core library was already locked in project-level STACK.md; this phase only re-verified exact version numbers and the specific API calls needed (Context7-confirmed)
- Architecture: MEDIUM — the stage-per-script structure is inherited directly from project ARCHITECTURE.md (already MEDIUM-confidence there); the click-loop and parser *implementation shapes* here are synthesized/adapted, not copy-verified against a single canonical running example
- Pitfalls: MEDIUM — MPS/skeleton-curvature/calibration pitfalls are carried forward from already-researched project PITFALLS.md; the two new phase-specific pitfalls here (Date-column ambiguity, click-state-across-photos) are this research's own analysis, cross-checked against CONTEXT.md's own flagging of the Date ambiguity

**Research date:** 2026-07-08
**Valid until:** 30 days for the pandas/scikit-image/opencv-python version pins (fast-moving PyPI releases); SAM2 API surface itself is more stable but MPS support status should be re-checked if this research is reused more than ~60 days out, since it's explicitly called "preliminary" by the upstream maintainers and could change without notice
