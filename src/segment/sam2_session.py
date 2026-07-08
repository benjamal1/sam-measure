"""SAM2 predictor lifecycle: device fallback, load-once predictor, predict_mask.

D-02/SEG-03: device selection is cuda > mps > cpu, with PYTORCH_ENABLE_MPS_FALLBACK set
BEFORE importing torch, and float32 forced throughout (never float64 — PITFALLS Pitfall 1,
the MPS float64-unsupported TypeError). On this build box (no GPU) the fallback branch to
cpu is exercised for real; the Mac exercises mps.
"""
from __future__ import annotations

import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from pathlib import Path

import numpy as np
import torch

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

DEFAULT_CHECKPOINT = Path("vendor/sam2/checkpoints/sam2.1_hiera_small.pt")
DEFAULT_MODEL_CFG = "configs/sam2.1/sam2.1_hiera_s.yaml"

_predictor_cache: SAM2ImagePredictor | None = None


def select_device() -> torch.device:
    """cuda > mps > cpu. Never raises."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_predictor(
    checkpoint: Path = DEFAULT_CHECKPOINT,
    model_cfg: str = DEFAULT_MODEL_CFG,
    device: torch.device | None = None,
) -> SAM2ImagePredictor:
    """Build the SAM2 predictor once and cache it — never reload per click (Performance Traps)."""
    global _predictor_cache
    if _predictor_cache is not None:
        return _predictor_cache

    device = device or select_device()
    model = build_sam2(model_cfg, str(checkpoint), device=device)
    model = model.float()  # force float32 throughout — never float64 (Pitfall 1)
    _predictor_cache = SAM2ImagePredictor(model)
    return _predictor_cache


def predict_mask(
    predictor: SAM2ImagePredictor,
    image: np.ndarray,
    points: list[tuple[float, float]],
    labels: list[int],
    multimask_output: bool = False,
) -> np.ndarray:
    """Run one image through set_image + predict; return an HxW boolean mask.

    labels: 1 = positive point (include), 0 = negative point (exclude).
    """
    image_rgb = image.astype(np.uint8)
    predictor.set_image(image_rgb)

    point_coords = np.asarray(points, dtype=np.float32)
    point_labels = np.asarray(labels, dtype=np.int32)

    masks, scores, _ = predictor.predict(
        point_coords=point_coords,
        point_labels=point_labels,
        multimask_output=multimask_output,
    )
    return masks[0].astype(bool)
