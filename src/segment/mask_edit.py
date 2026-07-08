"""Pure raster erase fallback for mask correction (D-08, SEG-02).

Used when a SAM2 negative point doesn't cleanly separate thread from an unwanted region
(e.g. a needle). Pure numpy — no cv2 GUI, no SAM2, no mutation of the input array.
"""
from __future__ import annotations

import numpy as np


def erase_region(mask: np.ndarray, points: list[tuple[float, float]], radius: int = 8) -> np.ndarray:
    """Return a NEW boolean array with True pixels cleared within `radius` of each point.

    Never mutates the input mask (immutability rule).
    """
    result = mask.copy()
    if not points:
        return result

    h, w = result.shape
    yy, xx = np.mgrid[0:h, 0:w]

    for x, y in points:
        dist_sq = (xx - x) ** 2 + (yy - y) ** 2
        result[dist_sq <= radius ** 2] = False

    return result
