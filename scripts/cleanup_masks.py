"""One-off cleanup: strip disconnected stray blobs from already-exported mask PNGs.

measure_masks.py already keeps only the largest connected component at MEASUREMENT time
(in-memory), so final numbers are correct regardless — this script applies the same fix to
the exported mask.png files themselves, so a quick look at data/masks/ (or a re-run of
measure_masks) isn't cluttered by stray blobs the researcher would otherwise erase by hand.

Only removes pixels DISCONNECTED from the largest blob — an unwanted region touching/
overlapping the real thread still needs manual erasing (this can't distinguish that case).

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


def clean_mask_folder(masks_dir: Path, dry_run: bool = True) -> list[dict]:
    """Clean every *.png in masks_dir. dry_run=True (default) reports what WOULD change
    without writing anything — always inspect this before dry_run=False.
    """
    masks_dir = Path(masks_dir)
    results = []

    for mask_path in sorted(masks_dir.glob("*.png")):
        mask = np.array(Image.open(mask_path).convert("L")) > 127
        cleaned, removed = clean_mask(mask)
        if removed > 0:
            results.append({"file": mask_path.name, "pixels_removed": removed})
            if not dry_run:
                Image.fromarray((cleaned.astype(np.uint8)) * 255).save(mask_path)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Strip disconnected stray blobs from exported masks")
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--apply", action="store_true", default=False,
                         help="Actually write changes. Without this flag, only reports what would change.")
    args = parser.parse_args()

    results = clean_mask_folder(args.masks_dir, dry_run=not args.apply)

    if not results:
        print(f"no stray blobs found in {args.masks_dir}")
        return

    for r in results:
        print(f"{'[dry-run] would clean' if not args.apply else 'cleaned'} {r['file']}: "
              f"removed {r['pixels_removed']} stray px")
    print(f"\n{len(results)} mask(s) affected"
          f"{' — rerun with --apply to actually write changes' if not args.apply else ''}")


if __name__ == "__main__":
    main()
