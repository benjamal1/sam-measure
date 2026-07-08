"""Stage-4: merge measurements + calibration on (date,batch), convert px->mm, emit exact R schema.

CSV-03: this is the single hard external compatibility boundary in the project — the R script
is not modified. D-09: Date is the day/measurement-folder date. A measurement row whose
(date,batch) has no calibration match raises loudly, naming BOTH the unmatched session (CAL-03:
the session has no ruler calibration at all) AND the affected thread id(s) (CSV-04: the specific
thread row(s) left unmatched by the merge) — before any output is written, so a hard-failed run
never produces a partial final.csv. An empty/missing calibration.csv is treated as zero
calibration rows rather than raising a cryptic pandas error (CAL-03). On hard-fail, any
pre-existing output_csv from a prior run is removed so a failed run cannot masquerade as a
current result (Pitfall 4).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

EXACT_R_SCRIPT_COLUMNS = [
    "Thread", "Batch", "Condition", "Date", "Conversion (pixels/cm)",
    "Avg diameter(px)", "StDev(px)", "AvgDiameter(mm)", "StDev(mm)",
]

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
    calibration["px_per_cm"] = pd.to_numeric(calibration["px_per_cm"])

    merged = measurements.merge(
        calibration[["date", "batch", "px_per_cm"]],
        on=["date", "batch"],
        how="left",
    )

    unmatched = merged[merged["px_per_cm"].isna()]
    if not unmatched.empty:
        if output_csv.exists():
            output_csv.unlink()
        raise ValueError(_unmatched_hard_fail_message(unmatched))

    merged["AvgDiameter(mm)"] = merged["avg_diameter_px"] / merged["px_per_cm"] * 10
    merged["StDev(mm)"] = merged["stdev_px"] / merged["px_per_cm"] * 10
    merged["Date"] = merged["date"].apply(_render_date)

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
