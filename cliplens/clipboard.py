"""Clipboard polling with de-duplication and an ignore list."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class ClipboardWatcher(threading.Thread):
    """Poll the clipboard and emit text that the user has not seen before.

    ``read`` is injectable so the polling logic can be unit-tested without a
    real clipboard.  The ignore list prevents our own "copy translation"
    action from being translated again.
    """

    def __init__(
        self,
        on_text: Callable[[str], None],
        interval: float = 0.6,
        min_length: int = 3,
        read: Callable[[], str] | None = None,
        name: str = "clipboard-watcher",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self._on_text = on_text
        self._interval = interval
        self._min_length = min_length
        self._read = read or _read_clipboard
        self._last_text: str | None = None
        self._ignored: deque[str] = deque(maxlen=30)
        self._enabled = threading.Event()
        self._enabled.set()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------- controls
    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self._enabled.set()
        else:
            self._enabled.clear()

    @property
    def enabled(self) -> bool:
        return self._enabled.is_set()

    def ignore(self, text: str) -> None:
        """Skip this exact text the next time it appears in the clipboard."""

        value = (text or "").strip()
        if value:
            with self._lock:
                self._ignored.append(value)

    def stop(self) -> None:
        self._stop_event.set()

    # ---------------------------------------------------------------- thread
    def run(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self._interval)

    def poll_once(self) -> str | None:
        """Read once; return the emitted text, if any (also handy for tests)."""

        try:
            raw = self._read()
        except Exception:
            # The clipboard is sometimes locked by another application.
            return None
        text = (raw or "").strip()
        if not text:
            return None
        if text == self._last_text:
            return None
        self._last_text = text

        with self._lock:
            if text in self._ignored:
                try:
                    self._ignored.remove(text)
                except ValueError:
                    pass
                return None

        if not self._enabled.is_set():
            return None
        if len(text) < self._min_length:
            return None
        try:
            self._on_text(text)
        except Exception:
            # A UI callback must never kill the watcher thread.
            return None
        return text


def _read_clipboard() -> str:
    import pyperclip

    return pyperclip.paste()
