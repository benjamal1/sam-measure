import numpy as np
import pytest
import torch
from PIL import Image

from segment.sam2_session import load_predictor, predict_mask, select_device


def test_select_device_returns_torch_device_and_never_raises():
    device = select_device()
    assert isinstance(device, torch.device)


@pytest.mark.slow
@pytest.mark.integration
def test_predict_mask_real_photo_positive_point_yields_nonempty_mask(sample_photo_path):
    """Real SAM2 CPU inference on 5.11.JPG. Point (2740, 1534) is on the thread body,
    picked by visual inspection (diagonal beige strip crossing the frame center),
    away from the needle tip visible near the top-left of the frame."""
    predictor = load_predictor()
    image = np.array(Image.open(sample_photo_path).convert("RGB"))

    point = (2740, 1534)
    mask = predict_mask(predictor, image, points=[point], labels=[1])

    assert mask.shape == image.shape[:2]
    assert mask.dtype == bool
    assert 0 < mask.sum() < mask.size, "mask must be non-empty and non-full"


@pytest.mark.slow
@pytest.mark.integration
def test_predict_mask_negative_point_changes_mask(sample_photo_path):
    predictor = load_predictor()
    image = np.array(Image.open(sample_photo_path).convert("RGB"))

    positive_only = predict_mask(predictor, image, points=[(2740, 1534)], labels=[1])
    # negative point placed near the needle tip visible top-left of the frame
    with_negative = predict_mask(
        predictor, image, points=[(2740, 1534), (1700, 250)], labels=[1, 0]
    )

    assert with_negative.shape == positive_only.shape
    assert not np.array_equal(with_negative, positive_only), "adding a negative point must change the mask"
