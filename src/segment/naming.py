"""Folder-path metadata parser and canonical filename builder.

Pure module — no torch, no cv2, no file I/O beyond pathlib string ops.

D-09: the canonical CSV `Date` is the day/measurement-folder date (e.g. `D12 05-11-26`),
never the batch-start date embedded in the batch folder name (e.g. `Batch 8 04-24-26`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_BATCH_RE = re.compile(r"^Batch\s+(?P<batch>\d+)\s+(?P<mm>\d{2})-(?P<dd>\d{2})-(?P<yy>\d{2})$", re.IGNORECASE)
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


def canonical_stem(meta: PhotoMetadata, thread: str) -> str:
    """Build a collision-resistant filename stem: no path separators, no spaces."""
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
