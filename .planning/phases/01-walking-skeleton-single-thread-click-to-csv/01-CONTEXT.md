# Phase 1: Walking Skeleton — Single-Thread Click-to-CSV - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the full pipeline shape end-to-end: click on a thread photo → SAM2 mask → manual correction → mask export with derived metadata → area/width measurement from the mask → ruler-photo calibration → matched, converted, correctly-columned CSV row(s). "Rough but real" per MVP mode — this phase can run against real data (not just one synthetic thread), but does NOT need Phase 2's batch-hardening (idempotency guards, ImageJ ground-truth validation, hard-fail safety nets, audit manifest) to be considered done.

</domain>

<decisions>
## Implementation Decisions

### Interactive segmentation tool
- **D-01:** Build a bespoke click-to-segment + erase-correction loop (matplotlib/OpenCV), not a napari+SAM2 plugin. Chosen over napari-sam/napari-segment-anything specifically to avoid depending on a third-party plugin's SAM2 (vs SAM1) support being solid — more code now, zero external plugin risk.
- **D-02:** SAM2 inference targets the M2's MPS backend with an explicit CPU fallback (per SEG-03) — the click loop itself is UI-only and doesn't change based on device.

### Measurement method
- **D-03:** Use skeleton + Euclidean-distance-transform width sampling (research's STACK.md recommendation) as the Phase 1 measurement method. This single method produces BOTH the average diameter (mean width across skeleton points) AND StDev (spread of per-point widths) directly from the mask — satisfies the user's ask for "an area/regularity measure from the mask" without inventing a separate concept. No separate "just area" shortcut needed; the width-sampling approach already is the area-derived, mask-native measure.
- **D-04:** True perpendicular-to-tangent ray-cast width measurement (MEAS-04, more accurate on curved threads) stays deferred to v2 per REQUIREMENTS.md — Phase 1 uses skeleton+distance-transform as-is, validated against ImageJ ground truth in Phase 2 (MEAS-03), not Phase 1.

### Invocation shape
- **D-05:** One CLI script per pipeline stage, not a single combined script/notebook: a segmentation/export script, a ruler-calibration script, and a measure+match+CSV-build script. Each stage script operates over a folder/set of inputs (not hardcoded to exactly one image) — the user's actual workflow is "segment everything I have, calibrate everything I have, then match by date and build the CSV," and the stage-per-script/mask-as-interface architecture (per research ARCHITECTURE.md) supports that naturally without extra Phase-1 scope. Matching thread measurements to calibration factors happens by date (see EXPT-01/CAL-02/CSV-01) — batch is the secondary key if date alone collides.
- **D-06:** Phase 1 running "for real" against more than one thread is not scope creep — it's the same code path as one thread, since scripts operate over folders. What stays out of Phase 1 (deferred to Phase 2) is the batch-scale *trust* work: idempotent re-export skip (EXPT-04), ImageJ validation (MEAS-03), hard-fail on missing calibration (CAL-03), hard-fail on join mismatch (CSV-04), and the run manifest (CSV-05).

### Metadata parsing
- **D-07:** Build the real folder-path metadata parser now (date, batch, condition, thread number from the nested Nextcloud path, e.g. `Batch 8 04-24-26/Poststretch/D12 05-11-26/IMG_8092.JPG`), not CLI-typed metadata. This is needed in Phase 2 anyway and Phase 1 should exercise it on real folder structures rather than build throwaway CLI-arg plumbing.
- Note: per PROJECT.md, shot order/thread-numbering convention varies by batch/day (no single global sequence) — the parser handles date/batch/condition from the path; thread-number-within-a-session identification still needs a human decision at click time (the user knows which physical thread they're clicking on), not automatic inference from shot order.

### Claude's Discretion
- Exact skeleton/distance-transform implementation details (skimage function calls, mask cleanup/smoothing before skeletonization) — left to research/planning, not discussed with user.
- CSV intermediate file layout between the three stage scripts (e.g., a measurements.csv + a calibration.csv joined by build_csv.py) — implementation detail, not a user-facing decision.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & requirements
- `.planning/PROJECT.md` — core value, constraints (M2-local SAM2, R-script CSV format, manual correction step, per-batch cleanup deferred), shot-order note
- `.planning/REQUIREMENTS.md` — Phase 1 requirements: SEG-01/02/03, EXPT-01/02/03, MEAS-01/02, CAL-01/02, CSV-01/02/03

### Research (all under `.planning/research/`)
- `research/SUMMARY.md` — synthesized findings and Phase 1 rationale
- `research/STACK.md` — SAM2-on-MPS setup, skeleton+distance-transform measurement method, ruler calibration approach, pandas CSV assembly
- `research/ARCHITECTURE.md` — mask-file-as-interface component boundary, on-disk layout, build order rationale (this phase compresses research's stages 1-2-3-4-5 into one vertical slice)
- `research/PITFALLS.md` — MPS numerical quirks (Pitfall 1), curved-thread measurement bias (Pitfall 2), per-session calibration (Pitfall 3), join-mismatch risk (Pitfall 4)
- `research/FEATURES.md` — table-stakes list (raw images untouched, overlay QC image, derived filenames) that Phase 1 must satisfy even though the manifest/outlier-flagging QoL items are Phase 2+

</canonical_refs>

<code_context>
## Existing Code Insights

Greenfield project — no existing code, no codebase maps. Nothing to reuse or integrate with yet; Phase 1 establishes the first patterns (naming convention, folder layout) that Phase 2 and Phase 3 will build on.

</code_context>

<specifics>
## Specific Ideas

- User's real folder path example: `/Volumes/LRSResearch/ENG_CVRegenEng_Shared/Group/Data/Benjamin/threads daily imaging/Batch 8 04-24-26/Poststretch/D12 05-11-26/IMG_8092.JPG` — batch number+date, condition (Poststretch/Prestretch etc.), day number+date; filename itself carries no info. Older data uses ad hoc in-folder names like `5.11.JPG`. The metadata parser (D-07) should be built against real examples like this, not synthetic paths.
- Existing R-script CSV column contract (verbatim, exact order): `Thread, Batch, Condition, Date, Conversion (pixels/cm), Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm)`.
- Images are migrating into Nextcloud; pipeline should read from the Nextcloud-synced local folder on the user's Mac, not a copy in the repo.

</specifics>

<deferred>
## Deferred Ideas

- Automatic needle/thread disambiguation without manual correction — explicitly out of scope per PROJECT.md, not revisited here.
- True perpendicular ray-cast diameter measurement (MEAS-04) — v2, only if skeleton+distance-transform proves insufficiently accurate against ImageJ ground truth in Phase 2.
- Keyboard-shortcut review queue, outlier flagging, explicit resume tracking (QOL-01/02/03) — v2.
- Historical folder cleanup tooling — Phase 3, separate track, only needs Phase 1's naming convention (D-07's parser) to exist first.

### Reviewed Todos (not folded)
None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Walking Skeleton — Single-Thread Click-to-CSV*
*Context gathered: 2026-07-08*
