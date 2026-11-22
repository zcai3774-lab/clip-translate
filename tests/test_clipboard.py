from __future__ import annotations

from cliplens.clipboard import ClipboardWatcher


def test_emits_new_text_once() -> None:
    values = iter(["  hello  ", "hello", "world"])
    seen: list[str] = []
    watcher = ClipboardWatcher(seen.append, read=lambda: next(values), min_length=2)

    assert watcher.poll_once() == "hello"
    assert watcher.poll_once() is None
    assert watcher.poll_once() == "world"
    assert seen == ["hello", "world"]


def test_ignores_short_and_empty_text() -> None:
    values = iter(["", "a", "   ", "okay"])
    seen: list[str] = []
    watcher = ClipboardWatcher(seen.append, read=lambda: next(values), min_length=3)

    assert watcher.poll_once() is None
    assert watcher.poll_once() is None
    assert watcher.poll_once() is None
    assert watcher.poll_once() == "okay"


def test_ignore_list_skips_once() -> None:
    seen: list[str] = []
    watcher = ClipboardWatcher(seen.append, read=lambda: "译文", min_length=1)
    watcher.ignore("译文")

    assert watcher.poll_once() is None
    assert seen == []


def test_disabled_watcher_does_not_emit() -> None:
    seen: list[str] = []
    watcher = ClipboardWatcher(seen.append, read=lambda: "hello", min_length=1)
    watcher.set_enabled(False)
    assert watcher.enabled is False
    assert watcher.poll_once() is None
    assert seen == []


def test_read_and_callback_errors_are_contained() -> None:
    def broken_read() -> str:
        raise RuntimeError("clipboard locked")

    watcher = ClipboardWatcher(lambda _text: None, read=broken_read)
    assert watcher.poll_once() is None

    def broken_callback(_text: str) -> None:
        raise RuntimeError("UI is gone")

    watcher = ClipboardWatcher(broken_callback, read=lambda: "hello", min_length=1)
    assert watcher.poll_once() is None


def test_ignore_does_not_leak_across_texts() -> None:
    seen: list[str] = []
    watcher = ClipboardWatcher(seen.append, read=lambda: "next", min_length=1)
    watcher.ignore("translation")
    assert watcher.poll_once() == "next"
    assert seen == ["next"]
