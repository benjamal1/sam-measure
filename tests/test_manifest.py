import json

from pipeline.manifest import add_calibration, add_error, add_input, add_output, new_manifest, write_manifest


def test_new_manifest_has_empty_lists():
    m = new_manifest("segment", "2026-07-08T00:00:00Z")
    assert m["run_kind"] == "segment"
    assert m["inputs"] == []
    assert m["outputs"] == []
    assert m["calibration"] == []
    assert m["errors"] == []


def test_add_input_appends_and_does_not_mutate_original():
    m = new_manifest("segment", "2026-07-08T00:00:00Z")
    m2 = add_input(m, "photo.jpg")

    assert len(m["inputs"]) == 0
    assert len(m2["inputs"]) == 1
    assert m2["inputs"][0]["source_path"] == "photo.jpg"


def test_add_output_records_skipped_action():
    m = new_manifest("segment", "2026-07-08T00:00:00Z")
    m2 = add_output(m, stem="2025-08-03_thread5.11", action="skipped", mask_path="a.png", qc_path="b.png")

    assert m2["outputs"][0]["action"] == "skipped"
    assert m2["outputs"][0]["stem"] == "2025-08-03_thread5.11"


def test_add_calibration_records_factor_per_thread():
    m = new_manifest("run", "2026-07-08T00:00:00Z")
    m2 = add_calibration(m, thread="5.11", date="2025-08-03", batch="", px_per_cm=8000.0, ruler_source_path="ruler.jpg")

    assert m2["calibration"][0]["thread"] == "5.11"
    assert m2["calibration"][0]["px_per_cm"] == 8000.0


def test_add_error_appends_record():
    m = new_manifest("run", "2026-07-08T00:00:00Z")
    m2 = add_error(m, stage="measure", message="bad mask", source_path="x.png")

    assert m2["errors"][0]["stage"] == "measure"
    assert m2["errors"][0]["message"] == "bad mask"


def test_write_manifest_creates_json_that_round_trips(tmp_path):
    m = new_manifest("run", "2026-07-08T00:00:00Z")
    m = add_input(m, "photo.jpg")
    m = add_output(m, stem="stem1", action="written", mask_path="m.png", qc_path="q.png")
    m = add_calibration(m, thread="5.11", date="2025-08-03", batch="", px_per_cm=8000.0, ruler_source_path="r.jpg")

    path = write_manifest(m, tmp_path)

    assert path.exists()
    assert path.parent == tmp_path
    assert path.name.startswith("manifest_")
    loaded = json.loads(path.read_text())
    assert loaded["inputs"][0]["source_path"] == "photo.jpg"
    assert loaded["outputs"][0]["action"] == "written"
    assert loaded["calibration"][0]["px_per_cm"] == 8000.0


def test_manifest_module_is_pure_no_torch_cv2_sam2():
    import pipeline.manifest as mod
    from pathlib import Path

    source = Path(mod.__file__).read_text()
    assert "import torch" not in source
    assert "import cv2" not in source
    assert "from sam2" not in source
