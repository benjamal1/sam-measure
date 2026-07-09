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


def erase_box(mask: np.ndarray, p1: tuple[float, float], p2: tuple[float, float]) -> np.ndarray:
    """Return a NEW boolean array with True pixels cleared inside the rectangle p1..p2.

    p1/p2 are (x, y) image coordinates in either order (drag can go any direction).
    A degenerate (zero-area) box is a no-op — never mutates the input mask.
    """
    result = mask.copy()
    h, w = result.shape

    x0, x1 = sorted((p1[0], p2[0]))
    y0, y1 = sorted((p1[1], p2[1]))

    xi0, xi1 = max(0, int(round(x0))), min(w, int(round(x1)) + 1)
    yi0, yi1 = max(0, int(round(y0))), min(h, int(round(y1)) + 1)

    if xi1 > xi0 and yi1 > yi0:
        result[yi0:yi1, xi0:xi1] = False

    return result
