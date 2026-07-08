# Phase 2: Batch Hardening & Validation - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning
**Source:** `--auto` mode — all gray areas auto-resolved to recommended defaults, logged below

<domain>
## Phase Boundary

Harden the Phase-1 pipeline (already proven end-to-end on one thread) for real batch use across the full multi-session dataset: idempotent re-export (don't duplicate/clobber already-processed masks), validate the measurement method against ImageJ ground truth, hard-fail loudly (not silently) on missing calibration or unmatched joins, and produce a per-run audit manifest. No new pipeline stages — every module from Phase 1 is reused unchanged; this phase adds safety nets and validation around them.

</domain>

<decisions>
## Implementation Decisions

### Idempotency (EXPT-04)
- **D2-01 [auto, recommended]:** Skip-if-output-exists, keyed by the canonical stem's mask filename. Before running SAM2 inference on a photo, `segment_export.py`/the export path checks whether `data/masks/<stem>.png` already exists and skips (with a log line) rather than re-inferring. Simplest correct mechanism — matches the existing filename-as-identity contract from Phase 1, no new state/database needed. A `--force` flag allows explicit re-export when the user wants to redo a thread.

### ImageJ validation (MEAS-03)
- **D2-02 [auto, recommended]:** Validate against the 4 known ImageJ ground-truth rows (5.11/5.12/5.21/5.22, `08-03-25` folder) plus the same 4 threads' photos in `08-04-25` (same threads, later day — useful as a second real-data check even without separate ground truth for that day, since the pipeline should behave consistently). Report measured vs. ImageJ values with percent difference in a `VALIDATION.md`-style output; per Phase 1's own finding (~3% avg-diameter agreement, StDev higher due to the simpler axis-sort method), this is a documented plausibility/regression check, not a strict pass/fail gate — only 4 ground-truth rows exist, acknowledged as thin evidence in Phase 1 CONTEXT.md already.
- **D2-03 [auto, recommended]:** No new measurement algorithm in Phase 2. If validation shows the axis-sort method is unacceptably far off, that becomes a documented finding pointing at MEAS-04 (v2, deferred) — Phase 2's job is to validate and report, not to fix the method.

### Hard-fail contracts (CAL-03, CSV-04)
- **D2-04 [auto, recommended]:** Both hard-fail behaviors already exist functionally from Phase 1's `build_final_csv` (raises `ValueError` naming unmatched sessions before writing any output). Phase 2 formalizes this with requirement-ID-labeled tests (dedicated `CAL-03`/`CSV-04` test names) and extends the same discipline to the batch/idempotency path — e.g., a batch run across many threads still refuses to write a partial/corrupted final.csv if any thread's session is unmatched, rather than silently dropping just that row.

### Run manifest (CSV-05)
- **D2-05 [auto, recommended]:** A JSON manifest per pipeline run (`data/manifest_<timestamp>.json` or similar), recording: photos processed, masks/overlays written (or skipped-as-existing), calibration factor applied per thread, and any errors. Written by `run_pipeline.py`'s orchestrator and by the Stage-1 CLI. JSON chosen over a second CSV format since it naturally nests per-photo detail without inventing a new tabular schema alongside the three CSVs the project already has.

### Batch validation data (this build session)
- **D2-06 [auto]:** Real batch data used for testing Phase 2: `08-03-25/` and `08-04-25/` folders (24 photos each, flat legacy convention), both synced to this build box. `08-03-25` has the 4 ImageJ ground-truth rows; `08-04-25` has the same 4 thread IDs (useful for idempotency/multi-file testing) plus additional threads (5.31 through 6.42) with no ground truth — used for volume/idempotency testing only, not accuracy validation.

### Claude's Discretion
- Exact manifest JSON schema (field names) — implementation detail.
- Whether the idempotency skip check is a file-exists check or a more thorough hash-based check — file-exists is sufficient per D2-01's own reasoning (simplest correct mechanism); no need for hashing given masks aren't mutated externally between runs.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 (reused unchanged)
- `.planning/phases/01-walking-skeleton-single-thread-click-to-csv/SKELETON.md` — architecture, schema contracts, directory layout — Phase 2 does not change these
- `.planning/phases/01-walking-skeleton-single-thread-click-to-csv/01-CONTEXT.md` — all D-01 through D-10 decisions still apply
- `.planning/phases/01-walking-skeleton-single-thread-click-to-csv/VERIFICATION.md` — what's already proven; Phase 2 builds on top, not around

### Project & requirements
- `.planning/REQUIREMENTS.md` — Phase 2 requirements: EXPT-04, MEAS-03, CAL-03, CSV-04, CSV-05
- `.planning/research/PITFALLS.md` — Pitfall 2 (curvature/boundary-noise bias — relevant to MEAS-03 validation framing), Pitfall 4 (join mismatch — relevant to CSV-04 hardening)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (all from Phase 1, unchanged)
- `src/segment/naming.py` — parser + canonical_stem/stem_to_fields
- `src/segment/sam2_session.py`, `mask_edit.py`, `export.py`, `click_loop.py`, `segment_export.py` — segmentation engine + UI
- `src/measure/measure_masks.py` — measurement stage
- `src/calibrate/ruler_scale.py` — calibration stage
- `src/join/build_final_csv.py` — CSV assembly (already raises ValueError on unmatched calibration — CAL-03/CSV-04's core mechanism exists)
- `run_pipeline.py` — end-to-end orchestrator

### Established Patterns
- Pure-function + thin-CLI-wrapper split (every stage) — Phase 2 additions follow the same pattern
- Hard-fail-with-named-culprit on data-integrity violations (already established, extend don't reinvent)

### Integration Points
- Idempotency check slots into `segment_export.py`'s per-photo loop (before calling the click loop / predict_mask)
- Manifest writing slots into `run_pipeline.py`'s `run()` and `segment_export.py`'s `main()`
- MEAS-03 validation is a new standalone script/test, not a change to `measure_masks.py` itself

</code_context>

<specifics>
## Specific Ideas

- Real ImageJ ground truth (from project discovery, Date 8/1/25): 5.11→0.789mm/0.111mm, 5.12→0.865mm/0.101mm, 5.21→0.858mm/0.100mm, 5.22→0.933mm/(stdev not recorded)
- Phase 1's own real-data cross-check already found: 5.11 measured at 0.81mm avg (vs 0.79mm ImageJ, ~3% off) but StDev higher (23.7px vs 17.7px) — MEAS-03 in Phase 2 should run this properly across all 4 threads and report systematically, not just the one spot-check Phase 1 did informally

</specifics>

<deferred>
## Deferred Ideas

- MEAS-04 (true perpendicular ray-cast measurement) — only pursued if Phase 2's validation shows the current method is unacceptably inaccurate; v2 per REQUIREMENTS.md
- Historical folder cleanup — Phase 3, separate track, user-handled
- Keyboard-shortcut review queue, outlier flagging (QOL-01/02) — v2, not touched by batch hardening

### Reviewed Todos (not folded)
None — discussion stayed within phase scope.

</deferred>

---

*Phase: 2-Batch Hardening & Validation*
*Context gathered: 2026-07-08*
