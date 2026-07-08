"""Stage-1 CLI: glob a photo folder, launch the click loop per photo, export mask+overlay.

D-05: operates over a whole folder, never a single hardcoded file. D-07: thread number is
prompted at click time (not inferable from a nested filename).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from segment.click_loop import run_click_loop
from segment.export import export_mask
from segment.naming import canonical_stem, parse_flat_path, parse_photo_path
from segment.sam2_session import load_predictor

_VALID_THREAD_RE = re.compile(r"^[^_/\\\s]+$")


def _derive_metadata(photo_path: Path, nextcloud_root: Path | None, date: str | None, condition: str | None):
    if nextcloud_root:
        try:
            return parse_photo_path(photo_path, nextcloud_root)
        except ValueError:
            pass
    return parse_flat_path(photo_path)


def _prompt_for_thread(photo_name: str) -> str:
    """Re-prompt until a canonical_stem-safe thread identifier is given (no '_', '/', whitespace)."""
    while True:
        thread = input(f"Thread number for {photo_name}: ").strip()
        if _VALID_THREAD_RE.match(thread):
            return thread
        print("Invalid thread identifier — must not contain '_', '/', or whitespace. Try again.")


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
        thread = meta.thread or _prompt_for_thread(photo_path.name)

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
