"""Stage-4: merge measurements + calibration on (date,batch), convert px->mm, emit exact R schema.

CSV-03: this is the single hard external compatibility boundary in the project — the R script
is not modified. D-09: Date is the day/measurement-folder date. A measurement row whose
(date,batch) has no calibration match raises loudly (Phase-1 form of CAL-03/CSV-04 — the formal
hard-fail contract is Phase 2, but Phase 1 must never fabricate a factor).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

EXACT_R_SCRIPT_COLUMNS = [
    "Thread", "Batch", "Condition", "Date", "Conversion (pixels/cm)",
    "Avg diameter(px)", "StDev(px)", "AvgDiameter(mm)", "StDev(mm)",
]


def _render_date(iso_date: str) -> str:
    """ISO YYYY-MM-DD -> M/D/YY (no leading zeros, 2-digit year), matching the ImageJ sample style."""
    year, month, day = iso_date.split("-")
    return f"{int(month)}/{int(day)}/{year[2:]}"


def build_final_csv(measurements_csv: Path, calibration_csv: Path, output_csv: Path) -> pd.DataFrame:
    measurements = pd.read_csv(measurements_csv, dtype=str)
    calibration = pd.read_csv(calibration_csv, dtype=str)

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
        sessions = sorted(set(zip(unmatched["date"], unmatched["batch"])))
        raise ValueError(
            "no matching calibration factor for session(s): "
            + ", ".join(f"(date={d}, batch={b!r})" for d, b in sessions)
        )

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

    output_csv = Path(output_csv)
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
