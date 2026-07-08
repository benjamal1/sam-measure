# Phase 1: Walking Skeleton — Single-Thread Click-to-CSV - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-08
**Phase:** 1-Walking Skeleton — Single-Thread Click-to-CSV
**Areas discussed:** Diameter/regularity measurement, Interactive tool shape, Invocation shape, Metadata entry

---

## Diameter/regularity measurement

Raised out of order — user initially deselected the "diameter measurement rigor" option and instead said "we can just do area, not extra diameter measurements needed," which conflicted with the existing CSV-03/MEAS-02 requirements (R script needs Avg diameter(px)/StDev(px)/mm columns). Flagged the conflict and asked for clarification.

| Option | Description | Selected |
|--------|-------------|----------|
| Derive diameter from area | Compute area only, approximate diameter as area/length | |
| Area now, diameter/stdev deferred to Phase 2 | CSV blank/0 for diameter columns in Phase 1 | |
| Let me clarify in my own words | — | ✓ |

**User's choice:** "I think area is fine, is there some regularity measure to replace stdev that can be found from the mask?"
**Notes:** Resolved without needing a new concept — skeleton + distance-transform width sampling (already research's Phase 1 default) inherently produces both average diameter (mean skeleton-point width) and StDev (spread of those widths) directly from the mask. This satisfies the user's ask and the existing CSV/measurement requirements with no extra work.

---

## Interactive tool shape

| Option | Description | Selected |
|--------|-------------|----------|
| napari + SAM2 plugin | Real desktop app, native paintbrush/eraser correction | |
| Bespoke matplotlib/OpenCV click loop | Minimal custom click+erase loop, no third-party plugin dependency | ✓ |

**User's choice:** Bespoke matplotlib/OpenCV click loop
**Notes:** More code upfront, but avoids depending on a third-party napari plugin's SAM2 (vs SAM1-only) support being solid — research flagged this as an open question.

---

## Invocation shape

| Option | Description | Selected |
|--------|-------------|----------|
| One CLI script per stage | segment.py → measure.py → calibrate.py → build_csv.py | ✓ (elaborated) |
| Single combined script/notebook | One script walks through all stages interactively | |

**User's choice:** "I think one script per stage because I want to segment all of them, do all the ruler calibrations, then figure out how to best match (by date probably), then have them all measured and written into a csv."
**Notes:** Confirms stage-per-script architecture, and clarifies each stage script should operate over the user's real folder of images/ruler photos (not one hardcoded file) — matching happens by date. Assessed against scope guardrail: this is not scope creep since the same code path handles one thread or many; batch-scale *trust* work (idempotency, ImageJ validation, hard-fail safety nets, manifest) stays in Phase 2 per roadmap.

---

## Metadata entry

| Option | Description | Selected |
|--------|-------------|----------|
| CLI args | Type date/batch/condition/thread# by hand per invocation | |
| Parse from folder path now | Build the real Nextcloud folder-path parser in Phase 1 | ✓ |

**User's choice:** Parse from folder path now
**Notes:** Same parser needed in Phase 2 regardless; better to exercise it on real folder structures in Phase 1 than build throwaway CLI-arg plumbing.

---

## Claude's Discretion

- Exact skeleton/distance-transform implementation details (skimage calls, mask cleanup before skeletonization)
- Intermediate CSV file layout between the three stage scripts

## Deferred Ideas

- Automatic needle/thread disambiguation without manual correction — explicitly out of scope (PROJECT.md)
- True perpendicular ray-cast diameter measurement (MEAS-04) — v2
- Keyboard-shortcut review queue, outlier flagging, explicit resume tracking (QOL-01/02/03) — v2
- Historical folder cleanup — Phase 3
