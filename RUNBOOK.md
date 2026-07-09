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
| Zoom in/out | Scroll wheel, centered on cursor |
| Accept current mask | `a` — then type condition + thread |
| Erase mode (fix a bad region, e.g. a needle) | `e` to toggle, then **click-drag a box** over the region to remove, release to erase |
| Undo last click or erase | `u` — never undoes an already-accepted/exported mask |
| Skip this photo | `n` |
| Quit the whole run | `q` — see below, not Ctrl+C |

After accepting a mask, you're asked whether to **label another thread on the same photo**
(for the multi-thread composite shots) or **advance to the next photo**.

Masks land in `data/masks/`, a red-tinted overlay QC image lands in `data/qc/` for every
accepted mask — check `data/qc/` if a measurement looks off later, the overlay shows
exactly what was measured.

**Resuming after a restart:** a photo whose window you've already closed (either you
labeled all its threads and advanced, or pressed `n` to skip it) is never reopened again
on a later run — it's tracked in `data/processed_photos.json`. `--force` ignores this and
reprocesses everything from scratch.

**To stop mid-session, press `q` in the plot window — not Ctrl+C.** Ctrl+C during Tk's
window loop hits a known Tk/macOS bug (Tcl's own signal handler tears the process down
mid-flight and hard-crashes with an abort trap) — harmless (nothing is lost, same as any
other stop), but the crash trace looks alarming. `q` stops the whole run cleanly through
plain Python instead of a signal. Rerun the same command any time to resume.

**If a folder's date/batch truly can't be inferred** from its path, pass them explicitly:
`--date MM-DD-YY --batch N`. (`--condition`/`--thread` can also be forced this way, but
that applies the SAME value to every photo in the run — only use them for a single
already-known folder, not a mixed batch-wide run.)

## 1.5. Clean up masks — strip disconnected stray blobs (optional but recommended)

```bash
# preview first — writes nothing
PYTHONPATH=src .venv/bin/python scripts/cleanup_masks.py --masks-dir data/masks

# writes a full cleaned COPY to data/masks_cleaned/ — originals in data/masks/ untouched
PYTHONPATH=src .venv/bin/python scripts/cleanup_masks.py --masks-dir data/masks --apply
```

Strips any blob disconnected from the largest region in each mask (e.g. SAM2 picking up a
small stray patch elsewhere in frame) — one less thing to manually erase in the click loop.
Only removes DISCONNECTED specks; a stray region actually touching/overlapping the real
thread still needs manual erasing in step 1. Writes every mask (cleaned or already-clean) to
`data/masks_cleaned/` so step 2 has the full set to work from — point step 2 at whichever
folder (`data/masks` or `data/masks_cleaned`) you want measured.

This is completely independent of segmentation progress — `data/processed_photos.json` and
the originals in `data/masks/` are untouched either way, so going back to step 1 later to
segment more photos works exactly the same regardless of whether you've run this or any
later pipeline step in between.

## 2. Measure — mask → pixel-space area/diameter/MAD

```bash
PYTHONPATH=src .venv/bin/python -m measure.measure_masks --masks-dir data/masks_cleaned
```

(Omit `--masks-dir` to read straight from `data/masks/` instead, if you skipped step 1.5.)

Writes `data/csv/measurements.csv` with area, average diameter, StDev, and MAD (median
absolute deviation — a spread metric more robust to SAM2's jagged mask-boundary noise than
StDev; both are reported). A mask that somehow
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
`mad_px`, `mad_mm`, `flag`, `flag_reason`, `calibration_date`, `calibration_source`,
`ruler_source_path`.

**Hard-fails loudly** (no partial/stale `final.csv` written) if any thread's session has
no resolvable calibration (exact or same-batch fallback) — the error names the exact
session and thread so you know what to fix (missing ruler photo, wrong date, etc.).

**`flag`/`flag_reason`**: a thread whose area or diameter is a statistical outlier
compared to its own same-date/batch/condition siblings gets flagged — worth a glance at
its `data/qc/` overlay to check for a mislabel, but it's advisory only, never blocks the
run.

**`calibration_date`/`calibration_source`/`ruler_source_path`**: which ruler actually
calibrated this row — `calibration_date` can differ from the thread's own `Date` when the
same-batch fallback kicked in (no ruler for that exact day), and `calibration_source` is
`exact` or `fallback` so you can tell at a glance. `ruler_source_path` points at the actual
ruler photo used, for full traceability.

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
- **Ctrl+C crashes with an abort trap / crash report** — use `q` in the plot window instead
  (see above). Nothing is lost either way, but `q` doesn't crash.
- **Need to redo one specific thread/photo** — use the helper script instead of editing
  `processed_photos.json` by hand:

  ```bash
  PYTHONPATH=src .venv/bin/python scripts/flag_for_redo.py \
    --stem 2025-11-14_batch4_poststretch_threadLH \
    --photo "/path/to/the/original/photo.JPG"
  ```

  (repeat `--stem` for multiple threads on the same composite photo). Deletes that thread's
  mask + QC overlay and unmarks the photo in `data/processed_photos.json`, so its window
  reopens on the next segment run while every other already-done photo still skips. Safe to
  rerun — no-ops cleanly if the mask or photo entry is already gone.

  Nothing else needs manual cleanup: `cleanup_masks.py --apply` mirrors `data/masks_cleaned/`
  to whatever's currently in `data/masks/` (removes stale entries for anything you deleted),
  and `measure_masks`/`build_final_csv` regenerate their CSVs from scratch every run — so as
  long as you rerun the later steps after re-segmenting, the redone thread's old numbers
  disappear on their own. `--force` on `segment_export` is the blunt alternative: reprocesses
  EVERY photo in the run, not just one.

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

Have real GPU compute available (e.g. a lab machine)? Go the other way — use the largest,
most accurate checkpoint instead, since the speed/accuracy tradeoff only mattered when
compute was the bottleneck:

```bash
curl -L -o vendor/sam2/checkpoints/sam2.1_hiera_large.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt

CUDA_VISIBLE_DEVICES=0 PYTHONPATH=src .venv/bin/python -m segment.segment_export \
  --input-dir "/path/to/your/photos" \
  --checkpoint vendor/sam2/checkpoints/sam2.1_hiera_large.pt \
  --model-cfg configs/sam2.1/sam2.1_hiera_l.yaml
```

## Running over SSH on a remote GPU machine — seeing the click window

Plain `ssh` never forwards a display — the click window would fail to open, or (if the
remote machine has its own monitor) open there instead of on your laptop.

**Best option: matplotlib's WebAgg backend** — serves the plot over HTTP instead of a
native window, viewable in an ordinary browser tab. No XQuartz, and it's built for network
latency (websocket updates) rather than X11's per-pixel round-trips:

```bash
MPLBACKEND=WebAgg PYTHONPATH=src .venv/bin/python -m segment.segment_export --input-dir ...
```

It'll print a `http://127.0.0.1:8988/` URL — forward that port (`ssh -L 8988:localhost:8988
user@host`, or let VS Code Remote-SSH auto-forward it) and open it in a browser on your
laptop. Clicks, keys, and scroll all work through the browser.

Alternative: X11 forwarding (`ssh -X`/`-Y` + XQuartz on macOS) also works, but tends to be
laggier for image-heavy redraws (erase-box drag, zoom) since every pixel round-trips instead
of just the websocket deltas WebAgg sends.

## Tests

```bash
.venv/bin/python -m pytest -q -m "not slow"    # fast suite, no SAM2/torch needed, run anytime
.venv/bin/python -m pytest -q -m slow           # real SAM2 inference against real photos
```
