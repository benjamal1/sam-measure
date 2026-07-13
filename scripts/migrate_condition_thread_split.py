"""One-off migration: re-stem already-exported masks whose thread label was typed BEFORE
condition+thread splitting existed (e.g. "HL1" typed as the thread, folder-derived
Poststretch/Prestretch left as the condition) into the new convention (condition="HL",
thread="1").

Downstream stages (measure_masks, build_final_csv) regenerate their CSVs from scratch every
run by reading mask FILENAMES (naming.stem_to_fields) — so the mask filename is the actual
source of truth. Patching measurements.csv by hand would just get overwritten on the next
measure run; this script fixes the thing measure_masks actually reads.

Safe to rerun: masks already in the new convention (thread is pure digits, e.g. "...thread1")
don't match the letters+digits split pattern and are left untouched, so running this twice
is a no-op the second time. Renames masks IN PLACE within masks_dir (and their matching QC
overlay/skeleton files in qc_dir) — no pixel data changes, only the filename.
"""
from __future__ import annotations

import argparse
from datetime import date as date_cls
from pathlib import Path

from segment.naming import PhotoMetadata, canonical_stem, split_condition_thread_label, stem_to_fields


def plan_migration(masks_dir: Path) -> list[dict]:
    """Return [{old_stem, new_stem, error}] for every mask in masks_dir whose thread field
    splits into a condition+thread label. error is set (new_stem is None) on a rename
    collision (two or more old stems mapping to the same new stem) — ALL entries sharing a
    colliding new_stem are flagged (not just the second one onward), so a collision can never
    half-apply and silently rename one mask away while looking like nothing happened to it.
    """
    masks_dir = Path(masks_dir)
    candidates = []  # (old_stem, new_stem)

    for mask_path in sorted(masks_dir.glob("*.png")):
        old_stem = mask_path.stem
        fields = stem_to_fields(old_stem)
        thread = fields.get("thread", "")
        label_condition, label_thread = split_condition_thread_label(thread)
        if label_condition is None:
            continue  # already migrated, or legacy decimal thread — nothing to do

        meta = PhotoMetadata(
            batch=fields.get("batch", ""), batch_start_date=None, condition=label_condition,
            day="", date=date_cls.fromisoformat(fields["date"]), thread=None, source_path=mask_path,
        )
        new_stem = canonical_stem(meta, label_thread)
        candidates.append((old_stem, new_stem))

    counts: dict[str, int] = {}
    for _, new_stem in candidates:
        counts[new_stem] = counts.get(new_stem, 0) + 1

    plan = []
    for old_stem, new_stem in candidates:
        if counts[new_stem] > 1:
            plan.append({
                "old_stem": old_stem, "new_stem": None,
                "error": f"collision: {counts[new_stem]} old stems (including {old_stem!r}) "
                         f"would all rename to {new_stem!r} — resolve manually before rerunning",
            })
        else:
            plan.append({"old_stem": old_stem, "new_stem": new_stem, "error": None})

    return plan


def apply_migration(masks_dir: Path, qc_dir: Path, plan: list[dict]) -> None:
    masks_dir = Path(masks_dir)
    qc_dir = Path(qc_dir)

    for item in plan:
        if item["error"] is not None:
            continue
        old_stem, new_stem = item["old_stem"], item["new_stem"]

        mask_old = masks_dir / f"{old_stem}.png"
        mask_new = masks_dir / f"{new_stem}.png"
        if mask_old.exists():
            mask_old.rename(mask_new)

        for suffix in ("_overlay.png", "_skeleton.png"):
            qc_old = qc_dir / f"{old_stem}{suffix}"
            qc_new = qc_dir / f"{new_stem}{suffix}"
            if qc_old.exists():
                qc_new.parent.mkdir(parents=True, exist_ok=True)
                qc_old.rename(qc_new)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-stem already-exported masks to split a typed thread label (e.g. HL1) "
                     "into condition+thread, matching the new naming convention"
    )
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--qc-dir", type=Path, default=Path("data/qc"))
    parser.add_argument("--apply", action="store_true", default=False,
                         help="Actually rename files. Without this flag, only reports the plan.")
    args = parser.parse_args()

    plan = plan_migration(args.masks_dir)

    if not plan:
        print(f"no masks need migration in {args.masks_dir} — already up to date")
        return

    errors = [p for p in plan if p["error"]]
    renames = [p for p in plan if not p["error"]]

    for p in renames:
        print(f"{'[dry-run] would rename' if not args.apply else 'renamed'} "
              f"{p['old_stem']} -> {p['new_stem']}")
    for p in errors:
        print(f"SKIPPED (needs manual resolution): {p['error']}")

    if args.apply:
        apply_migration(args.masks_dir, args.qc_dir, plan)
        print(f"\nrenamed {len(renames)} mask(s) ({len(errors)} collision(s) skipped, see above)")
        print("now rerun: measure_masks -> build_final_csv to regenerate the CSVs from the renamed masks")
    else:
        print(f"\n{len(renames)} mask(s) would be renamed ({len(errors)} collision(s) found) — "
              "rerun with --apply to actually rename")


if __name__ == "__main__":
    main()
