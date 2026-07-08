import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from segment.export import export_mask
from segment.naming import canonical_stem, parse_flat_path
from segment.segment_export import export_folder

NEXTCLOUD_ROOT_08_04_25 = "/home/bcjamal/Nextcloud/threads daily imaging/08-04-25"


def _real_08_04_25_photos():
    from pathlib import Path
    d = Path(NEXTCLOUD_ROOT_08_04_25)
    if not d.exists():
        pytest.skip(f"real data not found at {d}")
    return sorted(d.glob("*.JPG"))


def _raising_click_loop(predictor, image_rgb, on_accept):
    raise AssertionError("click_loop must not be invoked for an already-exported photo")


def test_export_folder_skips_already_exported_real_photos(data_root):
    photos = _real_08_04_25_photos()
    if not photos:
        pytest.skip("no real photos found in 08-04-25")

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"

    # Pre-seed masks for a subset (first 3 real photos) so they appear already-exported.
    seeded = photos[:3]
    for photo in seeded:
        meta = parse_flat_path(photo)
        stem = canonical_stem(meta, meta.thread)
        mask = np.zeros((10, 10), dtype=bool)
        mask[2:5, 2:5] = True
        image_rgb = np.full((10, 10, 3), 100, dtype=np.uint8)
        export_mask(mask, image_rgb, stem, masks_dir=masks_dir, qc_dir=qc_dir)

    manifest = export_folder(
        input_dir=seeded[0].parent, masks_dir=masks_dir, qc_dir=qc_dir,
        predictor=None, force=False, click_loop=_raising_click_loop,
        photos=seeded,
    )

    skipped_stems = {o["stem"] for o in manifest["outputs"] if o["action"] == "skipped"}
    assert len(skipped_stems) == 3


def test_export_folder_force_invokes_click_loop_for_seeded_photo(data_root):
    photos = _real_08_04_25_photos()
    if not photos:
        pytest.skip("no real photos found in 08-04-25")

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"
    photo = photos[0]
    meta = parse_flat_path(photo)
    stem = canonical_stem(meta, meta.thread)
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 2:5] = True
    image_rgb = np.full((10, 10, 3), 100, dtype=np.uint8)
    export_mask(mask, image_rgb, stem, masks_dir=masks_dir, qc_dir=qc_dir)

    invoked = []

    def _tracking_click_loop(predictor, image_rgb, on_accept):
        invoked.append(True)
        real_shaped_mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        real_shaped_mask[10:20, 10:20] = True
        on_accept(real_shaped_mask)

    manifest = export_folder(
        input_dir=photo.parent, masks_dir=masks_dir, qc_dir=qc_dir,
        predictor=None, force=True, click_loop=_tracking_click_loop,
        photos=[photo],
    )

    assert invoked
    assert manifest["outputs"][0]["action"] == "written"


def test_export_folder_skip_leaves_mask_bytes_unchanged(data_root):
    photos = _real_08_04_25_photos()
    if not photos:
        pytest.skip("no real photos found in 08-04-25")

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"
    photo = photos[0]
    meta = parse_flat_path(photo)
    stem = canonical_stem(meta, meta.thread)
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 2:5] = True
    image_rgb = np.full((10, 10, 3), 100, dtype=np.uint8)
    mask_path, _ = export_mask(mask, image_rgb, stem, masks_dir=masks_dir, qc_dir=qc_dir)
    before_hash = hashlib.sha256(mask_path.read_bytes()).hexdigest()

    export_folder(
        input_dir=photo.parent, masks_dir=masks_dir, qc_dir=qc_dir,
        predictor=None, force=False, click_loop=_raising_click_loop,
        photos=[photo],
    )

    after_hash = hashlib.sha256(mask_path.read_bytes()).hexdigest()
    assert before_hash == after_hash


@pytest.mark.slow
@pytest.mark.integration
def test_run_pipeline_second_call_skips_and_records_manifest(data_root, sample_photo_path, ruler_photo_path):
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from run_pipeline import run

    kwargs = dict(
        photo_path=sample_photo_path,
        click_points=[(2740, 1534)],
        click_labels=[1],
        ruler_path=ruler_photo_path,
        ruler_points=[(0.0, 0.0), (400.0, 0.0)],
        known_cm_span=0.5,
        date="2025-08-03",
        batch="",
        condition="",
        thread="5.11",
        data_root=data_root,
    )

    run(**kwargs)  # first call: writes the mask
    run(**kwargs)  # second call: should skip re-inference

    manifests = sorted((data_root).glob("manifest_*.json"))
    assert len(manifests) == 2
    second = json.loads(manifests[-1].read_text())
    assert second["outputs"][0]["action"] == "skipped"
    assert second["calibration"][0]["px_per_cm"] > 0
