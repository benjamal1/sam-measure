# Feature Research

**Domain:** Solo-researcher scientific image-measurement pipeline (SAM2 click-to-segment thread diameter measurement, replacing manual ImageJ workflow)
**Researched:** 2026-07-07
**Confidence:** MEDIUM

## Feature Landscape

### Table Stakes (Users Expect These)

For a pipeline whose entire purpose is producing numbers that feed a downstream statistical analysis, "table stakes" means: a lab member could audit any single CSV row back to the photo and mask that produced it, and never worry that a bug silently corrupted the source data. Missing any of these makes the output untrustworthy, not just unpolished.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Raw source images are never modified/overwritten | Nextcloud-synced originals are the only copy of irreplaceable lab data; PROJECT.md already commits to this | LOW | Pipeline must be strictly read-only on the source tree; all writes go to a separate output directory. Enforce with file permissions or a read-only mount check if feasible. |
| Outputs written to a separate, clearly-scoped folder tree | Standard reproducible-pipeline practice — never comingle derived data with raw data | LOW | e.g. `output/<batch>/<date>/masks/`, `output/<batch>/<date>/overlays/`, `output/csv/`. |
| Mask saved with derived filename encoding date/batch/condition/thread# | Explicit requirement in PROJECT.md; also the only way measurements stay traceable once decoupled from folder structure | LOW-MED | Filename becomes the join key between mask, overlay, and CSV row — get this right first, everything else depends on it. |
| Overlay image (mask boundary/fill drawn on original) saved alongside each mask | Standard QC pattern in every segmentation-based measurement pipeline (medical imaging, materials science) — lets you visually re-audit a suspicious number without re-running SAM2 | LOW | Cheap to generate (draw contour on a copy of the source image) and is the single highest-leverage QC feature for this domain. |
| Per-run manifest/log (what ran, when, on what inputs, with what conversion factors) | Reproducibility literature is unanimous: provenance capture at execution time, not reconstructed after the fact | LOW-MED | Minimum: a CSV or JSON log row per processed image — input path, output mask path, timestamp, SAM2 model/checkpoint version, pixel→cm factor used and which ruler-image it came from. |
| Explicit, logged pixel→cm conversion factor per shoot/session, joined by date | Core requirement — wrong conversion factor silently corrupts every downstream measurement and is very hard to catch after the fact | MED | Needs a deliberate join step (thread's date → correct ruler-session factor) with a hard failure (not a silent default) if no matching ruler image exists for a date. |
| Manual correction step before mask export (erase bad blob) | Explicit requirement; SAM2 known failure mode (grabs needle) makes this non-optional, not a nice-to-have | MED | This is the interactive core of the tool, not an add-on. |
| CSV output matches existing R script's columns exactly | Explicit hard constraint — R script is not being touched | LOW | Trivial to build wrong (off-by-one column, wrong units) and easy to verify — write a small fixture test against one known-good ImageJ-era CSV row. |
| Basic per-thread measurement sanity check (area > 0, mask not empty/tiny, diameter within plausible range) | Prevents garbage-in-garbage-out from a bad click or missed correction silently entering the CSV | LOW-MED | Doesn't need to be ML-based — simple bounds checks on pixel area / aspect ratio catch most real failure modes (needle-only mask, empty mask, disconnected blob). |
| Idempotent / re-runnable batch processing | Solo researcher will re-run on the same folder repeatedly during development and when new photos land | LOW-MED | Batch script should skip/refresh already-processed images rather than requiring a full clean re-run each time. |

### Differentiators (Nice-to-Have Quality-of-Life)

These make the tool pleasant to live with across "hundreds of images," but the pipeline is still trustworthy without them on day one.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Keyboard-driven review queue (next/prev/accept/reject via hotkeys, no mouse trips to menus) | Every SAM2-annotation tool surveyed (napari-sam, napari-SAMV2, labelme) treats this as core UX — clicking through hundreds of images without keyboard shortcuts is the single biggest time sink | MED | Established vocabulary from prior art: left-click = positive point, modifier-click (Ctrl/middle-click) = negative point, dedicated erase/brush mode, Ctrl+Z undo, Ctrl+S save-and-advance. |
| Implicit resume via per-image sidecar output (skip images whose mask+CSV row already exist) | labelme's pattern — saving each image's result as its own file the moment it's done means resume is "reopen the folder," not a separate checkpoint feature | LOW | Cheaper than building session/checkpoint state — just check "does output for this image already exist" before processing. |
| Automated outlier flagging on final CSV (z-score/IQR on diameter within a batch/condition) | Established scientific-QC pattern (OutlierFlag tool, standard IQR/z-score flagging) — catches a bad measurement that passed basic sanity checks but is still statistically weird | LOW-MED | Flag, don't delete — add a `flagged`/`notes` column, let the researcher decide. Do this after CSV generation, as a separate small script, not baked into the main pipeline. |
| One-command "audit this thread" (open original + overlay + mask side by side) | Turns "something looks off in the CSV" into a 5-second lookup instead of manually finding 3 files | LOW | Trivial once filenames are consistent — a small script that takes a thread ID and opens the 3 related files. |
| Undo/redo within a single correction session (not just last-click undo) | Reduces friction when a correction stroke goes wrong | MED | Nice but SAM2 tools already give point-based undo; full multi-step undo is more engineering than the problem needs for one user. |
| Batch-level progress summary (X of N threads processed, Y flagged, Z pending correction) | Useful when working through hundreds of images across multiple sessions | LOW | Just a count over the output directory / manifest — no new state needed if outputs are self-describing. |
| Skeletonize + medial-axis width measurement instead of bounding-box/area-only diameter | More faithful to what ImageJ's manual edge-tracing was actually measuring (width along the thread's length, not just area/major-axis) | MED | `skimage.morphology.skeletonize` + `skimage.morphology.medial_axis` give width-at-each-skeleton-point; matches the "Avg diameter / StDev" column semantics from the existing R script far better than area-derived diameter. Worth doing in v1 if it's not much harder than area-only — but area-only is an acceptable fallback if timeline pressure hits. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Full multi-user web app / server deployment | "Feels more professional," easier to imagine sharing later | Single user on one Mac — a server introduces auth, deployment, sync-conflict, and hosting concerns with zero payoff today | Local desktop/CLI tool only (napari window or simple script + viewer) |
| Cloud upload / cloud inference for SAM2 | Seems like it'd be "faster" or more scalable | Explicit constraint: must run locally on M2 Mac; cloud adds cost, latency, and a data-privacy question for unpublished research images with no offsetting benefit at this scale | Run SAM2 locally (Apple Silicon MPS backend is adequate for SAM2's model sizes) |
| Fully automatic needle/thread disambiguation (no manual correction) | Looks like it'd save clicks | PROJECT.md already rejects this deliberately — needle and thread can be similar scale/overlap, so a heuristic risks silently corrupting data with no visible failure signal, which is worse than a slow manual step | Keep manual "erase bad blob" step; if annoyance becomes real, add a review flag heuristic (e.g. mask aspect ratio) that suggests but doesn't auto-fix |
| One global historical-cleanup script for all past nested folders | Seems more "complete"/less manual work | PROJECT.md already rejects this — naming/folder conventions vary by batch and day, so a single script either breaks on edge cases silently or needs so many special cases it becomes unmaintainable | Per-batch inspected cleanup, as already decided |
| Database (SQL/ORM) for run manifest and measurements | Feels like the "proper" way to store structured data | Massive overkill for a single user's few-hundred-row-per-batch dataset that already has to end as a CSV for an R script; adds a schema-migration and backup burden with no query need that a CSV/JSON can't serve | Flat CSV/JSON manifest files, one per run or append-only log |
| General-purpose configurable annotation platform (arbitrary shapes, classes, multi-object taxonomies) | "Might need it for other projects later" | This pipeline has exactly one object class (thread) and one correction operation (erase); building a general annotation platform is solving a problem that doesn't exist yet | Purpose-built single-class click+erase tool, reusing an existing SAM2 napari plugin as the interaction layer rather than building one from scratch |
| Real-time collaborative review / commenting system | Sounds useful for "future lab members" | Solo researcher, no other current users; adds real-time sync infrastructure for a need that doesn't exist | Plain files + manifest are already shareable via Nextcloud if a second person ever needs to look |
| Auto-retraining / fine-tuning SAM2 on this dataset | Seems like it would improve accuracy over time | Massive extra ML-engineering surface (labeled data curation, training infra, evaluation) for a task where out-of-the-box SAM2 + a manual correction click already solves the accuracy problem at near-zero engineering cost | Stick with off-the-shelf SAM2 checkpoint; revisit only if manual-correction rate stays high after real usage data comes in |

## Feature Dependencies

```
Manual correction UX (click + erase)
    └──requires──> SAM2 running locally + interactive viewer (napari or equivalent)

Mask export with derived filename
    └──requires──> Correction UX (only export after correction)
    └──requires──> Filename-derivation logic (date/batch/condition/thread# parsed from folder path or user input)

Overlay image saved alongside mask
    └──enhances──> Mask export (near-zero extra cost once mask exists)

Batch pixel-area/diameter computation
    └──requires──> Mask export (operates on exported masks, not live session)

Pixel→cm conversion factor (per ruler photo)
    └──requires──> Ruler-image processing (separate, simpler SAM2 or manual-measurement pass)

CSV output (final)
    └──requires──> Batch pixel/diameter computation
    └──requires──> Pixel→cm conversion factor, correctly joined by date

Run manifest/log
    └──enhances──> every stage above (should be written incrementally as each stage runs, not bolted on after)

Outlier flagging
    └──requires──> CSV output (operates on the finished measurement table)

Implicit resume (skip already-processed images)
    └──requires──> Mask export with derived filename (existence check needs a stable, predictable output path)

Historical folder cleanup (per-batch)
    └──conflicts with──> Automated global rename (deliberately excluded, see Anti-Features)
```

### Dependency Notes

- **Mask export requires Correction UX:** exporting straight from SAM2's raw click output would bake needle-contamination into the archive; the manual erase step must happen before the file is written, not after.
- **CSV output requires conversion factor correctly joined by date:** this is the riskiest join in the whole pipeline — a silent mismatch (wrong ruler photo's factor applied to a thread) produces plausible-looking but wrong numbers with no error thrown. Build a hard failure/warning when a thread's date has no matching ruler-session factor rather than falling back to a default.
- **Run manifest enhances every stage:** don't treat the manifest as a final report generated at the end — write to it as each image is processed so an interrupted run still leaves a usable partial log (this is also what makes "resume" and "batch progress summary" nearly free).
- **Overlay generation enhances mask export:** because it's just drawing the already-computed mask contour back onto a copy of the source image, there is no reason to skip it — it should be considered part of "export a mask," not a separate optional feature.
- **Historical cleanup conflicts with a global script:** any temptation to write one clever script that walks all Nextcloud folders and renames everything should be resisted per the PROJECT.md decision; keep this a set of small, batch-specific, human-reviewed scripts/passes.

## MVP Definition

### Launch With (v1)

Minimum viable product — enough to fully replace the manual ImageJ workflow for one batch of real data.

- [ ] Click-to-segment with SAM2, running locally on M2 Mac — why essential: this is the core value proposition
- [ ] Manual erase/correction before export — why essential: explicit requirement, and SAM2's known failure mode (needle) makes uncorrected masks unusable
- [ ] Derived-filename mask export (date/batch/condition/thread#) — why essential: the join key for everything downstream
- [ ] Overlay image saved next to each mask — why essential: near-zero cost, and without it there is no way to visually audit a bad number later without re-running SAM2 on the original click session (which may not even be reproducible)
- [ ] Batch pixel-area/diameter computation from exported masks — why essential: explicit requirement
- [ ] Ruler-photo → pixels-per-cm conversion, logged per session/date — why essential: explicit requirement, and the riskiest silent-failure point in the pipeline
- [ ] Correct date-based join of conversion factor to thread measurements — why essential: without this the CSV units are simply wrong
- [ ] CSV output matching the R script's exact columns — why essential: explicit hard constraint, and the actual deliverable
- [ ] Basic per-run manifest/log (input path, output paths, timestamp, model version, conversion factor used) — why essential: minimum provenance needed to trust and debug the pipeline's own output
- [ ] Basic sanity checks on each mask (non-empty, plausible area) before it's allowed into the CSV — why essential: cheapest possible defense against garbage rows from a missed correction

### Add After Validation (v1.x)

Add once the MVP has been run on at least one real batch and the researcher has felt where the friction actually is.

- [ ] Keyboard-shortcut-driven review queue — trigger: clicking through a full batch by mouse alone feels slow in practice
- [ ] Implicit resume (skip already-processed images) — trigger: a batch run gets interrupted or spans multiple sessions
- [ ] Statistical outlier flagging on the CSV — trigger: first time a visibly wrong number makes it into the output undetected
- [ ] "Audit this thread" lookup helper — trigger: first time debugging a suspicious CSV row takes more than a minute of manual file-hunting
- [ ] Batch-level progress summary — trigger: batches grow large enough that "how much is left" becomes a real question

### Future Consideration (v2+)

Defer until there's concrete evidence the need is real, not hypothetical.

- [ ] Skeletonize/medial-axis-based diameter (vs. simpler area-derived diameter) — why defer: worth doing early if cheap, but if v1 timeline is tight, area-derived diameter with a documented conversion is an acceptable placeholder that can be swapped later without changing the CSV schema
- [ ] Any per-batch cleanup automation beyond simple scripted rename helpers — why defer: PROJECT.md deliberately scopes this to inspected, per-batch work; don't build tooling to eliminate a human step that exists on purpose

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| SAM2 click-to-segment + manual correction | HIGH | MED | P1 |
| Derived-filename mask export | HIGH | LOW | P1 |
| Overlay image export | HIGH | LOW | P1 |
| Pixel-area/diameter batch computation | HIGH | MED | P1 |
| Ruler-based pixel→cm conversion + date join | HIGH | MED | P1 |
| CSV output matching R script schema | HIGH | LOW | P1 |
| Run manifest/provenance log | HIGH | LOW | P1 |
| Basic mask sanity checks | MEDIUM | LOW | P1 |
| Keyboard-shortcut review queue | MEDIUM | MED | P2 |
| Implicit resume via output-existence check | MEDIUM | LOW | P2 |
| Outlier flagging on final CSV | MEDIUM | LOW | P2 |
| Skeletonize/medial-axis diameter | MEDIUM | MED | P2 |
| Audit-lookup helper script | LOW | LOW | P3 |
| Batch progress summary | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for launch (replaces the manual workflow end-to-end, trustworthy output)
- P2: Should have, add when possible (quality-of-life and QC hardening)
- P3: Nice to have, future consideration

## Competitor / Prior-Art Feature Analysis

No direct prior art exists for "SAM2 applied to thread/wire/fiber diameter measurement" specifically — this appears to be a genuine gap the project fills rather than a well-trodden path. The closest relevant precedents:

| Feature | napari-sam / napari-SAMV2 / napari-sam2long (interactive SAM(2) annotation) | U-Net distance-map fiber diameter method (PMC11398094) | Our Approach |
|---------|---|---|---|
| Click-to-segment UX | Point click = positive prompt, modifier-click = negative prompt, keyboard shortcuts for speed | N/A (fully automatic, not interactive) | Adopt the same click vocabulary; reuse an existing SAM2 napari plugin as the interaction layer rather than building point-prompt UI from scratch |
| Manual correction | Brush/eraser tools in some plugins (FrancisCrickInstitute napari_sam2, SAMannot) | None (automated method) | Erase/deselect bad regions before export, as required |
| Diameter/width computation | N/A (segmentation only, not measurement) | Distance-transform along a computed skeleton, giving width at each point | Consider skeletonize + medial-axis width (skimage) post-mask, as a v1.x/v2 upgrade over simple area-derived diameter |
| Calibration/units | N/A | Not addressed in surveyed literature | Dedicated ruler-photo pixel→cm step, explicitly required and logged per session |
| Provenance/audit | Not a focus of annotation tools | Not addressed | Overlay + manifest logging, per reproducible-pipeline best practice |

## Sources

- [napari-sam (MIC-DKFZ) — GitHub](https://github.com/MIC-DKFZ/napari-sam) — click-to-segment SAM napari integration
- [napari-SAMV2 — napari hub](https://www.napari-hub.org/plugins/napari-SAMV2) — point-prompt click/keyboard-shortcut UX for SAM2
- [napari-sam2long — napari hub](https://napari-hub.org/plugins/napari-sam2long.html) — point-click and mask corrections for volumetric/time-lapse
- [napari-vos-sam2 — GitHub](https://github.com/ledvic/napari-vos-sam2) — middle-click positive / Ctrl+middle-click negative prompt pattern
- [FrancisCrickInstitute/napari_sam2 — GitHub](https://github.com/FrancisCrickInstitute/napari_sam2) — keybind-driven correction workflow
- [Interactive Medical-SAM2 GUI (arXiv 2602.22649)](https://arxiv.org/html/2602.22649v1) — napari-based semi-automatic local annotation tool
- [SAMannot (arXiv 2601.11301)](https://arxiv.org/html/2601.11301v2) — local, open-source human-in-the-loop SAM2 framework, point/box prompts
- [A Deep Learning Approach to Distance Map Generation for Automatic Fiber Diameter Computation (PMC11398094)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11398094/) — distance-map/skeleton-based fiber width measurement
- [Medial axis skeletonization — scikit-image docs](https://scikit-image.org/docs/0.10.x/auto_examples/plot_medial_transform.html) — `skimage.morphology.medial_axis` for width-at-skeleton-point measurement
- [OutlierFlag: A Tool for Scientific Data Quality Control by Outlier Data Flagging (Journal of Open Research Software)](https://openresearchsoftware.metajnl.com/articles/10.5334/jors.90) — flag-don't-delete outlier QC pattern
- [Provenance Metadata — towards reproducible research (Open Targets blog)](https://blog.opentargets.org/provenance-metadata/) — manifest/provenance capture practice
- [Improving reproducibility of data science pipelines through transparent provenance capture (IBM Research, VLDB 2020)](https://research.ibm.com/publications/improving-reproducibility-of-data-science-pipelines-through-transparent-provenance-capture) — provenance-at-execution-time practice
- [How to Use LabelMe: A Complete Guide (Roboflow blog)](https://blog.roboflow.com/labelme/) — per-image sidecar file / implicit-resume annotation UX pattern
- [NP-SAM: SAM for nanoparticle segmentation in electron microscopy (ChemRxiv)](https://chemrxiv.org/engage/chemrxiv/article-details/6463c10aa32ceeff2dc08c49) — adjacent SAM-for-materials-science precedent
- [Biomedical SAM-2 survey (arXiv 2408.12889)](https://arxiv.org/pdf/2408.12889) — general SAM2-in-biomedical-imaging landscape confirming no fiber/thread-specific prior art found

---
*Feature research for: Solo-researcher SAM2-based scientific image-measurement pipeline*
*Researched: 2026-07-07*
