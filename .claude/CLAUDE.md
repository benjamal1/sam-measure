<!-- GSD:project-start source:PROJECT.md -->

## Project

**Thread Compaction Analysis (Auto)**

An automated pipeline that replaces a manual ImageJ workflow for measuring bioelectric thread diameter/compaction from photos. Instead of manually outlining both edges of a thread in ImageJ, the user clicks once on the thread in SAM2 to segment it, corrects any bad segments (e.g. needle picked up instead of thread), and the pipeline turns the resulting masks into per-thread diameter/area measurements matched against a ruler-image pixel-to-cm conversion, output as a CSV that feeds directly into an existing R compaction-analysis script. Also includes a first pass at cleaning up years of inconsistently-named, deeply-nested image files into a flat, informative naming convention.

**Core Value:** Turn a folder of thread photos (however messy) into the exact CSV shape the existing R script already consumes — with one click per thread instead of manual edge-tracing in ImageJ.

### Constraints

- **Hardware**: Must run SAM2 locally on an M2 Mac — no cloud GPU dependency assumed.
- **Output format**: Final CSV must match the existing R script's column names/order exactly, since the R script itself is not being modified.
- **Data location**: Source images live on Nextcloud sync, not copied into the repo — pipeline reads from the synced path.
- **Correction step**: Mask correction (removing needle blobs, etc.) must remain a manual, in-tool interactive step — not a fully automated heuristic.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11 or 3.12 | Runtime for the whole pipeline | Required by SAM2, scikit-image, and every supporting library below; 3.11/3.12 are the versions SAM2's own environment docs and PyTorch wheels target most reliably on macOS arm64 |
| PyTorch | >=2.3.1 (latest 2.x with MPS support) | Tensor runtime SAM2 sits on | SAM2's own README/notebooks require PyTorch >=2.3.1; PyTorch ships official Apple Silicon (`mps`) backend wheels — no CUDA needed, satisfies the "no cloud GPU" constraint |
| facebookresearch/sam2 (SAM 2.1) | Install from source via `git clone` + `pip install -e .` (repo has no numbered PyPI release under `sam2`; treat as source-installed, pin to a specific commit/tag for reproducibility) | The click-to-segment engine | This is the actual model the project requirement names explicitly. Official API (`SAM2ImagePredictor`) is a thin, well-documented wrapper: `set_image()` + `predict(point_coords, point_labels)` returns a mask in a few lines — matches the "click once on the thread" requirement directly |
| scikit-image | 0.26.x (confirmed current on PyPI at research time) | Mask → skeleton → distance-transform → diameter statistics | `skimage.morphology.skeletonize` / `medial_axis` + Euclidean distance transform is the standard, textbook way to turn a binary blob mask into "diameter measured perpendicular to the object's length, averaged along its length" — which is exactly what ImageJ edge-tracing already approximates by hand. This is the single most important library choice for measurement parity with the existing workflow |
| OpenCV (`opencv-python`) | latest 4.x stable in your resolver (verify pin at install time — a `5.0.0.x` line has also started appearing on PyPI; **pin to a tested 4.x version unless you've verified 5.x compatibility with your other pins**, since OpenCV major-version jumps can break API surfaces) | Ruler-image loading, two-click pixel distance measurement, general image I/O | Ubiquitous, zero-friction mouse-click calibration workflow (`cv2.setMouseCallback`) — the community-standard way to do reference-object pixel calibration, no extra dependency needed |
| pandas | 2.x (verify against your other pins; do not blindly adopt a pandas 3.x line without checking release notes against every other pinned library first — see "What NOT to Use") | Building the final CSV with an exact column set/order | `DataFrame.to_csv(path, columns=[...], index=False)` gives explicit, declarative control over column order/names in one line — the safest way to guarantee byte-for-byte header match with the existing R script's expected CSV shape |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| napari | 0.7.x (or latest 0.5+ stable) | Interactive point-click segmentation UI with built-in erase/correction tools | Use this as the **interactive review tool** the researcher actually clicks in — it's a real desktop image viewer (not a Jupyter widget), has a native `Labels` layer with paintbrush/eraser/fill tools out of the box, and several existing plugins already wrap SAM/SAM2 point-prompting into it (see below). This satisfies "click once, then manually erase bad regions, one image at a time" without writing a custom GUI |
| napari-sam (MIC-DKFZ) | latest | SAM/SAM2 point-prompt plugin for napari | Most mature/most-cited of the napari-SAM plugins; left-click = positive point, right-click = negative point, then use napari's native Labels eraser to fix bad blobs (e.g. the needle). Prefer this as the default plugin to prototype with first |
| napari-segment-anything (royerlab) | latest | Alternative native-Qt-UI SAM plugin for napari | Fallback if napari-sam's SAM2 support lags — has a clean native Qt widget; evaluate both in Phase 1 spike and keep whichever integrates SAM2 (not just SAM1) more cleanly |
| NumPy | 2.x (whatever scikit-image/OpenCV/PyTorch jointly resolve to) | Array plumbing between mask arrays, distance transforms, and measurement math | Implicit dependency of every library above — do not add a separate numeric layer |
| Pillow (PIL) | latest | Simple image read/write, especially for `SAM2ImagePredictor` which accepts `np.array(Image.open(...))` | Use for basic image loading where OpenCV's BGR-vs-RGB and heavier API aren't needed |
| matplotlib | latest | Optional: quick `ginput()`-based two-click ruler calibration if you'd rather avoid an OpenCV window loop | Only needed if OpenCV's mouse-callback loop feels heavier than wanted for the ruler step — `plt.ginput(2)` is a two-line alternative for the same task |
| Hugging Face `sam2-studio` (native macOS app) | latest (source-build via Xcode) | Reference/fallback interactive tool, NOT the primary pipeline component | Worth a 30-minute spike to see if it alone (Core ML SAM2, GUI, point/box prompts, background-point removal) already covers the "click + erase" step better than a custom napari plugin — if so, it could replace the napari layer entirely and simplify the stack. Flag as a Phase 1 research/spike decision, not a default pick |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `venv` or `conda`/`mamba` | Isolate the SAM2 + PyTorch + scikit-image environment | SAM2's own docs recommend a fresh Anaconda env; conda is not required, but pin exact versions of torch/torchvision/scikit-image/opencv together in a `requirements.txt` or `environment.yml` since these have historically fragile cross-version compatibility on macOS arm64 |
| `pytest` | Unit tests for the mask→diameter measurement math | This is the piece most worth testing rigorously since it must reproduce ImageJ's numbers — write tests against a few masks with known/hand-computed diameters before trusting it on real data |

## Installation

# Core environment (Python 3.11 recommended)

# PyTorch with MPS support (Apple Silicon build is automatic via standard pip wheel on macOS arm64)

# SAM2 — installed from source, not a stable PyPI package

# download checkpoints (choose a smaller checkpoint for interactive speed, e.g. sam2.1_hiera_small or base_plus)

# Interactive UI

# Measurement + CSV

# Dev

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| SAM2 (facebookresearch, full model) | MobileSAM / EdgeSAM | Only if interactive per-click latency on MPS/CPU turns out to be unacceptably slow in practice (multiple seconds per click). MobileSAM is ~5-38x faster with a much smaller encoder (5.78M vs 632M params) and keeps SAM's point-prompt API, so it's a drop-in speed fallback — but it's trained against SAM1's decoder, not SAM2's, so segmentation quality on ambiguous thread/needle overlaps will likely be worse. Treat as a fallback, not the default |
| napari + napari-sam plugin | Hugging Face `sam2-studio` native macOS app | If the researcher strongly prefers a polished native app UI over a Python-based viewer, and the app's export format (mask + metadata) can be adapted to the pipeline's needed identifying metadata. Spike this in Phase 1 before committing either way |
| napari + napari-sam plugin | Bespoke matplotlib/OpenCV click-and-poly-erase loop | Only if napari + existing SAM plugins turn out to integrate poorly with SAM2 specifically (some plugins were built against SAM1 and are still catching up to SAM2). A custom loop is more code to write and maintain but guarantees full control — treat as last resort, not first choice |
| `skimage.morphology.skeletonize` + distance transform | `skimage.morphology.medial_axis(..., return_distance=True)` | `medial_axis` returns the distance transform directly alongside the skeleton in one call and is arguably simpler to wire up; `skeletonize` produces a thinner, less-branchy skeleton which is usually cleaner for a single elongated thread shape. Start with `skeletonize` + `scipy.ndimage.distance_transform_edt`, but keep `medial_axis` as a one-line alternative if skeleton branch-pruning becomes fiddly |
| pandas `to_csv` | Plain `csv` module (`csv.DictWriter`) | If the pipeline stays extremely simple (no groupby/aggregation across threads needed before writing), the stdlib `csv.DictWriter(f, fieldnames=[...])` is a valid zero-dependency alternative and gives equally exact column control. Recommend pandas anyway because the pipeline already needs to join/aggregate per-thread measurements against the ruler conversion factor by date — that's a natural pandas merge/groupby, not a natural stdlib-csv operation |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| Cloud-hosted SAM2 APIs (e.g. Replicate, Roboflow-hosted SAM2 endpoints) | Explicitly out of scope per project constraints — must run locally on the M2 Mac with no cloud GPU dependency, and research images likely shouldn't leave the local machine for a lab workflow | Local SAM2 via PyTorch MPS/CPU as above |
| Bounding-box or min-area-rect "width" as the diameter measure | A bounding box or `cv2.minAreaRect` gives a single crude width estimate for the whole blob, not "diameter measured perpendicular to the thread at many points along its length, then averaged with a stdev" — it will not be comparable to ImageJ's edge-tracing output, which is exactly the parity requirement the project needs | `skimage.morphology.skeletonize` + Euclidean distance transform, sampled along the skeleton |
| Relying on SAM2's default `hiera_large` checkpoint for every click without evaluating smaller checkpoints first | Largest checkpoint maximizes accuracy but also maximizes per-click latency, which matters directly for a "click once per thread, review one at a time" interactive workflow the researcher will run repeatedly across a large photo backlog | Benchmark `sam2.1_hiera_small`/`base_plus` vs `large` on a handful of real thread photos in Phase 1 before committing to one checkpoint size |
| Assuming MPS "just works" without a fallback path | facebookresearch/sam2's own docs call MPS support "preliminary," and an open GitHub issue (#687) reports an unresolved `RuntimeError: Placeholder storage has not been allocated on MPS device!` on Apple Silicon as of this research — this is a live, unresolved upstream risk, not settled fact | Build the device-selection code with an explicit `try: mps except: cpu` fallback and budget time in Phase 1 to validate MPS actually works end-to-end on the target M2 machine before relying on it |
| Locking pandas to whatever the newest `3.x` line resolves to without checking compatibility | A live PyPI check during this research surfaced a `pandas` version in the `3.x` line — if that reflects a genuine pandas 3.0 release, it may include breaking API changes relative to the 1.x/2.x-era pandas code most existing examples (including this research's own docs lookups) are written against | Pin explicitly to a tested `pandas>=2.2,<3` unless you've deliberately verified 3.x compatibility with your other pins; re-check the actual current stable release at implementation time rather than trusting any single snapshot |

## Stack Patterns by Variant

- Fall back to CPU-only SAM2 inference
- Because CPU is slower per click but fully correct/stable — for a workflow that's "click once per thread photo," a few extra seconds of CPU latency per image is an acceptable tradeoff against wrong or crashing MPS inference; do not silently ship an MPS path that intermittently errors
- Fall back to a minimal custom OpenCV/matplotlib click-and-correct loop (single window: click to prompt SAM2, draw/erase polygon(s) to correct, save mask)
- Because the core requirement (click-to-segment + manual erase, one image at a time) doesn't strictly require napari — napari is the recommended default for speed of implementation and free correction tools, not a hard dependency
- Swap in MobileSAM (drop-in SAM-decoder-compatible, ~5-38x faster) instead of full SAM2 for the image encoder
- Because interactive latency compounds across a large photo backlog — but only make this swap after confirming SAM2/MPS speed is actually a bottleneck in practice, not preemptively

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| PyTorch >=2.3.1 (macOS arm64 wheel) | facebookresearch/sam2 (main branch) | SAM2's README states 2.3.1 as the floor; always match the SAM2 commit/tag you install against the PyTorch version it was tested with — check the repo's own README at install time since both move fast |
| napari 0.5+ | napari-sam / napari-segment-anything plugins | Some SAM-wrapping napari plugins were built against SAM1 and may lag SAM2 API changes — verify the specific plugin you pick actually calls `SAM2ImagePredictor`, not the older `SamPredictor`, before relying on it |
| scikit-image 0.25+ | NumPy 2.x | `skeletonize`/`medial_axis` behavior around dtype handling was clarified in scikit-image's 0.25 release notes — use a current 0.25+/0.26+ release, not anything from the 0.19-and-earlier era referenced in older tutorials |
| pandas 2.x | Python 3.11/3.12 | Straightforward; re-verify if you end up on a pandas 3.x line (see "What NOT to Use") |

## Sources

- `/facebookresearch/sam2` (Context7) — installation, MPS device-selection pattern, `SAM2ImagePredictor` point-prompt API, batch prediction API. Confidence: MEDIUM (official repo docs via Context7, not independently cross-verified against a second source for the API surface itself)
- `/scikit-image/scikit-image` (Context7) + scikit-image official skeletonize example page (websearch) — `medial_axis(return_distance=True)` / `skeletonize` + distance-transform pattern for measuring local width along a shape's skeleton. Confidence: MEDIUM-HIGH (cross-confirmed by both Context7 docs and official scikit-image example gallery)
- `pandas` official docs (Context7, `/websites/pandas_pydata`) — `DataFrame.to_csv(columns=..., index=False)` column control. Confidence: MEDIUM
- GitHub `facebookresearch/sam2` issue #687 (WebFetch) — unresolved MPS RuntimeError on Apple Silicon M4, install steps, "preliminary" MPS support warning from Meta's own notebook. Confidence: MEDIUM (single GitHub issue, but directly from the upstream repo)
- WebSearch: napari SAM/SAM2 plugin landscape (napari-sam, napari-segment-anything, napari-SAMV2, napari-sam2long) via napari-hub.org and GitHub. Confidence: MEDIUM
- WebSearch: PyImageSearch-style reference-object pixel calibration pattern for ruler-based pixels-per-cm conversion. Confidence: MEDIUM
- WebSearch: MobileSAM vs EdgeSAM vs SAM2 speed/size comparison (Ultralytics docs, EdgeSAM arXiv paper, emergentmind summaries). Confidence: MEDIUM
- Live PyPI JSON API queries (`pypi.org/pypi/<pkg>/json`) for current stable versions of scikit-image, pandas, numpy, opencv-python, torch, napari, sam2 (source-only, not PyPI-published) — Confidence: HIGH for the version numbers themselves (authoritative registry), but flagged in "What NOT to Use" where a version line looked surprising enough to warrant a manual re-check before pinning

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
