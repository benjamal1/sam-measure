"""Stage-1 CLI: walk a photo folder tree, launch the click loop per photo, export mask+overlay.

D-05: operates over a whole folder, never a single hardcoded file. EXPT-04-D2-01-QOL:
segment_export walks the ENTIRE nested tree (any depth — Condition/Batch/Day, per the user's
reorganized real folder layout) in one run, no per-photo CLI restart.

EXPT-01 revised: condition/thread are user-authoritative, never trusted from path parsing.
`_derive_metadata`'s parsed result is only ever a SUGGESTED DEFAULT (a display hint) —
an explicit `condition=`/`thread=` override always wins over it, and it is never silently
used to fill in a value the caller didn't ask for except as the existing thread-derivation
fallback below (kept for legacy-flat-convention backward compatibility — see D-07). The
actual per-mask interactive label entry (accept -> type condition/thread in-canvas ->
reclick-or-'n'-to-advance) is click_loop.py's multi-mask loop, not this module's per-photo
pre-loop — see click_loop.py's module docstring for why labeling is in-canvas (a TextBox
widget), not a terminal prompt.

EXPT-04/D2-01: idempotent — skip already-exported photos (masks_dir/<stem>.png exists)
without invoking segmentation; --force overrides. CSV-05/D2-05: records a manifest.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline.manifest import add_output, new_manifest, write_manifest
from segment.click_loop import run_click_loop
from segment.export import export_mask
from segment.naming import (
    PhotoMetadata,
    canonical_stem,
    parse_flat_path,
    parse_lenient_path,
    parse_photo_path,
    split_condition_thread_label,
)
from segment.sam2_session import load_predictor

_EXPLICIT_DATE_RE = re.compile(r"^(?P<mm>\d{2})-(?P<dd>\d{2})-(?P<yy>\d{2})$")
_PROCESSED_PHOTOS_FILENAME = "processed_photos.json"


def _load_processed_photos(data_root: Path) -> set[str]:
    """Photos whose click session has already run to completion (all threads labeled, or
    explicitly skipped with 'n') in a PRIOR run — read once at the start of a run so a
    restart doesn't reopen every photo's window from scratch.

    Per-mask idempotency (mask_out.exists() checks elsewhere) only skips re-EXPORTING a mask
    you type the exact same thread name for again — it does nothing to stop the window from
    reopening in the first place for a photo whose thread can't be known ahead of time (true
    for nearly all real photos here, since thread is always user-typed). This is the actual
    fix for "I have to reprocess every photo again after a restart."
    """
    import json

    path = Path(data_root) / _PROCESSED_PHOTOS_FILENAME
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return set()  # a corrupt/unreadable tracking file must never crash the run


def _mark_photo_processed(data_root: Path, processed: set[str], photo_path: Path) -> set[str]:
    """Add photo_path to the processed set and persist immediately (not just at run-end) —
    so a Ctrl+C right after finishing a photo still counts it as done next time."""
    import json

    new_processed = processed | {str(photo_path)}
    path = Path(data_root) / _PROCESSED_PHOTOS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(new_processed), indent=2))
    return new_processed


def _derive_metadata(
    photo_path: Path, nextcloud_root: Path | None, date: str | None, condition: str | None, batch: str | None = None
) -> PhotoMetadata:
    """Best-effort path-parsed guess — advisory only (EXPT-01 revised), never authoritative.

    Tries, in order: nextcloud_root-relative Batch/Condition/Day, legacy flat MM-DD-YY, a
    lenient any-ancestor Batch/Condition/Day scan, and finally the CLI's own --date (MM-DD-YY)
    + --batch as a last-resort explicit override when every path-parsing strategy fails — this
    is what makes the error message's own suggested fix ("pass --date explicitly") actually do
    something, instead of raising again on retry. Only raises when even that is unavailable.
    """
    if nextcloud_root:
        try:
            return parse_photo_path(photo_path, nextcloud_root)
        except ValueError:
            pass
    try:
        return parse_flat_path(photo_path)
    except ValueError:
        pass
    try:
        return parse_lenient_path(photo_path)
    except ValueError:
        pass
    if date is not None:
        m = _EXPLICIT_DATE_RE.match(date)
        if not m:
            raise ValueError(f"--date must be in MM-DD-YY format, got: {date!r}")
        from segment.naming import _to_date  # local import: internal helper, not part of the public API
        return PhotoMetadata(
            batch=batch or "", batch_start_date=None, condition=condition, day="",
            date=_to_date(m.group("mm"), m.group("dd"), m.group("yy")),
            thread=None, source_path=photo_path,
        )
    raise ValueError(
        f"could not derive any date/batch metadata from path: {photo_path} — "
        "pass --nextcloud-root, or ensure a 'D# MM-DD-YY' day folder is somewhere in its path, "
        "or pass --date MM-DD-YY (and optionally --batch) explicitly."
    )


def _discover_photos(input_dir: Path) -> list[Path]:
    """Recursively discover thread photos under input_dir (any depth), excluding ruler_*.

    Uses a single case-insensitive suffix match (not separate *.JPG/*.jpg globs) so photos
    are never double-counted on case-insensitive filesystems (e.g. macOS).

    Each result is resolved to an absolute, canonical path (Path.resolve()) — otherwise the
    SAME physical photo gets a DIFFERENT string key in data/processed_photos.json depending
    on whether --input-dir was passed relative or absolute across different invocations,
    causing an already-processed photo to silently look new (or double-recorded) on a later
    run with a differently-typed --input-dir.
    """
    return sorted(
        p.resolve() for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() == ".jpg" and not p.name.lower().startswith("ruler")
    )


def export_folder(
    input_dir: Path,
    masks_dir: Path,
    qc_dir: Path,
    predictor,
    *,
    force: bool = False,
    nextcloud_root: Path | None = None,
    date: str | None = None,
    batch: str | None = None,
    condition: str | None = None,
    thread: str | None = None,
    click_loop=run_click_loop,
    photos: list[Path] | None = None,
) -> dict:
    """Run the click-to-segment loop over every photo recursively discovered under input_dir
    (any depth — Condition/Batch/Day nesting), or the given `photos` list. Ruler photos
    (filename starting with 'ruler', case-insensitive) are never included.

    `condition`/`thread`, when given, are authoritative overrides applied to every photo in
    this run (EXPT-01 revised) — they win over any path-parsed guess.

    Multi-thread-per-photo: click_loop may call `on_label_submit` more than once per photo —
    condition/thread are resolved IN-CANVAS (a TextBox widget in click_loop, not a terminal
    prompt here; see click_loop.py's module docstring for why: this UI is also driven over
    SSH via matplotlib's WebAgg backend, where there's no terminal to prompt at all). Each
    submission resolves its OWN thread (never reusing a prior one on the same photo) and
    independently checks/records idempotency, so two threads on one photo never collide on a
    single stem. Advancing to the next photo is always an explicit 'n' press in click_loop —
    except the legacy fast path (condition AND thread both already known before any
    clicking — an explicit override or a flat-legacy filename-derived guess), which still
    auto-advances after one accept since there's nothing left to label.

    Skip-if-output-exists idempotency (EXPT-04/D2-01): if a photo's mask already exists and
    force is False, it is skipped WITHOUT invoking click_loop — only possible pre-loop when
    the thread is already known (see above); a genuinely unknown (nested-path) thread defers
    its own skip-check to label-submit time. Returns a manifest dict (CSV-05/D2-05) recording
    every output as written or skipped.
    """
    from PIL import Image
    import numpy as np
    from dataclasses import replace

    masks_dir = Path(masks_dir)
    qc_dir = Path(qc_dir)

    if photos is None:
        photos = _discover_photos(input_dir)

    manifest = new_manifest("segment_export", datetime.now(timezone.utc).isoformat())
    processed = _load_processed_photos(masks_dir.parent) if not force else set()

    for photo_path in photos:
        if not force and str(photo_path) in processed:
            print(f"skipping already-processed photo {photo_path.name} (all masks previously labeled)")
            manifest = add_output(
                manifest, stem=f"photo:{photo_path.name}", action="skipped",
                mask_path=str(photo_path), qc_path="",
            )
            continue

        guess = _derive_metadata(photo_path, nextcloud_root, date, condition, batch)

        # known_condition/known_thread: resolved once per photo, before any clicking. When
        # BOTH are known (explicit override or flat-legacy filename-derived guess), the
        # skip-check can run without ever opening click_loop, AND click_loop's own legacy
        # fast path auto-advances after one accept since there's nothing left to label.
        known_condition = condition if condition is not None else guess.condition
        known_thread = thread if thread is not None else guess.thread
        if known_condition is not None and known_thread is not None:
            meta = guess if known_condition == guess.condition else replace(guess, condition=known_condition)
            stem = canonical_stem(meta, known_thread)
            mask_path = masks_dir / f"{stem}.png"
            qc_path = qc_dir / f"{stem}_overlay.png"
            if mask_path.exists() and not force:
                print(f"skipping already-exported {stem}")
                manifest = add_output(manifest, stem=stem, action="skipped", mask_path=mask_path, qc_path=qc_path)
                continue

        image_rgb = np.array(Image.open(photo_path).convert("RGB"))
        had_any_accept = {"v": False}

        def on_label_submit(mask, condition_value, thread_value, guess=guess, image_rgb=image_rgb):
            nonlocal manifest
            had_any_accept["v"] = True
            # A typed label like "HL1" is condition+thread combined (letters=condition,
            # trailing digits=thread number, default "1") — it overrides whatever condition
            # was otherwise known (folder-derived or prior prompt). Legacy decimal threads
            # like "5.11" don't match this shape and pass through unchanged (see
            # split_condition_thread_label's docstring).
            label_condition, label_thread = split_condition_thread_label(thread_value)
            if label_condition is not None:
                condition_value, thread_value = label_condition, label_thread
            meta = guess if condition_value == guess.condition else replace(guess, condition=condition_value)
            mask_stem = canonical_stem(meta, thread_value)
            mask_out = masks_dir / f"{mask_stem}.png"
            qc_out = qc_dir / f"{mask_stem}_overlay.png"

            if mask_out.exists() and not force:
                print(f"skipping already-exported {mask_stem}")
                manifest = add_output(manifest, stem=mask_stem, action="skipped", mask_path=mask_out, qc_path=qc_out)
            else:
                export_mask(mask, image_rgb, mask_stem, masks_dir=masks_dir, qc_dir=qc_dir)
                manifest = add_output(manifest, stem=mask_stem, action="written", mask_path=mask_out, qc_path=qc_out)
                print(f"exported {mask_stem}")

        loop_state = click_loop(
            predictor, image_rgb, on_label_submit, photo_path=photo_path,
            known_condition=known_condition, known_thread=known_thread,
        )
        quit_requested = getattr(loop_state, "quit_all", False)

        # The photo's window has now closed. Mark it done UNLESS the user quit ('q') before
        # ever accepting anything on it — that photo genuinely wasn't touched (real bug fixed
        # here: quitting mid-photo previously marked it processed even with zero accepts,
        # meaning it silently disappeared from future runs despite never being labeled).
        # A normal 'n' skip or a completed labeling session is unaffected — both still mark done.
        if quit_requested and not had_any_accept["v"]:
            print(f"'q' pressed before labeling anything on {photo_path.name} — will reopen next run")
        else:
            processed = _mark_photo_processed(masks_dir.parent, processed, photo_path)

        if quit_requested:
            print("stopped ('q') — already-labeled photos are saved, rerun the same command to resume")
            break

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-1: interactive click-to-segment over a photo folder")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--nextcloud-root", type=Path, default=None)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--batch", type=str, default=None)
    parser.add_argument("--condition", type=str, default=None)
    parser.add_argument("--thread", type=str, default=None)
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--qc-dir", type=Path, default=Path("data/qc"))
    parser.add_argument("--force", action="store_true", default=False)
    parser.add_argument(
        "--checkpoint", type=Path, default=None,
        help="SAM2 checkpoint path — try vendor/sam2/checkpoints/sam2.1_hiera_tiny.pt for more "
             "speed at some accuracy cost (default: sam2.1_hiera_small.pt)",
    )
    parser.add_argument(
        "--model-cfg", type=str, default=None,
        help="Matching model config — 'configs/sam2.1/sam2.1_hiera_t.yaml' for the tiny checkpoint",
    )
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        raise SystemExit(
            f"--input-dir does not exist or is not a directory: {args.input_dir}\n"
            "(if you copy-pasted this path, check for lookalike unicode characters — "
            "cd into it interactively and use $PWD instead of retyping it)"
        )
    found = _discover_photos(args.input_dir)
    print(f"found {len(found)} photo(s) under {args.input_dir}")
    if not found:
        raise SystemExit("no .JPG photos found (excluding ruler_*) — check --input-dir is correct")

    load_predictor_kwargs = {}
    if args.checkpoint is not None:
        load_predictor_kwargs["checkpoint"] = args.checkpoint
    if args.model_cfg is not None:
        load_predictor_kwargs["model_cfg"] = args.model_cfg
    predictor = load_predictor(**load_predictor_kwargs)

    try:
        manifest = export_folder(
            args.input_dir, args.masks_dir, args.qc_dir, predictor,
            force=args.force, nextcloud_root=args.nextcloud_root,
            date=args.date, batch=args.batch, condition=args.condition, thread=args.thread,
        )
    except KeyboardInterrupt:
        # Ctrl+C is the documented way to stop mid-session (RUNBOOK.md) — every accepted
        # mask already wrote to disk immediately, and each finished photo is already recorded
        # in data/processed_photos.json, so nothing here is lost. Exit cleanly instead of
        # dumping a raw traceback, which reads as a crash rather than an expected stop.
        print("\nstopped — already-labeled photos are saved, rerun the same command to resume")
        raise SystemExit(0)

    manifest_path = write_manifest(manifest, args.masks_dir.parent)
    print(f"wrote manifest to {manifest_path}")


if __name__ == "__main__":
    main()
