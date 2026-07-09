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

from segment.segment_export import _derive_metadata, export_folder


def _write_photo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((10, 10, 3), 100, dtype=np.uint8)).save(path)


def _accepting_click_loop(seen: list) -> callable:
    def _loop(predictor, image_rgb, on_accept, photo_path=None):
        seen.append(image_rgb.shape)
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_accept(mask)

    return _loop


def _raising_click_loop(predictor, image_rgb, on_accept, photo_path=None):
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
        prompt_more_threads=lambda name: False,
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


def test_on_accept_supports_multiple_masks_per_photo_via_click_loop_return_contract(data_root):
    """A nested-tree photo with no thread guess: two accepts on the same photo (simulated by
    a fake click_loop that calls on_accept twice, honoring its reclick-vs-advance return
    value like the real click_loop does) must produce two independent, distinctly-stemmed
    masks — not a collision or a silent overwrite."""
    tree_root = data_root.parent / "input"
    root = tree_root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26"
    photo = root / "IMG_0001.JPG"
    _write_photo(photo)

    thread_values = ["01", "02"]
    accept_count = {"n": 0}

    def _next_thread(name, guess):
        value = thread_values[accept_count["n"]]
        return value

    def _more_threads(name):
        # Reclick after the first accept, advance after the second.
        return accept_count["n"] == 0

    def _two_accept_click_loop(predictor, image_rgb, on_accept, photo_path=None):
        for i in range(2):
            accept_count["n"] = i
            mask = np.zeros(image_rgb.shape[:2], dtype=bool)
            mask[2:5, 2:5] = True
            advance = on_accept(mask)
            if advance:
                break

    manifest = export_folder(
        input_dir=root,
        masks_dir=data_root / "masks",
        qc_dir=data_root / "qc",
        predictor=None,
        click_loop=_two_accept_click_loop,
        nextcloud_root=tree_root,
        condition="PreStretch",
        prompt_thread=_next_thread,
        prompt_more_threads=_more_threads,
    )

    stems = [o["stem"] for o in manifest["outputs"]]
    assert len(stems) == 2
    assert len(set(stems)) == 2, "two masks on one photo must not collide on the same stem"
    assert all(o["action"] == "written" for o in manifest["outputs"])


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


# --- _derive_metadata: --date/--batch as a real last-resort fallback ----------------------


def test_derive_metadata_falls_back_to_explicit_date_and_batch_when_unparseable(tmp_path):
    """A photo whose path matches none of the parsers must still resolve when --date/--batch
    are given explicitly — this is exactly what the function's own error message tells the
    user to do; it must not raise again on retry (the bug this test guards against)."""
    unparseable = tmp_path / "completely_flat_no_date_folder" / "photo.JPG"
    unparseable.parent.mkdir(parents=True)
    unparseable.touch()

    meta = _derive_metadata(unparseable, nextcloud_root=None, date="05-11-26", batch="8", condition="PostStretch")

    assert meta.date.isoformat() == "2026-05-11"
    assert meta.batch == "8"
    assert meta.condition == "PostStretch"


def test_derive_metadata_raises_clearly_on_malformed_explicit_date(tmp_path):
    unparseable = tmp_path / "flat_no_date" / "photo.JPG"
    unparseable.parent.mkdir(parents=True)
    unparseable.touch()

    with pytest.raises(ValueError, match="MM-DD-YY"):
        _derive_metadata(unparseable, nextcloud_root=None, date="not-a-date", batch=None, condition=None)


def test_derive_metadata_still_raises_when_nothing_at_all_is_available(tmp_path):
    unparseable = tmp_path / "flat_no_date" / "photo.JPG"
    unparseable.parent.mkdir(parents=True)
    unparseable.touch()

    with pytest.raises(ValueError):
        _derive_metadata(unparseable, nextcloud_root=None, date=None, batch=None, condition=None)
