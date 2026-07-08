# Morning Test — Validate on the M2 Mac

Everything below was built and unit-tested overnight on a Linux OptiPlex (CPU-only, no
display for the click UI). All the pure logic — naming/parsing, measurement math,
calibration math, CSV assembly, the SAM2 predictor itself — is real and tested against
real photos, including a full walking-skeleton run against `08-03-25/5.11.JPG` +
`ruler.JPG` producing a correct `final.csv` row.

**What could NOT be tested overnight:** the MPS backend (no GPU on the build box), and
the actual interactive click UX (nobody there to click). That's what this checklist covers.

## 1. Setup

```bash
git pull
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
git clone --depth 1 https://github.com/facebookresearch/sam2.git vendor/sam2
uv pip install -e vendor/sam2
curl -L -o vendor/sam2/checkpoints/sam2.1_hiera_small.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt
```

Run the fast suite first — should be 40 passed, ~5s, all green (proves nothing broke in transit):

```bash
pytest
```

Then the slow suite (real SAM2 inference, real photos — this is the one that matters most today):

```bash
pytest -m slow
```

## 2. MPS validation (the big unknown)

```python
from segment.sam2_session import select_device
print(select_device())  # should print mps, not cpu
```

If it prints `cpu`, MPS isn't being picked up — check `torch.backends.mps.is_available()` directly.

Run the slow suite and watch for these specific failure signatures (PITFALLS Pitfall 1 — MPS
support is officially "preliminary"):
- `TypeError` mentioning float64 / double
- `RuntimeError: Placeholder storage has not been allocated on MPS device!`
- A mask that looks feathered, islanded, or otherwise visually different from what CPU produced
  overnight (compare against `data/qc/2025-08-03_thread5.11_overlay.png` if you regenerate it,
  or just eyeball whether the mask cleanly covers the thread)

**Escape hatch:** if MPS misbehaves, `select_device()` still has the cpu fallback — you can
force it by passing `device=torch.device("cpu")` to `load_predictor()` while filing the MPS
issue as a known gap. This is SEG-03's actual purpose, not a workaround.

## 3. Interactive click UX (the thing nobody could test overnight)

```bash
python -m segment.segment_export --input-dir "/path/to/threads daily imaging/08-03-25" \
  --date 2025-08-03
```

- **Left-click** a thread → confirm a red mask overlay appears covering just the thread
- **Right-click** on a bad region (e.g. if the needle gets grabbed) → confirm it's excluded
- Press **`e`** to toggle raster-erase mode, click/drag over any leftover bad pixels → confirm they clear
- Press **`a`** to accept → confirm the terminal prints `exported <stem>` and check `data/masks/` +
  `data/qc/` for the new files
- Press **`n`** to move to the next photo → **confirm the mask/points reset** (this was flagged in
  RESEARCH as a real pitfall — stale clicks contaminating the next photo)

## 4. Overlay QC check (AC-005)

Open any `data/qc/*_overlay.png` in an image viewer — confirm the red-tinted region visually matches
the thread, not the needle or background artifacts. (Overnight testing on `5.11.JPG` confirmed this
works correctly on CPU — worth a quick re-check that MPS produces the same visual result.)

## 5. Calibration — the 0.5cm macro span (AC-007, D-10)

```bash
python -m calibrate.ruler_scale --ruler "/path/to/08-03-25/ruler.JPG" --date 2025-08-03 --span 0.5
```

**Zoom in first** — the ruler photos are macro/microscope shots; only ~2cm of the ruler fills the
frame, with fine mm tick marks. Click two points exactly 0.5cm apart (5 adjacent mm ticks), not a
wide span. Sanity-check the printed `px_per_cm` value by hand (should be in the same order of
magnitude as the 1591.369 px/cm seen in the original ImageJ ground-truth data, though it will vary
by photo/zoom level — a wildly different value, e.g. 10x off, means you clicked the wrong span).

## 6. Multi-file folder run (AC-009)

Point `segment_export.py --input-dir` at a folder with more than one photo — confirm it processes
each one in turn without requiring separate invocations.

## 7. Full end-to-end command

```bash
python run_pipeline.py \
  --photo "/path/to/08-03-25/5.11.JPG" \
  --click-x 2740 --click-y 1534 \
  --ruler "/path/to/08-03-25/ruler.JPG" \
  --ruler-p1 0 0 --ruler-p2 400 0 \
  --span 0.5 \
  --date 2025-08-03 --thread 5.11 \
  --data-root data
```

`final.csv` lands at `data/csv/final.csv` — open it and confirm the header is exactly:
`Thread,Batch,Condition,Date,Conversion (pixels/cm),Avg diameter(px),StDev(px),AvgDiameter(mm),StDev(mm)`

For real (non-hardcoded) runs, use the interactive `segment_export.py` (step 3) to click and export
masks first, then `measure_masks.py` / `ruler_scale.py` / `build_final_csv.py` on the resulting folders.

## 8. Known open risks (carried into Phase 2 / v2, not blockers today)

- **SAM2-on-MPS is "preliminary"** per Meta's own docs, with an open unresolved upstream GitHub
  issue (facebookresearch/sam2#687). If it works cleanly today, great — if not, the CPU fallback
  is real and tested, just slower.
- **StDev runs higher than ImageJ's** on the one real sample checked overnight (23.7px vs
  ImageJ's 17.7px for `5.11`, though avg diameter matched within 3%). The current skeleton+
  distance-transform method (D-03) uses axis-sort ordering as a proxy for "along the thread" —
  correct in shape, but the true perpendicular-to-tangent method (D-04) is deferred to v2 and
  will be the fix if Phase 2's formal ImageJ validation (MEAS-03) flags this as a real problem.
- Only 4 ImageJ ground-truth rows exist — today's numbers are a plausibility check, not a
  statistically rigorous validation.

## What to report back

- Did MPS work, or did you need the CPU fallback?
- Did the click/erase/accept loop feel right, or does the UX need adjusting?
- Was the 0.5cm calibration span workable, or too fiddly to click precisely?
- Any crash, wrong-looking mask, or surprising number — flag it, this all still needs your eyes.
