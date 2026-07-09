"""Structural wiring tests for the interactive click loop — Agg backend, no real display.

Cannot verify actual click UX (or the matplotlib TextBox widget itself) in this headless
session; this proves the callback/state-machine wiring (left/right button -> label,
accept -> label-collection -> export) is correct so a human only needs to validate the
visual/interactive feel, not the underlying logic.
"""
import matplotlib
matplotlib.use("Agg")  # noqa: E402

import numpy as np

from segment.click_loop import ClickLoopState, handle_click, handle_key, handle_label_submit, handle_release


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


def test_click_is_a_noop_while_label_box_is_active():
    """Clicking the photo mid-typing must not mutate the mask that's about to be exported."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    state.label_active = True
    before = state.points.copy()

    handle_click(state, _FakeEvent(button=1, xdata=60.0, ydata=60.0))

    assert state.points == before


def test_state_reset_clears_points_and_mask():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    assert state.points
    state.erase_mode = True
    state.erase_drag_start = (1.0, 1.0)
    state.label_active = True
    state.label_field = "thread"
    state.label_condition_value = "PostStretch"
    state.pending_mask = np.zeros((5, 5), dtype=bool)

    state.reset()

    assert state.points == []
    assert state.labels == []
    assert state.current_mask is None
    assert state.erase_mode is False
    assert state.erase_drag_start is None
    assert state.label_active is False
    assert state.label_field is None
    assert state.label_condition_value is None
    assert state.pending_mask is None


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


def test_erase_release_is_a_noop_while_label_box_is_active():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    state.erase_mode = True
    handle_click(state, _FakeEvent(button=1, xdata=5.0, ydata=5.0))
    state.label_active = True
    before_sum = state.current_mask.sum()

    handle_release(state, _FakeEvent(xdata=25.0, ydata=25.0))

    assert state.current_mask.sum() == before_sum


# --- 'a' (accept): legacy fast path (both known) vs. in-canvas label collection ------------


def _fake_predict_mask_at(region):
    def _predict(predictor, image, points, labels):
        mask = np.zeros(image.shape[:2], dtype=bool)
        y0, y1, x0, x1 = region
        mask[y0:y1, x0:x1] = True
        return mask
    return _predict


def test_accept_with_both_known_calls_on_label_submit_and_auto_advances():
    """Legacy fast path: condition AND thread both already known (CLI override or
    flat-legacy filename) — nothing to label, export immediately and auto-advance."""
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: calls.append((c, t)),
        known_condition="PostStretch", known_thread="5.11",
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="a"))

    assert calls == [("PostStretch", "5.11")]
    assert state.done is True


def test_accept_with_unknown_thread_opens_label_box_not_done():
    """When thread (or condition) is unknown, 'a' must NOT call on_label_submit immediately —
    it opens the in-canvas TextBox flow instead, and must not advance/close the window."""
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: calls.append((c, t)),
        known_condition="PostStretch", known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="a"))

    assert calls == []
    assert state.done is False
    assert state.label_active is True
    assert state.label_field == "thread"
    assert state.pending_mask is not None


def test_accept_with_unknown_condition_and_thread_starts_with_condition_field():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: None,
        known_condition=None, known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="a"))

    assert state.label_active is True
    assert state.label_field == "condition"


def test_accept_on_fully_erased_empty_mask_is_a_noop_not_an_export():
    """An all-False mask (accidentally erased entirely) must never reach label collection or
    on_label_submit — exporting/measuring an empty mask crashes downstream (measure_masks)."""
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: calls.append(mask),
        known_condition="PostStretch", known_thread="01",
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    state.current_mask = np.zeros_like(state.current_mask)  # simulate a full erase

    handle_key(state, _FakeEvent(key="a"))

    assert calls == []
    assert state.done is False
    assert state.label_active is False


def test_accept_key_is_a_noop_while_already_labeling():
    """A second 'a' press while a label box is already open must not start a nested prompt
    or otherwise corrupt state."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: None,
        known_condition="PostStretch", known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    handle_key(state, _FakeEvent(key="a"))
    assert state.label_active is True
    field_before = state.label_field

    handle_key(state, _FakeEvent(key="a"))

    assert state.label_field == field_before


# --- handle_label_submit: validation, field sequencing, finalization -----------------------


def test_handle_label_submit_rejects_unsafe_characters():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: None,
        known_condition="PostStretch", known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    handle_key(state, _FakeEvent(key="a"))

    error = handle_label_submit(state, "bad_thread")

    assert error is not None
    assert state.label_active is True  # box stays open on invalid input


def test_handle_label_submit_rejects_empty_string():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: None,
        known_condition="PostStretch", known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    handle_key(state, _FakeEvent(key="a"))

    error = handle_label_submit(state, "   ")

    assert error is not None


def test_handle_label_submit_thread_only_unknown_finalizes_immediately():
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: calls.append((c, t)),
        known_condition="PostStretch", known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    handle_key(state, _FakeEvent(key="a"))

    error = handle_label_submit(state, "ML2")

    assert error is None
    assert calls == [("PostStretch", "ML2")]
    assert state.label_active is False
    assert state.points == []  # reset() ran — ready for the next thread's click


def test_handle_label_submit_both_unknown_moves_from_condition_to_thread_field():
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: calls.append((c, t)),
        known_condition=None, known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    handle_key(state, _FakeEvent(key="a"))
    assert state.label_field == "condition"

    error = handle_label_submit(state, "PreStretch")

    assert error is None
    assert calls == []  # not finalized yet — still need the thread field
    assert state.label_active is True
    assert state.label_field == "thread"
    assert state.label_condition_value == "PreStretch"

    error2 = handle_label_submit(state, "HM3")

    assert error2 is None
    assert calls == [("PreStretch", "HM3")]
    assert state.label_active is False


def test_handle_label_submit_never_sets_done_advance_is_always_explicit_n():
    """Finalizing a label must NOT close the window/advance to the next photo — only 'n' does."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: None,
        known_condition="PostStretch", known_thread=None,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    handle_key(state, _FakeEvent(key="a"))

    handle_label_submit(state, "ML2")

    assert state.done is False


def test_two_consecutive_labels_on_same_photo_produce_independent_masks_no_cross_contamination():
    """Regression guard for Pitfall-2: two labeled threads on the SAME photo must not leak
    click points from the first mask into the second's prediction."""
    accepted = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask_at((10, 20, 10, 20)),
        on_label_submit=lambda mask, c, t: accepted.append(mask),
        known_condition="PostStretch", known_thread=None,
    )

    # First thread: one click, accept, label.
    handle_click(state, _FakeEvent(button=1, xdata=15.0, ydata=15.0))
    handle_key(state, _FakeEvent(key="a"))
    handle_label_submit(state, "T1")
    assert state.points == [], "click state must be empty before the second thread's click"

    # Second thread: a DIFFERENT click, on the same still-loaded photo.
    state.predict_fn = _fake_predict_mask_at((50, 60, 50, 60))
    handle_click(state, _FakeEvent(button=1, xdata=55.0, ydata=55.0))
    handle_key(state, _FakeEvent(key="a"))
    handle_label_submit(state, "T2")

    assert len(accepted) == 2
    assert not np.array_equal(accepted[0], accepted[1]), "the two masks must be independent"
    assert accepted[0][10:20, 10:20].all() and not accepted[0][50:60, 50:60].any()
    assert accepted[1][50:60, 50:60].all() and not accepted[1][10:20, 10:20].any()
    assert state.done is False, "labeling never advances by itself — only 'n' does"


def test_skip_key_resets_and_sets_done():
    """'n' moves to the next photo (full reset + done) without needing an accept first."""
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: calls.append(mask),
        known_condition="PostStretch", known_thread="01",
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="n"))

    assert calls == [], "skip must not invoke on_label_submit"
    assert state.points == []
    assert state.current_mask is None
    assert state.done is True


def test_new_state_starts_not_done():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    assert state.done is False


# --- 'q' quits the entire run, not just this photo (proper alternative to Ctrl+C) ----------


def test_q_key_sets_done_and_quit_all():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))

    handle_key(state, _FakeEvent(key="q"))

    assert state.done is True
    assert state.quit_all is True
    assert state.points == []  # 'q' resets click-state same as 'n'


def test_n_key_does_not_set_quit_all():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )

    handle_key(state, _FakeEvent(key="n"))

    assert state.done is True
    assert state.quit_all is False


def test_keys_are_ignored_while_label_box_is_active():
    """Keystrokes while typing a label (e.g. a letter that happens to also be 'e'/'n'/'q')
    must go to the TextBox widget, not be reinterpreted as click_loop hotkeys."""
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    state.label_active = True

    handle_key(state, _FakeEvent(key="q"))

    assert state.quit_all is False
    assert state.done is False


# --- undo: 'u' reverts the last click or erase, never an already-accepted mask -------------


def test_undo_reverts_last_click_point():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    assert state.points == [(30.0, 40.0)]

    handle_key(state, _FakeEvent(key="u"))

    assert state.points == []
    assert state.current_mask is None


def test_undo_reverts_last_erase():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    before_sum = state.current_mask.sum()
    state.erase_mode = True
    handle_click(state, _FakeEvent(button=1, xdata=5.0, ydata=5.0))
    handle_release(state, _FakeEvent(xdata=25.0, ydata=25.0))
    assert state.current_mask.sum() == 0

    handle_key(state, _FakeEvent(key="u"))

    assert state.current_mask.sum() == before_sum


def test_undo_with_empty_history_is_a_noop():
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask,
    )

    assert state.undo() is False


def test_undo_cannot_reach_back_into_an_already_labeled_mask():
    """History resets on every finalized label — 'u' after that must not resurrect the prior
    (already-exported) mask's points, since that mask is already saved and done."""
    calls = []
    state = ClickLoopState(
        predictor=None, image_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
        predict_fn=_fake_predict_mask, on_label_submit=lambda mask, c, t: calls.append(mask),
        known_condition="PostStretch", known_thread="01",
    )
    handle_click(state, _FakeEvent(button=1, xdata=30.0, ydata=40.0))
    handle_key(state, _FakeEvent(key="a"))
    assert len(calls) == 1
    assert state.history == []

    assert state.undo() is False
