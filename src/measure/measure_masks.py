"""Headless measurement stage: mask -> area/diameter/stdev via skeleton + distance transform.

D-03: skeleton + Euclidean distance-transform width sampling is THE method for Phase 1.
D-04: true perpendicular ray-cast measurement (more accurate on curved threads) is deferred
to v2.

Skeleton ordering walks actual pixel connectivity (not an x/y axis projection) — this is
orientation-invariant (works for diagonal threads) and curve-robust (works for bent/L-shaped
threads, where a single-axis sort would scramble ordering). The two most distant skeleton
endpoints (by path length) define the "backbone"; any other branch is a spur from boundary
noise and is excluded from measurement. Endpoint trim is a FRACTION of the backbone's real
arc length (not a fixed pixel/point count), so it trims a consistent physical proportion of
the thread's ends regardless of how much of the thread was captured in a given photo.

No SAM2/GUI import in this module — it must stay independently re-runnable against mask
fixtures alone (ARCHITECTURE Pattern 1).
"""
from __future__ import annotations

import argparse
from collections import deque
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

DEFAULT_ENDPOINT_TRIM_FRACTION = 0.05  # trim 5% of arc length off each end by default

_NEIGHBOR_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _skeleton_adjacency(skeleton: np.ndarray) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """8-connected adjacency graph over skeleton pixel coordinates (y, x)."""
    coords = set(zip(*np.nonzero(skeleton)))
    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {c: [] for c in coords}
    for y, x in coords:
        for dy, dx in _NEIGHBOR_OFFSETS:
            n = (y + dy, x + dx)
            if n in coords:
                adjacency[(y, x)].append(n)
    return adjacency


def _bfs_farthest(start: tuple[int, int], adjacency: dict) -> tuple[tuple[int, int], dict]:
    """BFS from start; returns the farthest node (by step count) and the distance map."""
    dist = {start: 0}
    queue = deque([start])
    farthest = start
    while queue:
        node = queue.popleft()
        if dist[node] > dist[farthest]:
            farthest = node
        for n in adjacency[node]:
            if n not in dist:
                dist[n] = dist[node] + 1
                queue.append(n)
    return farthest, dist


def _backbone_path(skeleton: np.ndarray) -> list[tuple[int, int]]:
    """Order skeleton pixels along the longest path between its two most distant endpoints
    (classic tree-diameter double-BFS). Excludes any branch spur not on that path.
    """
    adjacency = _skeleton_adjacency(skeleton)
    if not adjacency:
        return []
    any_node = next(iter(adjacency))
    end_a, _ = _bfs_farthest(any_node, adjacency)
    end_b, dist_from_a = _bfs_farthest(end_a, adjacency)

    # Reconstruct the path end_a -> end_b by walking from end_b back via decreasing distance.
    path = [end_b]
    current = end_b
    visited = {end_b}
    while current != end_a:
        candidates = [n for n in adjacency[current] if n not in visited and dist_from_a.get(n, -1) == dist_from_a[current] - 1]
        if not candidates:
            break  # disconnected/degenerate skeleton; return what we have
        current = candidates[0]
        visited.add(current)
        path.append(current)
    path.reverse()
    return path


def _arc_lengths(path: list[tuple[int, int]]) -> list[float]:
    """Cumulative euclidean arc length at each path point (diagonal steps count as sqrt(2))."""
    cum = [0.0]
    for i in range(1, len(path)):
        (y0, x0), (y1, x1) = path[i - 1], path[i]
        cum.append(cum[-1] + ((y1 - y0) ** 2 + (x1 - x0) ** 2) ** 0.5)
    return cum


def _trim_by_arc_fraction(path: list[tuple[int, int]], fraction: float) -> tuple[list[tuple[int, int]], list[int]]:
    """Return (kept_path, kept_indices) after trimming `fraction` of total arc length from
    each end. Falls back to the full path if trimming would remove everything."""
    if len(path) < 3 or fraction <= 0:
        return path, list(range(len(path)))
    cum = _arc_lengths(path)
    total = cum[-1]
    if total == 0:
        return path, list(range(len(path)))
    lo, hi = total * fraction, total * (1 - fraction)
    kept_indices = [i for i, d in enumerate(cum) if lo <= d <= hi]
    if len(kept_indices) < 2:
        return path, list(range(len(path)))
    return [path[i] for i in kept_indices], kept_indices


def measure_mask(mask: np.ndarray, endpoint_trim_fraction: float = DEFAULT_ENDPOINT_TRIM_FRACTION) -> dict:
    """Turn a binary mask into area_px / avg_diameter_px / stdev_px / mad_px.

    endpoint_trim_fraction: fraction of the skeleton's real arc length trimmed from each end
    before averaging widths (e.g. 0.05 = drop the outer 5% at each end, keep the middle 90%).

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

    path = _backbone_path(skeleton)
    if not path:
        raise ValueError("skeletonization produced no skeleton pixels")

    kept_path, _ = _trim_by_arc_fraction(path, endpoint_trim_fraction)
    widths = np.array([2.0 * distance[y, x] for y, x in kept_path])

    avg_diameter_px = float(np.mean(widths))
    stdev_px = float(np.std(widths, ddof=1)) if len(widths) > 1 else 0.0
    # Median absolute deviation: more robust to SAM2's jagged mask-boundary noise than
    # stdev (Phase-2 VALIDATION finding of ~30% stdev overshoot) — additive, does not
    # replace avg_diameter_px/stdev_px.
    mad_px = float(np.median(np.abs(widths - np.median(widths))))

    return {
        "area_px": area_px, "avg_diameter_px": avg_diameter_px, "stdev_px": stdev_px,
        "mad_px": mad_px,
    }


def render_skeleton_qc(mask: np.ndarray, endpoint_trim_fraction: float = DEFAULT_ENDPOINT_TRIM_FRACTION) -> np.ndarray:
    """Render an RGB QC image: mask in light gray, KEPT backbone skeleton in bright green,
    TRIMMED-off ends in red, any excluded spur in blue — so a human can visually confirm
    skeletonize picked a sane backbone before trusting the numbers.
    """
    mask = mask.astype(bool)
    h, w = mask.shape
    qc = np.zeros((h, w, 3), dtype=np.uint8)
    qc[mask] = (60, 60, 60)  # mask body: dark gray

    cleaned = closing(mask, disk(2))
    cleaned = remove_small_objects(cleaned, max_size=19)
    labeled, num_components = ndi_label(cleaned)
    if num_components > 1:
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0
        cleaned = labeled == sizes.argmax()

    skeleton = skeletonize(cleaned)
    all_skel_coords = set(zip(*np.nonzero(skeleton)))
    path = _backbone_path(skeleton)

    if path:
        _, kept_indices = _trim_by_arc_fraction(path, endpoint_trim_fraction)
        kept_set = {path[i] for i in kept_indices}
        backbone_set = set(path)
        for (y, x) in backbone_set:
            qc[y, x] = (0, 255, 0) if (y, x) in kept_set else (255, 0, 0)
        for (y, x) in all_skel_coords - backbone_set:
            qc[y, x] = (0, 100, 255)  # spur, excluded from measurement

    return qc


def measure_folder(masks_dir: Path, out_csv: Path, qc_dir: Path | None = None) -> pd.DataFrame:
    """Measure every *.png in masks_dir; write measurements.csv in the frozen schema.

    Per D-05, operates over a whole folder — no per-file argument required. If qc_dir is
    given, also writes a skeleton QC overlay per mask (<stem>_skeleton.png) so the actual
    backbone/trim can be visually reviewed, not just trusted.
    """
    masks_dir = Path(masks_dir)
    out_csv = Path(out_csv)
    rows = []
    errors = []

    for mask_path in sorted(masks_dir.glob("*.png")):
        try:
            mask = np.array(Image.open(mask_path).convert("L")) > 127
            measured = measure_mask(mask)
            if qc_dir is not None:
                qc_dir = Path(qc_dir)
                qc_dir.mkdir(parents=True, exist_ok=True)
                qc_img = render_skeleton_qc(mask)
                Image.fromarray(qc_img).save(qc_dir / f"{mask_path.stem}_skeleton.png")
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
    parser.add_argument("--qc-dir", type=Path, default=Path("data/qc"))
    args = parser.parse_args()
    df = measure_folder(args.masks_dir, args.out, qc_dir=args.qc_dir)
    print(f"wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
