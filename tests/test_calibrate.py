import matplotlib
matplotlib.use("Agg")  # noqa: E402 — headless, must precede any pyplot import in the module under test

import pandas as pd
import pytest

from calibrate.ruler_scale import (
    _discover_ruler_photos, px_per_cm, resolve_calibration_detailed, resolve_calibration_factor,
    write_calibration_csv,
)


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


# --- Task 3: resolve_calibration_factor (CAL-02 same-batch date-fallback) -----------------


_ROWS = [
    {"date": "2026-04-24", "batch": "8", "px_per_cm": 7000.0, "ruler_source_path": "r1.jpg"},
    {"date": "2026-05-01", "batch": "8", "px_per_cm": 7200.0, "ruler_source_path": "r2.jpg"},
    {"date": "2026-05-11", "batch": "8", "px_per_cm": 7500.0, "ruler_source_path": "r3.jpg"},
    # A DIFFERENT batch with a row closer in date than batch 8's own fallback candidates —
    # must never be selected over the same-batch fallback.
    {"date": "2026-05-10", "batch": "9", "px_per_cm": 9999.0, "ruler_source_path": "r4.jpg"},
]


def test_resolve_calibration_factor_prefers_exact_date_batch_match():
    factor = resolve_calibration_factor(_ROWS, date="2026-05-11", batch="8")

    assert factor == pytest.approx(7500.0)


def test_resolve_calibration_factor_falls_back_to_closest_earlier_same_batch_date():
    # No row for 2026-05-15/batch 8 — nearest earlier same-batch date is 2026-05-11.
    factor = resolve_calibration_factor(_ROWS, date="2026-05-15", batch="8")

    assert factor == pytest.approx(7500.0)


def test_resolve_calibration_factor_never_crosses_batches_even_when_closer_in_date():
    # 2026-05-10/batch 9 is closer in date than any batch-8 row, but must never be chosen —
    # the correct answer is batch 8's own most-recent EARLIER row (2026-05-01).
    factor = resolve_calibration_factor(_ROWS, date="2026-05-10", batch="8")

    assert factor == pytest.approx(7200.0)


def test_resolve_calibration_factor_returns_none_when_no_same_batch_row_at_or_before_date():
    factor = resolve_calibration_factor(_ROWS, date="2026-04-01", batch="8")

    assert factor is None


def test_resolve_calibration_factor_returns_none_for_unknown_batch():
    factor = resolve_calibration_factor(_ROWS, date="2026-05-11", batch="99")

    assert factor is None


# --- ruler discovery: recursive, extension-filtered, excludes non-image "ruler*" files -----


def test_discover_ruler_photos_finds_nested_ruler_files(tmp_path):
    (tmp_path / "Batch 8" / "D1 05-01-26").mkdir(parents=True)
    ruler = tmp_path / "Batch 8" / "D1 05-01-26" / "ruler_05-01-26.JPG"
    ruler.touch()

    found = _discover_ruler_photos(tmp_path)

    assert found == [ruler]


def test_discover_ruler_photos_excludes_non_image_ruler_named_files(tmp_path):
    """A stray ruler_notes.txt (or any non-.jpg/.jpeg file merely starting with 'ruler')
    must never reach calibrate_ruler/plt.imread — that crashed the whole calibration run."""
    day = tmp_path / "Batch 8" / "D1 05-01-26"
    day.mkdir(parents=True)
    (day / "ruler_05-01-26.JPG").touch()
    (day / "ruler_notes.txt").touch()
    (day / "ruler.docx").touch()

    found = _discover_ruler_photos(tmp_path)

    assert found == [day / "ruler_05-01-26.JPG"]


def test_discover_ruler_photos_case_insensitive_prefix_and_suffix(tmp_path):
    day = tmp_path / "Batch 8" / "D1 05-01-26"
    day.mkdir(parents=True)
    (day / "Ruler_05-01-26.jpeg").touch()

    found = _discover_ruler_photos(tmp_path)

    assert len(found) == 1


# --- resolve_calibration_detailed: same resolution, plus traceability -----------------------


def test_resolve_calibration_detailed_exact_match_reports_source_not_fallback():
    detailed = resolve_calibration_detailed(_ROWS, date="2026-05-11", batch="8")

    assert detailed["px_per_cm"] == pytest.approx(7500.0)
    assert detailed["calibration_date"] == "2026-05-11"
    assert detailed["is_fallback"] is False
    assert detailed["ruler_source_path"] == "r3.jpg"


def test_resolve_calibration_detailed_fallback_reports_the_date_actually_used():
    detailed = resolve_calibration_detailed(_ROWS, date="2026-05-15", batch="8")

    assert detailed["px_per_cm"] == pytest.approx(7500.0)
    assert detailed["calibration_date"] == "2026-05-11"  # NOT 2026-05-15 — the fallback date
    assert detailed["is_fallback"] is True
    assert detailed["ruler_source_path"] == "r3.jpg"


def test_resolve_calibration_detailed_returns_none_when_unresolvable():
    assert resolve_calibration_detailed(_ROWS, date="2020-01-01", batch="8") is None
