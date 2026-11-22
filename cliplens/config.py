"""Local configuration handling.

Only the API key and a few preferences are stored, in plain JSON under
``%APPDATA%\\ClipTranslate`` on Windows.  Nothing is uploaded anywhere except
the text / image the user explicitly asks to translate.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_DIR_NAME = "ClipTranslate"
CONFIG_ENV = "CLIPTRANSLATE_CONFIG"
API_KEY_ENV = "ZHIPUAI_API_KEY"

LANGUAGES: dict[str, str] = {
    "auto": "自动（中 ↔ 英）",
    "zh": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}
TARGET_ORDER: tuple[str, ...] = ("auto", "zh", "en", "ja", "ko")

DEFAULT_TEXT_MODEL = "glm-4-flash"
DEFAULT_VISION_MODEL = "glm-4v-flash"
DEFAULT_HOTKEY = "alt+t"


class ConfigError(RuntimeError):
    """Raised when the settings file cannot be written."""


def default_config_path() -> Path:
    """Return the per-user settings path (overridable for tests/portable use)."""

    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME / "config.json"
    return Path.home() / ".config" / APP_DIR_NAME.lower() / "config.json"


def language_label(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES["auto"])


@dataclass
class Config:
    """User settings.

    ``path`` is metadata and is never serialised.  It is populated by
    :meth:`load` so that a subsequent :meth:`save` writes to the same place.
    """

    api_key: str = ""
    target_language: str = "auto"
    auto_clipboard: bool = True
    text_model: str = DEFAULT_TEXT_MODEL
    vision_model: str = DEFAULT_VISION_MODEL
    hotkey: str = DEFAULT_HOTKEY
    max_chars: int = 6000
    path: Path | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        if not isinstance(self.api_key, str):
            self.api_key = ""
        self.api_key = self.api_key.strip()
        if not isinstance(self.target_language, str) or self.target_language not in LANGUAGES:
            self.target_language = "auto"
        if not isinstance(self.auto_clipboard, bool):
            self.auto_clipboard = True
        for attr, default in (
            ("text_model", DEFAULT_TEXT_MODEL),
            ("vision_model", DEFAULT_VISION_MODEL),
            ("hotkey", DEFAULT_HOTKEY),
        ):
            value = getattr(self, attr)
            if not isinstance(value, str) or not value.strip():
                setattr(self, attr, default)
            else:
                setattr(self, attr, value.strip())
        try:
            self.max_chars = max(500, min(int(self.max_chars), 20_000))
        except (TypeError, ValueError):
            self.max_chars = 6000

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Config":
        config_path = Path(path) if path is not None else default_config_path()
        data: dict = {}
        try:
            raw = config_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # A corrupt config should never prevent the app from starting.
            data = {}

        allowed = {f.name for f in fields(cls) if f.name != "path"}
        cfg = cls(**{k: v for k, v in data.items() if k in allowed})
        cfg.path = config_path
        return cfg

    def save(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path is not None else (self.path or default_config_path())
        payload = {k: v for k, v in asdict(self).items() if k != "path"}
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, target)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise ConfigError(f"无法保存设置：{exc}") from exc
        self.path = target
        return target

    def effective_api_key(self) -> str:
        """Prefer the key saved in the UI, then ``ZHIPUAI_API_KEY``."""

        return self.api_key or os.environ.get(API_KEY_ENV, "").strip()

    def has_api_key(self) -> bool:
        return bool(self.effective_api_key())


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"
