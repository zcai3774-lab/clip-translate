from __future__ import annotations

import json

import pytest

from cliplens.config import (
    API_KEY_ENV,
    CONFIG_ENV,
    Config,
    ConfigError,
    default_config_path,
    language_label,
    mask_key,
)


def test_defaults_and_normalisation() -> None:
    cfg = Config(api_key="  sk-test  ", target_language="xx", max_chars=10)
    assert cfg.api_key == "sk-test"
    assert cfg.target_language == "auto"
    assert cfg.max_chars == 500

    cfg = Config(max_chars="not-a-number")  # type: ignore[arg-type]
    assert cfg.max_chars == 6000
    assert cfg.text_model == "glm-4-flash"
    assert cfg.vision_model == "glm-4v-flash"


def test_malformed_types_fall_back() -> None:
    cfg = Config(api_key=123, text_model=None, hotkey=None)  # type: ignore[arg-type]
    assert cfg.api_key == ""
    assert cfg.text_model == "glm-4-flash"
    assert cfg.hotkey == "alt+t"


def test_roundtrip(tmp_path) -> None:
    path = tmp_path / "nested" / "config.json"
    cfg = Config(
        api_key="sk-1234567890",
        target_language="ja",
        auto_clipboard=False,
        max_chars=9000,
    )
    cfg.save(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "path" not in raw
    assert raw["api_key"] == "sk-1234567890"

    loaded = Config.load(path)
    assert loaded.path == path
    assert loaded.api_key == "sk-1234567890"
    assert loaded.target_language == "ja"
    assert loaded.auto_clipboard is False
    assert loaded.max_chars == 9000


def test_corrupt_file_falls_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.api_key == ""
    assert cfg.target_language == "auto"
    assert cfg.path == path


def test_env_key_is_used_when_config_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "  sk-from-env  ")
    cfg = Config.load(tmp_path / "missing.json")
    assert cfg.effective_api_key() == "sk-from-env"
    assert cfg.has_api_key() is True


def test_saved_key_wins_over_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "sk-from-env")
    cfg = Config(api_key="sk-saved")
    assert cfg.effective_api_key() == "sk-saved"


def test_default_path_override(monkeypatch, tmp_path) -> None:
    target = tmp_path / "portable.json"
    monkeypatch.setenv(CONFIG_ENV, str(target))
    assert default_config_path() == target


def test_labels_and_masking() -> None:
    assert language_label("auto").startswith("自动")
    assert language_label("nope") == language_label("auto")
    assert mask_key("") == ""
    assert mask_key("short") == "•" * 5
    assert mask_key("sk-1234567890") == "sk-1…7890"


def test_save_error_is_wrapped(tmp_path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    cfg = Config(api_key="x")
    with pytest.raises(ConfigError) as exc:
        cfg.save(blocker / "config.json")
    assert "无法保存设置" in str(exc.value)
