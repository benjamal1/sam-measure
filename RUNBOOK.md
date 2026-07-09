# Runbook — running the pipeline on real photos

For setup (first-time venv/SAM2 install) see `README.md`. This is the "how do I actually
run this again" guide for a normal analysis session.

## 0. One-time per session

```bash
cd ~/thread-compaction-analysis-auto
git pull                       # pick up any fixes since last time
```

All commands below assume you're in the repo root with the venv available. Prefix every
Python invocation with `PYTHONPATH=src .venv/bin/python` — the `-m module.path` form needs
`src/` on the path, and the plain `pytest`/`python` on your PATH can silently resolve to a
different interpreter (pyenv shim) than the project's venv.

Keep your photo folder **local, not cloud-synced** (Nextcloud/iCloud/etc.) while running
the pipeline — cloud-synced mounts have caused both slow first-open (files fetched over
network on first touch) and outright crashes (stale file handles) in practice.

## 1. Segment — click each thread, export masks

```bash
PYTHONPATH=src .venv/bin/python -m segment.segment_export \
  --input-dir "/path/to/your/photos"
```

- Walks the **entire folder tree recursively** in one run — point it at the top-level
  folder to process every batch/condition/day in one sitting, no restarting per photo.
- `ruler_*.JPG` files are automatically excluded from the click queue (they're consumed
  separately by the calibration step below).
- **Condition and thread number are typed by you**, not guessed from the folder — the tool
  shows a suggested default parsed from the path when it can, but your typed value always
  wins. Date/batch are auto-detected from the folder names (`Batch N`, `D# MM-DD-YY`,
  `PreStretch`/`PostStretch`) wherever those are present, in any order/nesting.
- **The window opens first**, before anything is asked of you — you look at the photo,
  click, then type condition + thread when you press `a` to accept.

**In the click window:**

| Action | Key/click |
|---|---|
| Positive point (mark thread) | Left click |
| Negative point (mark "not thread") | Right click |
| Accept current mask | `a` — then type condition + thread |
| Erase mode (fix a bad region, e.g. a needle) | `e` to toggle, then **click-drag a box** over the region to remove, release to erase |
| Skip this photo | `n` |

After accepting a mask, you're asked whether to **label another thread on the same photo**
(for the multi-thread composite shots) or **advance to the next photo**.

Masks land in `data/masks/`, a red-tinted overlay QC image lands in `data/qc/` for every
accepted mask — check `data/qc/` if a measurement looks off later, the overlay shows
exactly what was measured.

**Resuming after a restart:** a photo whose window you've already closed (either you
labeled all its threads and advanced, or pressed `n` to skip it) is never reopened again
on a later run — it's tracked in `data/processed_photos.json`. Safe to Ctrl+C mid-session
any time; rerun the same command and it picks up exactly where you left off. `--force`
ignores this and reprocesses everything from scratch.

**If a folder's date/batch truly can't be inferred** from its path, pass them explicitly:
`--date MM-DD-YY --batch N`. (`--condition`/`--thread` can also be forced this way, but
that applies the SAME value to every photo in the run — only use them for a single
already-known folder, not a mixed batch-wide run.)

## 2. Measure — mask → pixel-space area/diameter/MAD

```bash
PYTHONPATH=src .venv/bin/python -m measure.measure_masks
```

Reads every mask in `data/masks/`, writes `data/csv/measurements.csv` with area, average
diameter, StDev, and MAD (median absolute deviation — a spread metric more robust to
SAM2's jagged mask-boundary noise than StDev; both are reported). A mask that somehow
can't be measured (e.g. empty) is skipped with a printed warning — it won't abort the
whole batch.

## 3. Calibrate — ruler photos → pixels/cm

```bash
PYTHONPATH=src .venv/bin/python -m calibrate.ruler_scale --ruler-dir "/path/to/your/photos"
```

Finds every `ruler_*.JPG` recursively under the folder (same tree you segmented), opens
each one, and asks you to **click two points exactly 0.5cm apart** on the ruler's fine mm
tick marks (zoom in first — these are macro shots, not a full ruler). Writes
`data/calibration/calibration.csv`.

A session's date with no ruler of its own automatically falls back to the most recent
**earlier-dated ruler from the same batch** at the CSV-join step (step 4) — never across
batches. You don't need a ruler photo for every single day, just don't skip entire batches.

## 4. Build the final CSV

```bash
PYTHONPATH=src .venv/bin/python -m join.build_final_csv
```

Joins `measurements.csv` + `calibration.csv` into `data/csv/final.csv`, in the exact
column order your R script expects, plus extra columns after them: `area_px`, `area_mm2`,
`mad_px`, `mad_mm`, `flag`, `flag_reason`.

**Hard-fails loudly** (no partial/stale `final.csv` written) if any thread's session has
no resolvable calibration (exact or same-batch fallback) — the error names the exact
session and thread so you know what to fix (missing ruler photo, wrong date, etc.).

**`flag`/`flag_reason`**: a thread whose area or diameter is a statistical outlier
compared to its own same-date/batch/condition siblings gets flagged — worth a glance at
its `data/qc/` overlay to check for a mislabel, but it's advisory only, never blocks the
run.

## Troubleshooting

- **Nothing happens, empty manifest printed immediately** — `--input-dir` didn't resolve
  to a real folder (typo, or a copy-pasted path with a lookalike unicode character). The
  tool now fails loudly with a clear message instead of silently doing nothing — if you
  see "no .JPG photos found", double-check the path, ideally by `cd`-ing into it
  interactively (tab-complete) rather than retyping it.
- **A ValueError about "could not derive any date/batch metadata"** — the photo's folder
  doesn't contain a recognizable `D# MM-DD-YY` day folder anywhere in its path. Pass
  `--date MM-DD-YY --batch N` explicitly for that run, or fix the folder name.
- **A hard-fail from `build_final_csv` naming a session** — that session has no ruler
  calibration it can use (not even a same-batch earlier one). Add a ruler photo for that
  batch, or an earlier date in the same batch, then rerun step 3 and 4.
- **Ctrl+C prints a message and quits** — that's expected, not a crash. Every accepted mask
  already wrote to disk immediately, so nothing is lost; rerun the same command to resume.

## Speed

The first click on each photo pays a one-time SAM2 encoder cost (photo → embedding); every
click after that on the same photo is cheap. If it's still too slow, try the smaller `tiny`
checkpoint (faster, small accuracy tradeoff — hasn't been re-validated against ImageJ
ground truth the way `small` has):

```bash
curl -L -o vendor/sam2/checkpoints/sam2.1_hiera_tiny.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt

PYTHONPATH=src .venv/bin/python -m segment.segment_export \
  --input-dir "/path/to/your/photos" \
  --checkpoint vendor/sam2/checkpoints/sam2.1_hiera_tiny.pt \
  --model-cfg configs/sam2.1/sam2.1_hiera_t.yaml
```

## Tests

```bash
.venv/bin/python -m pytest -q -m "not slow"    # fast suite, no SAM2/torch needed, run anytime
.venv/bin/python -m pytest -q -m slow           # real SAM2 inference against real photos
```
