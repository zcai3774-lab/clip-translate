"""The main ClipTranslate window.

The UI is intentionally built from plain Tk widgets + a few small canvases.
That keeps startup instant, avoids a heavy theme dependency, and makes the
whole thing easy to read for anyone browsing the repository.
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import ttk

import pyperclip
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

from . import APP_TITLE, __version__
from .capture import CaptureResult, RegionSelector
from .clipboard import ClipboardWatcher
from .config import (
    API_KEY_ENV,
    TARGET_ORDER,
    Config,
    ConfigError,
    language_label,
)
from .hotkey import HotkeyManager
from .resources import resource_path
from .translator import TranslationResult, ZhipuClient, ZhipuError
from .widgets import PillButton, StatusPill, ToggleSwitch, round_rect

BG = "#0A0C11"
CARD = "#171B25"
CARD_DARK = "#10141C"
INPUT = "#0F131B"
BORDER = "#283044"
BORDER_LIGHT = "#33405A"
ACCENT = "#5B8CFF"
ACCENT_SOFT = "#7FA6FF"
TEXT = "#E8ECF4"
MUTED = "#8B95AB"
GREEN = "#54E0A6"
AMBER = "#F5B95C"
RED = "#FF7A8A"

FONT = "Microsoft YaHei UI"
MONO = "Cascadia Mono"

TARGET_SHORT = {
    "auto": "自动",
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}

SOURCE_NAMES = {
    "zh": "中文",
    "en": "EN",
    "ja": "日本語",
    "ko": "한국어",
    "other": "文本",
    "image": "截图",
}

API_KEYS_URL = "https://open.bigmodel.cn/usercenter/apikeys"


class ClipTranslateApp:
    def __init__(self, root: tk.Tk, config: Config, demo: bool = False) -> None:
        self.root = root
        self.config = config
        self.demo = demo

        self.events: queue.Queue = queue.Queue()
        self._closing = False
        self._poll_id: str | None = None
        self._pending = 0
        self._entry_count = 0
        self._thumbs: list[ImageTk.PhotoImage] = []
        self._selector: RegionSelector | None = None
        self._root_prev_state: str | None = None
        self._toast_label: tk.Label | None = None
        self._toast_after: str | None = None
        self._flash_after: str | None = None
        self._hotkey_error = ""

        self.watcher = ClipboardWatcher(
            self._on_clipboard_text, interval=0.55, min_length=2
        )
        self.hotkey = HotkeyManager(config.hotkey)
        self.target_var = tk.StringVar(value=config.target_language)

        self._setup_window()
        self._setup_styles()
        self._build()
        self._start_services()

        if demo:
            self._load_demo()
        elif self._hotkey_error:
            self._set_status(self._hotkey_error, "error")
        elif not config.has_api_key():
            self.root.after(400, self.key_entry.focus_set)
            self._set_status("请先填写智谱 API Key，然后复制文字或按 Alt+T", "muted")
        else:
            self._set_status("就绪 · 复制文字自动翻译，Alt+T 截图翻译", "muted")

    # --------------------------------------------------------------- window
    def _setup_window(self) -> None:
        self.root.title(APP_TITLE + (" · 预览" if self.demo else ""))
        self.root.configure(bg=BG)
        self.root.geometry("880x720")
        self.root.minsize(760, 620)
        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)
        ico = resource_path("cliplens/assets/icon.ico")
        if ico.exists() and sys.platform == "win32":
            try:
                self.root.iconbitmap(default=str(ico))
            except tk.TclError:
                pass
        icon = resource_path("cliplens/assets/icon.png")
        if icon.exists():
            try:
                self._icon = tk.PhotoImage(file=str(icon))
                self.root.iconphoto(True, self._icon)
            except tk.TclError:
                pass
        self.root.update_idletasks()
        width, height = 880, 720
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, min((screen_h - height) // 3, screen_h - height - 70))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.after(80, self._enable_dark_titlebar)

    def _enable_dark_titlebar(self) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            for attribute in (20, 19):  # Win11/10, then older Win10 builds
                value = ctypes.c_int(1)
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                if result == 0:
                    break
        except Exception:
            pass

    def _setup_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Vertical.TScrollbar",
            gripcount=0,
            background="#2A3346",
            darkcolor=CARD,
            lightcolor=CARD,
            troughcolor=CARD,
            bordercolor=CARD,
            arrowcolor=MUTED,
            width=9,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", "#3C4A66"), ("pressed", ACCENT)],
        )

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(fill="both", expand=True, padx=24, pady=20)

        self._build_header()
        self._build_key_card()
        self._build_toolbar()
        self._build_history()
        self._build_footer()

    def _build_header(self) -> None:
        header = tk.Frame(self.container, bg=BG)
        header.pack(fill="x")

        logo = tk.Canvas(header, width=46, height=46, bg=BG, highlightthickness=0)
        round_rect(
            logo, 1, 1, 45, 45, 13,
            fill="#16233D", outline="#2C4270", width=1,
        )
        logo.create_text(
            23, 21, text="译", fill=ACCENT_SOFT, font=(FONT, 18, "bold")
        )
        logo.create_oval(32, 31, 39, 38, fill=GREEN, outline="#16233D", width=2)
        logo.pack(side="left")

        title_box = tk.Frame(header, bg=BG)
        title_box.pack(side="left", padx=(12, 0))
        tk.Label(
            title_box, text="瞬译", fg=TEXT, bg=BG, font=(FONT, 17, "bold")
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="ClipTranslate · 复制即译，截图即译",
            fg=MUTED,
            bg=BG,
            font=(FONT, 9),
        ).pack(anchor="w", pady=(1, 0))

        self.status_pill = StatusPill(
            header, "待配置", AMBER, "#2A2113", font=(FONT, 9)
        )
        self.status_pill.pack(side="right", pady=8)

    def _build_key_card(self) -> None:
        self.key_card = tk.Frame(
            self.container,
            bg=CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        )
        self.key_card.pack(fill="x", pady=(18, 10))

        inner = tk.Frame(self.key_card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=12)

        top = tk.Frame(inner, bg=CARD)
        top.pack(fill="x")
        tk.Label(
            top, text="智谱 API Key", fg=TEXT, bg=CARD, font=(FONT, 10, "bold")
        ).pack(side="left")
        tk.Label(
            top,
            text="文本与视觉模型均使用免费额度",
            fg=MUTED,
            bg=CARD,
            font=(FONT, 8),
        ).pack(side="left", padx=(8, 0))

        link = tk.Label(
            top,
            text="免费获取 Key ↗",
            fg=ACCENT_SOFT,
            bg=CARD,
            font=(FONT, 8, "underline"),
            cursor="hand2",
        )
        link.pack(side="right")
        link.bind("<Button-1>", lambda _event: webbrowser.open(API_KEYS_URL))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x", pady=(9, 0))
        self.key_entry = tk.Entry(
            row,
            show="•",
            bg=INPUT,
            fg=TEXT,
            insertbackground=ACCENT,
            disabledbackground=INPUT,
            disabledforeground=MUTED,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=(MONO, 10),
            selectbackground="#2A3B60",
            selectforeground=TEXT,
        )
        self.key_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.save_btn = PillButton(
            row, "保存", self._save_key, kind="primary", height=35, padx=15
        )
        self.save_btn.pack(side="left", padx=(8, 0))
        self.test_btn = PillButton(
            row, "测试连接", self._test_connection, kind="ghost", height=35, padx=14
        )
        self.test_btn.pack(side="left", padx=(8, 0))

        self.key_note = tk.Label(
            inner,
            text="",
            fg=MUTED,
            bg=CARD,
            font=(FONT, 8),
            anchor="w",
        )
        self.key_note.pack(fill="x", pady=(6, 0))

        if self.demo:
            self.key_entry.insert(0, "demo-key-for-preview-only")
            self.key_note.configure(text="演示模式：不会读取、保存或发送任何 Key")
        elif self.config.api_key:
            self.key_entry.insert(0, self.config.api_key)
            self.key_note.configure(text="已保存到本机 · 可用“测试连接”验证")
        else:
            if os.environ.get(API_KEY_ENV, "").strip():
                self.key_note.configure(
                    text=f"已从环境变量 {API_KEY_ENV} 读取 Key（也可在上方保存一份）"
                )
            else:
                self.key_note.configure(
                    text="仅保存在本机配置文件中；除智谱 API 外不会发送到任何地方"
                )

    def _build_toolbar(self) -> None:
        toolbar = tk.Frame(self.container, bg=BG)
        toolbar.pack(fill="x", pady=(2, 12))

        self.shot_btn = PillButton(
            toolbar, "截图翻译", self._trigger_screenshot, kind="primary", height=40, padx=19
        )
        self.shot_btn.pack(side="left")

        keycap = tk.Label(
            toolbar,
            text="Alt + T",
            fg=MUTED,
            bg="#11151E",
            font=(MONO, 8),
            padx=8,
            pady=4,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        keycap.pack(side="left", padx=(8, 0))

        switch_box = tk.Frame(toolbar, bg=BG)
        switch_box.pack(side="left", padx=(18, 0))
        self.switch = ToggleSwitch(
            switch_box,
            value=self.config.auto_clipboard,
            command=self._on_toggle,
            bg=BG,
        )
        self.switch.pack(side="left")
        tk.Label(
            switch_box,
            text="复制后自动翻译",
            fg="#C3CBDD",
            bg=BG,
            font=(FONT, 9),
        ).pack(side="left", padx=(8, 0))

        self.target_btn = PillButton(
            toolbar,
            self._target_button_text(),
            self._open_target_menu,
            kind="ghost",
            height=36,
            padx=13,
        )
        self.target_btn.pack(side="right")

        self.target_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg="#171C27",
            fg=TEXT,
            activebackground=ACCENT,
            activeforeground="#FFFFFF",
            selectcolor=ACCENT,
            bd=0,
            font=(FONT, 9),
        )
        for code in TARGET_ORDER:
            self.target_menu.add_radiobutton(
                label=language_label(code),
                variable=self.target_var,
                value=code,
                command=self._on_target_change,
            )

    def _build_history(self) -> None:
        card = tk.Frame(
            self.container,
            bg=CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        card.pack(fill="both", expand=True)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=18, pady=(11, 7))
        self.history_title = tk.Label(
            head, text="翻译记录", fg=TEXT, bg=CARD, font=(FONT, 11, "bold")
        )
        self.history_title.pack(side="left")
        tk.Label(
            head,
            text="点击译文即可复制",
            fg=MUTED,
            bg=CARD,
            font=(FONT, 8),
        ).pack(side="left", padx=(9, 0))

        self.clear_btn = PillButton(
            head, "清空记录", self._clear_history, kind="subtle", height=26,
            padx=10, font=(FONT, 8),
        )
        self.clear_btn.pack(side="right")

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="both", expand=True)
        self.history_body = body

        scroll = ttk.Scrollbar(body, orient="vertical", style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y", padx=(0, 6), pady=(0, 8))
        self.text = tk.Text(
            body,
            wrap="word",
            bg=CARD,
            fg=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=18,
            pady=10,
            cursor="arrow",
            font=(FONT, 10),
            insertwidth=0,
            selectbackground="#2E4370",
            selectforeground=TEXT,
            inactiveselectbackground="#2E4370",
            exportselection=False,
            height=8,
            spacing1=0,
            spacing2=2,
            spacing3=0,
        )
        self.text.configure(yscrollcommand=scroll.set)
        scroll.configure(command=self.text.yview)
        self.text.pack(side="left", fill="both", expand=True)
        self.text.configure(state="disabled")

        self.text.tag_configure(
            "meta", foreground=MUTED, font=(FONT, 8), spacing1=8, spacing3=2
        )
        self.text.tag_configure(
            "source",
            foreground="#AEB8CB",
            font=(FONT, 9),
            lmargin1=1,
            lmargin2=1,
            rmargin=8,
            spacing3=3,
        )
        self.text.tag_configure(
            "trans",
            foreground=TEXT,
            font=(FONT, 11),
            lmargin1=1,
            lmargin2=1,
            rmargin=8,
            spacing3=9,
        )
        self.text.tag_configure("error", foreground=RED, font=(FONT, 10))

        self.empty = tk.Frame(body, bg=CARD)
        badge = tk.Canvas(self.empty, width=64, height=64, bg=CARD, highlightthickness=0)
        round_rect(
            badge, 2, 2, 62, 62, 17,
            fill="#141C2C", outline="#26334C", width=1,
        )
        badge.create_text(
            32, 30, text="译", fill=ACCENT_SOFT, font=(FONT, 21, "bold")
        )
        badge.pack()
        tk.Label(
            self.empty,
            text="复制即译，截图即译",
            fg="#D6DDEB",
            bg=CARD,
            font=(FONT, 12, "bold"),
        ).pack(pady=(10, 3))
        tk.Label(
            self.empty,
            text="在任意应用复制文字，或按 Alt+T 框选屏幕区域",
            fg=MUTED,
            bg=CARD,
            font=(FONT, 9),
        ).pack()
        self.empty_hint = tk.Label(
            self.empty,
            text="",
            fg="#6F7C94",
            bg=CARD,
            font=(FONT, 8),
        )
        self.empty_hint.pack(pady=(9, 0))
        self._show_empty()

    def _build_footer(self) -> None:
        footer = tk.Frame(self.container, bg=BG)
        footer.pack(fill="x", pady=(9, 0))
        self.status_label = tk.Label(
            footer,
            text="就绪",
            fg=MUTED,
            bg=BG,
            font=(FONT, 8),
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        tk.Label(
            footer,
            text=f"{self.config.text_model} · v{__version__}",
            fg="#5F6A80",
            bg=BG,
            font=(MONO, 8),
        ).pack(side="right")

    # ------------------------------------------------------------- services
    def _start_services(self) -> None:
        if self.demo:
            self.watcher.set_enabled(False)
            self.status_pill.set_state("演示模式", "#8FB3FF", "#16223D")
            return
        self.watcher.set_enabled(False)
        self.watcher.start()
        self._sync_listen_state()
        if not self.hotkey.register(lambda: self.events.put(("hotkey", ""))):
            self._hotkey_error = (
                "全局快捷键 Alt+T 注册失败，可点击“截图翻译”按钮；"
                "必要时以管理员身份运行"
            )
        self._poll_id = self.root.after(80, self._poll_events)

    def _poll_events(self) -> None:
        if self._closing:
            return
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        if not self._closing:
            self._poll_id = self.root.after(80, self._poll_events)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "clip":
            self._translate_clipboard(event[1])
        elif kind == "hotkey":
            if self._selector is not None:
                return
            if not self.config.has_api_key():
                self._ensure_visible()
                self._need_key()
                return
            self._trigger_screenshot()
        elif kind == "text_ok":
            self._on_text_ok(event[1], event[2])
        elif kind == "text_err":
            self._on_text_err(event[1], event[2])
        elif kind == "image_ok":
            self._on_image_ok(event[1], event[2])
        elif kind == "image_err":
            self._on_image_err(event[1], event[2])
        elif kind == "test_ok":
            self._pending = max(0, self._pending - 1)
            text, elapsed = event[1], event[2]
            self._toast(f"连接正常 · {elapsed:.1f}s · {text[:26]}")
            self._set_status("连接正常，模型可以使用", "success")
        elif kind == "test_err":
            self._pending = max(0, self._pending - 1)
            self._toast("连接失败，请检查 Key 或网络")
            self._set_status(event[1], "error")

    # ------------------------------------------------------------ clipboard
    def _on_clipboard_text(self, text: str) -> None:
        # Called from the watcher thread: only enqueue, never touch Tk here.
        self.events.put(("clip", text))

    def _translate_clipboard(self, text: str) -> None:
        if self.demo:
            return
        if not self.config.has_api_key():
            self._need_key()
            return
        if self._pending >= 3:
            self._set_status("正在翻译中，已跳过这次剪贴板变化", "busy")
            return
        target = self.config.target_language
        max_chars = self.config.max_chars
        self._pending += 1
        self._set_status(f"正在翻译剪贴板 · {len(text)} 字符", "busy")
        threading.Thread(
            target=self._run_text,
            args=(text, target, max_chars),
            daemon=True,
            name="cliplens-text",
        ).start()

    def _run_text(self, text: str, target: str, max_chars: int) -> None:
        try:
            result = ZhipuClient(
                self.config.effective_api_key(),
                self.config.text_model,
                self.config.vision_model,
            ).translate_text(text, target, max_chars)
            self.events.put(("text_ok", text, result))
        except ZhipuError as exc:
            self.events.put(("text_err", text, str(exc)))
        except Exception as exc:  # noqa: BLE001 - shown in the UI
            self.events.put(("text_err", text, f"翻译失败：{exc}"))

    def _on_text_ok(self, source_text: str, result: TranslationResult) -> None:
        self._pending = max(0, self._pending - 1)
        now = time.strftime("%H:%M")
        source_name = SOURCE_NAMES.get(result.source_lang, "文本")
        meta = (
            f"{now}  {source_name} → {result.target_name}"
            f"  ·  {result.model}  ·  {result.elapsed:.1f}s"
        )
        self._insert_entry(
            meta=meta,
            source=self._display_source(source_text),
            translation=result.text,
        )
        self._set_status("翻译完成 · 点击译文可复制", "success")

    def _on_text_err(self, source_text: str, message: str) -> None:
        self._pending = max(0, self._pending - 1)
        now = time.strftime("%H:%M")
        self._insert_entry(
            meta=f"{now}  剪贴板 · 翻译失败",
            source=self._display_source(source_text),
            translation=f"⚠ {message}",
            error=True,
        )
        self._set_status(message, "error")

    def _display_source(self, text: str) -> str:
        value = (text or "").strip()
        if len(value) > 700:
            value = value[:700].rstrip() + "\n……（原文较长，仅显示开头）"
        return value

    # ------------------------------------------------------------- screenshot
    def _trigger_screenshot(self) -> None:
        if self._closing:
            return
        if self.demo:
            self._toast("演示模式不会截图")
            return
        if not self.config.has_api_key():
            self._ensure_visible()
            self._need_key()
            return
        if self._selector is not None:
            return
        self._root_prev_state = self.root.state()
        if self._root_prev_state == "normal":
            self.root.withdraw()
        self.root.after(180, self._open_selector)

    def _open_selector(self) -> None:
        if self._closing:
            return
        try:
            self._selector = RegionSelector(
                self.root, self._on_capture_done, self._on_capture_cancel
            )
        except Exception as exc:  # noqa: BLE001 - capture is OS dependent
            self._selector = None
            self._restore_root()
            self._toast("截图失败，请重试")
            self._set_status(f"截图失败：{exc}", "error")

    def _on_capture_done(self, capture: CaptureResult) -> None:
        self._selector = None
        self._restore_root()
        if self._pending >= 3:
            self._toast("正在翻译，请稍候再截图")
            return
        self._pending += 1
        self._set_status("正在识别并翻译截图…", "busy")
        threading.Thread(
            target=self._run_image,
            args=(capture, self.config.target_language),
            daemon=True,
            name="cliplens-image",
        ).start()

    def _on_capture_cancel(self) -> None:
        self._selector = None
        self._restore_root()
        self._set_status("已取消截图", "muted")

    def _run_image(self, capture: CaptureResult, target: str) -> None:
        try:
            result = ZhipuClient(
                self.config.effective_api_key(),
                self.config.text_model,
                self.config.vision_model,
            ).translate_image(capture.data, capture.mime, target)
            self.events.put(("image_ok", capture, result))
        except ZhipuError as exc:
            self.events.put(("image_err", capture, str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("image_err", capture, f"截图翻译失败：{exc}"))

    def _on_image_ok(self, capture: CaptureResult, result: TranslationResult) -> None:
        self._pending = max(0, self._pending - 1)
        width, height = capture.image.size
        target = "自动识别" if result.target_lang == "auto" else result.target_name
        meta = (
            f"{time.strftime('%H:%M')}  截图 {width}×{height} → {target}"
            f"  ·  {result.model}  ·  {result.elapsed:.1f}s"
        )
        self._insert_entry(
            meta=meta,
            translation=result.text,
            thumbnail=self._make_thumb(capture.image),
        )
        if "未识别到文字" in result.text:
            self._set_status("截图里没有识别到文字，请重新框选", "muted")
        else:
            self._set_status("截图翻译完成 · 点击译文可复制", "success")

    def _on_image_err(self, capture: CaptureResult, message: str) -> None:
        self._pending = max(0, self._pending - 1)
        self._insert_entry(
            meta=f"{time.strftime('%H:%M')}  截图翻译失败",
            translation=f"⚠ {message}",
            thumbnail=self._make_thumb(capture.image),
            error=True,
        )
        self._set_status(message, "error")

    def _make_thumb(
        self, image: Image.Image, max_size: tuple[int, int] = (250, 130)
    ) -> Image.Image:
        thumb = ImageOps.contain(image.convert("RGB"), max_size)
        return ImageOps.expand(thumb, border=1, fill=BORDER)

    def _restore_root(self) -> None:
        if self._closing:
            return
        state = self._root_prev_state
        self._root_prev_state = None
        if state == "normal":
            self.root.deiconify()
            self.root.lift()
        elif state == "iconic":
            self.root.deiconify()
            self.root.iconify()

    def _ensure_visible(self) -> None:
        if self.root.state() in ("withdrawn", "iconic"):
            self.root.deiconify()
        self.root.lift()

    # ---------------------------------------------------------------- actions
    def _save_key(self) -> None:
        if self.demo:
            self._toast("演示模式不会保存设置")
            return
        key = self.key_entry.get().strip()
        if not key:
            self._toast("请先粘贴智谱 API Key")
            self.key_entry.focus_set()
            return
        old = self.config.api_key
        self.config.api_key = key
        if not self._persist():
            self.config.api_key = old
            return
        self.key_note.configure(text="已保存到本机 · 可用“测试连接”验证")
        self._sync_listen_state()
        self._toast("API Key 已保存")
        if self.config.auto_clipboard:
            self._set_status("Key 已保存，剪贴板监听已开启", "success")
        else:
            self._set_status("Key 已保存；自动翻译当前为关闭状态", "success")

    def _test_connection(self) -> None:
        if self.demo:
            self._toast("演示模式不会调用 API")
            return
        key = self.key_entry.get().strip() or self.config.effective_api_key()
        if not key:
            self._need_key()
            return
        if self._pending >= 3:
            self._toast("正在处理其他请求，请稍候")
            return
        self._pending += 1
        self._set_status("正在测试连接…", "busy")
        threading.Thread(
            target=self._run_test,
            args=(key,),
            daemon=True,
            name="cliplens-test",
        ).start()

    def _run_test(self, key: str) -> None:
        try:
            result = ZhipuClient(
                key, self.config.text_model, self.config.vision_model
            ).translate_text("Hello, world!", "zh")
            self.events.put(("test_ok", result.text, result.elapsed))
        except ZhipuError as exc:
            self.events.put(("test_err", str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("test_err", f"连接失败：{exc}"))

    def _on_toggle(self, value: bool) -> None:
        if self.demo:
            self.switch.set_value(not value)
            self._toast("演示模式不会保存设置")
            return
        old = self.config.auto_clipboard
        self.config.auto_clipboard = value
        if not self._persist():
            self.config.auto_clipboard = old
            self.switch.set_value(old)
            return
        self._sync_listen_state()
        if value:
            if self.config.has_api_key():
                self._set_status("已开启剪贴板监听", "success")
            else:
                self._set_status("已开启监听，填写并保存 API Key 后生效", "muted")
        else:
            self._set_status("已暂停剪贴板监听，截图翻译仍可使用", "muted")

    def _open_target_menu(self) -> None:
        if self.demo:
            self._toast("演示模式不会修改目标语言")
            return
        try:
            x = self.target_btn.winfo_rootx()
            y = self.target_btn.winfo_rooty() + self.target_btn.winfo_height() + 4
            self.target_menu.tk_popup(x, y)
        finally:
            self.target_menu.grab_release()

    def _on_target_change(self) -> None:
        code = self.target_var.get()
        old = self.config.target_language
        self.config.target_language = code
        if not self._persist():
            self.config.target_language = old
            self.target_var.set(old)
            return
        self.target_btn.set_text(self._target_button_text())
        self._set_status(f"目标语言：{language_label(code)}", "muted")

    def _target_button_text(self) -> str:
        label = TARGET_SHORT.get(self.config.target_language, "自动")
        return f"目标 · {label}  ▾"

    def _persist(self) -> bool:
        try:
            self.config.save()
            return True
        except ConfigError as exc:
            self._toast("设置保存失败")
            self._set_status(str(exc), "error")
            return False

    def _need_key(self) -> None:
        self._set_status("请先填写并保存智谱 API Key", "error")
        self._toast("请先填写 API Key")
        self._flash_key_card()
        self.key_entry.focus_set()

    def _flash_key_card(self) -> None:
        self.key_card.configure(highlightbackground=ACCENT)
        if self._flash_after is not None:
            try:
                self.root.after_cancel(self._flash_after)
            except tk.TclError:
                pass
        self._flash_after = self.root.after(
            1200, lambda: self.key_card.configure(highlightbackground=BORDER)
        )

    def _sync_listen_state(self) -> None:
        if self.demo:
            self.watcher.set_enabled(False)
            self.status_pill.set_state("演示模式", "#8FB3FF", "#16223D")
            return
        if not self.config.has_api_key():
            self.watcher.set_enabled(False)
            self.status_pill.set_state("待配置", AMBER, "#2A2113")
            self.empty_hint.configure(text="第一步：填写 API Key；之后复制任意文字即可")
        elif self.config.auto_clipboard:
            self.watcher.set_enabled(True)
            self.status_pill.set_state("监听中", GREEN, "#10251D")
            self.empty_hint.configure(text="正在监听剪贴板 · 复制一段文字试试")
        else:
            self.watcher.set_enabled(False)
            self.status_pill.set_state("已暂停", AMBER, "#2A2113")
            self.empty_hint.configure(text="自动翻译已暂停 · 截图翻译仍然可用")

    # ---------------------------------------------------------------- history
    def _insert_entry(
        self,
        meta: str,
        translation: str,
        source: str = "",
        thumbnail: Image.Image | None = None,
        error: bool = False,
    ) -> None:
        at_bottom = self.text.yview()[1] > 0.97
        self._hide_empty()
        self.text.configure(state="normal")
        if self._entry_count:
            self.text.insert("end", "\n")
        self.text.insert("end", meta + "\n", ("meta",))
        if thumbnail is not None:
            photo = ImageTk.PhotoImage(thumbnail)
            self._thumbs.append(photo)
            self.text.image_create("end", image=photo, padx=2, pady=5, align="top")
            self.text.insert("end", "\n")
        if source:
            self.text.insert("end", source + "\n", ("source",))

        tag = f"copy_{self._entry_count}"
        self.text.insert(
            "end",
            translation + "\n",
            ("trans", "error", tag) if error else ("trans", tag),
        )
        self.text.tag_bind(
            tag,
            "<Button-1>",
            lambda _event, value=translation: self._copy_translation(value),
        )
        self.text.tag_bind(
            tag, "<Enter>", lambda _event: self.text.configure(cursor="hand2")
        )
        self.text.tag_bind(
            tag, "<Leave>", lambda _event: self.text.configure(cursor="arrow")
        )
        self.text.configure(state="disabled")
        self._entry_count += 1
        self.history_title.configure(text=f"翻译记录 · {self._entry_count}")
        if at_bottom:
            self.text.see("end")

    def _show_empty(self) -> None:
        self.empty.place(relx=0.5, rely=0.48, anchor="center")
        self.empty.lift()
        if not hasattr(self, "empty_hint"):
            return
        if self.demo:
            self.empty_hint.configure(text="演示模式 · 不会调用 API")
        elif not self.config.has_api_key():
            self.empty_hint.configure(text="第一步：填写 API Key；之后复制任意文字即可")
        elif self.config.auto_clipboard:
            self.empty_hint.configure(text="正在监听剪贴板 · 复制一段文字试试")
        else:
            self.empty_hint.configure(text="自动翻译已暂停 · 截图翻译仍然可用")

    def _hide_empty(self) -> None:
        self.empty.place_forget()

    def _copy_translation(self, text: str) -> None:
        self.watcher.ignore(text)
        try:
            pyperclip.copy(text)
        except Exception:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update_idletasks()
            except tk.TclError:
                self._toast("复制失败，请手动选择译文")
                return
        self._toast("译文已复制")
        self._set_status("译文已复制到剪贴板", "success")

    def _clear_history(self) -> None:
        if self._entry_count == 0:
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._thumbs.clear()
        self._entry_count = 0
        self.history_title.configure(text="翻译记录")
        self._show_empty()
        self._set_status("翻译记录已清空", "muted")

    # ------------------------------------------------------------------ misc
    def _set_status(self, text: str, kind: str = "muted") -> None:
        value = " ".join(str(text).split())
        if len(value) > 80:
            value = value[:79] + "…"
        colors = {
            "muted": MUTED,
            "success": GREEN,
            "error": RED,
            "busy": ACCENT_SOFT,
        }
        self.status_label.configure(text=value, fg=colors.get(kind, MUTED))

    def _toast(self, message: str) -> None:
        if self._closing:
            return
        if self._toast_label is not None:
            try:
                self._toast_label.destroy()
            except tk.TclError:
                pass
            self._toast_label = None
        if self._toast_after is not None:
            try:
                self.root.after_cancel(self._toast_after)
            except tk.TclError:
                pass
        value = " ".join(str(message).split())
        if len(value) > 60:
            value = value[:59] + "…"
        label = tk.Label(
            self.root,
            text=value,
            fg="#DCE6FF",
            bg="#202B42",
            font=(FONT, 9),
            padx=14,
            pady=7,
            highlightthickness=1,
            highlightbackground="#38507F",
        )
        label.place(relx=0.5, y=12, anchor="n")
        label.lift()
        self._toast_label = label
        self._toast_after = self.root.after(2200, self._hide_toast)

    def _hide_toast(self) -> None:
        self._toast_after = None
        if self._toast_label is not None:
            try:
                self._toast_label.destroy()
            except tk.TclError:
                pass
            self._toast_label = None

    def _load_demo(self) -> None:
        self.switch.set_value(False)
        self.status_pill.set_state("演示模式", "#8FB3FF", "#16223D")
        self._set_status("演示模式 · 不调用 API、不写入配置；点击译文可以复制", "muted")
        self._insert_entry(
            meta="14:31  截图 520×180 → 自动识别  ·  glm-4v-flash  ·  1.6s",
            translation="深色模式 · 蓝色强调色",
            thumbnail=self._make_demo_thumb(),
        )
        self._insert_entry(
            meta="14:33  EN → 简体中文  ·  glm-4-flash  ·  0.9s",
            source="The best way to predict the future is to invent it.",
            translation="预测未来最好的方式，就是去创造它。",
        )
        self._hide_empty()

    def _make_demo_thumb(self) -> Image.Image:
        image = Image.new("RGB", (520, 180), "#0E121A")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (0, 0, 519, 179), radius=10, outline="#2B3550", width=2
        )
        try:
            title_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 19)
            body_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
            small_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 12)
        except OSError:
            title_font = body_font = small_font = ImageFont.load_default()
        draw.text((24, 18), "Appearance", font=title_font, fill="#E8ECF4")
        draw.text((24, 52), "Dark mode", font=body_font, fill="#B8C1D4")
        draw.rounded_rectangle((420, 50, 476, 76), radius=13, fill="#5B8CFF")
        draw.ellipse((450, 53, 473, 73), fill="#FFFFFF")
        draw.text((24, 88), "Accent color", font=body_font, fill="#B8C1D4")
        draw.ellipse((438, 90, 458, 110), fill="#5B8CFF")
        draw.text((24, 124), "Language", font=body_font, fill="#B8C1D4")
        draw.text((420, 126), "English (US)", font=small_font, fill="#8B95AB")
        draw.line((24, 154, 496, 154), fill="#20293C", width=1)
        return self._make_thumb(image, (180, 62))

    def _shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._poll_id is not None:
            try:
                self.root.after_cancel(self._poll_id)
            except tk.TclError:
                pass
        self.watcher.stop()
        self.hotkey.unregister()
        self._selector = None
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def run(config: Config, demo: bool = False) -> None:
    root = tk.Tk()
    ClipTranslateApp(root, config, demo=demo)
    root.mainloop()
