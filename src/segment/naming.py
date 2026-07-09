"""Folder-path metadata parser and canonical filename builder.

Pure module — no torch, no cv2, no file I/O beyond pathlib string ops.

D-09: the canonical CSV `Date` is the day/measurement-folder date (e.g. `D12 05-11-26`),
never the batch-start date embedded in the batch folder name (e.g. `Batch 8 04-24-26`).

EXPT-01 revised: `parse_photo_path`/`parse_flat_path` results (especially `condition` and
`thread`) are a SUGGESTED DEFAULT only — a display hint segment_export shows the user at
label time, never authoritative. The user's manually typed value always wins when given;
see `src/segment/segment_export.py::_resolve_field`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_BATCH_RE = re.compile(r"^Batch\s+(?P<batch>\d+)\s+(?P<mm>\d{2})-(?P<dd>\d{2})-(?P<yy>\d{2})$", re.IGNORECASE)
_BATCH_NO_DATE_RE = re.compile(r"^Batch\s+(?P<batch>\d+)$", re.IGNORECASE)
_CONDITION_RE = re.compile(r"^(Pre|Post)[Ss]tretch$")
_DAY_RE = re.compile(r"^D(?P<day>\d+)\s+(?P<mm>\d{2})-(?P<dd>\d{2})-(?P<yy>\d{2})$", re.IGNORECASE)
_FLAT_DATE_RE = re.compile(r"^(?P<mm>\d{2})-(?P<dd>\d{2})-(?P<yy>\d{2})$")


def _to_date(mm: str, dd: str, yy: str) -> date:
    return date(2000 + int(yy), int(mm), int(dd))


@dataclass(frozen=True)
class PhotoMetadata:
    batch: str
    batch_start_date: date | None
    condition: str
    day: str
    date: date
    thread: str | None
    source_path: Path


def parse_photo_path(photo_path: Path, nextcloud_root: Path) -> PhotoMetadata:
    """Parse a nested Nextcloud path: Batch N MM-DD-YY / Condition / D<n> MM-DD-YY / file.

    Raises ValueError naming the offending path when required segments can't be matched —
    never returns partial metadata (ASVS V5).
    """
    try:
        parts = photo_path.relative_to(nextcloud_root).parts
    except ValueError as exc:
        raise ValueError(f"photo path is not under nextcloud_root: {photo_path}") from exc

    batch = None
    batch_start_date = None
    condition = None
    day = None
    day_date = None

    for part in parts[:-1]:  # last part is the filename
        m = _BATCH_RE.match(part)
        if m:
            batch = m.group("batch")
            batch_start_date = _to_date(m.group("mm"), m.group("dd"), m.group("yy"))
            continue
        if _CONDITION_RE.match(part):
            condition = part
            continue
        m = _DAY_RE.match(part)
        if m:
            day = m.group("day")
            day_date = _to_date(m.group("mm"), m.group("dd"), m.group("yy"))
            continue

    if batch is None or condition is None or day is None or day_date is None:
        raise ValueError(
            f"could not parse batch/condition/day metadata from path: {photo_path}"
        )

    return PhotoMetadata(
        batch=batch,
        batch_start_date=batch_start_date,
        condition=condition,
        day=day,
        date=day_date,
        thread=None,
        source_path=photo_path,
    )


def parse_flat_path(photo_path: Path) -> PhotoMetadata:
    """Parse the legacy flat convention: MM-DD-YY/<thread>.JPG.

    Date comes from the parent folder name; thread comes from the filename stem.
    """
    folder = photo_path.parent.name
    m = _FLAT_DATE_RE.match(folder)
    if not m:
        raise ValueError(f"could not parse flat-convention date from folder: {photo_path}")

    return PhotoMetadata(
        batch="",
        batch_start_date=None,
        condition="",
        day="",
        date=_to_date(m.group("mm"), m.group("dd"), m.group("yy")),
        thread=photo_path.stem,
        source_path=photo_path,
    )


def parse_lenient_path(photo_path: Path) -> PhotoMetadata:
    """Best-effort scan of ANY ancestor folder names for Batch/Condition/D# MM-DD-YY segments,
    IN ANY ORDER (unlike parse_photo_path, which requires the strict Batch/Condition/Day
    nesting order).

    Covers curated subtrees (e.g. a "For analysis" pick-list, possibly with Condition ABOVE
    Batch rather than between Batch and Day) without requiring a nextcloud_root. condition is
    left None (EXPT-01: prompted, not guessed) only when no Pre/PostStretch segment is found
    anywhere in the path; thread is always left None (composite multi-thread photos can't be
    guessed). Raises only when no day-folder date can be found at all, since PhotoMetadata.date
    is mandatory.
    """
    batch = None
    condition = None
    day = None
    day_date = None

    for part in photo_path.parts[:-1]:  # last part is the filename
        m = _BATCH_RE.match(part)
        if m:
            batch = m.group("batch")
            continue
        m = _BATCH_NO_DATE_RE.match(part)
        if m:
            batch = m.group("batch")
            continue
        if _CONDITION_RE.match(part):
            condition = part
            continue
        m = _DAY_RE.match(part)
        if m:
            day = m.group("day")
            day_date = _to_date(m.group("mm"), m.group("dd"), m.group("yy"))
            continue

    if day_date is None:
        raise ValueError(f"could not find a D# MM-DD-YY day folder anywhere in path: {photo_path}")

    return PhotoMetadata(
        batch=batch or "",
        batch_start_date=None,
        condition=condition,
        day=day or "",
        date=day_date,
        thread=None,
        source_path=photo_path,
    )


_UNSAFE_STEM_CHARS_RE = re.compile(r"[_/\\\s]")


def canonical_stem(meta: PhotoMetadata, thread: str) -> str:
    """Build a collision-resistant filename stem: no path separators, no spaces.

    `thread` and `condition`/`batch` (when present) may all be typed by a human — at an
    interactive prompt (D-07) or via a CLI --condition/--thread/--batch override that bypasses
    the prompt path entirely. ALL of them are validated here (not just thread), since any of
    them containing the "_" join delimiter, "/", or whitespace corrupts stem_to_fields' inverse
    parsing and silently misassigns fields rather than merely producing an ugly filename.
    """
    if not thread or _UNSAFE_STEM_CHARS_RE.search(thread):
        raise ValueError(
            f"invalid thread identifier {thread!r}: must not contain '_', '/', or whitespace"
        )
    if meta.condition and _UNSAFE_STEM_CHARS_RE.search(meta.condition):
        raise ValueError(
            f"invalid condition {meta.condition!r}: must not contain '_', '/', or whitespace"
        )
    if meta.batch and _UNSAFE_STEM_CHARS_RE.search(meta.batch):
        raise ValueError(
            f"invalid batch {meta.batch!r}: must not contain '_', '/', or whitespace"
        )
    parts = [meta.date.isoformat()]
    if meta.batch:
        parts.append(f"batch{meta.batch}")
    if meta.condition:
        parts.append(meta.condition.lower())
    parts.append(f"thread{thread}")
    return "_".join(parts)


def stem_to_fields(stem: str) -> dict:
    """Inverse of canonical_stem: split a canonical stem back into its fields."""
    parts = stem.split("_")
    fields: dict[str, str] = {"date": parts[0]}
    for part in parts[1:]:
        if part.startswith("batch"):
            fields["batch"] = part[len("batch"):]
        elif part.startswith("thread"):
            fields["thread"] = part[len("thread"):]
        else:
            fields["condition"] = part
    return fields
