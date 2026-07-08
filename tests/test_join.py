import pandas as pd
import pytest

from join.build_final_csv import EXACT_R_SCRIPT_COLUMNS, build_final_csv

EXACT_HEADER = (
    "Thread,Batch,Condition,Date,Conversion (pixels/cm),"
    "Avg diameter(px),StDev(px),AvgDiameter(mm),StDev(mm)"
)


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
    }])
    _write_calibration(calibration_csv, [{
        "date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    header_line = output_csv.read_text().splitlines()[0]
    assert header_line == EXACT_HEADER
    assert list(df.columns) == EXACT_R_SCRIPT_COLUMNS

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
    }])
    _write_calibration(calibration_csv, [{
        "date": "2026-05-11", "batch": "8", "px_per_cm": 7500.0, "ruler_source_path": "ruler.jpg",
    }])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert len(df) == 1
    assert df.iloc[0]["Batch"] == "8"
