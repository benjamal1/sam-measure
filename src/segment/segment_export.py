"""Stage-1 CLI: glob a photo folder, launch the click loop per photo, export mask+overlay.

D-05: operates over a whole folder, never a single hardcoded file. D-07: thread number is
prompted at click time (not inferable from a nested filename).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from segment.click_loop import run_click_loop
from segment.export import export_mask
from segment.naming import canonical_stem, parse_flat_path, parse_photo_path
from segment.sam2_session import load_predictor


def _derive_metadata(photo_path: Path, nextcloud_root: Path | None, date: str | None, condition: str | None):
    if nextcloud_root:
        try:
            return parse_photo_path(photo_path, nextcloud_root)
        except ValueError:
            pass
    return parse_flat_path(photo_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-1: interactive click-to-segment over a photo folder")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--nextcloud-root", type=Path, default=None)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--batch", type=str, default=None)
    parser.add_argument("--condition", type=str, default=None)
    parser.add_argument("--masks-dir", type=Path, default=Path("data/masks"))
    parser.add_argument("--qc-dir", type=Path, default=Path("data/qc"))
    args = parser.parse_args()

    predictor = load_predictor()

    for photo_path in sorted(args.input_dir.glob("*.JPG")) + sorted(args.input_dir.glob("*.jpg")):
        meta = _derive_metadata(photo_path, args.nextcloud_root, args.date, args.condition)
        thread = meta.thread or input(f"Thread number for {photo_path.name}: ").strip()

        from PIL import Image
        import numpy as np
        image_rgb = np.array(Image.open(photo_path).convert("RGB"))

        def on_accept(mask, meta=meta, thread=thread, image_rgb=image_rgb):
            stem = canonical_stem(meta, thread)
            export_mask(mask, image_rgb, stem, masks_dir=args.masks_dir, qc_dir=args.qc_dir)
            print(f"exported {stem}")

        run_click_loop(predictor, image_rgb, on_accept)


if __name__ == "__main__":
    main()
