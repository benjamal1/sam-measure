"""Interactive matplotlib click UI (D-01): click to segment, correct, accept, export.

Bespoke loop, not napari — zero third-party SAM2-plugin dependency risk (D-01).
Left click = positive point, right click = negative point, 'a' = accept (export),
'e' = raster-erase drag mode on the accepted mask, 'n' = skip to next photo.

CRITICAL (PITFALLS Pitfall 2): click state MUST be reset per photo — stale points from
a prior image must never leak into the next prediction. `ClickLoopState.reset()` is the
single place that happens; callers must invoke it at the start of every new photo.

Multi-thread-per-photo (this task): photo-level state (image_rgb, predictor) persists
across multiple accepts on the SAME photo; only click-state (points/labels/current_mask)
resets between accepts. This is a NEW reset point in addition to the existing per-new-photo
reset — both call the exact same `ClickLoopState.reset()`, just at a different trigger.
`on_accept`'s return value decides which: a truthy return means "advance" (this photo is
done, `state.done` is set so the event loop closes/moves on); a falsy return means "reclick"
(stay on this photo, ready for the next thread's click). 'n' (skip) still moves to the next
photo without accepting, same as before, and also sets `state.done`.

The callback logic (`handle_click`/`handle_key`) is separated from the matplotlib event
loop plumbing (`run_click_loop`) specifically so it's testable under the Agg backend
without a real display — this module cannot be interactively verified in an unattended
headless session; its UX is validated by hand on the Mac (see MORNING-TEST.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from segment.mask_edit import erase_box
from segment.sam2_session import predict_mask as _default_predict_mask


@dataclass
class ClickLoopState:
    predictor: object
    image_rgb: np.ndarray
    predict_fn: Callable = _default_predict_mask
    on_accept: Callable[[np.ndarray], object] | None = None
    points: list[tuple[float, float]] = field(default_factory=list)
    labels: list[int] = field(default_factory=list)
    current_mask: np.ndarray | None = None
    erase_mode: bool = False
    erase_drag_start: tuple[float, float] | None = None
    done: bool = False

    def reset(self) -> None:
        """Clear all per-photo (or per-mask, see module docstring) click state.

        MUST be called before starting a new image, AND after every accept (whether
        reclicking the same photo for another thread or advancing) — same method, two
        different trigger points, never confuse the two.
        """
        self.points = []
        self.labels = []
        self.current_mask = None
        self.erase_mode = False
        self.erase_drag_start = None


def handle_click(state: ClickLoopState, event) -> None:
    """Mouse-DOWN handler. button 1 = left = positive point (label 1) OR erase-drag start
    (in erase mode); button 3 = right = negative point (label 0, ignored in erase mode).

    Erase is a click-drag box select (not a per-click radius) for more precise removal of
    unwanted blobs (e.g. a needle) — the actual erase happens on mouse-UP, see handle_release.
    """
    if event.xdata is None or event.ydata is None:
        return

    if state.erase_mode:
        if state.current_mask is None:
            return  # nothing to erase yet — no-op instead of crashing
        if event.button == 1:
            state.erase_drag_start = (event.xdata, event.ydata)
        return

    if event.button == 1:
        state.points.append((event.xdata, event.ydata))
        state.labels.append(1)
    elif event.button == 3:
        state.points.append((event.xdata, event.ydata))
        state.labels.append(0)
    else:
        return

    state.current_mask = state.predict_fn(state.predictor, state.image_rgb, state.points, state.labels)


def handle_release(state: ClickLoopState, event) -> None:
    """Mouse-UP handler: completes an erase-box drag started in handle_click.

    No-op outside erase mode or if no drag was started (e.g. release without a matching
    press, or the press landed off-canvas so xdata/ydata was None and no start was recorded).
    """
    if not state.erase_mode or state.erase_drag_start is None:
        return
    if event.xdata is None or event.ydata is None:
        state.erase_drag_start = None
        return
    state.current_mask = erase_box(state.current_mask, state.erase_drag_start, (event.xdata, event.ydata))
    state.erase_drag_start = None


def handle_key(state: ClickLoopState, event) -> None:
    if event.key == "a":
        if state.current_mask is not None and state.on_accept is not None:
            if not state.current_mask.any():
                print("mask is empty (fully erased) — nothing to accept, keep clicking or press 'n' to skip")
                return
            advance = state.on_accept(state.current_mask)
            # Reset click-state after EVERY accept (Pitfall-2 guard) — a second thread's
            # click on this same photo must never see the first thread's points/mask.
            state.reset()
            if advance:
                state.done = True
    elif event.key == "e":
        if state.current_mask is not None:  # erase is meaningless before a mask exists
            state.erase_mode = not state.erase_mode
    elif event.key == "n":
        state.reset()
        state.done = True


def run_click_loop(predictor, image_rgb: np.ndarray, on_accept: Callable[[np.ndarray], object]) -> ClickLoopState:
    """Launch the interactive matplotlib window for ONE photo, supporting multiple
    labeled masks before the window closes. Guarded so import/construction works under
    Agg (no display) — only plt.show() requires a real display, and is only reached when
    this function is actually called with a live backend.

    `on_accept` may be called more than once per photo (multi-thread-per-photo): the window
    stays open and click-state resets after each accept, ready for the next thread's click,
    until `on_accept` returns truthy (advance) or the user presses 'n' (skip) — either sets
    `state.done`, which closes the window and returns control to the caller.
    """
    import matplotlib.pyplot as plt

    state = ClickLoopState(predictor=predictor, image_rgb=image_rgb, on_accept=on_accept)

    fig, ax = plt.subplots()
    ax.imshow(image_rgb)
    ax.set_title(
        "Left=positive, Right=negative, 'a'=accept (label + reclick-or-advance), "
        "'e'=erase mode (drag a box), 'n'=next photo"
    )

    def _redraw():
        ax.clear()
        ax.imshow(image_rgb)
        if state.current_mask is not None:
            overlay = np.zeros((*state.current_mask.shape, 4))
            overlay[state.current_mask] = [1, 0, 0, 0.4]
            ax.imshow(overlay)
        fig.canvas.draw_idle()

    def _on_press(event):
        handle_click(state, event)
        _redraw()

    def _on_release(event):
        handle_release(state, event)
        _redraw()

    def _on_key(event):
        handle_key(state, event)
        if state.done:
            plt.close(fig)
            return
        _redraw()

    fig.canvas.mpl_connect("button_press_event", _on_press)
    fig.canvas.mpl_connect("button_release_event", _on_release)
    fig.canvas.mpl_connect("key_press_event", _on_key)
    plt.show()

    return state
