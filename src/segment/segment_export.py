"""Stage-1 CLI: walk a photo folder tree, launch the click loop per photo, export mask+overlay.

D-05: operates over a whole folder, never a single hardcoded file. EXPT-04-D2-01-QOL:
segment_export walks the ENTIRE nested tree (any depth — Condition/Batch/Day, per the user's
reorganized real folder layout) in one run, no per-photo CLI restart.

EXPT-01 revised: condition/thread are user-authoritative, never trusted from path parsing.
`_derive_metadata`'s parsed result is only ever a SUGGESTED DEFAULT (a display hint) —
an explicit `condition=`/`thread=` override always wins over it, and it is never silently
used to fill in a value the caller didn't ask for except as the existing thread-derivation
fallback below (kept for legacy-flat-convention backward compatibility — see D-07). The
actual per-mask interactive label prompt (accept -> ask condition+thread -> reclick-or-advance)
is Task 2's click_loop-driven multi-mask loop, not this module's per-photo pre-loop.

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
from segment.naming import PhotoMetadata, canonical_stem, parse_flat_path, parse_lenient_path, parse_photo_path
from segment.sam2_session import load_predictor

_VALID_THREAD_RE = re.compile(r"^[^_/\\\s]+$")
_EXPLICIT_DATE_RE = re.compile(r"^(?P<mm>\d{2})-(?P<dd>\d{2})-(?P<yy>\d{2})$")


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


def _prompt_safe_identifier(label: str, photo_name: str, guess: str | None) -> str:
    """Re-prompt until a canonical_stem-safe identifier is given (no '_', '/', whitespace).

    `guess` (from path-parsing) is shown as a suggested default only — pressing Enter
    accepts it, but any typed value always wins (EXPT-01 revised: manual entry is
    authoritative, path-parsing is a display hint at most).
    """
    suffix = f" [Enter for: {guess}]" if guess else ""
    while True:
        raw = input(f"{label} for {photo_name}{suffix}: ").strip()
        value = raw or (guess or "")
        if _VALID_THREAD_RE.match(value):
            return value
        print(f"Invalid {label.lower()} — must not contain '_', '/', or whitespace. Try again.")


def _prompt_for_thread(photo_name: str, guess: str | None = None) -> str:
    return _prompt_safe_identifier("Thread number", photo_name, guess)


def _prompt_for_condition(photo_name: str, guess: str | None = None) -> str:
    return _prompt_safe_identifier("Condition", photo_name, guess)


def _prompt_more_threads(photo_name: str) -> bool:
    """After an accept: ask whether to label another thread on this SAME photo (Task 2's
    multi-mask loop) — True = reclick same photo, False (default, Enter) = advance."""
    raw = input(f"Label another thread on {photo_name}? [y/N]: ").strip().lower()
    return raw in ("y", "yes")


def _resolve_field(explicit: str | None, guessed: str | None, prompt_fn, photo_name: str) -> str:
    """Explicit override > path-parsed guess > interactive prompt (EXPT-01 revised).

    `guessed is not None` treats an empty string as an already-known value (e.g. the flat
    legacy convention's condition="") rather than "unknown, needs a prompt" — only a real
    None (nested-path thread that path-parsing couldn't infer) reaches the prompt.
    """
    if explicit is not None:
        return explicit
    if guessed is not None:
        return guessed
    return prompt_fn(photo_name, guessed)


def _discover_photos(input_dir: Path) -> list[Path]:
    """Recursively discover thread photos under input_dir (any depth), excluding ruler_*.

    Uses a single case-insensitive suffix match (not separate *.JPG/*.jpg globs) so photos
    are never double-counted on case-insensitive filesystems (e.g. macOS)."""
    return sorted(
        p for p in input_dir.rglob("*")
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
    prompt_condition=_prompt_for_condition,
    prompt_thread=_prompt_for_thread,
    prompt_more_threads=_prompt_more_threads,
    click_loop=run_click_loop,
    photos: list[Path] | None = None,
) -> dict:
    """Run the click-to-segment loop over every photo recursively discovered under input_dir
    (any depth — Condition/Batch/Day nesting), or the given `photos` list. Ruler photos
    (filename starting with 'ruler', case-insensitive) are never included.

    `condition`/`thread`, when given, are authoritative overrides applied to every photo in
    this run (EXPT-01 revised) — they win over any path-parsed guess.

    Multi-thread-per-photo (Task 2): click_loop may call `on_accept` more than once per
    photo. Each accept resolves its OWN thread (never reusing a prior accept's value on the
    same photo) and independently checks/records idempotency, so two threads on one photo
    never collide on a single stem. When the thread identity is already fully known before
    any clicking happens (an explicit `thread=` override, or a flat-legacy filename-derived
    guess), there is nothing left to interactively label, so the photo auto-advances after
    one accept without asking "another thread?" — preserving pre-multi-mask behavior exactly
    for that case (also required so EXPT-04's non-interactive skip/--force tests still pass
    without stubbing every new prompt hook).

    Skip-if-output-exists idempotency (EXPT-04/D2-01): if a photo's mask already exists and
    force is False, it is skipped WITHOUT invoking click_loop — only possible pre-loop when
    the thread is already known (see above); a genuinely unknown (nested-path) thread defers
    its own skip-check to accept time. Returns a manifest dict (CSV-05/D2-05) recording every
    output as written or skipped.
    """
    from PIL import Image
    import numpy as np
    from dataclasses import replace

    masks_dir = Path(masks_dir)
    qc_dir = Path(qc_dir)

    if photos is None:
        photos = _discover_photos(input_dir)

    manifest = new_manifest("segment_export", datetime.now(timezone.utc).isoformat())

    for photo_path in photos:
        guess = _derive_metadata(photo_path, nextcloud_root, date, condition, batch)

        # Skip-check pre-pass: only possible without prompting when BOTH condition and thread
        # are already known (explicit override or flat-legacy filename-derived guess) — neither
        # requires a prompt to determine. A truly nested photo (no guess for one or both) can
        # only get them by the user labeling a mask, so the prompt (and its skip-check) is
        # deferred to on_accept — this also means the image window opens BEFORE any typing,
        # since a prompt here would block before the window ever shows.
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

        def on_accept(mask, guess=guess, image_rgb=image_rgb):
            nonlocal manifest
            condition_value = condition if condition is not None else _resolve_field(
                None, guess.condition, prompt_condition, photo_path.name
            )
            meta = guess if condition_value == guess.condition else replace(guess, condition=condition_value)
            mask_thread = thread if thread is not None else _resolve_field(
                None, guess.thread, prompt_thread, photo_path.name
            )
            mask_stem = canonical_stem(meta, mask_thread)
            mask_out = masks_dir / f"{mask_stem}.png"
            qc_out = qc_dir / f"{mask_stem}_overlay.png"

            if mask_out.exists() and not force:
                print(f"skipping already-exported {mask_stem}")
                manifest = add_output(manifest, stem=mask_stem, action="skipped", mask_path=mask_out, qc_path=qc_out)
            else:
                export_mask(mask, image_rgb, mask_stem, masks_dir=masks_dir, qc_dir=qc_dir)
                manifest = add_output(manifest, stem=mask_stem, action="written", mask_path=mask_out, qc_path=qc_out)
                print(f"exported {mask_stem}")

            if thread is not None or guess.thread is not None:
                return True  # thread already fully known — nothing more to label, advance
            return not prompt_more_threads(photo_path.name)

        click_loop(predictor, image_rgb, on_accept)

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

    predictor = load_predictor()

    manifest = export_folder(
        args.input_dir, args.masks_dir, args.qc_dir, predictor,
        force=args.force, nextcloud_root=args.nextcloud_root,
        date=args.date, batch=args.batch, condition=args.condition, thread=args.thread,
    )
    manifest_path = write_manifest(manifest, args.masks_dir.parent)
    print(f"wrote manifest to {manifest_path}")


if __name__ == "__main__":
    main()
