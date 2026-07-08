import matplotlib
matplotlib.use("Agg")  # noqa: E402 — headless, must precede any pyplot import in the module under test

import pandas as pd
import pytest

from calibrate.ruler_scale import px_per_cm, write_calibration_csv


def test_px_per_cm_known_distance():
    assert px_per_cm((0, 0), (400, 0), 0.5) == pytest.approx(800.0)


def test_px_per_cm_raises_on_zero_span():
    with pytest.raises(ValueError):
        px_per_cm((0, 0), (400, 0), 0.0)


def test_px_per_cm_raises_on_coincident_points():
    with pytest.raises(ValueError):
        px_per_cm((10, 10), (10, 10), 0.5)


def test_calibrate_folder_two_sessions_two_distinct_rows(tmp_path):
    out_csv = tmp_path / "calibration.csv"
    entries = [
        {"date": "2025-08-03", "batch": "", "px_per_cm": 8000.0, "ruler_source_path": "a.jpg"},
        {"date": "2026-05-11", "batch": "8", "px_per_cm": 7500.0, "ruler_source_path": "b.jpg"},
    ]

    write_calibration_csv(entries, out_csv)

    df = pd.read_csv(out_csv, dtype=str)
    assert list(df.columns) == ["date", "batch", "px_per_cm", "ruler_source_path"]
    assert len(df) == 2
    assert set(df["date"]) == {"2025-08-03", "2026-05-11"}
    assert len(set(df["px_per_cm"])) == 2
