"""Recursive folder walk + manual condition/thread override coverage for export_folder.

Real photo pixel content is irrelevant here — these tests exercise discovery/ruler-exclusion
and the metadata-resolution seam (explicit override > path-parsed guess > interactive prompt),
not SAM2 inference. click_loop is stubbed via DI, matching the existing test_idempotent_export.py
pattern, so no matplotlib/display or real segmentation is invoked.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from segment.segment_export import export_folder


def _write_photo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((10, 10, 3), 100, dtype=np.uint8)).save(path)


def _accepting_click_loop(seen: list) -> callable:
    def _loop(predictor, image_rgb, on_accept):
        seen.append(image_rgb.shape)
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_accept(mask)

    return _loop


def _raising_click_loop(predictor, image_rgb, on_accept):
    raise AssertionError("click_loop must not be invoked in this test")


def test_export_folder_recursively_discovers_nested_tree_and_skips_ruler(data_root):
    root = data_root.parent / "input" / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26"
    _write_photo(root / "IMG_0001.JPG")
    _write_photo(root / "IMG_0002.JPG")
    _write_photo(root / "ruler_04-25-26.JPG")
    _write_photo(root / "Ruler_lowercase.JPG")

    def _thread_by_name(photo_name: str, guess) -> str:
        return "01" if "0001" in photo_name else "02"

    seen: list = []
    manifest = export_folder(
        input_dir=data_root.parent / "input",
        masks_dir=data_root / "masks",
        qc_dir=data_root / "qc",
        predictor=None,
        click_loop=_accepting_click_loop(seen),
        nextcloud_root=data_root.parent / "input",
        condition="PreStretch",
        prompt_thread=_thread_by_name,
    )

    # 2 distinct thread photos processed (ruler_*/Ruler_* excluded regardless of case).
    assert len(seen) == 2
    outputs = manifest["outputs"]
    assert len(outputs) == 2
    assert all(o["action"] == "written" for o in outputs)
    assert {o["stem"] for o in outputs} == {
        "2026-04-25_batch8_prestretch_thread01",
        "2026-04-25_batch8_prestretch_thread02",
    }


def test_export_folder_discovers_multi_level_nested_tree(data_root):
    base = data_root.parent / "input"
    _write_photo(base / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0001.JPG")
    _write_photo(base / "Poststretch" / "Batch 9 05-01-26" / "D2 05-03-26" / "IMG_0002.JPG")

    seen: list = []
    manifest = export_folder(
        input_dir=base,
        masks_dir=data_root / "masks",
        qc_dir=data_root / "qc",
        predictor=None,
        click_loop=_accepting_click_loop(seen),
        nextcloud_root=base,
        condition="Whatever",
        thread="01",
    )

    assert len(seen) == 2
    assert len(manifest["outputs"]) == 2


def test_manual_condition_and_thread_override_wins_over_path_guess(data_root):
    """Nested path-parsing would guess condition='PreStretch' and leave thread unset —
    an explicit override must win over both (EXPT-01 revised: manual entry authoritative)."""
    root = data_root.parent / "input"
    nextcloud_root = root
    photo = root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0001.JPG"
    _write_photo(photo)

    seen: list = []
    manifest = export_folder(
        input_dir=root,
        masks_dir=data_root / "masks",
        qc_dir=data_root / "qc",
        predictor=None,
        click_loop=_accepting_click_loop(seen),
        nextcloud_root=nextcloud_root,
        condition="Poststretch",  # disagrees with the "PreStretch" folder the photo lives in
        thread="99",
    )

    stem = manifest["outputs"][0]["stem"]
    assert "poststretch" in stem
    assert "thread99" in stem
    assert "prestretch" not in stem


def test_export_folder_flat_legacy_thread_guess_used_without_prompting_when_no_override(data_root, monkeypatch):
    """Preserves pre-existing EXPT-04 behavior: a flat-legacy photo's filename-derived thread
    is used directly (no interactive prompt) when no explicit override is supplied."""
    root = data_root.parent / "input" / "08-03-25"
    _write_photo(root / "5.11.JPG")

    def _hang(*a, **k):
        raise AssertionError("must not prompt when a path-derived thread guess is available")

    monkeypatch.setattr("builtins.input", _hang)

    seen: list = []
    manifest = export_folder(
        input_dir=root,
        masks_dir=data_root / "masks",
        qc_dir=data_root / "qc",
        predictor=None,
        click_loop=_accepting_click_loop(seen),
    )

    assert len(seen) == 1
    assert "thread5.11" in manifest["outputs"][0]["stem"]


def test_export_folder_skip_already_exported_still_works_over_recursive_tree(data_root):
    root = data_root.parent / "input" / "08-03-25"
    _write_photo(root / "5.11.JPG")

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"

    # First call: writes the mask.
    export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_accepting_click_loop([]),
    )

    # Second call: must skip, never touching click_loop.
    manifest = export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_raising_click_loop,
    )

    assert manifest["outputs"][0]["action"] == "skipped"
