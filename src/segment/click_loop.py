"""Interactive matplotlib click UI (D-01): click to segment, correct, label in-canvas, export.

Bespoke loop, not napari — zero third-party SAM2-plugin dependency risk (D-01).
Left click = positive point, right click = negative point, 'a' = accept (opens an in-canvas
TextBox for condition/thread, whichever is unknown), 'e' = raster-erase drag mode on the
accepted mask, 'u' = undo, 'n' = advance to next photo, 'q' = quit the whole run.

CRITICAL (PITFALLS Pitfall 2): click state MUST be reset per photo — stale points from
a prior image must never leak into the next prediction. `ClickLoopState.reset()` is the
single place that happens; callers must invoke it at the start of every new photo.

Multi-thread-per-photo: photo-level state (image_rgb, predictor) persists across multiple
accepts on the SAME photo; only click-state (points/labels/current_mask) resets between
accepts. Advance to the next photo is ALWAYS an explicit 'n' press — there is no y/n
"label another thread?" prompt anymore: after a label is submitted, the photo simply stays
open, ready for another click, until the user presses 'n' themselves. The one exception is
the legacy fast path (condition AND thread both already known before any clicking — an
explicit CLI override or a flat-legacy filename-derived guess): that still auto-advances
after one accept, since there's nothing left to label and no reason to make the user press
an extra key.

In-canvas labeling (not a terminal prompt) is required, not just nicer: this UI is also
driven over SSH via matplotlib's WebAgg backend (a browser tab, no local display at all) —
there is no "terminal to refocus" in that scenario, so any prompt that isn't part of the
same canvas/websocket session is simply unreachable.

The callback logic (`handle_click`/`handle_key`/`handle_label_submit`) is separated from the
matplotlib event loop plumbing (`run_click_loop`) specifically so it's testable under the Agg
backend without a real display — this module cannot be interactively verified in an
unattended headless session; its UX is validated by hand (see RUNBOOK.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from segment.mask_edit import erase_box
from segment.sam2_session import predict_mask as _default_predict_mask

_VALID_LABEL_RE = re.compile(r"^[^_/\\\s]+$")


@dataclass
class ClickLoopState:
    predictor: object
    image_rgb: np.ndarray
    predict_fn: Callable = _default_predict_mask
    on_label_submit: Callable[[np.ndarray, str, str], None] | None = None
    known_condition: str | None = None  # pre-resolved (CLI override or path-guess) — skip prompting for it
    known_thread: str | None = None     # pre-resolved (CLI override or flat-legacy filename) — skip prompting
    points: list[tuple[float, float]] = field(default_factory=list)
    labels: list[int] = field(default_factory=list)
    current_mask: np.ndarray | None = None
    erase_mode: bool = False
    erase_drag_start: tuple[float, float] | None = None
    done: bool = False
    quit_all: bool = False
    history: list[tuple[list, list, np.ndarray | None]] = field(default_factory=list)

    # Label-collection state (in-canvas TextBox flow — see handle_label_submit)
    label_active: bool = False
    label_field: str | None = None          # "condition" or "thread" — which field is showing
    label_condition_value: str | None = None
    pending_mask: np.ndarray | None = None

    _MAX_HISTORY = 20

    def reset(self) -> None:
        """Clear all per-photo (or per-mask, see module docstring) click state.

        MUST be called before starting a new image, AND after every label submission (ready
        for the next thread's click) — same method, two different trigger points, never
        confuse the two. Undo history is per-mask-in-progress too — it must never let you
        undo back into an already-exported prior mask.
        """
        self.points = []
        self.labels = []
        self.current_mask = None
        self.erase_mode = False
        self.erase_drag_start = None
        self.history = []
        self.label_active = False
        self.label_field = None
        self.label_condition_value = None
        self.pending_mask = None

    def push_history(self) -> None:
        """Snapshot points/labels/current_mask BEFORE a mutating click or erase, so 'u' can
        restore it. Bounded so a long correction session can't grow this unboundedly."""
        self.history.append((list(self.points), list(self.labels), self.current_mask))
        if len(self.history) > self._MAX_HISTORY:
            self.history.pop(0)

    def undo(self) -> bool:
        """Restore the most recent pre-mutation snapshot. Returns False (no-op) if empty."""
        if not self.history:
            return False
        self.points, self.labels, self.current_mask = self.history.pop()
        return True


def handle_click(state: ClickLoopState, event) -> None:
    """Mouse-DOWN handler. button 1 = left = positive point (label 1) OR erase-drag start
    (in erase mode); button 3 = right = negative point (label 0, ignored in erase mode).

    No-op while a label TextBox is active — clicking the photo mid-typing would otherwise
    silently mutate the mask that's about to be exported.

    Erase is a click-drag box select (not a per-click radius) for more precise removal of
    unwanted blobs (e.g. a needle) — the actual erase happens on mouse-UP, see handle_release.
    """
    if state.label_active:
        return
    if event.xdata is None or event.ydata is None:
        return

    if state.erase_mode:
        if state.current_mask is None:
            return  # nothing to erase yet — no-op instead of crashing
        if event.button == 1:
            state.erase_drag_start = (event.xdata, event.ydata)
        return

    if event.button == 1:
        state.push_history()
        state.points.append((event.xdata, event.ydata))
        state.labels.append(1)
    elif event.button == 3:
        state.push_history()
        state.points.append((event.xdata, event.ydata))
        state.labels.append(0)
    else:
        return

    state.current_mask = state.predict_fn(state.predictor, state.image_rgb, state.points, state.labels)


def handle_release(state: ClickLoopState, event) -> None:
    """Mouse-UP handler: completes an erase-box drag started in handle_click.

    No-op outside erase mode, while labeling, or if no drag was started (e.g. release
    without a matching press, or the press landed off-canvas so xdata/ydata was None).
    """
    if state.label_active or not state.erase_mode or state.erase_drag_start is None:
        return
    if event.xdata is None or event.ydata is None:
        state.erase_drag_start = None
        return
    state.push_history()
    state.current_mask = erase_box(state.current_mask, state.erase_drag_start, (event.xdata, event.ydata))
    state.erase_drag_start = None


def handle_key(state: ClickLoopState, event) -> None:
    if state.label_active:
        return  # the TextBox widget owns keyboard input while a label is being typed

    if event.key == "a":
        if state.current_mask is not None and state.on_label_submit is not None:
            if not state.current_mask.any():
                print("mask is empty (fully erased) — nothing to accept, keep clicking or press 'n' to skip")
                return
            state.pending_mask = state.current_mask
            if state.known_condition is not None and state.known_thread is not None:
                # Legacy fast path: nothing to label, export immediately and auto-advance —
                # preserves pre-existing behavior for CLI overrides / flat-legacy filenames.
                state.on_label_submit(state.pending_mask, state.known_condition, state.known_thread)
                state.reset()
                state.done = True
            else:
                state.label_active = True
                state.label_field = "condition" if state.known_condition is None else "thread"
    elif event.key == "e":
        if state.current_mask is not None:  # erase is meaningless before a mask exists
            state.erase_mode = not state.erase_mode
    elif event.key == "u":
        # Undo the last click (point add) or erase-box, whichever happened most recently —
        # does NOT undo an already-accepted/exported mask (history is cleared on every accept).
        if not state.undo():
            print("nothing to undo")
    elif event.key == "n":
        state.reset()
        state.done = True
    elif event.key == "q":
        # Stop the ENTIRE run, not just this photo — the proper way to quit, instead of
        # Ctrl+C. Ctrl+C during Tk's mainloop hits a known Tk/macOS quirk (Tcl's own signal
        # handler tears down mid-flight and aborts the process) — this avoids ever sending
        # a signal into Tk at all, it's a plain Python flag checked after the window closes.
        state.reset()
        state.done = True
        state.quit_all = True


def handle_label_submit(state: ClickLoopState, text: str) -> str | None:
    """Process one submitted TextBox value (condition or thread, whichever field is active).

    Returns an error message (caller should re-show the box, unchanged field) on invalid
    input, or None on success. On success, either advances to the next unknown field
    (state.label_field changes, state.label_active stays True — caller shows the next box)
    or finalizes the label (calls on_label_submit, resets click-state, state.label_active
    becomes False — caller hides the box and redraws, ready for the next click on this photo).

    Never sets state.done — advancing to the next PHOTO is always an explicit 'n' press.
    """
    text = text.strip()
    if not text or not _VALID_LABEL_RE.match(text):
        return "must not contain '_', '/', or whitespace — try again"

    if state.label_field == "condition":
        if state.known_thread is None:
            state.label_condition_value = text
            state.label_field = "thread"
            return None
        condition_value, thread_value = text, state.known_thread
    else:
        condition_value = state.label_condition_value if state.label_condition_value is not None else state.known_condition
        thread_value = text

    if state.on_label_submit is not None:
        state.on_label_submit(state.pending_mask, condition_value, thread_value)
    state.reset()
    return None


def run_click_loop(
    predictor,
    image_rgb: np.ndarray,
    on_label_submit: Callable[[np.ndarray, str, str], None],
    photo_path=None,
    known_condition: str | None = None,
    known_thread: str | None = None,
) -> ClickLoopState:
    """Launch the interactive matplotlib window for ONE photo, supporting multiple
    labeled masks before the window closes. Guarded so import/construction works under
    Agg (no display) — only plt.show() requires a real display, and is only reached when
    this function is actually called with a live backend.

    `on_label_submit(mask, condition, thread)` is called once per accepted+labeled mask —
    purely an export/bookkeeping callback, no prompting inside it. The window stays open
    across multiple accepts on the same photo; the user explicitly presses 'n' to advance
    (no more y/n "another thread?" prompt) — except the legacy fast path where
    known_condition AND known_thread are both already resolved, which still auto-advances
    after one accept (nothing left to label).

    `photo_path` (optional): sets the OS window title to the full file path — matplotlib's
    default "Figure 1" title otherwise gives no clue which photo is open.
    """
    import matplotlib

    # Prefer TkAgg over the default macosx backend specifically: macosx has a known flaky
    # window-close behavior when plt.show()/plt.close() cycle repeatedly within one process
    # (observed: stale windows piling up across photos in a session). Only overrides macosx —
    # any OTHER explicit backend choice (e.g. MPLBACKEND=WebAgg for viewing over SSH in a
    # browser, no XQuartz needed) must be respected, not silently clobbered back to TkAgg.
    if matplotlib.get_backend().lower() == "macosx":
        try:
            matplotlib.use("TkAgg")
        except Exception:
            pass

    # WebAgg defaults to auto-opening a browser tab on ITS OWN machine when the server
    # starts (matplotlib.rcParams['webagg.open_in_browser']) — over SSH that's the remote
    # machine's own (probably headless, or GUI-but-irrelevant) session, not the browser
    # you're actually viewing from, so every restart pops a useless tab there instead.
    # You always open the URL yourself in your own browser via the SSH port-forward.
    if matplotlib.get_backend().lower() == "webagg":
        matplotlib.rcParams["webagg.open_in_browser"] = False

    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    from matplotlib.widgets import TextBox

    # Safety net: close any figure left open from a prior photo before opening a new one.
    # plt.close(fig) at done-time (below) should already handle this, but some backends
    # (observed: macOS) can leave a stale window rendered if the close doesn't fully take
    # effect before the next plt.subplots() — this guarantees a clean slate regardless.
    plt.close("all")

    state = ClickLoopState(
        predictor=predictor, image_rgb=image_rgb, on_label_submit=on_label_submit,
        known_condition=known_condition, known_thread=known_thread,
    )

    fig, ax = plt.subplots()
    if photo_path is not None:
        try:
            fig.canvas.manager.set_window_title(str(photo_path))
        except AttributeError:
            pass  # some backends (e.g. Agg, used in headless tests) have no window manager

    def _title() -> str:
        if state.label_active:
            return f"Type {state.label_field} and press Enter"
        base = (
            "Left=positive, Right=negative, scroll=zoom, 'a'=accept+label, 'u'=undo, "
            "'n'=next photo, 'q'=quit (not Ctrl+C)"
        )
        return f"[ERASE MODE — drag a box] {base}" if state.erase_mode else f"'e'=erase mode (drag a box) | {base}"

    # Persistent artists, created ONCE and updated in place — not cleared/recreated on every
    # interaction. The base photo (image_rgb) never changes across clicks on the same photo,
    # so there is no reason to re-encode/re-transmit it on every click/keypress; only the
    # small overlay array and rectangle patch actually change. This is the main lag fix: the
    # old approach did ax.clear() + a fresh imshow(image_rgb) on every single interaction,
    # which for a large macro photo re-sends the FULL image over WebAgg's websocket every
    # time — unrelated to SAM2 (SAM2 only runs on an actual click, never on accept/label/erase).
    ax.imshow(image_rgb)
    _overlay_rgba = np.zeros((*image_rgb.shape[:2], 4))
    overlay_artist = ax.imshow(_overlay_rgba)
    drag_rect = {"patch": mpatches.Rectangle(
        (0, 0), 0, 0, edgecolor="yellow", facecolor="none", linewidth=1.5, visible=False,
    )}
    ax.add_patch(drag_rect["patch"])

    def _update_overlay():
        if state.current_mask is not None:
            _overlay_rgba[..., 3] = 0
            _overlay_rgba[state.current_mask] = [1, 0, 0, 0.4]
            overlay_artist.set_data(_overlay_rgba)
        else:
            _overlay_rgba[..., 3] = 0
            overlay_artist.set_data(_overlay_rgba)

    # In-canvas label TextBox: one small axes, created once, shown/hidden as needed rather
    # than recreated per prompt (recreating a widget's own axes on every _redraw() would lose
    # its focus/typed-so-far state).
    label_ax = fig.add_axes([0.3, 0.01, 0.4, 0.05])
    label_ax.set_visible(False)
    label_box = TextBox(label_ax, "")

    # Work around a matplotlib bug: TextBox's own internal resize_event handler
    # (_resize, wired in TextBox.__init__ to recompute cursor rendering on window
    # resize) is decorated with a helper that unconditionally reads event.inaxes —
    # but a real ResizeEvent has no such attribute, so it raises AttributeError on
    # every actual window resize. Harmless under TkAgg (native windows rarely fire
    # a matching resize_event in practice); fatal under WebAgg, which forwards the
    # browser's real resize events and hits this every time. _resize only affects
    # cursor-position cosmetics inside the box — safe to disconnect outright. It's
    # always the LAST event TextBox.__init__ connects (see matplotlib's widgets.py),
    # so _cids[-1] is it; best-effort since this pokes a private attribute.
    try:
        fig.canvas.mpl_disconnect(label_box._cids[-1])
    except Exception:
        pass

    def _sync_label_box():
        if state.label_active:
            label_ax.set_visible(True)
            guess = known_condition if state.label_field == "condition" else known_thread
            label_box.label.set_text(f"{state.label_field}: ")
            label_box.set_val(guess or "")
            # Grab keyboard focus programmatically — without this, the box just sits
            # there and the user has to click INTO it first before typing does anything.
            label_box.begin_typing()
            label_box.cursor_index = len(label_box.text)
            label_box._rendercursor()
        else:
            label_ax.set_visible(False)

    def _on_label_submit(text):
        error = handle_label_submit(state, text)
        if error:
            label_box.set_val("")
            ax.set_title(f"{error} — {_title()}")
            fig.canvas.draw_idle()
            return
        _sync_label_box()  # either moves to the next field, or hides the box (label done)
        _redraw()

    label_box.on_submit(_on_label_submit)

    def _redraw():
        """Update the overlay/title in place — no ax.clear(), no re-imshow() of the base
        photo. Zoom (axis limits) is untouched by this, since nothing is ever cleared."""
        _update_overlay()
        drag_rect["patch"].set_visible(False)
        ax.set_title(_title())
        fig.canvas.draw_idle()

    def _on_scroll(event):
        """Scroll wheel = zoom in/out centered on the cursor. Doesn't conflict with click
        semantics (unlike matplotlib's default toolbar zoom-rectangle, which would intercept
        left-clicks meant for SAM2 points) and doesn't need a full image re-render — it only
        changes the visible axis window into the already-drawn image/overlay."""
        if state.label_active or event.xdata is None or event.ydata is None:
            return
        scale = 1 / 1.3 if event.button == "up" else 1.3
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        x, y = event.xdata, event.ydata
        new_w = (xlim[1] - xlim[0]) * scale
        new_h = (ylim[1] - ylim[0]) * scale
        relx = (xlim[1] - x) / (xlim[1] - xlim[0])
        rely = (ylim[1] - y) / (ylim[1] - ylim[0])
        ax.set_xlim([x - new_w * (1 - relx), x + new_w * relx])
        ax.set_ylim([y - new_h * (1 - rely), y + new_h * rely])
        fig.canvas.draw_idle()

    def _on_press(event):
        if event.inaxes is label_ax:
            return  # clicks inside the label box are the TextBox widget's own business
        handle_click(state, event)
        _redraw()

    def _on_motion(event):
        if not (state.erase_mode and state.erase_drag_start is not None):
            return
        if event.xdata is None or event.ydata is None:
            return
        rect = drag_rect["patch"]
        if rect is None:
            return
        x0, y0 = state.erase_drag_start
        x1, y1 = event.xdata, event.ydata
        rect.set_bounds(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        rect.set_visible(True)
        fig.canvas.draw_idle()  # cheap: just the patch, no full image re-render

    def _on_release(event):
        if event.inaxes is label_ax:
            return
        handle_release(state, event)
        _redraw()

    def _on_key(event):
        if state.label_active:
            return  # TextBox widget consumes its own keystrokes; nothing for us to do here
        handle_key(state, event)
        if state.done:
            plt.close(fig)
            return
        if state.label_active:
            # Just entered label mode ('a' with something unknown to ask) — the mask/overlay
            # hasn't changed, only the box needs to appear. Skip _update_overlay/title-redraw
            # entirely: a title-string draw_idle is enough.
            _sync_label_box()
            fig.canvas.draw_idle()
        elif event.key == "e":
            # Erase-mode toggle only changes the title text, not the mask/overlay — no need
            # to touch the overlay artist at all.
            ax.set_title(_title())
            fig.canvas.draw_idle()
        else:
            _redraw()

    _redraw()
    fig.canvas.mpl_connect("button_press_event", _on_press)
    fig.canvas.mpl_connect("motion_notify_event", _on_motion)
    fig.canvas.mpl_connect("button_release_event", _on_release)
    fig.canvas.mpl_connect("key_press_event", _on_key)
    fig.canvas.mpl_connect("scroll_event", _on_scroll)
    plt.show()

    return state
