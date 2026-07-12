from pathlib import Path

from scripts.organize_by_condition import organize_folder, plan_organize


def _touch(path: Path) -> None:
    path.write_bytes(b"fake png bytes")


def test_plan_organize_groups_by_condition_and_batch(tmp_path):
    source = tmp_path / "qc"
    source.mkdir()
    _touch(source / "2025-08-04_batch3_prestretch_thread5.11_overlay.png")
    _touch(source / "2025-08-05_batch3_poststretch_thread5.11_overlay.png")

    plan = plan_organize(source)

    dest_rels = {str(p["dest_rel"]) for p in plan}
    assert "prestretch/batch3/2025-08-04_batch3_prestretch_thread5.11_overlay.png" in dest_rels
    assert "poststretch/batch3/2025-08-05_batch3_poststretch_thread5.11_overlay.png" in dest_rels


def test_plan_organize_reports_unparseable_stem_without_aborting(tmp_path):
    source = tmp_path / "qc"
    source.mkdir()
    _touch(source / "not_a_canonical_stem.png")
    _touch(source / "2025-08-04_batch3_prestretch_thread5.11_overlay.png")

    plan = plan_organize(source)

    errors = [p for p in plan if p["error"]]
    ok = [p for p in plan if p["dest_rel"] is not None]
    assert len(errors) == 1
    assert len(ok) == 1


def test_organize_folder_dry_run_writes_nothing(tmp_path):
    source = tmp_path / "qc"
    source.mkdir()
    _touch(source / "2025-08-04_batch3_prestretch_thread5.11_overlay.png")
    out_dir = tmp_path / "qc_by_condition"

    organize_folder(source, out_dir, dry_run=True)

    assert not out_dir.exists()


def test_organize_folder_apply_copies_and_preserves_source(tmp_path):
    source = tmp_path / "qc"
    source.mkdir()
    src_file = source / "2025-08-04_batch3_prestretch_thread5.11_overlay.png"
    _touch(src_file)
    out_dir = tmp_path / "qc_by_condition"

    organize_folder(source, out_dir, dry_run=False)

    dest = out_dir / "prestretch" / "batch3" / src_file.name
    assert dest.exists()
    assert src_file.exists()  # source is never touched


def test_organize_folder_mirrors_deletions_on_rerun(tmp_path):
    source = tmp_path / "qc"
    source.mkdir()
    keep = source / "2025-08-04_batch3_prestretch_thread5.11_overlay.png"
    gone = source / "2025-08-04_batch3_prestretch_thread5.12_overlay.png"
    _touch(keep)
    _touch(gone)
    out_dir = tmp_path / "qc_by_condition"

    organize_folder(source, out_dir, dry_run=False)
    assert (out_dir / "prestretch" / "batch3" / gone.name).exists()

    gone.unlink()  # simulate "flagged for redo, deleted upstream"
    organize_folder(source, out_dir, dry_run=False)

    assert (out_dir / "prestretch" / "batch3" / keep.name).exists()
    assert not (out_dir / "prestretch" / "batch3" / gone.name).exists()
