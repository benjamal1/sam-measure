# Thread Compaction Analysis (Auto)

## What This Is

An automated pipeline that replaces a manual ImageJ workflow for measuring bioelectric thread diameter/compaction from photos. Instead of manually outlining both edges of a thread in ImageJ, the user clicks once on the thread in SAM2 to segment it, corrects any bad segments (e.g. needle picked up instead of thread), and the pipeline turns the resulting masks into per-thread diameter/area measurements matched against a ruler-image pixel-to-cm conversion, output as a CSV that feeds directly into an existing R compaction-analysis script. Also includes a first pass at cleaning up years of inconsistently-named, deeply-nested image files into a flat, informative naming convention.

## Core Value

Turn a folder of thread photos (however messy) into the exact CSV shape the existing R script already consumes — with one click per thread instead of manual edge-tracing in ImageJ.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] User can click once on a thread in a SAM2-based tool (running locally on M2 Mac) to get a segmentation mask of the thread
- [ ] User can manually erase/deselect bad regions in the same tool before export (e.g. needle picked up alongside thread)
- [ ] Exported masks are named with the identifying info (date, batch, day, condition, thread number) derived from context — original nested folder structure is not required to survive
- [ ] A batch script processes all exported masks and computes area in pixels (and diameter/avg/stdev consistent with the current ImageJ output) for each
- [ ] User can process a photo of a ruler to get a pixels-per-cm conversion factor per shoot/session
- [ ] Pipeline matches each thread's pixel measurements to the correct date's conversion factor and outputs cm/mm units
- [ ] Final output is a CSV matching the existing R script's expected columns exactly: `Thread, Batch, Condition, Date, Conversion (pixels/cm), Avg diameter(px), StDev(px), AvgDiameter(mm), StDev(mm)` — no changes needed to the R script
- [ ] A one-time cleanup pass renames/flattens existing messy nested image folders (see Context) into flat, informative filenames — done per-batch/per-day since the mess isn't uniform, inspected batch by batch rather than one global script
- [ ] Pipeline operates directly on the Nextcloud-synced local folder on the user's Mac (no copying images into this repo)

### Out of Scope

- Automatic needle/thread disambiguation without user correction — SAM2 sometimes grabs the needle; deliberately keeping a manual "erase the bad blob" step rather than building fragile auto-detection
- A single global script to rename all historical images — folder structure and naming mess varies by batch/day, so cleanup is inspected and handled per-batch rather than blindly automated end-to-end
- Rewriting the existing R compaction-analysis script — pipeline conforms its CSV output to the R script's existing expected format instead

## Context

- Current manual process: ImageJ script where the user outlines both edges of the thread by hand, computes distances along the thread length, and averages to diameter + stdev. Works but is slow.
- Images live in deeply nested Nextcloud folders that already encode metadata in the path, not the filename, e.g.:
  `.../threads daily imaging/Batch 8 04-24-26/Poststretch/D12 05-11-26/IMG_8092.JPG`
  — batch number+date, condition (e.g. Prestretch/Poststretch), day number+date — but the filename itself (`IMG_8092.JPG`) carries no info.
  Older/other data uses ad hoc names like `5.11.JPG` (thread.subthread numbering) directly in less-nested folders.
- Photos are taken in a consistent shot order within a given day, but that order/labeling scheme differs by batch and sometimes by day — so there's no single global sequence to auto-derive thread identity from shot order; identification has to be worked out per-batch when the cleanup pass inspects that batch's folder.
- User is migrating the working data into Nextcloud now, which this pipeline will read from directly.
- An existing R script consumes a CSV with fixed columns (see Requirements) and does the actual compaction statistics/analysis — this project's job stops at producing that CSV correctly.
- Target hardware: user's Mac (Apple Silicon, M2), so SAM2 should run well locally without needing a GPU server.

## Constraints

- **Hardware**: Must run SAM2 locally on an M2 Mac — no cloud GPU dependency assumed.
- **Output format**: Final CSV must match the existing R script's column names/order exactly, since the R script itself is not being modified.
- **Data location**: Source images live on Nextcloud sync, not copied into the repo — pipeline reads from the synced path.
- **Correction step**: Mask correction (removing needle blobs, etc.) must remain a manual, in-tool interactive step — not a fully automated heuristic.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use SAM2 (click-to-segment) instead of manual edge tracing | Cuts manual ImageJ outlining work down to one click + occasional correction | — Pending |
| Derive clean names on mask export rather than renaming raw source images upfront | Keeps raw Nextcloud data untouched/safe; renaming happens only for the pipeline's own output | — Pending |
| Historical image cleanup handled per-batch, not by one global script | Folder/naming conventions are inconsistent across batches and days; needs inspection, not a blind global rename | — Pending |
| Manual mask correction (erase bad blob) instead of auto largest-component filtering | Needle can overlap/be similar in scale to thread — safer to let user fix it than risk auto-picking wrong region | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-07 after initialization*
