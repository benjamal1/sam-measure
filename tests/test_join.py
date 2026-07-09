import pandas as pd
import pytest

from join.build_final_csv import EXACT_R_SCRIPT_COLUMNS, build_final_csv

EXACT_HEADER = (
    "Thread,Batch,Condition,Date,Conversion (pixels/cm),"
    "Avg diameter(px),StDev(px),AvgDiameter(mm),StDev(mm)"
)

# The 6 columns Task 6 appends after EXACT_R_SCRIPT_COLUMNS — order matters (plan-specified).
NEW_APPENDED_COLUMNS = ["area_px", "area_mm2", "mad_px", "mad_mm", "flag", "flag_reason"]


def _write_measurements(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_calibration(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_build_final_csv_exact_header_and_mm_conversion(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2025-08-03", "batch": "", "condition": "",
        "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        "mad_px": 40.0,
    }])
    _write_calibration(calibration_csv, [{
        "date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    header_line = output_csv.read_text().splitlines()[0]
    # EXACT_R_SCRIPT_COLUMNS (the frozen R-facing contract) must be the first N columns,
    # unchanged order — new columns are appended AFTER, never inserted/reordered.
    assert header_line.startswith(EXACT_HEADER + ",")
    assert list(df.columns[: len(EXACT_R_SCRIPT_COLUMNS)]) == EXACT_R_SCRIPT_COLUMNS
    assert list(df.columns) == EXACT_R_SCRIPT_COLUMNS + NEW_APPENDED_COLUMNS

    row = df.iloc[0]
    assert row["AvgDiameter(mm)"] == pytest.approx(632.0 / 8000.0 * 10)
    assert row["StDev(mm)"] == pytest.approx(89.0 / 8000.0 * 10)


def test_build_final_csv_date_renders_no_leading_zeros_2digit_year(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2025-08-03", "batch": "", "condition": "",
        "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        "mad_px": 40.0,
    }])
    _write_calibration(calibration_csv, [{
        "date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert df.iloc[0]["Date"] == "8/3/25"


def test_build_final_csv_raises_on_unmatched_calibration(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2025-08-03", "batch": "", "condition": "",
        "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        "mad_px": 40.0,
    }])
    _write_calibration(calibration_csv, [{
        "date": "2026-01-01", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg",
    }])

    with pytest.raises(ValueError, match="2025-08-03"):
        build_final_csv(measurements_csv, calibration_csv, output_csv)


def test_build_final_csv_joins_on_empty_string_batch_not_nan(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
        "thread": "05", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        "mad_px": 40.0,
    }])
    _write_calibration(calibration_csv, [{
        "date": "2026-05-11", "batch": "8", "px_per_cm": 7500.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert len(df) == 1
    assert df.iloc[0]["Batch"] == "8"


# --- Task 6: date-fallback calibration + area/MAD/outlier columns ------------------------


def test_build_final_csv_uses_same_batch_earlier_date_fallback_when_no_exact_match(tmp_path):
    """A session with no same-date calibration but a same-batch EARLIER-dated one now
    succeeds — previously this would have hard-failed under exact-match-only."""
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
        "thread": "05", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        "mad_px": 40.0,
    }])
    # Only an EARLIER same-batch ruler exists (no exact 2026-05-11 row) — must fall back.
    _write_calibration(calibration_csv, [{
        "date": "2026-05-01", "batch": "8", "px_per_cm": 7000.0, "ruler_source_path": "ruler_earlier.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert len(df) == 1
    assert df.iloc[0]["Conversion (pixels/cm)"] == pytest.approx(7000.0)
    assert df.iloc[0]["AvgDiameter(mm)"] == pytest.approx(632.0 / 7000.0 * 10)


def test_build_final_csv_never_falls_back_across_batches(tmp_path):
    """A different-batch row, even at the exact date, must never be used as a fallback."""
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
        "thread": "05", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        "mad_px": 40.0,
    }])
    _write_calibration(calibration_csv, [
        {"date": "2026-05-11", "batch": "9", "px_per_cm": 9999.0, "ruler_source_path": "wrong_batch.jpg"},
    ])

    with pytest.raises(ValueError, match="2026-05-11"):
        build_final_csv(measurements_csv, calibration_csv, output_csv)


def test_build_final_csv_appends_area_mm2_and_mad_mm_after_exact_columns(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2025-08-03", "batch": "", "condition": "",
        "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        "mad_px": 40.0,
    }])
    _write_calibration(calibration_csv, [{
        "date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    row = df.iloc[0]
    px_per_mm = 8000.0 / 10
    assert row["area_px"] == 12000
    assert row["area_mm2"] == pytest.approx(12000 / (px_per_mm ** 2))
    assert row["mad_px"] == pytest.approx(40.0)
    assert row["mad_mm"] == pytest.approx(40.0 / 8000.0 * 10)
    assert row["flag"] == False  # noqa: E712 — single row, never flagged
    assert row["flag_reason"] == ""


def test_build_final_csv_missing_mad_px_column_defaults_gracefully(tmp_path):
    """Backward compatibility: a measurements.csv predating Task 4's mad_px column must
    not crash build_final_csv."""
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "x.jpg", "date": "2025-08-03", "batch": "", "condition": "",
        "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
    }])
    _write_calibration(calibration_csv, [{
        "date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert df.iloc[0]["mad_px"] == 0.0
    assert df.iloc[0]["mad_mm"] == 0.0


def test_build_final_csv_flags_outlier_within_its_own_group(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    rows = [
        {
            "source_path": f"{i}.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
            "thread": f"0{i}", "area_px": 1000 + i, "avg_diameter_px": 20.0, "stdev_px": 1.0, "mad_px": 0.5,
        }
        for i in range(5)
    ]
    rows.append({
        "source_path": "outlier.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
        "thread": "99", "area_px": 5000, "avg_diameter_px": 20.0, "stdev_px": 1.0, "mad_px": 0.5,
    })
    _write_measurements(measurements_csv, rows)
    _write_calibration(calibration_csv, [{
        "date": "2026-05-11", "batch": "8", "px_per_cm": 7500.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    outlier_row = df[df["Thread"] == "99"].iloc[0]
    assert outlier_row["flag"] == True  # noqa: E712
    assert "area_px" in outlier_row["flag_reason"]
    normal_rows = df[df["Thread"] != "99"]
    assert (normal_rows["flag"] == False).all()  # noqa: E712
