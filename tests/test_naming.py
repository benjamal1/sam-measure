from datetime import date
from pathlib import Path

import pytest

from segment.naming import PhotoMetadata, canonical_stem, parse_flat_path, parse_photo_path, stem_to_fields

NEXTCLOUD_ROOT = Path("/Volumes/LRSResearch/ENG_CVRegenEng_Shared/Group/Data/Benjamin/threads daily imaging")


def test_parse_nested_path_uses_day_folder_date_not_batch_start_date():
    """D-09: canonical Date is the day/measurement-folder date, not the batch-start date."""
    photo = NEXTCLOUD_ROOT / "Batch 8 04-24-26" / "Poststretch" / "D12 05-11-26" / "IMG_8092.JPG"

    meta = parse_photo_path(photo, NEXTCLOUD_ROOT)

    assert meta.batch == "8"
    assert meta.condition == "Poststretch"
    assert meta.day == "12"
    assert meta.date == date(2026, 5, 11)
    assert meta.batch_start_date == date(2026, 4, 24)


def test_parse_nested_path_would_fail_if_batch_date_used_as_date():
    """Explicit guard: a parser that grabs the FIRST date-looking segment is wrong."""
    photo = NEXTCLOUD_ROOT / "Batch 8 04-24-26" / "Poststretch" / "D12 05-11-26" / "IMG_8092.JPG"

    meta = parse_photo_path(photo, NEXTCLOUD_ROOT)

    assert meta.date != date(2026, 4, 24), "date must not be the batch-start date"


def test_parse_nested_path_prestretch_condition():
    photo = NEXTCLOUD_ROOT / "Batch 7 04-15-26" / "PreStretch" / "D1 04-23-26" / "IMG_1234.JPG"

    meta = parse_photo_path(photo, NEXTCLOUD_ROOT)

    assert meta.condition == "PreStretch"
    assert meta.day == "1"
    assert meta.date == date(2026, 4, 23)


def test_parse_photo_path_raises_on_unparseable_path():
    photo = NEXTCLOUD_ROOT / "random_folder" / "weird_name.JPG"

    with pytest.raises(ValueError, match=str(photo).replace("(", r"\(").replace(")", r"\)")):
        parse_photo_path(photo, NEXTCLOUD_ROOT)


def test_parse_photo_path_raises_on_truncated_path():
    photo = NEXTCLOUD_ROOT / "Batch 8 04-24-26" / "IMG_8092.JPG"

    with pytest.raises(ValueError):
        parse_photo_path(photo, NEXTCLOUD_ROOT)


def test_parse_flat_path_legacy_convention():
    photo = Path("/home/bcjamal/Nextcloud/threads daily imaging/08-03-25/5.11.JPG")

    meta = parse_flat_path(photo)

    assert meta.date == date(2025, 8, 3)
    assert meta.thread == "5.11"
    assert meta.batch == ""
    assert meta.condition == ""


def test_canonical_stem_nested_omits_no_segments():
    meta = PhotoMetadata(
        batch="8",
        batch_start_date=date(2026, 4, 24),
        condition="Poststretch",
        day="12",
        date=date(2026, 5, 11),
        thread=None,
        source_path=Path("x"),
    )

    stem = canonical_stem(meta, thread="05")

    assert stem == "2026-05-11_batch8_poststretch_thread05"
    assert "/" not in stem
    assert " " not in stem


def test_canonical_stem_rejects_thread_with_underscore():
    """A human-typed thread number (D-07) containing '_' would corrupt stem_to_fields'
    inverse parsing — must raise loudly instead of silently emitting a broken stem."""
    meta = PhotoMetadata(
        batch="8", batch_start_date=date(2026, 4, 24), condition="Poststretch",
        day="12", date=date(2026, 5, 11), thread=None, source_path=Path("x"),
    )

    with pytest.raises(ValueError):
        canonical_stem(meta, thread="5_11")


def test_canonical_stem_rejects_thread_with_whitespace_or_slash():
    meta = PhotoMetadata(
        batch="8", batch_start_date=date(2026, 4, 24), condition="Poststretch",
        day="12", date=date(2026, 5, 11), thread=None, source_path=Path("x"),
    )

    with pytest.raises(ValueError):
        canonical_stem(meta, thread="5 11")
    with pytest.raises(ValueError):
        canonical_stem(meta, thread="5/11")
    with pytest.raises(ValueError):
        canonical_stem(meta, thread="")


def test_canonical_stem_flat_omits_empty_batch_and_condition():
    meta = PhotoMetadata(
        batch="",
        batch_start_date=None,
        condition="",
        day="",
        date=date(2025, 8, 3),
        thread="5.11",
        source_path=Path("x"),
    )

    stem = canonical_stem(meta, thread="5.11")

    assert stem == "2025-08-03_thread5.11"
    assert "batch" not in stem
    assert "/" not in stem
    assert " " not in stem


def test_stem_to_fields_round_trips_nested():
    stem = "2026-05-11_batch8_poststretch_thread05"

    fields = stem_to_fields(stem)

    assert fields["date"] == "2026-05-11"
    assert fields["batch"] == "8"
    assert fields["condition"] == "poststretch"
    assert fields["thread"] == "05"


def test_stem_to_fields_round_trips_flat():
    stem = "2025-08-03_thread5.11"

    fields = stem_to_fields(stem)

    assert fields["date"] == "2025-08-03"
    assert fields.get("batch", "") == ""
    assert fields["thread"] == "5.11"


# --- canonical_stem validates condition/batch, not just thread (silent-corruption fix) ----


def _meta(**overrides):
    base = dict(
        batch="8", batch_start_date=None, condition="PostStretch", day="1",
        date=date(2026, 5, 11), thread=None, source_path=Path("x.JPG"),
    )
    base.update(overrides)
    return PhotoMetadata(**base)


def test_canonical_stem_raises_on_unsafe_condition():
    with pytest.raises(ValueError, match="condition"):
        canonical_stem(_meta(condition="Pre_Stretch"), "A1")


def test_canonical_stem_raises_on_unsafe_batch():
    with pytest.raises(ValueError, match="batch"):
        canonical_stem(_meta(batch="8 "), "A1")


def test_canonical_stem_still_accepts_safe_condition_and_batch():
    stem = canonical_stem(_meta(condition="PostStretch", batch="8"), "A1")
    assert stem == "2026-05-11_batch8_poststretch_threadA1"


def test_naming_module_does_not_import_torch_or_cv2():
    import sys

    assert "torch" not in sys.modules or True  # informational; real guard is import-time below
    import segment.naming as naming_mod

    source = Path(naming_mod.__file__).read_text()
    assert "import torch" not in source
    assert "import cv2" not in source
