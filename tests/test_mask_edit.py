import numpy as np

from segment.mask_edit import erase_box, erase_region


def test_erase_region_reduces_true_pixel_count():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True
    original_sum = mask.sum()

    result = erase_region(mask, [(50, 50)], radius=8)

    assert result.sum() < original_sum


def test_erase_region_does_not_mutate_input():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True
    original = mask.copy()

    erase_region(mask, [(50, 50)], radius=8)

    assert np.array_equal(mask, original)


def test_erase_region_over_false_pixels_is_noop():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True

    result = erase_region(mask, [(5, 5)], radius=3)

    assert result.sum() == mask.sum()
    assert np.array_equal(result, mask)


def test_erase_region_empty_points_returns_equal_copy():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True

    result = erase_region(mask, [], radius=8)

    assert np.array_equal(result, mask)
    assert result is not mask


def test_erase_box_clears_only_pixels_inside_the_rectangle():
    mask = np.ones((100, 100), dtype=bool)

    result = erase_box(mask, (10, 10), (30, 30))

    assert not result[10:31, 10:31].any()
    assert result[50, 50]  # outside the box, untouched


def test_erase_box_works_with_reversed_corner_order():
    mask = np.ones((100, 100), dtype=bool)

    result = erase_box(mask, (30, 30), (10, 10))  # p2 "before" p1

    assert not result[10:31, 10:31].any()


def test_erase_box_does_not_mutate_input():
    mask = np.ones((100, 100), dtype=bool)
    original = mask.copy()

    erase_box(mask, (10, 10), (30, 30))

    assert np.array_equal(mask, original)


def test_erase_box_degenerate_zero_area_clears_only_the_single_pixel():
    mask = np.ones((100, 100), dtype=bool)

    result = erase_box(mask, (50, 50), (50, 50))

    assert not result[50, 50]
    assert result.sum() == mask.sum() - 1


def test_erase_box_clamps_to_mask_bounds():
    mask = np.ones((20, 20), dtype=bool)

    result = erase_box(mask, (-5, -5), (100, 100))  # way outside bounds either direction

    assert not result.any()


def test_mask_edit_does_not_import_torch_or_cv2():
    import segment.mask_edit as mod
    from pathlib import Path

    source = Path(mod.__file__).read_text()
    assert "import torch" not in source
    assert "import cv2" not in source
