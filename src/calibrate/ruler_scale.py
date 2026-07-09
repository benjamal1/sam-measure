"""Stage-3: per-session ruler calibration -> pixels/cm.

D-10: ruler photos are macro/microscope shots — the default known span is 0-0.5cm
using fine mm tick marks, NOT a wide 0-10cm span. CAL-02: calibration is stored per
(date, batch) session, never as one global constant.

Pure math (px_per_cm, write_calibration_csv, resolve_calibration_factor) is split from
the interactive ginput collection (calibrate_ruler) so the pure layer is unit-testable
without a display. The interactive path is validated by hand on the Mac, not in this
build session.
"""
from __future__ import annotations

import argparse
import math
from datetime import date as _date
from pathlib import Path

import pandas as pd

from segment.naming import parse_flat_path, parse_lenient_path, parse_photo_path

_CALIBRATION_COLUMNS = ["date", "batch", "px_per_cm", "ruler_source_path"]

DEFAULT_KNOWN_CM_SPAN = 0.5  # D-10: macro ruler, 0-0.5cm span with fine mm ticks


def resolve_calibration_detailed(calibration_rows: list[dict], date: str, batch: str) -> dict | None:
    """Exact (date,batch) match first; else the closest EARLIER-dated row within the SAME
    batch; else None (caller hard-fails per the existing CAL-03 unmatched-session guard).

    Never matches across batches, even if a different-batch row is closer in date — a
    same-date different-batch row is not a fallback candidate (CAL-02: per-session, never
    global; batches may have different camera/lighting setups per user confirmation).

    Returns full traceability, not just the factor: which ruler DATE and source photo were
    actually used, and whether it was an exact match or a same-batch fallback — a thread's
    own date can silently differ from the ruler date that calibrated it, and that was
    previously invisible in the output.
    """
    target_date = _date.fromisoformat(date)
    same_batch = [row for row in calibration_rows if str(row.get("batch", "")) == str(batch)]

    for row in same_batch:
        if row["date"] == date:
            return {
                "px_per_cm": float(row["px_per_cm"]), "calibration_date": row["date"],
                "is_fallback": False, "ruler_source_path": row.get("ruler_source_path", ""),
            }

    earlier = [row for row in same_batch if _date.fromisoformat(row["date"]) < target_date]
    if not earlier:
        return None

    best = max(earlier, key=lambda row: _date.fromisoformat(row["date"]))
    return {
        "px_per_cm": float(best["px_per_cm"]), "calibration_date": best["date"],
        "is_fallback": True, "ruler_source_path": best.get("ruler_source_path", ""),
    }


def resolve_calibration_factor(calibration_rows: list[dict], date: str, batch: str) -> float | None:
    """Just the factor — thin wrapper over resolve_calibration_detailed for callers (and
    existing tests) that only need px_per_cm, not the full traceability info."""
    detailed = resolve_calibration_detailed(calibration_rows, date, batch)
    return detailed["px_per_cm"] if detailed is not None else None


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
        meta = None
        if nextcloud_root:
            try:
                meta = parse_photo_path(ruler_path, nextcloud_root)
            except ValueError:
                pass
        if meta is None:
            try:
                meta = parse_flat_path(ruler_path)
            except ValueError:
                pass
        if meta is None:
            # Same reorganized-tree layout as segment_export's thread photos (Condition/Batch
            # level dropped or reordered) — same lenient fallback, same reason (naming.py's
            # parse_lenient_path docstring).
            meta = parse_lenient_path(ruler_path)
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


def _discover_ruler_photos(ruler_dir: Path) -> list[Path]:
    """Recursively find ruler_*.jpg/JPG under ruler_dir (any depth), excluding non-image files
    that merely start with "ruler" (e.g. ruler_notes.txt) — pure/testable, no interactive I/O.
    """
    return sorted(
        p for p in Path(ruler_dir).rglob("*")
        if p.is_file() and p.name.lower().startswith("ruler") and p.suffix.lower() in (".jpg", ".jpeg")
    )


def calibrate_folder(
    ruler_dir: Path,
    out_csv: Path,
    known_cm_span: float = DEFAULT_KNOWN_CM_SPAN,
    date: str | None = None,
    batch: str | None = None,
    nextcloud_root: Path | None = None,
) -> pd.DataFrame:
    """Interactive: calibrate every ruler*.jpg/JPG under ruler_dir (any depth), write calibration.csv.

    Recursive (rglob) so a single run over the whole photo tree collects every session's
    ruler — matching segment_export's recursive photo discovery — rather than requiring one
    run per day-folder. Necessary for resolve_calibration_factor's same-batch date-fallback
    (build_final_csv) to have full data to fall back across.
    """
    ruler_photos = _discover_ruler_photos(ruler_dir)
    rows = []
    for p in ruler_photos:
        try:
            rows.append(calibrate_ruler(p, known_cm_span, date, batch, nextcloud_root))
        except ValueError as exc:
            # One bad/unparseable ruler file must not abort calibration for every other
            # already-good session in the same run — isolate and continue.
            print(f"skipping unusable ruler {p}: {exc}")
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
