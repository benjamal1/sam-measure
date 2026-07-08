import numpy as np
import pandas as pd
import pytest
from PIL import Image

from measure.measure_masks import measure_folder, measure_mask


def test_measure_mask_strip_returns_known_area_and_width(synthetic_strip_mask):
    result = measure_mask(synthetic_strip_mask)

    assert result["area_px"] == 2000
    assert result["avg_diameter_px"] == pytest.approx(20.0, abs=1.5)
    assert result["stdev_px"] == pytest.approx(0.0, abs=1.0)


def test_measure_mask_empty_raises_value_error():
    empty = np.zeros((50, 50), dtype=bool)

    with pytest.raises(ValueError):
        measure_mask(empty)


def test_measure_mask_tapered_strip_not_bounding_box():
    """A tapered strip's measured mean must lie strictly between its min and max true widths —
    proves per-point skeleton sampling, not a single bounding-box/minAreaRect width."""
    mask = np.zeros((120, 140), dtype=bool)
    min_width, max_width = 10, 30
    for col in range(20, 120):
        t = (col - 20) / (120 - 20)
        width = int(min_width + t * (max_width - min_width))
        center = 60
        mask[center - width // 2 : center + width // 2, col] = True

    result = measure_mask(mask)

    assert min_width < result["avg_diameter_px"] < max_width


def test_measure_mask_frayed_ends_still_measures_interior_width():
    """Endpoint trimming: frayed/irregular ends shouldn't skew the average away from the
    true interior width."""
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    # Fray the very ends with narrow spurs
    mask[55:65, 15:20] = True
    mask[58:62, 5:15] = True

    result = measure_mask(mask)

    assert result["avg_diameter_px"] == pytest.approx(20.0, abs=3.0)


def test_measure_mask_does_not_import_torch_or_gui_cv2():
    import measure.measure_masks as mod
    from pathlib import Path

    source = Path(mod.__file__).read_text()
    assert "import torch" not in source
    assert "cv2.imshow" not in source


def test_measure_folder_writes_schema_exact_csv(tmp_path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    out_csv = tmp_path / "csv" / "measurements.csv"

    for stem in ["2026-05-11_batch8_poststretch_thread05", "2025-08-03_thread5.11"]:
        mask = np.zeros((120, 140), dtype=bool)
        mask[50:70, 20:120] = True
        Image.fromarray((mask * 255).astype(np.uint8)).save(masks_dir / f"{stem}.png")

    df = measure_folder(masks_dir, out_csv)

    assert out_csv.exists()
    written = pd.read_csv(out_csv)
    assert list(written.columns) == [
        "source_path", "date", "batch", "condition", "thread",
        "area_px", "avg_diameter_px", "stdev_px",
    ]
    assert len(written) == 2
    assert (written["area_px"] > 0).all()
    assert (written["avg_diameter_px"] > 0).all()
    assert set(written["date"]) == {"2026-05-11", "2025-08-03"}
    assert len(df) == 2
