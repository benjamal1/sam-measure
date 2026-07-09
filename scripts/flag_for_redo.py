"""Flag one or more thread masks for redo: deletes the mask + QC overlay, and removes the
source photo from data/processed_photos.json so its window reopens on the next segment run.

Downstream stages (cleanup_masks.py --apply, measure_masks, build_final_csv) all regenerate
their output from scratch on every run — as long as you rerun them AFTER this, the redone
thread's stale rows disappear on their own. cleanup_masks.py's out-dir mirroring (deletes
files with no corresponding source) is what makes that automatic for masks_cleaned/.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/flag_for_redo.py \\
        --stem 2025-11-14_batch4_poststretch_threadLH \\
        --photo "/path/to/the/original/photo.JPG"

--stem may be repeated for multiple threads on the same photo (composite shots) — pass the
photo only once regardless; --photo is required so the source photo can be located in
processed_photos.json (mask stems don't record which photo they came from).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def flag_for_redo(
    stems: list[str], photo_path: str, masks_dir: Path, qc_dir: Path, data_root: Path,
) -> dict:
    """Delete each stem's mask+QC overlay (if present) and remove photo_path from
    data/processed_photos.json (if present). Returns a summary dict — never raises on
    already-missing files/entries, since "flag for redo" should be safely re-runnable.
    """
    masks_dir = Path(masks_dir)
    qc_dir = Path(qc_dir)
    data_root = Path(data_root)

    deleted_masks = []
    for stem in stems:
        mask_path = masks_dir / f"{stem}.png"
        qc_path = qc_dir / f"{stem}_overlay.png"
        if mask_path.exists():
            mask_path.unlink()
            deleted_masks.append(str(mask_path))
        if qc_path.exists():
            qc_path.unlink()

    processed_path = data_root / "processed_photos.json"
    photo_was_removed = False
    if processed_path.exists():
        try:
            processed = set(json.loads(processed_path.read_text()))
        except (json.JSONDecodeError, OSError):
            processed = set()
        if photo_path in processed:
            processed.discard(photo_path)
            processed_path.write_text(json.dumps(sorted(processed), indent=2))
            photo_was_removed = True

    return {"deleted_masks": deleted_masks, "photo_unmarked": photo_was_removed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Flag mask(s) for redo — delete + reopen their photo")
    parser.add_argument("--stem", action="append", required=True, dest="stems",
                         help="Mask stem to delete (repeatable for multiple threads on one photo)")
    parser.add_argument("--photo", required=True, help="Source photo path, exactly as it appears "
                                                         "in data/processed_photos.json")
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--qc-dir", type=Path, default=Path("data/qc"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()

    result = flag_for_redo(args.stems, args.photo, args.masks_dir, args.qc_dir, args.data_root)

    for m in result["deleted_masks"]:
        print(f"deleted {m} (+ its QC overlay, if it existed)")
    missing = set(args.stems) - {Path(m).stem for m in result["deleted_masks"]}
    for stem in missing:
        print(f"no mask found for stem {stem!r} — nothing to delete there")

    if result["photo_unmarked"]:
        print(f"unmarked {args.photo} in processed_photos.json — it will reopen next run")
    else:
        print(f"{args.photo} was not in processed_photos.json (already unmarked, or never marked)")

    print("\nnow rerun: segment (for this photo) -> cleanup_masks --apply -> measure -> "
          "calibrate (if needed) -> build_final_csv")


if __name__ == "__main__":
    main()
