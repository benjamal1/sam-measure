import numpy as np

from segment.mask_edit import erase_region


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


def test_mask_edit_does_not_import_torch_or_cv2():
    import segment.mask_edit as mod
    from pathlib import Path

    source = Path(mod.__file__).read_text()
    assert "import torch" not in source
    assert "import cv2" not in source
