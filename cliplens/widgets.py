"""Small hand-drawn Tk widgets used by the main window."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

ACCENT = "#5B8CFF"
ACCENT_HOVER = "#6D9AFF"
TEXT = "#E8ECF4"
MUTED = "#8B95AB"
CARD = "#171B25"
CARD_HOVER = "#1E2431"
BORDER = "#283044"


def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    """Draw a rounded rectangle using a smoothed polygon."""

    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class PillButton(tk.Canvas):
    """A flat, rounded button that matches the dark palette."""

    def __init__(
        self,
        master,
        text: str,
        command,
        kind: str = "primary",
        height: int = 38,
        padx: int = 16,
        font=None,
    ) -> None:
        self._text = text
        self._command = command
        self._kind = kind
        self._height = height
        self._padx = padx
        self._font = font or ("Microsoft YaHei UI", 10, "bold")
        self._bg = master.cget("bg")
        self._hover = False
        width = self._measure() + padx * 2
        super().__init__(
            master,
            width=width,
            height=height,
            bg=self._bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._render()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _measure(self) -> int:
        font = tkfont.Font(font=self._font)
        return font.measure(self._text)

    def _colors(self):
        if self._kind == "ghost":
            return (
                CARD_HOVER if self._hover else CARD,
                ACCENT if self._hover else BORDER,
                TEXT,
            )
        if self._kind == "subtle":
            return (CARD_HOVER if self._hover else "#10141C", "", MUTED)
        return (ACCENT_HOVER if self._hover else ACCENT, "", "#FFFFFF")

    def _render(self) -> None:
        self.delete("all")
        fill, outline, fg = self._colors()
        round_rect(
            self, 1, 1, self._width - 1, self._height - 1, 9,
            fill=fill, outline=outline, width=1 if outline else 0,
        )
        self.create_text(
            self._width / 2,
            self._height / 2,
            text=self._text,
            fill=fg,
            font=self._font,
        )

    @property
    def _width(self) -> int:
        return int(self.cget("width"))

    def set_text(self, text: str) -> None:
        self._text = text
        self.configure(width=self._measure() + self._padx * 2)
        self._render()

    def _click(self, _event) -> None:
        if callable(self._command):
            self._command()

    def _enter(self, _event) -> None:
        self._hover = True
        self._render()
        self.configure(cursor="hand2")

    def _leave(self, _event) -> None:
        self._hover = False
        self._render()


class ToggleSwitch(tk.Canvas):
    def __init__(self, master, value: bool = True, command=None, bg=None) -> None:
        self._value = bool(value)
        self._command = command
        self._bg = bg or master.cget("bg")
        super().__init__(
            master,
            width=42,
            height=24,
            bg=self._bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._draw()
        self.bind("<Button-1>", self._toggle)

    def _draw(self) -> None:
        self.delete("all")
        round_rect(
            self, 2, 3, 40, 21, 9,
            fill=ACCENT if self._value else "#3A4356",
            outline="",
        )
        cx = 30 if self._value else 12
        self.create_oval(cx - 7, 5, cx + 7, 19, fill="#FFFFFF", outline="")

    @property
    def value(self) -> bool:
        return self._value

    def set_value(self, value: bool) -> None:
        self._value = bool(value)
        self._draw()

    def _toggle(self, _event) -> None:
        self._value = not self._value
        self._draw()
        if callable(self._command):
            self._command(self._value)


class StatusPill(tk.Canvas):
    def __init__(self, master, text: str, fg: str, bg: str, font=None) -> None:
        self._text = text
        self._fg = fg
        self._bg = bg
        self._font = font or ("Microsoft YaHei UI", 9)
        width = tkfont.Font(font=self._font).measure(text) + 30
        super().__init__(
            master,
            width=width,
            height=26,
            bg=master.cget("bg"),
            highlightthickness=0,
            bd=0,
        )
        self._render()

    def _render(self) -> None:
        self.delete("all")
        round_rect(self, 1, 1, self._width - 1, 25, 9, fill=self._bg, outline="")
        self.create_text(
            15, 13, text="●", fill=self._fg, font=("Segoe UI", 8), anchor="w"
        )
        self.create_text(
            29, 13, text=self._text, fill=self._fg, font=self._font, anchor="w"
        )

    @property
    def _width(self) -> int:
        return int(self.cget("width"))

    def set_state(self, text: str, fg: str, bg: str) -> None:
        self._text = text
        self._fg = fg
        self._bg = bg
        width = tkfont.Font(font=self._font).measure(text) + 30
        self.configure(width=width)
        self._render()
