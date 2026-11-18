"""
Progress feedback for Generate, using Fusion's own progress dialog.

Generate runs on Fusion's main thread, so the palette cannot repaint while it
works. Fusion's ProgressDialog can: it is updated from inside the loop that is
doing the work, and it has a Cancel button.

Every call here is safe to make when no dialog is available (progress turned
off, or the dialog failed to open). Progress must never be the reason a
Generate fails.
"""

import time
from typing import Any, Optional


class GenerationCancelled(Exception):
    """Raised inside a node when the user clicks Cancel in the progress dialog."""


class GenerateProgress:
    # Don't touch the dialog more often than this. Setting its values is cheap.
    MIN_UPDATE_INTERVAL_S = 0.5
    # Letting Fusion process events is what repaints the dialog and notices a
    # Cancel click, but it also redraws the viewport, which slows as bodies are
    # added (over 100 ms each with 1600 bodies). So it happens this rarely.
    PUMP_INTERVAL_S = 2.0
    # Fusion only shows the dialog if the work lasts longer than this, so quick
    # Generates never flash a dialog.
    SHOW_DELAY_S = 1

    def __init__(self, ui: Any = None, enabled: bool = True, clock=time.monotonic):
        self._ui = ui if enabled else None
        self._dialog = None
        self._clock = clock
        self._last_update = 0.0
        self._last_pump = None  # Clock time of the last event pump
        self._node_label = ''
        self._cancelled = False

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self, total_nodes: int) -> None:
        """Open the dialog for a Generate of `total_nodes` nodes."""
        if not self._ui or total_nodes <= 0:
            return
        try:
            dialog = self._ui.createProgressDialog()
            dialog.cancelButtonText = 'Cancel'
            dialog.isCancelButtonShown = True
            dialog.isBackgroundTranslucent = False
            dialog.show('Noodle', 'Generating…', 0, total_nodes, self.SHOW_DELAY_S)
            self._dialog = dialog
        except Exception:
            self._dialog = None

    def finish(self) -> None:
        """Close the dialog. Safe to call more than once."""
        dialog, self._dialog = self._dialog, None
        if dialog is not None:
            try:
                dialog.hide()
            except Exception:
                pass

    # ── reporting ────────────────────────────────────────────────────────────
    def node(self, index: int, total: int, name: str) -> None:
        """Report that node `index` (1-based) of `total` is about to run."""
        self._node_label = f'{name} ({index} of {total})'
        self._set(self._node_label, value=index - 1, maximum=total, force=True)
        self.check_cancelled()

    def step(self, done: int, total: int, what: str = 'bodies') -> None:
        """Report progress inside the current node, e.g. bodies created so far.

        Call this once per item. It throttles itself, and raises
        GenerationCancelled if the user clicked Cancel.
        """
        if self._dialog is None:
            return
        now = self._clock()
        if done < total and now - self._last_update < self.MIN_UPDATE_INTERVAL_S:
            return
        self._set(f'{self._node_label}\n{done} of {total} {what}', value=done, maximum=total, force=True)
        self.check_cancelled()

    def check_cancelled(self) -> None:
        """Raise GenerationCancelled if the user clicked Cancel.

        Fusion only sees the click when events are pumped, so this checks at
        most every PUMP_INTERVAL_S.
        """
        if self._dialog is None:
            return
        now = self._clock()
        if self._last_pump is not None and now - self._last_pump < self.PUMP_INTERVAL_S:
            return
        self._last_pump = now
        try:
            self._pump_events()
            cancelled = bool(self._dialog.wasCancelled)
        except Exception:
            return
        if cancelled:
            self._cancelled = True
            raise GenerationCancelled('Generate was cancelled.')

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    # ── internals ────────────────────────────────────────────────────────────
    def _set(self, message: str, value: Optional[int] = None, maximum: Optional[int] = None,
             force: bool = False) -> None:
        if self._dialog is None:
            return
        now = self._clock()
        if not force and now - self._last_update < self.MIN_UPDATE_INTERVAL_S:
            return
        self._last_update = now
        try:
            if maximum is not None:
                self._dialog.maximumValue = max(1, int(maximum))
            if value is not None:
                self._dialog.progressValue = int(value)
            self._dialog.message = message
        except Exception:
            # A dialog that stops accepting updates is dropped; the Generate carries on.
            self._dialog = None

    @staticmethod
    def _pump_events() -> None:
        """Let Fusion process the Cancel click and repaint the dialog."""
        import adsk  # type: ignore
        adsk.doEvents()
