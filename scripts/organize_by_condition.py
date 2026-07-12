"""One-off view helper: copy QC overlays (or masks) into condition/batch subfolders for
fast eyeballing — spot mislabeled threads or masks that need a redo by shape at a glance.

Source stays untouched: this only COPIES into a separate organized tree, built from the
canonical stem already encoded in each filename (see naming.stem_to_fields) — no new metadata,
no re-parsing photo paths. Safe to rerun any time; mirrors deletions like cleanup_masks.py does
(a stale copy for a mask/overlay you deleted upstream gets removed from the organized tree too).

Overlay QC images (data/qc/*_overlay.png) are usually the better source to organize: they show
the mask drawn over the real photo, so a mislabeled thread or a bad segment is obvious at a
glance. Masks alone (data/masks/*.png) show only the blob shape, no photo context — pass
--source masks if that's all you want (lighter files, pure shape comparison).
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from segment.naming import stem_to_fields

_NO_CONDITION = "_no_condition"
_NO_BATCH = "_no_batch"


def _stem_from_filename(path: Path) -> str:
    """Strip the '_overlay' suffix QC images carry, so both masks and overlays share one
    stem-parsing path."""
    name = path.stem
    if name.endswith("_overlay"):
        name = name[: -len("_overlay")]
    return name


def plan_organize(source_dir: Path) -> list[dict]:
    """Return [{src, dest_rel, stem, error}] for every file in source_dir.

    dest_rel is relative to the output root: <condition>/<batch>/<original filename>.
    error is set (dest_rel is None) when a filename doesn't parse as a canonical stem —
    those are reported, never silently skipped.
    """
    plan = []
    for src in sorted(source_dir.iterdir()):
        if not src.is_file():
            continue
        stem = _stem_from_filename(src)
        try:
            fields = stem_to_fields(stem)
            if "thread" not in fields:
                raise ValueError(f"stem has no 'thread<id>' segment: {stem!r}")
        except Exception as exc:  # noqa: BLE001 - report and continue, never abort the batch
            plan.append({"src": src, "dest_rel": None, "stem": stem, "error": str(exc)})
            continue
        condition = fields.get("condition") or _NO_CONDITION
        batch = fields.get("batch")
        batch_folder = f"batch{batch}" if batch else _NO_BATCH
        plan.append({
            "src": src,
            "dest_rel": Path(condition) / batch_folder / src.name,
            "stem": stem,
            "error": None,
        })
    return plan


def organize_folder(source_dir: Path, out_dir: Path, dry_run: bool = True) -> list[dict]:
    """Copy every file in source_dir into out_dir/<condition>/<batch>/, mirroring deletions.

    dry_run=True (default) only reports what would happen. source_dir is never modified
    either way — this only ever writes into out_dir.
    """
    source_dir = Path(source_dir)
    out_dir = Path(out_dir)
    plan = plan_organize(source_dir)

    expected_dest_rels = {str(p["dest_rel"]) for p in plan if p["dest_rel"] is not None}

    if not dry_run:
        for item in plan:
            if item["dest_rel"] is None:
                continue
            dest = out_dir / item["dest_rel"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["src"], dest)

        if out_dir.exists():
            for stale in out_dir.rglob("*"):
                if not stale.is_file():
                    continue
                rel = str(stale.relative_to(out_dir))
                if rel not in expected_dest_rels:
                    stale.unlink()
                    plan.append({"src": None, "dest_rel": stale.relative_to(out_dir),
                                 "stem": None, "error": None, "removed_stale": True})

    return plan


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy QC overlays or masks into condition/batch subfolders for quick review"
    )
    parser.add_argument("--source", choices=["qc", "masks"], default="qc",
                         help="Which exported folder to organize (default: qc — shows mask+photo)")
    parser.add_argument("--source-dir", type=Path, default=None,
                         help="Override the source folder directly (default: data/<source>)")
    parser.add_argument("--out-dir", type=Path, default=None,
                         help="Where to write the organized copies (default: data/<source>_by_condition)")
    parser.add_argument("--apply", action="store_true", default=False,
                         help="Actually copy files. Without this flag, only reports the plan.")
    args = parser.parse_args()

    source_dir = args.source_dir or Path("data") / args.source
    out_dir = args.out_dir or Path("data") / f"{args.source}_by_condition"

    if not source_dir.exists():
        print(f"source folder not found: {source_dir}")
        return

    plan = organize_folder(source_dir, out_dir, dry_run=not args.apply)

    errors = [p for p in plan if p.get("error")]
    stale = [p for p in plan if p.get("removed_stale")]
    copied = [p for p in plan if p["dest_rel"] is not None and not p.get("removed_stale")]

    for p in errors:
        print(f"SKIPPED (unparseable stem) {p['src'].name}: {p['error']}")
    for p in stale:
        print(f"removed stale {p['dest_rel']} (no longer in {source_dir})")

    if args.apply:
        print(f"\ncopied {len(copied)} file(s) into {out_dir} ({len(errors)} skipped, "
              f"{len(stale)} stale removed)")
    else:
        print(f"\n[dry-run] would copy {len(copied)} file(s) into {out_dir} "
              f"({len(errors)} would be skipped) — rerun with --apply to actually copy")


if __name__ == "__main__":
    main()
