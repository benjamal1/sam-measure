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


def test_clean_mask_folder_dry_run_reports_and_writes_nothing(tmp_path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    out_dir = tmp_path / "masks_cleaned"
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    mask[10:20, 10:30] = True
    path = masks_dir / "test.png"
    Image.fromarray((mask.astype(np.uint8)) * 255).save(path)

    results = clean_mask_folder(masks_dir, out_dir, dry_run=True)

    assert len(results) == 1
    assert results[0]["file"] == "test.png"
    assert results[0]["pixels_removed"] == 200

    # Original untouched, and out_dir isn't even created in dry-run mode.
    reloaded = np.array(Image.open(path).convert("L")) > 127
    assert np.array_equal(reloaded, mask)
    assert not out_dir.exists()


def test_clean_mask_folder_apply_writes_cleaned_copy_leaves_original_untouched(tmp_path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    out_dir = tmp_path / "masks_cleaned"
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    mask[10:20, 10:30] = True
    path = masks_dir / "test.png"
    Image.fromarray((mask.astype(np.uint8)) * 255).save(path)

    results = clean_mask_folder(masks_dir, out_dir, dry_run=False)

    assert len(results) == 1
    cleaned = np.array(Image.open(out_dir / "test.png").convert("L")) > 127
    assert cleaned.sum() == 2000
    assert not cleaned[10:20, 10:30].any()

    # Original in masks_dir must be completely untouched — resume/idempotency depends on this.
    original = np.array(Image.open(path).convert("L")) > 127
    assert np.array_equal(original, mask)


def test_clean_mask_folder_copies_already_clean_masks_verbatim_too(tmp_path):
    """out_dir must end up with EVERY mask (measure_masks needs the full set), not just the
    ones that had stray blobs to remove."""
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    out_dir = tmp_path / "masks_cleaned"
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True
    Image.fromarray((mask.astype(np.uint8)) * 255).save(masks_dir / "clean.png")

    results = clean_mask_folder(masks_dir, out_dir, dry_run=False)

    assert results == []  # nothing needed cleaning...
    assert (out_dir / "clean.png").exists()  # ...but it's still copied to out_dir


def test_clean_mask_folder_removes_stale_out_dir_files_no_longer_in_source(tmp_path):
    """Delete-a-mask-and-rerun safety: if a mask was removed from masks_dir (flagged for
    redo), its stale leftover copy in out_dir must be deleted too — otherwise a deleted
    mask's old measurements would keep lingering in out_dir forever."""
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    out_dir = tmp_path / "masks_cleaned"
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True

    Image.fromarray((mask.astype(np.uint8)) * 255).save(masks_dir / "keep.png")
    Image.fromarray((mask.astype(np.uint8)) * 255).save(masks_dir / "to_delete.png")
    clean_mask_folder(masks_dir, out_dir, dry_run=False)
    assert (out_dir / "to_delete.png").exists()

    (masks_dir / "to_delete.png").unlink()  # simulate "flagged for redo, deleted"

    clean_mask_folder(masks_dir, out_dir, dry_run=False)

    assert (out_dir / "keep.png").exists()
    assert not (out_dir / "to_delete.png").exists()


def test_clean_mask_folder_dry_run_never_removes_stale_files(tmp_path):
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()
    out_dir = tmp_path / "masks_cleaned"
    mask = np.zeros((120, 140), dtype=bool)
    mask[50:70, 20:120] = True

    Image.fromarray((mask.astype(np.uint8)) * 255).save(masks_dir / "to_delete.png")
    clean_mask_folder(masks_dir, out_dir, dry_run=False)
    (masks_dir / "to_delete.png").unlink()

    clean_mask_folder(masks_dir, out_dir, dry_run=True)

    assert (out_dir / "to_delete.png").exists()  # dry-run must not delete anything
