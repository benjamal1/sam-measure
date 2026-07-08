"""Stage-3: per-session ruler calibration -> pixels/cm.

D-10: ruler photos are macro/microscope shots — the default known span is 0-0.5cm
using fine mm tick marks, NOT a wide 0-10cm span. CAL-02: calibration is stored per
(date, batch) session, never as one global constant.

Pure math (px_per_cm, write_calibration_csv) is split from the interactive ginput
collection (calibrate_ruler) so the pure layer is unit-testable without a display.
The interactive path is validated by hand on the Mac, not in this build session.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from segment.naming import parse_flat_path, parse_photo_path

_CALIBRATION_COLUMNS = ["date", "batch", "px_per_cm", "ruler_source_path"]

DEFAULT_KNOWN_CM_SPAN = 0.5  # D-10: macro ruler, 0-0.5cm span with fine mm ticks


def px_per_cm(p1: tuple[float, float], p2: tuple[float, float], known_cm_span: float) -> float:
    """Pure math: euclidean pixel distance between two clicked points / known cm span."""
    if known_cm_span <= 0:
        raise ValueError(f"known_cm_span must be positive, got {known_cm_span}")
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    distance = math.hypot(dx, dy)
    if distance == 0:
        raise ValueError("clicked points are coincident — cannot derive a scale from zero distance")
    return distance / known_cm_span


def write_calibration_csv(rows: list[dict], out_csv: Path) -> pd.DataFrame:
    """Write calibration rows (one per (date,batch) session) to calibration.csv."""
    out_csv = Path(out_csv)
    df = pd.DataFrame(rows, columns=_CALIBRATION_COLUMNS)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df


def calibrate_ruler(
    ruler_path: Path,
    known_cm_span: float = DEFAULT_KNOWN_CM_SPAN,
    date: str | None = None,
    batch: str | None = None,
    nextcloud_root: Path | None = None,
) -> dict:
    """Interactive: open the ruler image, collect two clicks via ginput, return a calibration row.

    date/batch overrides are used for flat/legacy data where the path can't be parsed nested.
    Not exercised by the automated test suite (requires a display) — validated by hand on the Mac.
    """
    import matplotlib.pyplot as plt

    if date is None or batch is None:
        try:
            meta = parse_photo_path(ruler_path, nextcloud_root) if nextcloud_root else parse_flat_path(ruler_path)
        except ValueError:
            meta = parse_flat_path(ruler_path)
        date = date or meta.date.isoformat()
        batch = batch if batch is not None else meta.batch

    img = plt.imread(ruler_path)
    fig, ax = plt.subplots()
    ax.imshow(img)
    ax.set_title(
        f"Click two points exactly {known_cm_span} cm apart on the ruler's fine mm ticks "
        "(zoom in first — D-10 macro span)"
    )
    points = plt.ginput(2, timeout=0)
    plt.close(fig)

    factor = px_per_cm(points[0], points[1], known_cm_span)
    return {
        "date": date,
        "batch": batch,
        "px_per_cm": factor,
        "ruler_source_path": str(ruler_path),
    }


def calibrate_folder(
    ruler_dir: Path,
    out_csv: Path,
    known_cm_span: float = DEFAULT_KNOWN_CM_SPAN,
    date: str | None = None,
    batch: str | None = None,
    nextcloud_root: Path | None = None,
) -> pd.DataFrame:
    """Interactive: calibrate every ruler*.jpg/JPG in a folder, write calibration.csv."""
    ruler_dir = Path(ruler_dir)
    rows = [
        calibrate_ruler(p, known_cm_span, date, batch, nextcloud_root)
        for p in sorted(ruler_dir.glob("ruler*"))
    ]
    return write_calibration_csv(rows, out_csv)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-3: calibrate ruler photo(s) into calibration.csv")
    parser.add_argument("--ruler-dir", type=Path)
    parser.add_argument("--ruler", type=Path)
    parser.add_argument("--span", type=float, default=DEFAULT_KNOWN_CM_SPAN)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--batch", type=str, default=None)
    parser.add_argument("--out", type=Path, default=Path("data/calibration/calibration.csv"))
    args = parser.parse_args()

    if args.ruler:
        row = calibrate_ruler(args.ruler, args.span, args.date, args.batch)
        df = write_calibration_csv([row], args.out)
    else:
        ruler_dir = args.ruler_dir or Path("data/masks")
        df = calibrate_folder(ruler_dir, args.out, args.span, args.date, args.batch)
    print(f"wrote {len(df)} calibration row(s) to {args.out}")


if __name__ == "__main__":
    main()
