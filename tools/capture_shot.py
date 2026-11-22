"""Render the demo window and save a clean, DPI-correct screenshot."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cliplens.capture import enable_dpi_awareness  # noqa: E402
from cliplens.config import Config  # noqa: E402
from cliplens.ui import ClipTranslateApp  # noqa: E402


def main() -> int:
    enable_dpi_awareness()
    root = tk.Tk()
    ClipTranslateApp(root, Config(), demo=True)

    def snap() -> None:
        root.update_idletasks()
        root.update()
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        w = root.winfo_width()
        h = root.winfo_height()
        print(f"client={w}x{h} at {x},{y} screen={root.winfo_screenwidth()}x{root.winfo_screenheight()} scaling={root.tk.call('tk', 'scaling')}")
        out = ROOT / "docs" / "app.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(out)
        print(f"saved {out}")
        root.destroy()

    root.after(1200, snap)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
