---
phase: 01-walking-skeleton-single-thread-click-to-csv
plan: 01
subsystem: infra
tags: [pytest, dataclasses, regex, pathlib]

requires: []
provides:
  - "src/ package layout (segment/measure/calibrate/join) importable via pytest pythonpath"
  - "pyproject.toml pytest config with slow/integration markers, default run skips slow"
  - "requirements.txt frozen from the provisioned .venv/ (documentation only, no install)"
  - "tests/conftest.py finalized shared fixtures (sample_photo_path, ruler_photo_path, data_root, synthetic_strip_mask, ground_truth_imagej)"
  - "src/segment/naming.py: PhotoMetadata, parse_photo_path(), parse_flat_path(), canonical_stem(), stem_to_fields()"
affects: [01-02, 01-03, 01-04, 01-05]

tech-stack:
  added: []
  patterns: ["pathlib.Path.relative_to + per-segment regex matching for folder metadata parsing", "frozen dataclass for immutable metadata"]

key-files:
  created: [pyproject.toml, requirements.txt, run_pipeline.py, tests/conftest.py, tests/test_naming.py, src/segment/naming.py, README.md]
  modified: [.gitignore]

key-decisions:
  - "D-09 locked in code: canonical Date = day-folder date, never batch-start date — explicit regression test guards this"
  - "vendor/sam2/ (293MB nested git clone) gitignored entirely rather than committed — install steps documented in README instead"

patterns-established:
  - "Pure modules (no torch/cv2 imports) get a source-scan test asserting that, so accidental heavy imports are caught immediately"
  - "ValueError with the offending path in the message, never partial metadata, on any unparseable input"

requirements-completed: [EXPT-01]

duration: 25min
completed: 2026-07-08
status: complete
---

# Phase 1 Plan 01: Scaffold + naming.py Summary

**Folder-path metadata parser resolving the Date-column ambiguity (day-date vs batch-start-date) with 11 passing TDD tests, plus a frozen pytest-configured package scaffold.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 completed
- **Files modified:** 12 (9 created, .gitignore modified, README.md rewritten)

## Accomplishments
- `naming.py` correctly discriminates the day-folder date from the batch-start date (D-09) — the one silent-correctness bug the research flagged as highest-risk, now guarded by an explicit regression test
- Full package scaffold importable, pytest configured to skip slow/SAM2 tests by default
- `conftest.py` fixtures point at real Nextcloud data already synced to this build box

## Task Commits

1. **Task 1: Project scaffold, pytest config, frozen requirements, shared fixtures** + **Task 2: naming.py TDD** — `74782a2` (feat, combined — both tasks landed as one clean commit since Task 1 had no independently-testable behavior)

## Files Created/Modified
- `pyproject.toml` — pytest config (pythonpath, slow/integration markers)
- `requirements.txt` — frozen versions from live `.venv/`
- `.gitignore` — added `data/`, `vendor/`, `.pytest_cache/`, `*.egg-info/`
- `src/segment/naming.py` — PhotoMetadata, parse_photo_path, parse_flat_path, canonical_stem, stem_to_fields
- `tests/conftest.py` — shared fixtures for all later plans
- `tests/test_naming.py` — 11 tests, all passing
- `run_pipeline.py` — orchestrator stub (wired in plan 05)
- `README.md` — setup + test-running instructions

## Decisions Made
- `vendor/sam2/` gitignored wholesale rather than committed (293MB nested git repo) — README documents the clone+install steps instead
- Task 1 and Task 2 committed together — Task 1 (scaffold) had no meaningful standalone test to gate a separate commit on; TDD discipline applied fully to Task 2 (naming.py), which is the task with actual logic

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. (SAM2 checkpoint download already done this session, documented in README for the Mac setup tomorrow.)

## Next Phase Readiness
`naming.py` is ready for Wave 2 (`01-02` measure, `01-03` calibrate+join, `01-04` segment) to import `canonical_stem`/`stem_to_fields` without modification. No blockers.

---
*Phase: 01-walking-skeleton-single-thread-click-to-csv*
*Completed: 2026-07-08*
