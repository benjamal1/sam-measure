import hashlib
import shutil

import numpy as np
from PIL import Image

from segment.export import export_mask, make_overlay


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_export_mask_writes_mask_and_overlay_and_leaves_source_untouched(tmp_path):
    source = tmp_path / "source.jpg"
    Image.fromarray(np.full((50, 60, 3), 128, dtype=np.uint8)).save(source)
    before_hash = _hash(source)

    mask = np.zeros((50, 60), dtype=bool)
    mask[10:20, 10:20] = True
    image_rgb = np.array(Image.open(source).convert("RGB"))

    data_root = tmp_path / "data"
    mask_path, overlay_path = export_mask(
        mask, image_rgb, stem="2025-08-03_thread5.11",
        masks_dir=data_root / "masks", qc_dir=data_root / "qc",
    )

    assert mask_path.exists()
    assert overlay_path.exists()
    assert mask_path.stat().st_size > 0
    assert overlay_path.stat().st_size > 0
    assert _hash(source) == before_hash, "source photo must remain byte-identical (EXPT-02)"

    written_mask = np.array(Image.open(mask_path))
    assert written_mask.max() > 0


def test_export_mask_paths_resolve_under_data_root(tmp_path):
    data_root = tmp_path / "data"
    mask = np.zeros((30, 30), dtype=bool)
    mask[5:10, 5:10] = True
    image_rgb = np.full((30, 30, 3), 200, dtype=np.uint8)

    mask_path, overlay_path = export_mask(
        mask, image_rgb, stem="stem", masks_dir=data_root / "masks", qc_dir=data_root / "qc",
    )

    assert data_root in mask_path.parents
    assert data_root in overlay_path.parents


def test_make_overlay_returns_nonempty_image():
    mask = np.zeros((40, 40), dtype=bool)
    mask[10:20, 10:20] = True
    image_rgb = np.full((40, 40, 3), 100, dtype=np.uint8)

    overlay = make_overlay(image_rgb, mask)

    assert overlay.shape[:2] == (40, 40)
    assert overlay.size > 0
