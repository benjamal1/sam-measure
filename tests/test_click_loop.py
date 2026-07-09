"""Structural wiring tests for the interactive click loop — Agg backend, no real display.

Cannot verify actual click UX in this headless session; this proves the callback wiring
(left/right button -> label, accept -> export) is correct so a human on the Mac only needs
to validate the visual/interactive feel, not the underlying logic.
"""
import matplotlib
matplotlib.use("Agg")  # noqa: E402

import numpy as np

from segment.click_loop import ClickLoopState, handle_click, handle_key, handle_release


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
    state.erase_mode = True
    state.erase_drag_start = (1.0, 1.0)

    state.reset()

    assert state.points == []
    assert state.labels == []
    assert state.current_mask is None
    assert state.erase_mode is False
    assert state.erase_drag_start is None


def test_erase_key_toggles_erase_mode_only_when_a_mask_exists():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="e"))

    assert state.erase_mode is True


def test_erase_key_before_any_mask_is_a_noop():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )

    handle_key(state, _FakeEvent(key="e"))

    assert state.erase_mode is False


def test_erase_drag_press_then_release_clears_box_from_mask():
    """Erase is a click-drag box select: press records the start, release performs the erase."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,  # fills mask[10:20, 10:20] = True
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    state.erase_mode = True

    handle_click(state, _FakeEvent(button=1, xdata=5.0, ydata=5.0))
    assert state.erase_drag_start == (5.0, 5.0)
    assert state.current_mask.sum() > 0  # not erased yet, only the drag started

    handle_release(state, _FakeEvent(xdata=25.0, ydata=25.0))

    assert state.current_mask.sum() == 0  # (5,5)-(25,25) box fully covers the 10:20,10:20 fill
    assert state.erase_drag_start is None


def test_erase_click_alone_without_release_does_not_erase():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    state.erase_mode = True
    before_sum = state.current_mask.sum()

    handle_click(state, _FakeEvent(button=1, xdata=15.0, ydata=15.0))

    assert state.current_mask.sum() == before_sum  # erase only completes on release


def test_erase_release_without_a_prior_drag_start_is_noop():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    state.erase_mode = True
    before_sum = state.current_mask.sum()

    handle_release(state, _FakeEvent(xdata=15.0, ydata=15.0))

    assert state.current_mask.sum() == before_sum


# --- Task 2: multi-thread-per-photo label loop --------------------------------------------


def _fake_predict_mask_at(region):
    def _predict(predictor, image, points, labels):
        mask = np.zeros(image.shape[:2], dtype=bool)
        y0, y1, x0, x1 = region
        mask[y0:y1, x0:x1] = True
        return mask
    return _predict


def test_accept_returning_falsy_does_not_set_done_stays_on_photo():
    """on_accept returning a falsy value (reclick) must NOT close/advance the loop."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_accept=lambda mask: False,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="a"))

    assert state.done is False


def test_accept_returning_truthy_sets_done_signals_advance():
    """on_accept returning a truthy value (advance) signals run_click_loop to move on."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_accept=lambda mask: True,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="a"))

    assert state.done is True


def test_accept_always_resets_click_state_regardless_of_advance_or_reclick():
    """Every accept clears points/labels/current_mask — a NEW reset point in addition to
    the existing per-new-photo reset (both call ClickLoopState.reset(), different trigger)."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_accept=lambda mask: False,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    assert state.points

    handle_key(state, _FakeEvent(key="a"))

    assert state.points == []
    assert state.labels == []
    assert state.current_mask is None


def test_two_consecutive_accepts_on_same_photo_produce_independent_masks_no_cross_contamination():
    """Regression guard for Pitfall-2: two accepts on the SAME photo must not leak click
    points from the first mask into the second's prediction."""
    accepted = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask_at((10, 20, 10, 20)),
        on_accept=lambda mask: accepted.append(mask) or False,  # reclick after each accept
    )

    # First thread: one click, accept.
    handle_click(state, _FakeEvent(button=1, xdata=15.0, ydata=15.0))
    first_points_at_accept = list(state.points)
    handle_key(state, _FakeEvent(key="a"))

    assert state.points == [], "click state must be empty before the second thread's click"

    # Second thread: a DIFFERENT click, on the same still-loaded photo.
    state.predict_fn = _fake_predict_mask_at((50, 60, 50, 60))
    handle_click(state, _FakeEvent(button=1, xdata=55.0, ydata=55.0))
    second_points_at_accept = list(state.points)
    handle_key(state, _FakeEvent(key="a"))

    assert len(accepted) == 2
    assert first_points_at_accept != second_points_at_accept
    assert not np.array_equal(accepted[0], accepted[1]), "the two masks must be independent"
    assert accepted[0][10:20, 10:20].all() and not accepted[0][50:60, 50:60].any()
    assert accepted[1][50:60, 50:60].all() and not accepted[1][10:20, 10:20].any()
    assert state.done is False, "both accepts reclicked; loop must still be on this photo"


def test_skip_key_resets_and_sets_done():
    """'n' (skip) still moves to the next photo (full reset + done) without accepting."""
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_accept=lambda mask: calls.append(mask),
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="n"))

    assert calls == [], "skip must not invoke on_accept"
    assert state.points == []
    assert state.current_mask is None
    assert state.done is True


def test_new_state_starts_not_done():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    assert state.done is False
