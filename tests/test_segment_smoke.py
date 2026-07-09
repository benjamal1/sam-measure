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


# --- predict_mask caches the expensive encoder pass per-photo, not per-click --------------


class _FakeSAM2Predictor:
    """Counts set_image/predict calls without needing real SAM2/torch inference."""
    def __init__(self):
        self.set_image_calls = 0
        self.predict_calls = 0

    def set_image(self, image_rgb):
        self.set_image_calls += 1

    def predict(self, point_coords, point_labels, multimask_output=False):
        self.predict_calls += 1
        h, w = 50, 50
        mask = np.zeros((h, w), dtype=bool)
        mask[10:20, 10:20] = True
        return np.array([mask]), np.array([1.0]), None


def test_predict_mask_only_calls_set_image_once_per_photo_across_multiple_clicks():
    predictor = _FakeSAM2Predictor()
    image = np.zeros((50, 50, 3), dtype=np.uint8)

    predict_mask(predictor, image, [(10.0, 10.0)], [1])
    predict_mask(predictor, image, [(10.0, 10.0), (20.0, 20.0)], [1, 1])
    predict_mask(predictor, image, [(10.0, 10.0), (20.0, 20.0), (5.0, 5.0)], [1, 1, 0])

    assert predictor.set_image_calls == 1  # encoder ran once, not on every click
    assert predictor.predict_calls == 3    # decoder ran every time, as expected


def test_predict_mask_re_encodes_when_the_image_changes():
    predictor = _FakeSAM2Predictor()
    first_photo = np.zeros((50, 50, 3), dtype=np.uint8)
    second_photo = np.ones((50, 50, 3), dtype=np.uint8)

    predict_mask(predictor, first_photo, [(10.0, 10.0)], [1])
    predict_mask(predictor, second_photo, [(10.0, 10.0)], [1])

    assert predictor.set_image_calls == 2  # a genuinely new photo must re-encode
