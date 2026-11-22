"""Full-screen region selection and screenshot preparation."""

from __future__ import annotations

import ctypes
import io
import sys
import tkinter as tk
from dataclasses import dataclass
from typing import Callable

import mss
from PIL import Image, ImageEnhance, ImageTk

ACCENT = "#5B8CFF"
TEXT = "#F2F5FA"
MUTED = "#9AA4B8"
OVERLAY_TEXT_BG = "#11151D"


def enable_dpi_awareness() -> None:
    """Make Tk and mss agree on physical pixels on scaled Windows displays."""

    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class CaptureResult:
    image: Image.Image
    data: bytes
    mime: str
    bbox: tuple[int, int, int, int]


def grab_virtual_screen() -> tuple[Image.Image, dict]:
    with mss.mss() as sct:
        monitor = dict(sct.monitors[0])
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return image, monitor


def prepare_image(image: Image.Image, max_side: int = 2400) -> tuple[bytes, str]:
    """Shrink very large captures and return bytes below the API size limit."""

    image = image.convert("RGB")
    width, height = image.size
    scale = min(1.0, max_side / max(width, height))
    if scale < 1.0:
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    data = buffer.getvalue()
    if len(data) <= 4_500_000:
        return data, "image/png"

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue(), "image/jpeg"


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
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


class RegionSelector:
    """A borderless overlay that lets the user drag a rectangle.

    The screen is captured *before* the overlay appears and then dimmed, so
    the final crop can never contain the selection UI itself.
    """

    def __init__(
        self,
        master: tk.Misc,
        on_done: Callable[[CaptureResult], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self.master = master
        self.on_done = on_done
        self.on_cancel = on_cancel
        self._done = False
        self._start: tuple[int, int] | None = None
        self._rect = None
        self._last_x = 0
        self._last_y = 0

        self.screen, self.monitor = grab_virtual_screen()
        dimmed = ImageEnhance.Brightness(self.screen).enhance(0.42)

        self.top = tk.Toplevel(master)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="black")
        self.top.geometry(
            f"{self.monitor['width']}x{self.monitor['height']}"
            f"+{self.monitor['left']}+{self.monitor['top']}"
        )

        self.canvas = tk.Canvas(
            self.top,
            width=self.monitor["width"],
            height=self.monitor["height"],
            highlightthickness=0,
            bd=0,
            bg="black",
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self._photo = ImageTk.PhotoImage(dimmed)
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        self._draw_hint()
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", lambda _event: self._cancel())
        self.top.bind("<Escape>", lambda _event: self._cancel())

        self.top.deiconify()
        self.top.update_idletasks()
        self.top.lift()
        self.top.focus_force()
        try:
            self.top.grab_set()
        except tk.TclError:
            pass

    # -------------------------------------------------------------- drawing
    def _draw_hint(self) -> None:
        width = self.monitor["width"]
        x1, x2 = width / 2 - 270, width / 2 + 270
        y1, y2 = 18, 102
        _round_rect(
            self.canvas, x1, y1, x2, y2, 14,
            fill=OVERLAY_TEXT_BG, outline="#2A3345", width=1,
        )
        self.canvas.create_text(
            width / 2, y1 + 25, text="拖动鼠标框选要翻译的区域",
            fill=TEXT, font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.canvas.create_text(
            width / 2, y1 + 59, text="松开鼠标开始识别并翻译   ·   Esc / 右键取消",
            fill=MUTED, font=("Microsoft YaHei UI", 9),
        )

    def _on_press(self, event: tk.Event) -> None:
        if self._done:
            return
        self._start = (event.x, event.y)
        self._last_x, self._last_y = event.x, event.y
        self.canvas.delete("sel")
        self._rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=ACCENT, width=2, fill=ACCENT, stipple="gray12",
        )
        self._draw_size_badge(event.x, event.y, 0, 0)

    def _on_drag(self, event: tk.Event) -> None:
        if self._start is None or self._done:
            return
        x0, y0 = self._start
        x1 = max(0, min(event.x, self.monitor["width"]))
        y1 = max(0, min(event.y, self.monitor["height"]))
        self._last_x, self._last_y = x1, y1
        self.canvas.coords(self._rect, x0, y0, x1, y1)
        self.canvas.delete("sel_extra")
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)
        size = 4
        for cx, cy in ((left, top), (right, top), (left, bottom), (right, bottom)):
            self.canvas.create_rectangle(
                cx - size, cy - size, cx + size, cy + size,
                fill=ACCENT, outline="", tags="sel_extra",
            )
        self._draw_size_badge(left, top, right - left, bottom - top)

    def _draw_size_badge(self, left: int, top: int, width: int, height: int) -> None:
        self.canvas.delete("sel_size")
        if self._start is None:
            return
        x = max(8, min(left, self.monitor["width"] - 150))
        y = top - 32
        if y < 92:
            y = top + 10
        label = f"{max(0, width)} × {max(0, height)}"
        self.canvas.create_rectangle(
            x, y, x + 112, y + 24, fill=OVERLAY_TEXT_BG,
            outline="#35405A", width=1, tags="sel_size",
        )
        self.canvas.create_text(
            x + 10, y + 12, anchor="w", text=label, fill=TEXT,
            font=("Cascadia Mono", 9), tags="sel_size",
        )

    def _on_release(self, event: tk.Event) -> None:
        if self._start is None or self._done:
            return
        x0, y0 = self._start
        x1 = max(0, min(event.x, self.monitor["width"]))
        y1 = max(0, min(event.y, self.monitor["height"]))
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)
        if right - left < 8 or bottom - top < 8:
            self.canvas.delete("sel")
            self.canvas.delete("sel_extra")
            self.canvas.delete("sel_size")
            self._start = None
            return

        self._done = True
        crop = self.screen.crop((left, top, right, bottom))
        data, mime = prepare_image(crop)
        bbox = (
            self.monitor["left"] + left,
            self.monitor["top"] + top,
            self.monitor["left"] + right,
            self.monitor["top"] + bottom,
        )
        result = CaptureResult(image=crop, data=data, mime=mime, bbox=bbox)
        self._teardown()
        self.master.after(20, lambda: self.on_done(result))

    def _cancel(self) -> None:
        if self._done:
            return
        self._done = True
        self._teardown()
        if self.on_cancel is not None:
            self.master.after(20, self.on_cancel)

    def _teardown(self) -> None:
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
