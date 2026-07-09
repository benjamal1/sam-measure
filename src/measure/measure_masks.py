"""Headless measurement stage: mask -> area/diameter/stdev via skeleton + distance transform.

D-03: skeleton + Euclidean distance-transform width sampling is THE method for Phase 1.
D-04: true perpendicular ray-cast measurement (more accurate on curved threads) is deferred
to v2. The axis-sort skeleton ordering used here is a single-thread proxy — correct for
Phase 1's straight/near-straight walking-skeleton proof, validated against ImageJ ground
truth in Phase 2 per MEAS-03, not silently patched further here.

No SAM2/GUI import in this module — it must stay independently re-runnable against mask
fixtures alone (ARCHITECTURE Pattern 1).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.ndimage import label as ndi_label
from skimage.morphology import closing, disk, remove_small_objects, skeletonize

from segment.naming import stem_to_fields

_CSV_COLUMNS = [
    "source_path", "date", "batch", "condition", "thread",
    "area_px", "avg_diameter_px", "stdev_px", "mad_px",
]


def measure_mask(mask: np.ndarray, endpoint_trim_px: int = 5) -> dict:
    """Turn a binary mask into area_px / avg_diameter_px / stdev_px.

    Raises ValueError on an empty/degenerate mask rather than returning NaN.
    """
    mask = mask.astype(bool)
    if not mask.any():
        raise ValueError("cannot measure an empty mask (all-zero)")

    cleaned = closing(mask, disk(2))
    cleaned = remove_small_objects(cleaned, max_size=19)
    if not cleaned.any():
        raise ValueError("mask became empty after cleanup (likely noise-only input)")

    # remove_small_objects only drops specks below max_size — a second SIZABLE stray blob
    # (e.g. a mis-segmented fragment elsewhere in frame, more likely with a smaller/less
    # accurate SAM2 checkpoint) would otherwise be summed into area_px and interleaved into
    # the skeleton/diameter calc alongside the real thread. Keep only the single largest
    # connected component — the thread being measured is always the biggest accepted region.
    labeled, num_components = ndi_label(cleaned)
    if num_components > 1:
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0  # background label is never a candidate
        cleaned = labeled == sizes.argmax()

    area_px = int(cleaned.sum())

    skeleton = skeletonize(cleaned)
    distance = distance_transform_edt(cleaned)

    ys, xs = np.nonzero(skeleton)
    if len(xs) == 0:
        raise ValueError("skeletonization produced no skeleton pixels")

    widths = 2.0 * distance[ys, xs]

    # Order skeleton points along the dominant axis (proxy for "along the thread"),
    # then trim a fixed pixel margin from both ends before averaging (endpoint trim).
    x_extent = xs.max() - xs.min()
    y_extent = ys.max() - ys.min()
    order = np.argsort(xs if x_extent >= y_extent else ys)
    widths_ordered = widths[order]

    trim = min(endpoint_trim_px, len(widths_ordered) // 3)
    trimmed = widths_ordered[trim: len(widths_ordered) - trim] if trim > 0 else widths_ordered
    if len(trimmed) == 0:
        trimmed = widths_ordered

    avg_diameter_px = float(np.mean(trimmed))
    stdev_px = float(np.std(trimmed, ddof=1)) if len(trimmed) > 1 else 0.0
    # Median absolute deviation: more robust to SAM2's jagged mask-boundary noise than
    # stdev (Phase-2 VALIDATION finding of ~30% stdev overshoot) — additive, does not
    # replace avg_diameter_px/stdev_px.
    mad_px = float(np.median(np.abs(trimmed - np.median(trimmed))))

    return {
        "area_px": area_px, "avg_diameter_px": avg_diameter_px, "stdev_px": stdev_px,
        "mad_px": mad_px,
    }


def measure_folder(masks_dir: Path, out_csv: Path) -> pd.DataFrame:
    """Measure every *.png in masks_dir; write measurements.csv in the frozen schema.

    Per D-05, operates over a whole folder — no per-file argument required.
    """
    masks_dir = Path(masks_dir)
    out_csv = Path(out_csv)
    rows = []
    errors = []

    for mask_path in sorted(masks_dir.glob("*.png")):
        try:
            mask = np.array(Image.open(mask_path).convert("L")) > 127
            measured = measure_mask(mask)
        except ValueError as exc:
            # One bad mask (e.g. fully erased/degenerate) must not lose every other
            # already-good mask's measurements in the same batch — isolate and continue.
            print(f"skipping unmeasurable mask {mask_path.name}: {exc}")
            errors.append((str(mask_path), str(exc)))
            continue
        fields = stem_to_fields(mask_path.stem)
        rows.append({
            "source_path": str(mask_path),
            "date": fields.get("date", ""),
            "batch": fields.get("batch", ""),
            "condition": fields.get("condition", ""),
            "thread": fields.get("thread", ""),
            "area_px": measured["area_px"],
            "avg_diameter_px": measured["avg_diameter_px"],
            "stdev_px": measured["stdev_px"],
            "mad_px": measured["mad_px"],
        })

    if errors:
        print(f"measured {len(rows)} mask(s), skipped {len(errors)} unmeasurable mask(s) — see messages above")

    df = pd.DataFrame(rows, columns=_CSV_COLUMNS)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-2: measure a folder of masks into measurements.csv")
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--out", type=Path, default=Path("data/csv/measurements.csv"))
    args = parser.parse_args()
    df = measure_folder(args.masks_dir, args.out)
    print(f"wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
