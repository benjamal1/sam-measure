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


def test_measure_mask_returns_finite_nonnegative_mad_px(synthetic_strip_mask):
    result = measure_mask(synthetic_strip_mask)

    assert "mad_px" in result
    assert result["mad_px"] >= 0.0
    assert np.isfinite(result["mad_px"])


def test_measure_mask_does_not_remove_or_reorder_existing_keys(synthetic_strip_mask):
    result = measure_mask(synthetic_strip_mask)

    assert set(result.keys()) == {"area_px", "avg_diameter_px", "stdev_px", "mad_px"}


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
        "area_px", "avg_diameter_px", "stdev_px", "mad_px",
    ]
    assert len(written) == 2
    assert (written["area_px"] > 0).all()
    assert (written["avg_diameter_px"] > 0).all()
    assert (written["mad_px"] >= 0).all()
    assert set(written["date"]) == {"2026-05-11", "2025-08-03"}
    assert len(df) == 2


# --- measure_folder isolates a bad mask instead of aborting the whole batch ----------------


def test_measure_folder_skips_empty_mask_but_measures_the_rest(tmp_path, capsys):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    out_csv = tmp_path / "measurements.csv"

    good = np.zeros((50, 50), dtype=bool)
    good[10:30, 10:15] = True
    Image.fromarray((good.astype("uint8")) * 255).save(masks_dir / "2026-05-11_thread01.png")

    empty = np.zeros((50, 50), dtype=bool)  # fully empty — measure_mask raises ValueError on this
    Image.fromarray((empty.astype("uint8")) * 255).save(masks_dir / "2026-05-11_thread02.png")

    df = measure_folder(masks_dir, out_csv)

    assert len(df) == 1  # the bad mask was skipped, not fatal to the run
    assert df.iloc[0]["thread"] == "01"
    assert "skipping unmeasurable mask" in capsys.readouterr().out


# --- measure_mask keeps only the largest connected component -------------------------------


def test_measure_mask_ignores_a_second_sizable_stray_blob():
    """A second disconnected region well above remove_small_objects' 19px threshold (e.g. a
    mis-segmented fragment elsewhere in frame) must not be summed into area_px or interleaved
    into the skeleton/diameter calc alongside the real thread."""
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True   # the real thread: 20x100 = 2000px
    mask[10:20, 10:30] = True    # a stray blob: 10x20 = 200px — well above the 19px speck cutoff

    result = measure_mask(mask)

    # If the stray blob were included, area_px would be ~2200 and the skeleton would span
    # two disconnected pieces, corrupting avg_diameter_px. Only the larger region should count.
    assert result["area_px"] < 2100
    assert result["area_px"] > 1900


def test_measure_mask_single_component_unaffected_by_stray_blob_guard():
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True

    result = measure_mask(mask)

    assert result["area_px"] == 2000


# --- skeleton path ordering: orientation- and curvature-robust, real arc length ------------


def test_measure_mask_diagonal_straight_strip_same_as_horizontal():
    """A straight strip at 45 degrees must measure the same width as an equivalent horizontal
    strip — orientation must not matter now that ordering walks skeleton connectivity."""
    from scipy.ndimage import rotate

    horiz = np.zeros((120, 140), dtype=bool)
    horiz[50:70, 20:120] = True  # 20px wide, 100px long

    diag = rotate(horiz.astype(float), 45, reshape=True, order=1) > 0.5

    horiz_result = measure_mask(horiz)
    diag_result = measure_mask(diag)

    assert diag_result["avg_diameter_px"] == pytest.approx(horiz_result["avg_diameter_px"], rel=0.25)


def test_measure_mask_l_shaped_curve_does_not_scramble_ordering():
    """An L-shaped (curved) thread must still measure a sane uniform width — a naive x/y
    axis-sort would scramble ordering on the vertical leg; path-walking must not."""
    mask = np.zeros((150, 150), dtype=bool)
    width = 16
    mask[20:100, 30:30 + width] = True  # vertical leg
    mask[100 - width:100, 30:120] = True  # horizontal leg (L-shape corner)

    result = measure_mask(mask)

    assert 10 < result["avg_diameter_px"] < 22
    assert result["stdev_px"] < 8  # uniform width along both legs; should not blow up from bad ordering


def test_measure_mask_percentage_trim_removes_end_fraction_of_arc_length_not_point_count():
    """endpoint_trim_fraction=0.5 on a strongly tapered strip should average close to the
    TRUE middle-section width, regardless of total skeleton point count."""
    mask = np.zeros((120, 220), dtype=bool)
    # Narrow ends (width 4), wide middle (width 40) — extreme taper so trim fraction matters.
    for col in range(20, 200):
        t = (col - 20) / (200 - 20)
        # peak in the middle, narrow at both ends
        width = int(4 + 36 * (1 - abs(2 * t - 1)))
        center = 60
        mask[center - width // 2: center + width // 2, col] = True

    default_result = measure_mask(mask, endpoint_trim_fraction=0.05)
    heavy_trim_result = measure_mask(mask, endpoint_trim_fraction=0.45)

    # Trimming more aggressively should pull the average UP toward the wide middle peak,
    # away from the narrow ends included by the lighter trim.
    assert heavy_trim_result["avg_diameter_px"] > default_result["avg_diameter_px"]


def test_measure_mask_spur_from_boundary_noise_excluded_from_backbone():
    """A small branch spur off the main skeleton (from jagged boundary noise) must not be
    walked as part of the measured backbone path."""
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True  # main strip, 20px wide, 100px long
    mask[45:50, 60:64] = True   # small bump on the top edge mid-strip -> skeletonize spur

    result = measure_mask(mask)

    # Spur should not meaningfully distort the average away from the true ~20px width.
    assert result["avg_diameter_px"] == pytest.approx(20.0, abs=4.0)


# --- skeleton QC rendering -------------------------------------------------------------


def test_render_skeleton_qc_returns_rgb_image_matching_mask_shape():
    from measure.measure_masks import render_skeleton_qc

    mask = np.zeros((80, 100), dtype=bool)
    mask[30:50, 10:90] = True

    qc = render_skeleton_qc(mask, endpoint_trim_fraction=0.1)

    assert qc.shape == (80, 100, 3)
    assert qc.dtype == np.uint8


def test_render_skeleton_qc_marks_trimmed_and_kept_regions_differently():
    from measure.measure_masks import render_skeleton_qc

    mask = np.zeros((80, 200), dtype=bool)
    mask[30:50, 10:190] = True

    qc = render_skeleton_qc(mask, endpoint_trim_fraction=0.2)

    # Distinct colors must appear for kept vs trimmed skeleton pixels (not a uniform image).
    unique_colors = {tuple(c) for c in qc.reshape(-1, 3)}
    assert len(unique_colors) >= 3  # background + kept-skeleton color + trimmed-skeleton color


def test_measure_folder_writes_skeleton_qc_images(tmp_path):
    from measure.measure_masks import measure_folder

    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    qc_dir = tmp_path / "qc"
    stem = "2025-08-03_thread5.11"
    mask = np.zeros((80, 100), dtype=bool)
    mask[30:50, 10:90] = True
    Image.fromarray((mask * 255).astype(np.uint8)).save(masks_dir / f"{stem}.png")

    measure_folder(masks_dir, tmp_path / "measurements.csv", qc_dir=qc_dir)

    assert (qc_dir / f"{stem}_skeleton.png").exists()
