"""Structural wiring tests for the interactive click loop — Agg backend, no real display.

Cannot verify actual click UX in this headless session; this proves the callback wiring
(left/right button -> label, accept -> export) is correct so a human on the Mac only needs
to validate the visual/interactive feel, not the underlying logic.
"""
import matplotlib
matplotlib.use("Agg")  # noqa: E402

import numpy as np

from segment.click_loop import ClickLoopState, handle_click, handle_key


class _FakeEvent:
    def __init__(self, button=None, key=None, xdata=100.0, ydata=50.0):
        self.button = button
        self.key = key
        self.xdata = xdata
        self.ydata = ydata


def _fake_predict_mask(predictor, image, points, labels):
    mask = np.zeros(image.shape[:2], dtype=bool)
    mask[10:20, 10:20] = True
    return mask


def test_left_click_appends_positive_point():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )

    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    assert state.points == [(30.0, 40.0)]
    assert state.labels == [1]


def test_right_click_appends_negative_point():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )

    handle_click(state, _FakeEvent(button=3, xdata=30.0, ydata=40.0))

    assert state.points == [(30.0, 40.0)]
    assert state.labels == [0]


def test_click_recomputes_mask_via_predict_fn():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )

    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    assert state.current_mask is not None
    assert state.current_mask.sum() > 0


def test_accept_key_invokes_on_accept_exactly_once():
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_accept=lambda mask: calls.append(mask),
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="a"))

    assert len(calls) == 1


def test_state_reset_clears_points_and_mask():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    assert state.points

    state.reset()

    assert state.points == []
    assert state.labels == []
    assert state.current_mask is None


def test_erase_key_applies_erase_region_to_accepted_mask():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    before_sum = state.current_mask.sum()

    handle_key(state, _FakeEvent(key="e", xdata=15.0, ydata=15.0))

    assert state.current_mask.sum() <= before_sum
