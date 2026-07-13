# SAMeasure

Click-to-segment, then measure. A SAM2-based pipeline: click once on an object in a photo,
correct the mask if needed, and get calibrated real-world measurements (area, width/diameter)
out the other end as a CSV.

**Origin:** built for bioelectric thread compaction analysis — measuring thread diameter/area
from microscope photos, replacing manual ImageJ edge-tracing. The pipeline generalizes to any
task that boils down to "segment an object in a photo, then measure it in real-world units":
other tissue types, materials, or objects — as long as each photo (or session) has a calibration
reference in frame (a ruler, a known-scale object) to convert pixels to real units.

See `.planning/PROJECT.md` for the full project history/context and
`.planning/phases/01-.../SKELETON.md` for the architecture.

## What it does

1. **Segment** — click once on the object (SAM2), correct the mask if it grabs the wrong thing
   (negative point or raster erase)
2. **Measure** — mask → pixel area, and average width/diameter + spread via skeleton +
   distance-transform sampling
3. **Calibrate** — a two-click reference measurement (e.g. a ruler) converts pixels to real units,
   stored per session so different photos/sessions can use different scales
4. **Export** — a CSV row per object, matched to its session's calibration factor

## Setup

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
git clone --depth 1 https://github.com/facebookresearch/sam2.git vendor/sam2
uv pip install -e vendor/sam2
curl -L -o vendor/sam2/checkpoints/sam2.1_hiera_small.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt
```

- Further guidance for day-to-day use is in `RUNBOOK.md`.

## Running the pipeline

See `run_pipeline.py` and the per-stage CLIs under `src/{segment,measure,calibrate,join}/`.

## Adapting to a new use case

The pipeline was written for elongated objects (threads), but each stage is a separate,
swappable module:

- **Naming/metadata** (`src/segment/naming.py`) — parses your folder/filename convention into
  the identifying fields (date, batch, condition, object ID) that flow through to the CSV. Swap
  this for your own folder convention.
- **Measurement method** (`src/measure/measure_masks.py`) — skeleton + distance-transform width
  sampling assumes a roughly linear/elongated shape. For a different object shape (e.g. a
  roughly circular or blob-like object), swap in a different measurement function — `area_px` is
  shape-agnostic and needs no change, but `avg_diameter_px`/`stdev_px` do.
- **CSV schema** (`src/join/build_final_csv.py`) — `EXACT_R_SCRIPT_COLUMNS` locks the output to
  match an existing downstream R script. If you don't need that compatibility, this is the one
  place to change the output column set.

## Running tests (for dev/troubleshooting)

```bash
pytest                 # fast suite — pure logic only, no torch/SAM2/real images
pytest -m slow          # real-image / SAM2 tests
pytest -m integration   # end-to-end skeleton pipeline test
```
