import numpy as np
from PIL import Image

from scripts.migrate_condition_thread_split import apply_migration, plan_migration


def _write_mask(masks_dir, stem):
    masks_dir.mkdir(parents=True, exist_ok=True)
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:15, 5:15] = True
    Image.fromarray((mask.astype(np.uint8)) * 255).save(masks_dir / f"{stem}.png")


def test_plan_migration_splits_letters_thread_label(tmp_path):
    masks_dir = tmp_path / "masks"
    _write_mask(masks_dir, "2026-05-03_batch9_Poststretch_threadHL1")

    plan = plan_migration(masks_dir)

    assert len(plan) == 1
    assert plan[0]["old_stem"] == "2026-05-03_batch9_Poststretch_threadHL1"
    assert plan[0]["new_stem"] == "2026-05-03_batch9_HL_thread1"
    assert plan[0]["error"] is None


def test_plan_migration_leaves_already_migrated_masks_untouched(tmp_path):
    masks_dir = tmp_path / "masks"
    _write_mask(masks_dir, "2026-05-03_batch9_HL_thread1")

    plan = plan_migration(masks_dir)

    assert plan == []


def test_plan_migration_leaves_legacy_decimal_thread_untouched(tmp_path):
    masks_dir = tmp_path / "masks"
    _write_mask(masks_dir, "2025-08-03_thread5.11")

    plan = plan_migration(masks_dir)

    assert plan == []


def test_plan_migration_defaults_letters_only_label_to_thread_1(tmp_path):
    masks_dir = tmp_path / "masks"
    _write_mask(masks_dir, "2026-05-03_batch9_Poststretch_threadMM")

    plan = plan_migration(masks_dir)

    assert len(plan) == 1
    assert plan[0]["new_stem"] == "2026-05-03_batch9_MM_thread1"


def test_plan_migration_flags_collision_and_does_not_produce_a_silent_overwrite(tmp_path):
    masks_dir = tmp_path / "masks"
    # Two different old stems that would both migrate to the same new stem.
    _write_mask(masks_dir, "2026-05-03_batch9_Poststretch_threadHL1")
    _write_mask(masks_dir, "2026-05-03_batch9_Prestretch_threadHL1")

    plan = plan_migration(masks_dir)

    errors = [p for p in plan if p["error"]]
    assert len(errors) >= 1
    assert "collision" in errors[0]["error"]


def test_apply_migration_renames_mask_and_qc_files(tmp_path):
    masks_dir = tmp_path / "masks"
    qc_dir = tmp_path / "qc"
    old_stem = "2026-05-03_batch9_Poststretch_threadHL1"
    _write_mask(masks_dir, old_stem)
    qc_dir.mkdir(parents=True, exist_ok=True)
    (qc_dir / f"{old_stem}_overlay.png").write_bytes(b"fake overlay bytes")
    (qc_dir / f"{old_stem}_skeleton.png").write_bytes(b"fake skeleton bytes")

    plan = plan_migration(masks_dir)
    apply_migration(masks_dir, qc_dir, plan)

    new_stem = "2026-05-03_batch9_HL_thread1"
    assert (masks_dir / f"{new_stem}.png").exists()
    assert not (masks_dir / f"{old_stem}.png").exists()
    assert (qc_dir / f"{new_stem}_overlay.png").exists()
    assert (qc_dir / f"{new_stem}_skeleton.png").exists()
    assert not (qc_dir / f"{old_stem}_overlay.png").exists()


def test_apply_migration_skips_collision_entries_leaves_originals_in_place(tmp_path):
    masks_dir = tmp_path / "masks"
    stem_a = "2026-05-03_batch9_Poststretch_threadHL1"
    stem_b = "2026-05-03_batch9_Prestretch_threadHL1"
    _write_mask(masks_dir, stem_a)
    _write_mask(masks_dir, stem_b)

    plan = plan_migration(masks_dir)
    apply_migration(masks_dir, masks_dir, plan)

    # Neither original should be renamed away — collision must block both.
    assert (masks_dir / f"{stem_a}.png").exists()
    assert (masks_dir / f"{stem_b}.png").exists()
