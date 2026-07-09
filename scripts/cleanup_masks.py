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

    out_dir is treated as a MIRROR of masks_dir: any *.png in out_dir with no corresponding
    file left in masks_dir is deleted too. This makes "delete a mask you want redone, then
    rerun the pipeline" safe — without this, a removed mask's stale cleaned copy (and stale
    row in measurements.csv) would linger forever even though the original is gone.

    dry_run=True (default) reports what WOULD change and writes/deletes nothing — always
    inspect this before dry_run=False. Originals in masks_dir are never modified either way.
    """
    masks_dir = Path(masks_dir)
    out_dir = Path(out_dir)
    results = []

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    current_names = {p.name for p in masks_dir.glob("*.png")}

    for mask_path in sorted(masks_dir.glob("*.png")):
        mask = np.array(Image.open(mask_path).convert("L")) > 127
        cleaned, removed = clean_mask(mask)
        if removed > 0:
            results.append({"file": mask_path.name, "pixels_removed": removed})
        if not dry_run:
            Image.fromarray((cleaned.astype(np.uint8)) * 255).save(out_dir / mask_path.name)

    if not dry_run and out_dir.exists():
        for stale in out_dir.glob("*.png"):
            if stale.name not in current_names:
                stale.unlink()
                results.append({"file": stale.name, "pixels_removed": 0, "removed_stale": True})

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

    cleaned_results = [r for r in results if not r.get("removed_stale")]
    stale_results = [r for r in results if r.get("removed_stale")]

    for r in cleaned_results:
        print(f"{'[dry-run] would clean' if not args.apply else 'cleaned'} {r['file']}: "
              f"removed {r['pixels_removed']} stray px")
    for r in stale_results:
        print(f"removed stale {r['file']} from {out_dir} (no longer in {args.masks_dir})")

    if args.apply:
        print(f"\nwrote {total} mask(s) to {out_dir} ({len(cleaned_results)} cleaned, "
              f"{total - len(cleaned_results)} copied verbatim, {len(stale_results)} stale removed)")
    else:
        print(f"\n{len(cleaned_results)}/{total} mask(s) have stray blobs — "
              f"rerun with --apply to write the cleaned copy to {out_dir}")


if __name__ == "__main__":
    main()
