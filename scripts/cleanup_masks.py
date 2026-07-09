"""One-off cleanup: strip disconnected stray blobs from already-exported mask PNGs.

measure_masks.py already keeps only the largest connected component at MEASUREMENT time
(in-memory), so final numbers are correct regardless — this script applies the same fix to
a COPY of the exported masks, written to a separate out-dir (default data/masks_cleaned/),
never touching the originals in data/masks/ — segmentation resume (data/processed_photos.json,
per-mask idempotency) is entirely path-independent of this script, so it's safe to run any
time without affecting the ability to go back and segment more photos later.

Only removes pixels DISCONNECTED from the largest blob — an unwanted region touching/
overlapping the real thread still needs manual erasing (this can't distinguish that case).

Every mask is copied to out-dir (cleaned if it had stray blobs, verbatim otherwise) — the
next pipeline stage (measure_masks) should point --masks-dir at the cleaned folder, and needs
every mask there, not just the ones that changed.

QC overlays (data/qc/*_overlay.png) are NOT regenerated — cosmetic only, the mask.png itself
(and everything computed from it) is what's corrected.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import label as ndi_label


def clean_mask(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Return (cleaned_mask, pixels_removed). No-op (0 removed) if already single-component
    or empty. Never mutates the input array."""
    mask = mask.astype(bool)
    if not mask.any():
        return mask.copy(), 0

    labeled, num_components = ndi_label(mask)
    if num_components <= 1:
        return mask.copy(), 0

    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0  # background is never a candidate
    largest = labeled == sizes.argmax()
    removed = int(mask.sum() - largest.sum())
    return largest, removed


def clean_mask_folder(masks_dir: Path, out_dir: Path, dry_run: bool = True) -> list[dict]:
    """Clean every *.png in masks_dir, writing ALL of them (cleaned or verbatim) to out_dir.

    dry_run=True (default) reports what WOULD change and writes nothing at all — always
    inspect this before dry_run=False. Originals in masks_dir are never modified either way.
    """
    masks_dir = Path(masks_dir)
    out_dir = Path(out_dir)
    results = []

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    for mask_path in sorted(masks_dir.glob("*.png")):
        mask = np.array(Image.open(mask_path).convert("L")) > 127
        cleaned, removed = clean_mask(mask)
        if removed > 0:
            results.append({"file": mask_path.name, "pixels_removed": removed})
        if not dry_run:
            Image.fromarray((cleaned.astype(np.uint8)) * 255).save(out_dir / mask_path.name)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Strip disconnected stray blobs from exported masks")
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--out-dir", type=Path, default=None,
                         help="Where to write cleaned masks (default: <masks-dir>_cleaned, e.g. data/masks_cleaned)")
    parser.add_argument("--apply", action="store_true", default=False,
                         help="Actually write the cleaned copy. Without this flag, only reports what would change.")
    args = parser.parse_args()

    out_dir = args.out_dir or args.masks_dir.parent / f"{args.masks_dir.name}_cleaned"
    results = clean_mask_folder(args.masks_dir, out_dir, dry_run=not args.apply)

    total = len(list(args.masks_dir.glob("*.png")))

    if not results:
        print(f"no stray blobs found in {args.masks_dir} ({total} mask(s) checked)")
        if not args.apply:
            return

    for r in results:
        print(f"{'[dry-run] would clean' if not args.apply else 'cleaned'} {r['file']}: "
              f"removed {r['pixels_removed']} stray px")

    if args.apply:
        print(f"\nwrote {total} mask(s) to {out_dir} ({len(results)} cleaned, "
              f"{total - len(results)} copied verbatim)")
    else:
        print(f"\n{len(results)}/{total} mask(s) have stray blobs — "
              f"rerun with --apply to write the cleaned copy to {out_dir}")


if __name__ == "__main__":
    main()
