import json

from scripts.flag_for_redo import flag_for_redo


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake png")


def test_flag_for_redo_deletes_mask_and_qc_and_unmarks_photo(tmp_path):
    masks_dir = tmp_path / "masks"
    qc_dir = tmp_path / "qc"
    data_root = tmp_path
    stem = "2025-11-14_batch4_poststretch_threadLH"
    photo = "/photos/IMG_0001.JPG"

    _touch(masks_dir / f"{stem}.png")
    _touch(qc_dir / f"{stem}_overlay.png")
    (data_root / "processed_photos.json").write_text(json.dumps([photo, "/photos/other.JPG"]))

    result = flag_for_redo([stem], photo, masks_dir, qc_dir, data_root)

    assert not (masks_dir / f"{stem}.png").exists()
    assert not (qc_dir / f"{stem}_overlay.png").exists()
    assert result["photo_unmarked"] is True
    remaining = json.loads((data_root / "processed_photos.json").read_text())
    assert photo not in remaining
    assert "/photos/other.JPG" in remaining  # other photos' entries untouched


def test_flag_for_redo_is_safely_rerunnable_on_already_missing_files(tmp_path):
    masks_dir = tmp_path / "masks"
    qc_dir = tmp_path / "qc"
    data_root = tmp_path
    masks_dir.mkdir()
    qc_dir.mkdir()

    result = flag_for_redo(["nonexistent_stem"], "/no/such/photo.JPG", masks_dir, qc_dir, data_root)

    assert result["deleted_masks"] == []
    assert result["photo_unmarked"] is False


def test_flag_for_redo_handles_multiple_stems_for_one_composite_photo(tmp_path):
    masks_dir = tmp_path / "masks"
    qc_dir = tmp_path / "qc"
    data_root = tmp_path
    photo = "/photos/composite.JPG"
    stems = ["date_batch_cond_threadA1", "date_batch_cond_threadA2"]

    for stem in stems:
        _touch(masks_dir / f"{stem}.png")
    (data_root / "processed_photos.json").write_text(json.dumps([photo]))

    result = flag_for_redo(stems, photo, masks_dir, qc_dir, data_root)

    assert len(result["deleted_masks"]) == 2
    assert result["photo_unmarked"] is True


def test_flag_for_redo_missing_processed_photos_json_is_a_noop_not_a_crash(tmp_path):
    masks_dir = tmp_path / "masks"
    qc_dir = tmp_path / "qc"
    data_root = tmp_path  # no processed_photos.json created at all

    result = flag_for_redo(["some_stem"], "/photos/x.JPG", masks_dir, qc_dir, data_root)

    assert result["photo_unmarked"] is False
