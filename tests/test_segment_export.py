"""Recursive folder walk + manual condition/thread override coverage for export_folder.

Real photo pixel content is irrelevant here — these tests exercise discovery/ruler-exclusion
and the metadata-resolution seam (explicit override > path-parsed guess > in-canvas label,
the latter simulated by the fake click_loop calling on_label_submit directly), not SAM2
inference. click_loop is stubbed via DI, matching the existing test_idempotent_export.py
pattern, so no matplotlib/display or real segmentation is invoked.

Labeling itself (condition/thread entry) now happens INSIDE click_loop (an in-canvas
TextBox widget — see test_click_loop.py for that state machine's own coverage) — from
export_folder's point of view, click_loop is a black box that eventually calls
on_label_submit(mask, condition, thread) zero or more times per photo. These fakes simulate
that contract directly instead of the old prompt_thread/prompt_more_threads DI hooks, which
no longer exist (labeling isn't resolved in this module anymore).
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
    """Simulates the legacy fast path: calls on_label_submit ONCE with whatever
    known_condition/known_thread export_folder already resolved (explicit override or a
    flat-legacy filename-derived guess) — used wherever both end up known one way or
    another, matching what the real click_loop's auto-advance fast path would do."""
    def _loop(predictor, image_rgb, on_label_submit, photo_path=None, known_condition=None, known_thread=None):
        seen.append(image_rgb.shape)
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_label_submit(mask, known_condition, known_thread)

    return _loop


def _raising_click_loop(predictor, image_rgb, on_label_submit, photo_path=None, known_condition=None, known_thread=None):
    raise AssertionError("click_loop must not be invoked in this test")


def test_export_folder_recursively_discovers_nested_tree_and_skips_ruler(data_root):
    root = data_root.parent / "input" / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26"
    _write_photo(root / "IMG_0001.JPG")
    _write_photo(root / "IMG_0002.JPG")
    _write_photo(root / "ruler_04-25-26.JPG")
    _write_photo(root / "Ruler_lowercase.JPG")

    seen: list = []

    def _thread_by_name_click_loop(predictor, image_rgb, on_label_submit, photo_path=None,
                                    known_condition=None, known_thread=None):
        seen.append(image_rgb.shape)
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        thread = "01" if "0001" in photo_path.name else "02"
        on_label_submit(mask, known_condition, thread)

    manifest = export_folder(
        input_dir=data_root.parent / "input",
        masks_dir=data_root / "masks",
        qc_dir=data_root / "qc",
        predictor=None,
        click_loop=_thread_by_name_click_loop,
        nextcloud_root=data_root.parent / "input",
        condition="PreStretch",
    )

    # 2 distinct thread photos processed (ruler_*/Ruler_* excluded regardless of case).
    assert len(seen) == 2
    outputs = manifest["outputs"]
    assert len(outputs) == 2
    assert all(o["action"] == "written" for o in outputs)
    assert {o["stem"] for o in outputs} == {
        "2026-04-25_batch8_PreStretch_thread01",
        "2026-04-25_batch8_PreStretch_thread02",
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
    assert "Poststretch" in stem
    assert "thread99" in stem
    assert "Prestretch" not in stem


def test_export_folder_flat_legacy_thread_guess_used_without_prompting_when_no_override(data_root):
    """Preserves pre-existing EXPT-04 behavior: a flat-legacy photo's filename-derived thread
    is passed through as known_thread (no in-canvas label needed) when no explicit override
    is supplied."""
    root = data_root.parent / "input" / "08-03-25"
    _write_photo(root / "5.11.JPG")

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


def test_multiple_labels_per_photo_via_click_loop_calling_on_label_submit_repeatedly(data_root):
    """A nested-tree photo with no thread guess: two on_label_submit calls on the same photo
    (simulated by a fake click_loop that calls it twice, like the real click_loop does across
    two 'a'-then-type-then-Enter cycles before the user finally presses 'n') must produce two
    independent, distinctly-stemmed masks — not a collision or a silent overwrite."""
    tree_root = data_root.parent / "input"
    root = tree_root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26"
    photo = root / "IMG_0001.JPG"
    _write_photo(photo)

    def _two_label_click_loop(predictor, image_rgb, on_label_submit, photo_path=None,
                               known_condition=None, known_thread=None):
        for thread_value in ("01", "02"):
            mask = np.zeros(image_rgb.shape[:2], dtype=bool)
            mask[2:5, 2:5] = True
            on_label_submit(mask, known_condition, thread_value)

    manifest = export_folder(
        input_dir=root,
        masks_dir=data_root / "masks",
        qc_dir=data_root / "qc",
        predictor=None,
        click_loop=_two_label_click_loop,
        nextcloud_root=tree_root,
        condition="PreStretch",
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


# --- photo-level completion tracker: restart must not reopen already-done photos ----------


def test_second_run_skips_already_processed_photo_without_ever_opening_click_loop(data_root):
    """The real-world bug this guards against: a photo whose thread can never be known ahead
    of time (composite/nested, thread always None from path-parsing) must still be skipped
    entirely on a second run — not just its already-exported masks, the WINDOW itself must
    never reopen. Before this fix, every restart reprocessed every such photo from scratch."""
    root = data_root.parent / "input"
    photo = root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0001.JPG"
    _write_photo(photo)

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"

    def _label_thread_01(predictor, image_rgb, on_label_submit, photo_path=None,
                         known_condition=None, known_thread=None):
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_label_submit(mask, known_condition, "01")

    # First run: label the one thread on this photo.
    export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_label_thread_01,
        nextcloud_root=root, condition="PreStretch",
    )

    # Second run ("restart after a fix"): must skip the photo without ever calling click_loop.
    manifest = export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_raising_click_loop,
        nextcloud_root=root, condition="PreStretch",
    )

    assert manifest["outputs"][0]["action"] == "skipped"


def test_force_reprocesses_a_previously_completed_photo(data_root):
    root = data_root.parent / "input"
    photo = root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0001.JPG"
    _write_photo(photo)

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"

    def _label_thread_01(predictor, image_rgb, on_label_submit, photo_path=None,
                         known_condition=None, known_thread=None):
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_label_submit(mask, known_condition, "01")

    export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_label_thread_01,
        nextcloud_root=root, condition="PreStretch",
    )

    seen: list = []

    def _label_thread_01_tracked(predictor, image_rgb, on_label_submit, photo_path=None,
                                  known_condition=None, known_thread=None):
        seen.append(image_rgb.shape)
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_label_submit(mask, known_condition, "01")

    manifest = export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_label_thread_01_tracked,
        nextcloud_root=root, condition="PreStretch", force=True,
    )

    assert len(seen) == 1  # --force reopened the photo despite it being previously completed
    assert manifest["outputs"][0]["action"] == "written"


def test_skipping_a_photo_with_n_also_marks_it_processed(data_root):
    """Pressing 'n' (no thread labeled at all) still counts as a concluded session for that
    photo — it must not reopen every future run either."""
    root = data_root.parent / "input"
    photo = root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0001.JPG"
    _write_photo(photo)

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"

    def _skip_everything_click_loop(predictor, image_rgb, on_label_submit, photo_path=None,
                                     known_condition=None, known_thread=None):
        pass  # simulates pressing 'n' — window closes without ever calling on_label_submit

    export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_skip_everything_click_loop,
        nextcloud_root=root, condition="PreStretch",
    )

    manifest = export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_raising_click_loop,
        nextcloud_root=root, condition="PreStretch",
    )

    assert manifest["outputs"][0]["action"] == "skipped"


# --- 'q' (quit_all) stops the whole export_folder run, not just the current photo ---------


def test_quit_all_stops_processing_remaining_photos(data_root):
    root = data_root.parent / "input"
    photo1 = root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0001.JPG"
    photo2 = root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0002.JPG"
    _write_photo(photo1)
    _write_photo(photo2)

    class _FakeState:
        quit_all = True

    seen: list = []

    def _quit_after_one_photo(predictor, image_rgb, on_label_submit, photo_path=None,
                               known_condition=None, known_thread=None):
        seen.append(photo_path)
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_label_submit(mask, known_condition, "01")
        return _FakeState()

    export_folder(
        input_dir=root, masks_dir=data_root / "masks", qc_dir=data_root / "qc", predictor=None,
        click_loop=_quit_after_one_photo,
        nextcloud_root=root, condition="PreStretch",
    )

    assert len(seen) == 1  # stopped after the first photo, never opened the second


# --- real bug fix: quitting before any accept must NOT mark the photo processed -----------


def test_quit_before_any_accept_does_not_mark_photo_processed(data_root):
    root = data_root.parent / "input"
    photo = root / "PreStretch" / "Batch 8 04-24-26" / "D1 04-25-26" / "IMG_0001.JPG"
    _write_photo(photo)

    masks_dir = data_root / "masks"
    qc_dir = data_root / "qc"

    class _QuitImmediatelyState:
        quit_all = True

    def _quit_without_accepting(predictor, image_rgb, on_label_submit, photo_path=None,
                                 known_condition=None, known_thread=None):
        return _QuitImmediatelyState()  # 'q' pressed before ever clicking/labeling

    export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_quit_without_accepting,
        nextcloud_root=root, condition="PreStretch",
    )

    # Rerun with a click_loop that would raise if invoked — the photo must still be OPEN,
    # i.e. reprocessed, since nothing was ever actually labeled on it last time.
    seen: list = []

    def _label_thread_01(predictor, image_rgb, on_label_submit, photo_path=None,
                         known_condition=None, known_thread=None):
        seen.append(image_rgb.shape)
        mask = np.zeros(image_rgb.shape[:2], dtype=bool)
        mask[2:5, 2:5] = True
        on_label_submit(mask, known_condition, "01")

    export_folder(
        input_dir=root, masks_dir=masks_dir, qc_dir=qc_dir, predictor=None,
        click_loop=_label_thread_01,
        nextcloud_root=root, condition="PreStretch",
    )

    assert len(seen) == 1  # photo was reopened — the bug this test guards against


# --- discovered photos are resolved to a canonical absolute path (relative/absolute mismatch fix) --


def test_discover_photos_resolves_relative_input_dir_to_absolute(tmp_path, monkeypatch):
    """Real bug: the same physical photo got a DIFFERENT string key in processed_photos.json
    depending on whether --input-dir was passed relative or absolute across runs, making an
    already-done photo look unprocessed (or double-recorded) on a later differently-typed run."""
    from segment.segment_export import _discover_photos

    root = tmp_path / "photos"
    _write_photo(root / "IMG_0001.JPG")

    monkeypatch.chdir(tmp_path)
    relative_result = _discover_photos(Path("photos"))
    absolute_result = _discover_photos(root)

    assert relative_result == absolute_result
    assert relative_result[0].is_absolute()
