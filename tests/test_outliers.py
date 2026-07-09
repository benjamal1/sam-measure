"""IQR-based outlier flagging within (date,batch,condition) groups (QOL-02, pulled
forward from v2 per user request this plan). Pure function — no I/O, no SAM2/torch/cv2.
"""
import pytest

from validate.outliers import flag_outliers


def _row(date, batch, condition, thread, area_px, avg_diameter_px=20.0):
    return {
        "date": date, "batch": batch, "condition": condition, "thread": thread,
        "area_px": area_px, "avg_diameter_px": avg_diameter_px,
    }


def test_flags_only_the_obvious_outlier_in_a_group_of_six():
    rows = [
        _row("2026-05-11", "8", "Poststretch", "01", 1000),
        _row("2026-05-11", "8", "Poststretch", "02", 1050),
        _row("2026-05-11", "8", "Poststretch", "03", 980),
        _row("2026-05-11", "8", "Poststretch", "04", 1020),
        _row("2026-05-11", "8", "Poststretch", "05", 1010),
        _row("2026-05-11", "8", "Poststretch", "06", 3000),  # ~3x the others
    ]

    flagged = flag_outliers(rows)

    flagged_threads = {r["thread"] for r in flagged if r["flag"]}
    assert flagged_threads == {"06"}
    outlier_row = next(r for r in flagged if r["thread"] == "06")
    assert "area_px" in outlier_row["flag_reason"]


def test_groups_of_three_or_fewer_never_flagged_regardless_of_spread():
    rows = [
        _row("2026-05-11", "8", "Poststretch", "01", 100),
        _row("2026-05-11", "8", "Poststretch", "02", 100),
        _row("2026-05-11", "8", "Poststretch", "03", 100000),  # wild outlier, but group size 3
    ]

    flagged = flag_outliers(rows)

    assert all(not r["flag"] for r in flagged)


def test_outlier_scoped_per_group_not_flagged_globally():
    """A value that's an outlier in one group but normal in another is only flagged where
    it's actually anomalous within its own (date,batch,condition) group."""
    low_group = [
        _row("2026-05-11", "8", "Poststretch", f"{i}", 1000 + i) for i in range(5)
    ]
    high_group = [
        _row("2026-05-12", "8", "Poststretch", f"h{i}", 5000 + i * 20) for i in range(5)
    ]
    # This value (5050) is way outside low_group's tight range, but sits comfortably
    # inside high_group's own spread — it must only ever be evaluated against ITS OWN
    # group, never low_group's.
    normal_in_its_group = _row("2026-05-12", "8", "Poststretch", "hx", 5050)

    flagged = flag_outliers(low_group + high_group + [normal_in_its_group])

    hx = next(r for r in flagged if r["thread"] == "hx")
    assert hx["flag"] is False
    assert all(not r["flag"] for r in flagged if r["date"] == "2026-05-12")


def test_returns_new_list_does_not_mutate_input_rows():
    rows = [_row("2026-05-11", "8", "Poststretch", str(i), 1000 + i) for i in range(5)]
    original_keys = set(rows[0].keys())

    flag_outliers(rows)

    assert set(rows[0].keys()) == original_keys, "input rows must not be mutated"


def test_flag_defaults_false_and_reason_empty_when_no_outliers():
    rows = [_row("2026-05-11", "8", "Poststretch", str(i), 1000 + i) for i in range(5)]

    flagged = flag_outliers(rows)

    assert all(r["flag"] is False for r in flagged)
    assert all(r["flag_reason"] == "" for r in flagged)


def test_module_does_not_import_torch_or_cv2():
    from pathlib import Path
    import validate.outliers as mod

    source = Path(mod.__file__).read_text()
    assert "import torch" not in source
    assert "import cv2" not in source
