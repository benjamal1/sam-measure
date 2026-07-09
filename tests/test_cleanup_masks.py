import numpy as np
from PIL import Image

from scripts.cleanup_masks import clean_mask, clean_mask_folder


def test_clean_mask_removes_disconnected_stray_blob():
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True   # real thread: 2000px
    mask[10:20, 10:30] = True    # stray blob: 200px

    cleaned, removed = clean_mask(mask)

    assert removed == 200
    assert cleaned.sum() == 2000
    assert not cleaned[10:20, 10:30].any()


def test_clean_mask_single_component_is_noop():
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True

    cleaned, removed = clean_mask(mask)

    assert removed == 0
    assert np.array_equal(cleaned, mask)


def test_clean_mask_empty_is_noop():
    mask = np.zeros((50, 50), dtype=bool)

    cleaned, removed = clean_mask(mask)

    assert removed == 0
    assert not cleaned.any()


def test_clean_mask_does_not_mutate_input():
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    mask[10:20, 10:30] = True
    original = mask.copy()

    clean_mask(mask)

    assert np.array_equal(mask, original)


def test_clean_mask_folder_dry_run_reports_but_does_not_write(tmp_path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    mask[10:20, 10:30] = True
    path = masks_dir / "test.png"
    Image.fromarray((mask.astype(np.uint8)) * 255).save(path)

    results = clean_mask_folder(masks_dir, dry_run=True)

    assert len(results) == 1
    assert results[0]["file"] == "test.png"
    assert results[0]["pixels_removed"] == 200

    # File on disk must be untouched in dry-run mode.
    reloaded = np.array(Image.open(path).convert("L")) > 127
    assert np.array_equal(reloaded, mask)


def test_clean_mask_folder_apply_writes_cleaned_mask(tmp_path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    mask[10:20, 10:30] = True
    path = masks_dir / "test.png"
    Image.fromarray((mask.astype(np.uint8)) * 255).save(path)

    results = clean_mask_folder(masks_dir, dry_run=False)

    assert len(results) == 1
    reloaded = np.array(Image.open(path).convert("L")) > 127
    assert reloaded.sum() == 2000
    assert not reloaded[10:20, 10:30].any()


def test_clean_mask_folder_skips_already_clean_masks(tmp_path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    Image.fromarray((mask.astype(np.uint8)) * 255).save(masks_dir / "clean.png")

    results = clean_mask_folder(masks_dir, dry_run=True)

    assert results == []
