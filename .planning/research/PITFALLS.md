# Pitfalls Research

**Domain:** Local SAM2-based click-to-segment scientific image measurement pipeline (bioelectric thread compaction analysis), M2 Mac, Nextcloud-synced data, R-script CSV output
**Researched:** 2026-07-08
**Confidence:** MEDIUM (web search only — no MCP doc providers configured for this project; findings are cross-corroborated across multiple independent sources per topic, but nothing here is verified against this project's own hardware/data)

## Critical Pitfalls

### Pitfall 1: MPS backend silently produces numerically different masks/results than CUDA references

**What goes wrong:**
SAM2 (and PyTorch generally) on Apple Silicon's MPS backend is not a drop-in numerical equivalent of CUDA. Documented PyTorch/MPS bugs include incorrect `index_select` with scalar index tensors, incorrect `torch.var` on zero-dim inputs, incorrect `AvgPool2d` outputs, zeroed imaginary parts in complex ops, and reports of measurably worse inference/training results on MPS vs. CPU/CUDA for identical float32 weights — traced to MPS using different low-level kernels per-op, not just reduced precision. Separately, MPS does not support float64 at all (float32/float16/bfloat16 only), so any code path (including inside SAM2's own preprocessing or a dependency) that defaults to double precision throws a hard `TypeError`.

**Why it happens:**
MPS is a newer, less mature backend than CUDA; Meta's SAM2 was primarily developed/benchmarked on CUDA, so edge-case kernel behavior on MPS has had far less real-world exercise. Developers assume "float32 in, float32 out" means numerically identical results across backends — it doesn't.

**How to avoid:**
- Force `dtype=torch.float32` explicitly everywhere in the pipeline; never let a float64 default leak in from numpy interop (e.g., `torch.from_numpy` on a float64 array).
- Do not port IoU/confidence acceptance thresholds from published CUDA benchmarks — tune them empirically against this project's own MPS-generated masks.
- Treat the "SAM2 gave a mask" step and the "is this mask good enough to accept" step as separate, human-verified stages (this project already does this via the manual correction step — keep it, don't let it atrophy into blind trust of MPS output).

**Warning signs:**
- Masks that look subtly "off" (feathered edges, extra small islands) compared to what SAM2 demos show on CUDA.
- `RuntimeError: Placeholder storage has not been allocated on MPS device!` or `TypeError: ... doesn't support float64` at runtime.

**Phase to address:**
SAM2 integration / segmentation-tool phase — validate on real sample photos before building the batch measurement stage on top of it.

---

### Pitfall 2: Skeleton/medial-axis width measurement breaks on curvature and boundary noise — not a drop-in replacement for "perpendicular edge distance"

**What goes wrong:**
The manual ImageJ workflow measures true perpendicular width along the thread's local direction. The tempting shortcut — `2 × distance_transform` at the mask centerline, or `skeleton × distance_map` — is only exactly correct when the object is locally straight and symmetric. On curved thread segments (which bioelectric threads under compaction routinely have), this systematically over- or under-estimates width because it implicitly assumes local radial symmetry rather than measuring perpendicular to the actual local tangent. Separately, the medial axis/skeleton is highly sensitive to boundary jaggedness — a rough SAM2 mask boundary (vs. a hand-traced smooth ImageJ edge) produces spurious skeleton branches and endpoint spurs, especially near the thread's cut ends, which corrupts both the centerline path and any per-point width sample taken near it.

**Why it happens:**
Distance-transform/skeleton approaches are what most tutorials and Stack Overflow answers reach for first because they're a few lines of `scikit-image`/`cv2` code, and they work fine on synthetic straight test images — the failure only shows up on real curved, noisy data.

**How to avoid:**
- Implement true perpendicular measurement: walk the medial axis, estimate the local tangent direction at each skeleton point (e.g., via a short local fit), cast a ray perpendicular to that tangent, and measure the distance between the two mask-boundary intersections. This is the closest computational analog to the manual ImageJ edge-tracing method and is what the R script's existing stdev-based output implicitly assumes.
- Smooth/despike the mask boundary (light morphological opening/closing, or a smoothing pass on the extracted contour) before skeletonizing, so the roughness doesn't get read as real diameter variance.
- Trim a fixed margin (e.g., a few percent of skeleton length) off both skeleton endpoints before sampling width, to discard endpoint-spur artifacts.
- Validate the new pipeline's `Avg diameter(px)` / `StDev(px)` against a handful of images already measured manually in ImageJ, on the same images, before trusting it on the full batch. A stdev that's systematically higher than the ImageJ baseline is the signature of boundary-roughness contamination, not real thread variability.

**Warning signs:**
- StDev(px) values noticeably higher than historical ImageJ StDev(px) for what should be similar thread conditions.
- Visual spot-check of the width-sampling rays shows them not perpendicular to the thread at curved sections.

**Phase to address:**
Batch measurement / mask-to-CSV computation phase — this is the single highest-risk correctness pitfall in the whole project since it silently changes the meaning of the R script's downstream statistics without any error being thrown.

---

### Pitfall 3: A single global pixels-per-cm factor is wrong whenever camera distance, angle, or ruler tilt varies between sessions

**What goes wrong:**
Perspective distortion occurs whenever the ruler's plane isn't parallel to the camera sensor plane — this produces a pixel-to-metric scale factor that is spatially non-uniform across that single frame, and different photo sessions with even slightly different camera distance/angle produce different true px/cm ratios. A pipeline that computes one conversion factor once (or reuses last session's factor when the ruler photo is missing/skipped for a given day) will silently mis-scale every measurement from that session — no error, no NaN, just quietly wrong cm values feeding straight into the R statistics.

**Why it happens:**
It's tempting to treat "pixels per cm" as a fixed property of the camera+lens rather than a property of the specific shot geometry, especially since the camera itself doesn't change between sessions — but distance-to-subject and ruler placement do.

**How to avoid:**
- Require exactly one ruler photo per shoot/session (this is already a stated requirement) and hard-fail (not silently fall back to a prior/default factor) if a session's ruler photo is missing when its threads are being processed.
- Sanity-check each derived conversion factor against a plausible range (e.g., known rough distance range → expected px/cm band) and flag outliers instead of accepting a wildly different factor without review.
- Encourage (in the ruler-photo capture step) laying the ruler flat and roughly parallel to the camera sensor — full perspective correction (checkerboard-based) is overkill for this use case but a badly tilted ruler photo should be visually rejected/reshot rather than accepted and blindly measured with a straight-line pixel count.
- Store the calibration factor keyed by session/date (matching the R script's `Conversion (pixels/cm)` column), never as a single pipeline-wide constant or config default.

**Warning signs:**
- Ruler photo shows the ruler at a visible angle/skew relative to the frame edges.
- A session's derived conversion factor is a significant outlier vs. other sessions shot with the same physical setup.

**Phase to address:**
Ruler calibration phase — build the "one ruler photo → one session factor, hard-fail if missing" logic before wiring calibration into the join with thread measurements.

---

### Pitfall 4: Joining thread measurements to the wrong session's calibration factor (or losing raw-image traceability) corrupts the CSV without any visible error

**What goes wrong:**
Because calibration must be per-session (Pitfall 3) rather than global, the join between "this thread's pixel measurement" and "this session's px/cm factor" is a real join operation with a real key (batch + date), not a constant lookup — and joins on loosely-matched date/batch strings are exactly where silent mismatches happen (e.g., a thread photographed on `D12 05-11-26` accidentally joined to the ruler factor from a differently-formatted or adjacent date). Separately, if the pipeline doesn't carry the original raw image path/filename through every derived artifact (exported mask → measurement row → final CSV row), there's no way to trace a suspicious CSV row back to the source photo to debug it later, and no way to detect if a raw image was accidentally reprocessed/double-counted.

**Why it happens:**
It's easy to build the join key ad hoc from whatever the current per-batch folder-derived naming scheme is, and folder naming is explicitly inconsistent across batches/days in this project's real data — so a key format that works for one batch's date strings silently fails to match (or worse, false-matches) another batch's.

**How to avoid:**
- Define one canonical session-key format (e.g., ISO date + batch number) up front, and require every exported mask filename and every ruler-photo record to carry that same canonical key — do the folder-name-to-canonical-key translation once, explicitly, during export/cleanup, not implicitly at join time.
- Carry the original raw image path (or a stable relative identifier) as a literal column through every intermediate artifact, even though it's not one of the R script's required output columns — drop it only at the very final CSV write if it must exactly match the R script's schema, but keep an intermediate "with provenance" CSV alongside the final one.
- Hard-fail the join (list the unmatched thread rows) if any thread's session key has no matching calibration factor, rather than defaulting to a fallback factor or silently dropping the row.
- Log which raw calibration factor (and its source ruler-photo filename) was applied to every output row, at least in an intermediate/debug artifact, so a suspicious cm value can always be traced back to both its source photo and its calibration source.

**Warning signs:**
- Any code path that has a default/fallback conversion factor "just in case" the exact-match lookup fails.
- No column/log anywhere in the pipeline linking a final CSV row back to its source image filename.

**Phase to address:**
Data-join / CSV-assembly phase — should be designed alongside the calibration and measurement phases, not bolted on after both already work independently.

---

### Pitfall 5: Batch folder-name cleanup silently overwrites files when two source names flatten to the same target name, or silently skips unrecognized folder patterns

**What goes wrong:**
When flattening nested, inconsistently-named folders (e.g., `Batch 8 04-24-26/Poststretch/D12 05-11-26/IMG_8092.JPG` alongside ad hoc `5.11.JPG` schemes) into flat informative filenames, two distinct source files can produce the same computed target filename — a naive rename/copy silently lets the second write clobber the first, permanently losing that thread's original photo with no error raised. This is a documented, real-world failure mode: a rename script with a subtly buggy pattern-matching rule silently produced empty/degenerate capture groups for a subset of filenames, causing dozens of files to collapse onto a handful of surviving names, with the tool reporting success the whole time.

**Why it happens:**
The project's own context confirms naming/folder conventions vary by batch and even by day, so any single parsing rule written against one batch's pattern will either mis-parse or under-parse another batch's folder names — and a "best effort" renamer that doesn't hard-fail on unparseable input will quietly either skip those files (silent data gaps) or produce degenerate/colliding names (silent data loss).

**How to avoid:**
- This project has already correctly scoped cleanup as per-batch/per-day with manual inspection rather than one global script (see Key Decisions) — preserve that discipline in implementation, not just in planning: build a small reusable rename primitive, not a single all-batches script, and run+review it one batch at a time.
- Before executing any batch's rename, generate and display the full old-name → new-name mapping (dry run) and explicitly detect and hard-fail on any destination-name collision within that batch — never proceed past a detected collision silently.
- Never rename/move in place against the original Nextcloud-synced files — copy (or export from the SAM2 tool) into a new location with the clean name, leaving the raw synced originals untouched. This is also already reflected in this project's Key Decisions ("Derive clean names on mask export rather than renaming raw source images upfront") — the pitfall is only in *not* extending the same untouched-originals discipline to the standalone folder-cleanup pass, which is a separate step from mask export.
- Explicitly log and hard-fail (do not silently skip) on any folder name that doesn't match that batch's expected pattern, so unrecognized naming schemes surface for manual handling instead of quietly vanishing from the output.

**Warning signs:**
- A batch's cleanup pass reports fewer output files than input files with no per-file explanation of what happened to the missing ones.
- The rename mapping step is skipped/not reviewed before execution "because the batch is small."

**Phase to address:**
Folder-cleanup phase — should ship with a mandatory dry-run/collision-check step before any actual file operation, and should be scoped and tested per-batch as already decided.

---

### Pitfall 6: Nextcloud sync activity racing against the pipeline's own reads/writes on the synced folder

**What goes wrong:**
Nextcloud's desktop client uses transactional file locking during active sync; if the pipeline reads a file mid-sync or (worse) writes into the synced tree while a sync cycle is in flight, this can produce partial reads, sync conflicts, or files that get "stuck locked" if a process holding a lock crashes or times out. The project's design already reads directly from the Nextcloud-synced path rather than copying in — which is reasonable, but means the pipeline is a second concurrent actor on that folder tree alongside the sync client.

**Why it happens:**
It's easy to treat a Nextcloud-synced local folder as a plain local filesystem and forget a background daemon is also mutating/locking files there, especially right after the user described "migrating the working data into Nextcloud now."

**How to avoid:**
- Treat all pipeline writes (mask exports, cleaned filenames, CSVs) as writes to a location outside the actively-synced raw-photo tree where practical, or at minimum avoid writing into the same subfolder the raw photos live in.
- Avoid holding a file open/locked for long-running operations on files inside the synced tree; read, close, then process in memory.
- If large photo migrations are still in progress (per the stated context — "User is migrating the working data into Nextcloud now"), prefer running batch jobs after a sync cycle has settled rather than concurrently with active large uploads.

**Warning signs:**
- Intermittent read failures or "file in use" errors that don't reproduce on retry.
- Nextcloud desktop client showing sync as stalled/paused while the pipeline is running.

**Phase to address:**
Pipeline I/O / infrastructure setup phase — a minor but easy-to-prevent operational pitfall, worth a one-line guard (e.g., check Nextcloud sync status before batch runs) rather than a full phase of its own.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|--------------------|-----------------|------------------|
| Distance-transform-only width measurement (skip perpendicular ray-casting) | Ships faster, simpler code | Systematically wrong widths on curved thread segments, breaks comparability with ImageJ baseline | Never for the shipped pipeline — acceptable only as a throwaway first prototype to validate the rest of the pipeline shape |
| Single global (not per-session) calibration factor | One less join/lookup to implement | Silently wrong cm values whenever camera distance/angle varies session to session | Never — this directly contradicts a stated project requirement |
| Renaming/moving raw Nextcloud-synced originals in place during cleanup | Simpler one-pass script | Irreversible data loss on any bug (collision, bad parse); this is explicitly the project's own stated anti-pattern to avoid | Never |
| Skipping the dry-run/collision-check step on a "small, obviously simple" batch | Saves a few minutes per batch | One silent collision permanently destroys a thread's only photo | Never — the failure is exactly as catastrophic on a small batch as a large one |
| Hardcoding SAM2 IoU/confidence thresholds copied from CUDA reference notebooks | Faster to get first masks | MPS numerical differences mean thresholds tuned on CUDA may accept/reject differently on this Mac | Acceptable only as an initial guess to be re-tuned empirically once real MPS masks are visible |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|------------------|-------------------|
| SAM2 checkpoints | Assuming `pip install` fetches model weights | Explicitly run the checkpoint download script/curl step and verify checkpoint file presence before first model build; fail with a clear message if missing, not a cryptic tensor-shape error |
| SAM2 + MPS device | Passing `device="mps"` and assuming CUDA-identical behavior | Force float32 explicitly, test on real sample images before trusting output, avoid `pin_memory()` in any MPS-bound dataloading path |
| Nextcloud-synced folder | Treating it as a plain local path with no concurrent writer | Avoid writing into the actively-synced raw-photo tree; read-then-close rather than holding files open |
| R script CSV consumption | Loosely matching column names/order "close enough" | Match the R script's exact column names/order/types (`Thread, Batch, Condition, Date, Conversion (pixels/cm), Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm)`) verified against a real run of the R script, not just visual inspection |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Reloading the SAM2 model checkpoint per image in a batch loop | Batch processing becomes dramatically slower than expected; each image pays full model-load cost | Load the model once, reuse the predictor/session object across all images in a run | Any batch with more than a handful of images |
| No warmup before timing/UX expectations | First segmentation feels "broken" or "hung" (JIT/graph warmup on MPS) | Run one throwaway inference at startup and communicate "warming up" in the UI, or budget for it explicitly | Every first run after (re)starting the tool |
| Skeletonizing/ray-casting on full-resolution masks with fine boundary noise | Measurement step is slow and skeleton is noisy/spur-heavy | Lightly smooth mask boundary and/or downsample before skeletonization, upscale results back | Batches with dozens+ of threads processed in one run |

## Security Mistakes

Not primarily applicable — this is a single-user, local, no-network-exposed personal research tool. The closest analog is data-integrity rather than security:

| Mistake | Risk | Prevention |
|---------|------|------------|
| Pipeline writes/renames land inside the actively Nextcloud-synced raw-photo tree | Original irreplaceable research photos get mutated/overwritten and the mutation propagates to the cloud copy | Keep all pipeline writes (masks, cleaned names, CSVs) in a separate output tree; never rename raw originals in place |
| No dry-run before destructive batch rename | Permanent, syncable data loss across all Nextcloud-connected devices, not just local | Mandatory dry-run + collision hard-fail before any destructive file operation, as covered in Pitfall 5 |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| No visual feedback distinguishing "SAM2 is thinking" from "SAM2 is stuck" during first-run warmup | User assumes the tool crashed and force-quits mid-load | Explicit "warming up model, first click may take longer" indicator on tool launch |
| No preview of what a batch rename will produce before it runs | User can't catch an obviously wrong flattening scheme before it's applied | Always show the full proposed old→new mapping for review before committing, one batch at a time |
| Silent fallback to a default/previous calibration factor when a session's ruler photo is missing | User doesn't notice a session's measurements are quietly wrong until much later in R analysis | Hard-fail loudly and name the missing session when a ruler photo can't be found for a batch/date being processed |
| No way to see which raw photo produced a given CSV row when a result looks wrong | User can't debug or manually re-verify an outlier measurement | Carry source image path/filename through to at least an intermediate/debug CSV, even if trimmed from the final R-facing CSV |

## "Looks Done But Isn't" Checklist

- [ ] **SAM2 segmentation:** Often missing float32 enforcement and MPS-specific error handling — verify by running on several real thread photos (not just the demo image) and confirming no dtype/storage errors.
- [ ] **Diameter measurement:** Often missing true perpendicular-to-tangent sampling — verify by comparing StDev(px)/Avg diameter(px) against a handful of the same images' existing ImageJ manual measurements; a mismatch flags a boundary-roughness or curvature-blindness bug.
- [ ] **Ruler calibration:** Often missing hard-fail on missing/ambiguous ruler photo — verify by deliberately testing a batch with no ruler photo and confirming the pipeline stops loudly rather than reusing a stale factor.
- [ ] **Session/date join to calibration:** Often missing collision/mismatch detection — verify by testing two batches with differently-formatted date strings and confirming the join either matches correctly or fails loudly, never silently mismatches.
- [ ] **Folder cleanup pass:** Often missing collision detection and unparseable-name handling — verify with a synthetic test batch containing two files that would flatten to the same name, and one file with a completely unrecognized naming pattern; confirm both are caught, not silently resolved.
- [ ] **Traceability:** Often missing raw-image-to-CSV-row provenance — verify by picking a random final CSV row and confirming there is *some* path (even in an intermediate artifact) back to the exact source photo.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|------------------|
| Curved-thread width measurement bias discovered after a large batch already processed | MEDIUM | Re-run only the measurement stage (not re-segment) against the already-exported masks with the corrected perpendicular algorithm — cheap if masks were retained as artifacts, expensive only if masks weren't saved and photos must be re-segmented |
| Wrong/global calibration factor discovered after CSV already fed into R analysis | LOW–MEDIUM | If per-session raw pixel measurements were retained separately from the final cm-converted CSV, only the calibration-join step needs re-running; if only final cm values were kept, must re-derive from stored px measurements or re-measure |
| Batch rename collision destroyed a source file | HIGH (possibly unrecoverable) | Restore from Nextcloud version history/trash if available within its retention window; otherwise the photo is likely permanently lost — this is why prevention (dry-run + hard-fail) matters far more than recovery here |
| Provenance was never tracked and a suspicious CSV row can't be traced | MEDIUM | Manually cross-reference by date/batch/thread-number metadata already in the CSV against the folder structure — slow and error-prone but usually possible since folder paths do encode metadata even where filenames don't |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|--------------------|----------------|
| MPS numerical/precision quirks in SAM2 | SAM2 integration / segmentation-tool phase | Run on several real photos with no dtype/storage errors; visually confirm masks look sane, not just "no crash" |
| Skeleton/curvature width-measurement bias | Batch measurement phase | Compare pipeline output against existing ImageJ manual measurements on a shared sample set |
| Global-vs-per-session calibration factor | Ruler calibration phase | Deliberately test with a missing ruler photo and confirm hard failure, not silent fallback |
| Wrong join between thread measurement and calibration factor | Data-join / CSV-assembly phase | Test with two differently-formatted batch date strings and confirm correct match or loud failure |
| Folder-cleanup collisions/silent skips | Folder-cleanup phase | Run against a synthetic test batch with a deliberate collision and a deliberate unparseable name; confirm both are caught |
| Loss of raw-image traceability | Data-join / CSV-assembly phase (carried through from mask-export phase) | Trace a random final CSV row back to its source photo via an intermediate artifact |
| Nextcloud sync race conditions | Pipeline I/O / infrastructure setup phase | Run a batch job during active Nextcloud sync and confirm no partial-read errors |

## Sources

- [SAM3 inference fails on MPS (Mac M2) due to pin_memory() usage · Issue #22954 · ultralytics/ultralytics](https://github.com/ultralytics/ultralytics/issues/22954)
- [How can SAM2 be used on Macs with Apple Silicon? · Issue #687 · facebookresearch/sam2](https://github.com/facebookresearch/sam2/issues/687)
- [facebook/sam3 · Cannot run on Apple Silicon (M4) due to Triton](https://huggingface.co/facebook/sam3/discussions/11)
- [Supporting Apple "mps" device · Issue #453 · facebookresearch/segment-anything](https://github.com/facebookresearch/segment-anything/issues/453)
- [sam2/INSTALL.md at main · facebookresearch/sam2](https://github.com/facebookresearch/sam2/blob/main/INSTALL.md)
- [GitHub - facebookresearch/sam2](https://github.com/facebookresearch/sam2)
- [Test fails on MPS due to unsupported float64 precision · Issue #21261 · Lightning-AI/pytorch-lightning](https://github.com/Lightning-AI/pytorch-lightning/issues/21261)
- [the bug that taught me more about PyTorch than years of using it | Elana Simon](https://elanapearl.github.io/blog/2025/the-bug-that-taught-me-pytorch/)
- [MPS 16Bit Not Working correctly · Issue #78168 · pytorch/pytorch](https://github.com/pytorch/pytorch/issues/78168)
- [Training results from using MPS backend are poor compared to CPU and CUDA · Issue #109457 · pytorch/pytorch](https://github.com/pytorch/pytorch/issues/109457)
- [TypeError: Trying to convert Double to the MPS backend but there is no mapping for it · Issue #77781 · pytorch/pytorch](https://github.com/pytorch/pytorch/issues/77781)
- [Skeletonize — skimage 0.26.0 documentation](https://scikit-image.org/docs/stable/auto_examples/edges/plot_skeleton.html)
- [Medial axis - Wikipedia](https://en.wikipedia.org/wiki/Medial_axis)
- [Quanfima: An open source Python package for automated fiber analysis of biomaterials | PLOS One](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0215137)
- [Image processing: Determine fiber diameter - MATLAB Answers](https://www.mathworks.com/matlabcentral/answers/397267-image-processing-determine-fiber-diameter)
- [How to measure fiber length and width using masking of watershed and distance transform - MATLAB Answers](https://in.mathworks.com/matlabcentral/answers/425195-how-to-measure-fiber-length-and-width-using-masking-of-watershed-and-distance-transform-of-a-binariz)
- [A Perspective Distortion Correction Method for Planar Imaging Based on Homography Mapping](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11945749/)
- [A Planar-Dimensions Machine Vision Measurement Method Based on Lens Distortion Correction](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3826339/)
- [Vision AI Camera Calibration Guide: Intrinsics, Distortion](https://blog.roboflow.com/vision-ai-camera-calibration/)
- [Improving Reproducibility of Data Science Pipelines Through Transparent Provenance Capture (VLDB 2020)](https://www.vldb.org/pvldb/vol13/p3354-rupprecht.pdf)
- [Keeping a paper trail: data management skills for reproducible science – Laskowski Lab, UC Davis](https://laskowskilab.faculty.ucdavis.edu/2020/08/03/keeping-a-paper-trail-data-management-skills-for-reproducible-science/)
- [FAIR data pipeline: provenance-driven data management for traceable scientific workflows | Phil. Trans. R. Soc. A](https://royalsocietypublishing.org/rsta/article/380/2233/20210300/112235/FAIR-data-pipeline-provenance-driven-data)
- [How do I avoid accidental overwriting during batch rename? | Wisfile](https://www.wisfile.ai/faq/how-do-i-avoid-accidental-overwriting-during-batch-rename)
- [[FEATURE] Claude Code executed destructive bulk file rename without backup · Issue #31034 · anthropics/claude-code](https://github.com/anthropics/claude-code/issues/31034)
- [SAMAug: Point Prompt Augmentation for Segment Anything Model](https://arxiv.org/html/2307.01187v4)
- [SAMRefiner: Taming Segment Anything Model for Universal Mask Refinement](https://arxiv.org/html/2502.06756v1)
- [Synchronization problems due to locked files - Nextcloud community](https://help.nextcloud.com/t/synchronization-problems-due-to-locked-files/225428)
- [[Bug]: Desktop client stops syncing if 1 or more files are locked · Issue #9111 · nextcloud/desktop](https://github.com/nextcloud/desktop/issues/9111)
- [Delay file sync in the presence of lock-file · Issue #26926 · nextcloud/server](https://github.com/nextcloud/server/issues/26926)

---
*Pitfalls research for: SAM2-based local scientific image measurement pipeline (bioelectric thread compaction analysis)*
*Researched: 2026-07-08*
