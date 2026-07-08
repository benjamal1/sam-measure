"""Stage-1 CLI: glob a photo folder, launch the click loop per photo, export mask+overlay.

D-05: operates over a whole folder, never a single hardcoded file. D-07: thread number is
prompted at click time (not inferable from a nested filename).

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
    if nextcloud_root:
        try:
            return parse_photo_path(photo_path, nextcloud_root)
        except ValueError:
            pass
    return parse_flat_path(photo_path)


def _prompt_for_thread(photo_name: str) -> str:
    """Re-prompt until a canonical_stem-safe thread identifier is given (no '_', '/', whitespace)."""
    while True:
        thread = input(f"Thread number for {photo_name}: ").strip()
        if _VALID_THREAD_RE.match(thread):
            return thread
        print("Invalid thread identifier — must not contain '_', '/', or whitespace. Try again.")


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
    click_loop=run_click_loop,
    photos: list[Path] | None = None,
) -> dict:
    """Run the click-to-segment loop over every photo in input_dir, or the given `photos` list.

    Skip-if-output-exists idempotency (EXPT-04/D2-01): if masks_dir/<stem>.png already
    exists and force is False, the photo is skipped WITHOUT invoking click_loop. Returns
    a manifest dict (CSV-05/D2-05) recording every photo as written or skipped.
    """
    from PIL import Image
    import numpy as np

    masks_dir = Path(masks_dir)
    qc_dir = Path(qc_dir)

    if photos is None:
        photos = sorted(input_dir.glob("*.JPG")) + sorted(input_dir.glob("*.jpg"))

    manifest = new_manifest("segment_export", datetime.now(timezone.utc).isoformat())

    for photo_path in photos:
        meta = _derive_metadata(photo_path, nextcloud_root, date, condition)
        thread = meta.thread or _prompt_for_thread(photo_path.name)
        stem = canonical_stem(meta, thread)

        mask_path = masks_dir / f"{stem}.png"
        qc_path = qc_dir / f"{stem}_overlay.png"

        if mask_path.exists() and not force:
            print(f"skipping already-exported {stem}")
            manifest = add_output(manifest, stem=stem, action="skipped", mask_path=mask_path, qc_path=qc_path)
            continue

        image_rgb = np.array(Image.open(photo_path).convert("RGB"))

        def on_accept(mask, meta=meta, thread=thread, stem=stem, image_rgb=image_rgb):
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
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--qc-dir", type=Path, default=Path("data/qc"))
    parser.add_argument("--force", action="store_true", default=False)
    args = parser.parse_args()

    predictor = load_predictor()

    manifest = export_folder(
        args.input_dir, args.masks_dir, args.qc_dir, predictor,
        force=args.force, nextcloud_root=args.nextcloud_root,
        date=args.date, batch=args.batch, condition=args.condition,
    )
    manifest_path = write_manifest(manifest, args.masks_dir.parent)
    print(f"wrote manifest to {manifest_path}")


if __name__ == "__main__":
    main()
