"""Write mask + overlay QC image under data/, source photo always untouched (EXPT-01/02/03).

Every output path is built via pathlib joins under a fixed data/ root — never string-concatenated
from the source path (path-traversal guard, Security V12). This module never opens the source
photo for writing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def make_overlay(image_rgb: np.ndarray, mask: np.ndarray, tint=(255, 0, 0), alpha: float = 0.4) -> np.ndarray:
    """Blend a semi-transparent tint over the masked region of image_rgb. No display, no cv2 GUI."""
    overlay = image_rgb.astype(np.float32).copy()
    tint_arr = np.array(tint, dtype=np.float32)
    overlay[mask] = overlay[mask] * (1 - alpha) + tint_arr * alpha
    return overlay.astype(np.uint8)


def export_mask(
    mask: np.ndarray,
    image_rgb: np.ndarray,
    stem: str,
    masks_dir: Path = Path("data/masks"),
    qc_dir: Path = Path("data/qc"),
) -> tuple[Path, Path]:
    """Write the boolean mask as a 0/255 PNG and an overlay QC PNG, both under their fixed roots.

    Receives an already-loaded image_rgb array and a canonical stem — never opens the source
    photo itself, so it cannot accidentally write into or over the Nextcloud source tree.
    """
    masks_dir = Path(masks_dir)
    qc_dir = Path(qc_dir)
    masks_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    mask_path = masks_dir / f"{stem}.png"
    overlay_path = qc_dir / f"{stem}_overlay.png"

    mask_uint8 = (mask.astype(np.uint8)) * 255
    Image.fromarray(mask_uint8).save(mask_path)

    overlay = make_overlay(image_rgb, mask)
    Image.fromarray(overlay).save(overlay_path)

    return mask_path, overlay_path
