"""Requirement-ID-labeled hard-fail contract tests for build_final_csv (CAL-03 + CSV-04).

CAL-03: a thread whose (date,batch) session has no ruler calibration hard-fails with a
clear, named error instead of silently defaulting or skipping.
CSV-04: a thread row that cannot be matched to a calibration factor during CSV assembly
hard-fails the whole run instead of being silently skipped or nulled out; a hard-failed
run leaves no partial and no stale final.csv (Pitfall 4).
"""
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


def test_CAL_03_session_without_ruler_calibration_hard_fails(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [
        {
            "source_path": "a.jpg", "date": "2025-08-03", "batch": "", "condition": "",
            "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        },
        {
            "source_path": "b.jpg", "date": "2025-08-03", "batch": "", "condition": "",
            "thread": "5.12", "area_px": 11500, "avg_diameter_px": 600.0, "stdev_px": 80.0,
        },
        {
            "source_path": "c.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
            "thread": "05", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        },
    ])
    _write_calibration(calibration_csv, [
        {"date": "2026-05-11", "batch": "8", "px_per_cm": 7500.0, "ruler_source_path": "ruler2.jpg"},
    ])

    with pytest.raises(ValueError, match=r"2025-08-03") as excinfo:
        build_final_csv(measurements_csv, calibration_csv, output_csv)

    message = str(excinfo.value)
    assert "5.11" in message
    assert "5.12" in message
    assert not output_csv.exists()


def test_CSV_04_unmatched_thread_row_hard_fails_no_partial_output(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [
        {
            "source_path": "a.jpg", "date": "2025-08-03", "batch": "", "condition": "",
            "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        },
        {
            "source_path": "b.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
            "thread": "05", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        },
    ])
    _write_calibration(calibration_csv, [
        {"date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg"},
    ])

    with pytest.raises(ValueError, match=r"2026-05-11"):
        build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert not output_csv.exists()


def test_CAL_03_empty_calibration_file_hard_fails_clearly(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [{
        "source_path": "a.jpg", "date": "2025-08-03", "batch": "", "condition": "",
        "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
    }])
    calibration_csv.write_text("")

    with pytest.raises(ValueError, match=r"2025-08-03") as excinfo:
        build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert "5.11" in str(excinfo.value)
    assert not output_csv.exists()


def test_CSV_04_hard_fail_removes_stale_final_csv(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    output_csv.write_text(EXACT_HEADER + "\nstale,row,from,prior,run,,,,\n")
    assert output_csv.exists()

    _write_measurements(measurements_csv, [{
        "source_path": "a.jpg", "date": "2025-08-03", "batch": "", "condition": "",
        "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
    }])
    _write_calibration(calibration_csv, [
        {"date": "2026-01-01", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg"},
    ])

    with pytest.raises(ValueError):
        build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert not output_csv.exists()


def test_happy_path_multi_thread_still_writes(tmp_path):
    measurements_csv = tmp_path / "measurements.csv"
    calibration_csv = tmp_path / "calibration.csv"
    output_csv = tmp_path / "final.csv"

    _write_measurements(measurements_csv, [
        {
            "source_path": "a.jpg", "date": "2025-08-03", "batch": "", "condition": "",
            "thread": "5.11", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        },
        {
            "source_path": "b.jpg", "date": "2026-05-11", "batch": "8", "condition": "Poststretch",
            "thread": "05", "area_px": 12000, "avg_diameter_px": 632.0, "stdev_px": 89.0,
        },
    ])
    _write_calibration(calibration_csv, [
        {"date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "ruler.jpg"},
        {"date": "2026-05-11", "batch": "8", "px_per_cm": 7500.0, "ruler_source_path": "ruler2.jpg"},
    ])

    df = build_final_csv(measurements_csv, calibration_csv, output_csv)

    assert len(df) == 2
    # Plan 02-04/Task 6: EXACT_R_SCRIPT_COLUMNS (the frozen R-facing contract) must still be
    # the first N columns in unchanged order — area/MAD/outlier columns are appended AFTER,
    # never inserted/reordered, so this is a prefix check rather than a strict equality.
    assert list(df.columns[: len(EXACT_R_SCRIPT_COLUMNS)]) == EXACT_R_SCRIPT_COLUMNS
    header_line = output_csv.read_text().splitlines()[0]
    assert header_line.startswith(EXACT_HEADER + ",")
    assert output_csv.exists()
