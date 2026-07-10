# Thread Compaction Analysis (Auto)

Replaces manual ImageJ thread-edge-tracing with a SAM2 click-to-segment pipeline: click once on a
thread photo, correct the mask if needed, and get a CSV row in the exact format the existing R
compaction-analysis script consumes.

See `.planning/PROJECT.md` for full context and `.planning/phases/01-.../SKELETON.md` for the
architecture.

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
- Further guidance for use found in RUNBOOK.md

## Running tests (For dev/troubleshooting)

```bash
pytest              # fast suite — pure logic only, no torch/SAM2/real images
pytest -m slow       # real-image / SAM2 tests
pytest -m integration  # end-to-end skeleton pipeline test
```

## Running the pipeline

See `run_pipeline.py` and the per-stage CLIs under `src/{segment,measure,calibrate,join}/`.
