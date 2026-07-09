"""Stage-4: merge measurements + calibration on (date,batch), convert px->mm, emit exact R schema.

CSV-03: this is the single hard external compatibility boundary in the project — the R script
is not modified. D-09: Date is the day/measurement-folder date. A measurement row whose
(date,batch) has no resolvable calibration factor (exact OR same-batch date-fallback — see
`resolve_calibration_factor`) raises loudly, naming BOTH the unmatched session (CAL-03: the
session has no ruler calibration at all, even via fallback) AND the affected thread id(s)
(CSV-04: the specific thread row(s) left unmatched) — before any output is written, so a
hard-failed run never produces a partial final.csv. An empty/missing calibration.csv is
treated as zero calibration rows rather than raising a cryptic pandas error (CAL-03). On
hard-fail, any pre-existing output_csv from a prior run is removed so a failed run cannot
masquerade as a current result (Pitfall 4).

Task 6: final.csv appends area_px, area_mm2, mad_px, mad_mm, flag, flag_reason AFTER
EXACT_R_SCRIPT_COLUMNS — that frozen column set/order/count is the live R-script contract
and must never change; new columns are additive only, never inserted/reordered.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from calibrate.ruler_scale import resolve_calibration_factor
from validate.outliers import flag_outliers

EXACT_R_SCRIPT_COLUMNS = [
    "Thread", "Batch", "Condition", "Date", "Conversion (pixels/cm)",
    "Avg diameter(px)", "StDev(px)", "AvgDiameter(mm)", "StDev(mm)",
]

# Task 6: appended AFTER EXACT_R_SCRIPT_COLUMNS, this exact order, never inserted/reordered.
_APPENDED_COLUMNS = ["area_px", "area_mm2", "mad_px", "mad_mm", "flag", "flag_reason"]

CALIBRATION_COLUMNS = ["date", "batch", "px_per_cm", "ruler_source_path"]


def _render_date(iso_date: str) -> str:
    """ISO YYYY-MM-DD -> M/D/YY (no leading zeros, 2-digit year), matching the ImageJ sample style."""
    year, month, day = iso_date.split("-")
    return f"{int(month)}/{int(day)}/{year[2:]}"


def _read_calibration(calibration_csv: Path) -> pd.DataFrame:
    """Read calibration.csv as zero calibration rows if the file is empty, instead of letting
    pandas raise a bare EmptyDataError (CAL-03: an empty/missing calibration file must still
    produce a clear, named hard-fail via the unmatched-session guard below)."""
    try:
        return pd.read_csv(calibration_csv, dtype=str)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=CALIBRATION_COLUMNS)


def _unmatched_hard_fail_message(unmatched: pd.DataFrame) -> str:
    """Name BOTH the unmatched (date,batch) session(s) (CAL-03) AND the affected thread id(s)
    (CSV-04) so an operator can trace the failure back to the source data (Pitfall 4)."""
    sessions = sorted(set(zip(unmatched["date"], unmatched["batch"])))
    parts = []
    for date, batch in sessions:
        threads = sorted(
            unmatched.loc[(unmatched["date"] == date) & (unmatched["batch"] == batch), "thread"]
        )
        parts.append(f"(date={date}, batch={batch!r}) thread(s)={threads}")
    return "no matching calibration factor for session(s): " + "; ".join(parts)


def build_final_csv(measurements_csv: Path, calibration_csv: Path, output_csv: Path) -> pd.DataFrame:
    output_csv = Path(output_csv)

    measurements = pd.read_csv(measurements_csv, dtype=str)
    calibration = _read_calibration(calibration_csv)

    measurements["batch"] = measurements["batch"].fillna("")
    calibration["batch"] = calibration["batch"].fillna("")

    for col in ("area_px", "avg_diameter_px", "stdev_px"):
        measurements[col] = pd.to_numeric(measurements[col])
    # mad_px (Task 4) is additive — a measurements.csv predating it must not crash here.
    if "mad_px" in measurements.columns:
        measurements["mad_px"] = pd.to_numeric(measurements["mad_px"])
    else:
        measurements["mad_px"] = 0.0
    calibration["px_per_cm"] = pd.to_numeric(calibration["px_per_cm"])

    # Task 3: date-fallback-within-batch calibration resolution replaces the flat
    # exact-match merge. Resolved row-wise since each measurement row may need a
    # DIFFERENT calibration row (its own session's exact match or same-batch fallback).
    calibration_rows = calibration.to_dict("records")
    merged = measurements.copy()
    merged["px_per_cm"] = pd.to_numeric(merged.apply(
        lambda row: resolve_calibration_factor(calibration_rows, date=row["date"], batch=row["batch"]),
        axis=1,
    ))

    unmatched = merged[merged["px_per_cm"].isna()]
    if not unmatched.empty:
        if output_csv.exists():
            output_csv.unlink()
        raise ValueError(_unmatched_hard_fail_message(unmatched))

    merged["AvgDiameter(mm)"] = merged["avg_diameter_px"] / merged["px_per_cm"] * 10
    merged["StDev(mm)"] = merged["stdev_px"] / merged["px_per_cm"] * 10
    merged["Date"] = merged["date"].apply(_render_date)

    # area_mm2: px_per_cm is pixels-per-CENTIMETER (linear); area needs pixels-per-MM
    # SQUARED, since area scales with the square of the linear conversion factor —
    # px_per_mm = px_per_cm / 10, so area_mm2 = area_px / (px_per_cm/10)**2. This is a
    # genuinely different conversion than the linear AvgDiameter(mm)/StDev(mm)/mad_mm above.
    px_per_mm = merged["px_per_cm"] / 10
    merged["area_mm2"] = merged["area_px"] / (px_per_mm ** 2)
    merged["mad_mm"] = merged["mad_px"] / merged["px_per_cm"] * 10

    # Task 5: outlier flagging runs over the FULL assembled frame (all sessions present)
    # grouped by (date,batch,condition) — advisory only, never blocks/hard-fails a run.
    flagged = flag_outliers(
        merged[["date", "batch", "condition", "thread", "area_px", "avg_diameter_px"]].to_dict("records")
    )
    merged["flag"] = [row["flag"] for row in flagged]
    merged["flag_reason"] = [row["flag_reason"] for row in flagged]

    out = pd.DataFrame({
        "Thread": merged["thread"],
        "Batch": merged["batch"],
        "Condition": merged["condition"],
        "Date": merged["Date"],
        "Conversion (pixels/cm)": merged["px_per_cm"],
        "Avg diameter(px)": merged["avg_diameter_px"],
        "StDev(px)": merged["stdev_px"],
        "AvgDiameter(mm)": merged["AvgDiameter(mm)"],
        "StDev(mm)": merged["StDev(mm)"],
    })[EXACT_R_SCRIPT_COLUMNS]

    for col in _APPENDED_COLUMNS:
        out[col] = merged[col].values

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-4: build the final R-script-exact CSV")
    parser.add_argument("--measurements", type=Path, default=Path("data/csv/measurements.csv"))
    parser.add_argument("--calibration", type=Path, default=Path("data/calibration/calibration.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/csv/final.csv"))
    args = parser.parse_args()
    df = build_final_csv(args.measurements, args.calibration, args.out)
    print(f"wrote {len(df)} row(s) to {args.out}")


if __name__ == "__main__":
    main()
