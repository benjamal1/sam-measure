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
from segment.naming import canonical_stem, parse_flat_path, parse_photo_path
from segment.sam2_session import load_predictor

_VALID_THREAD_RE = re.compile(r"^[^_/\\\s]+$")


def _derive_metadata(photo_path: Path, nextcloud_root: Path | None, date: str | None, condition: str | None):
    """Best-effort path-parsed guess — advisory only (EXPT-01 revised), never authoritative."""
    if nextcloud_root:
        try:
            return parse_photo_path(photo_path, nextcloud_root)
        except ValueError:
            pass
    return parse_flat_path(photo_path)


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
    click_loop=run_click_loop,
    photos: list[Path] | None = None,
) -> dict:
    """Run the click-to-segment loop over every photo recursively discovered under input_dir
    (any depth — Condition/Batch/Day nesting), or the given `photos` list. Ruler photos
    (filename starting with 'ruler', case-insensitive) are never included.

    `condition`/`thread`, when given, are authoritative overrides applied to every photo in
    this run (EXPT-01 revised) — they win over any path-parsed guess.

    Skip-if-output-exists idempotency (EXPT-04/D2-01): if masks_dir/<stem>.png already
    exists and force is False, the photo is skipped WITHOUT invoking click_loop. Returns
    a manifest dict (CSV-05/D2-05) recording every photo as written or skipped.
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
        guess = _derive_metadata(photo_path, nextcloud_root, date, condition)

        condition_value = _resolve_field(condition, guess.condition, prompt_condition, photo_path.name)
        thread_value = _resolve_field(thread, guess.thread, prompt_thread, photo_path.name)

        meta = guess if condition_value == guess.condition else replace(guess, condition=condition_value)
        stem = canonical_stem(meta, thread_value)

        mask_path = masks_dir / f"{stem}.png"
        qc_path = qc_dir / f"{stem}_overlay.png"

        if mask_path.exists() and not force:
            print(f"skipping already-exported {stem}")
            manifest = add_output(manifest, stem=stem, action="skipped", mask_path=mask_path, qc_path=qc_path)
            continue

        image_rgb = np.array(Image.open(photo_path).convert("RGB"))

        def on_accept(mask, meta=meta, stem=stem, image_rgb=image_rgb):
            nonlocal manifest
            export_mask(mask, image_rgb, stem, masks_dir=masks_dir, qc_dir=qc_dir)
            manifest = add_output(manifest, stem=stem, action="written", mask_path=mask_path, qc_path=qc_path)
            print(f"exported {stem}")

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
