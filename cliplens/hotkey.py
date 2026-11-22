"""Global hotkey registration (optional, best effort)."""

from __future__ import annotations


class HotkeyManager:
    def __init__(self, combination: str = "alt+t") -> None:
        self.combination = combination
        self._handle = None
        self._registered = False
        self.last_error = ""

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self, callback) -> bool:
        if self._registered:
            return True
        try:
            import keyboard  # imported lazily: it hooks the OS

            self._handle = keyboard.add_hotkey(
                self.combination, callback, suppress=False, trigger_on_release=False
            )
            self._registered = True
            return True
        except Exception as exc:  # noqa: BLE001 - optional OS integration
            self.last_error = str(exc)
            self._registered = False
            return False

    def unregister(self) -> None:
        if not self._registered:
            return
        try:
            import keyboard

            if self._handle is not None:
                keyboard.remove_hotkey(self._handle)
            else:
                keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        finally:
            self._registered = False
            self._handle = None
