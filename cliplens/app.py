"""Application entry point."""

from __future__ import annotations

import argparse
import ctypes
import sys
import tkinter as tk

from . import APP_TITLE, __version__
from .capture import enable_dpi_awareness
from .config import Config
from .ui import ClipTranslateApp


def _set_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ClipTranslate.Desktop.0.1"
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cliplens",
        description="瞬译 ClipTranslate - 复制即译，截图即译",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="使用内置示例启动，不读取配置也不调用 API",
    )
    parser.add_argument(
        "--version", action="version", version=f"{APP_TITLE} {__version__}"
    )
    args = parser.parse_args(argv)

    enable_dpi_awareness()
    _set_app_id()

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"无法创建窗口：{exc}", file=sys.stderr)
        return 1

    config = Config() if args.demo else Config.load()
    ClipTranslateApp(root, config, demo=args.demo)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
