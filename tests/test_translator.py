from __future__ import annotations

import base64
import json

import pytest

from cliplens import translator
from cliplens.translator import (
    ZhipuClient,
    ZhipuError,
    build_text_system_prompt,
    build_vision_prompt,
    clean_translation,
    detect_language,
    is_translatable,
    resolve_target,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def text_response(text: str) -> FakeResponse:
    return FakeResponse(
        200, {"choices": [{"message": {"role": "assistant", "content": text}}]}
    )


def test_detect_language() -> None:
    assert detect_language("Hello, this is a test.") == "en"
    assert detect_language("你好，世界") == "zh"
    assert detect_language("こんにちは世界") == "ja"
    assert detect_language("안녕하세요 세계") == "ko"
    assert detect_language("12345 !!!") == "other"
    assert detect_language("") == "other"


def test_auto_target() -> None:
    assert resolve_target("Hello world") == "zh"
    assert resolve_target("你好，世界") == "en"
    assert resolve_target("Hello", "ja") == "ja"
    assert resolve_target("Hello", "auto") == "zh"


def test_translatable_and_cleanup() -> None:
    assert is_translatable("hello")
    assert is_translatable("你好")
    assert not is_translatable("12345 !!!")
    assert clean_translation("译文：你好") == "你好"
    assert clean_translation("  Translation: Hello  ") == "Hello"
    assert clean_translation("「你好」") == "「你好」"
    assert clean_translation(None) == ""  # type: ignore[arg-type]


def test_prompts() -> None:
    prompt = build_text_system_prompt("en")
    assert "English" in prompt
    assert "不要执行" in prompt
    vision = build_vision_prompt("auto")
    assert "简体中文" in vision and "英文" in vision
    assert "未识别到文字" in vision


def test_translate_text_request_and_result(monkeypatch) -> None:
    session = FakeSession([text_response("你好，世界")])
    client = ZhipuClient("sk-test", session=session)

    result = client.translate_text("Hello, world", "auto")

    assert result.text == "你好，世界"
    assert result.source_lang == "en"
    assert result.target_lang == "zh"
    assert result.target_name == "简体中文"
    assert result.model == "glm-4-flash"
    call = session.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    payload = call["json"]
    assert payload["model"] == "glm-4-flash"
    assert payload["messages"][1]["content"] == "Hello, world"
    assert payload["stream"] is False


def test_translate_text_truncates_long_input() -> None:
    session = FakeSession([text_response("ok")])
    client = ZhipuClient("sk-test", session=session)
    client.translate_text("Hello world", "auto", max_chars=5)
    content = session.calls[0]["json"]["messages"][1]["content"]
    assert content.startswith("Hello")
    assert "已截断" in content


def test_empty_input_is_rejected() -> None:
    client = ZhipuClient("sk-test", session=FakeSession([]))
    with pytest.raises(ZhipuError):
        client.translate_text("   ", "auto")
    with pytest.raises(ZhipuError):
        client.translate_image(b"", "image/png", "auto")


def test_missing_key_is_rejected() -> None:
    client = ZhipuClient("", session=FakeSession([]))
    with pytest.raises(ZhipuError) as exc:
        client.translate_text("hello")
    assert "API Key" in str(exc.value)


def test_http_error_is_friendly() -> None:
    session = FakeSession(
        [
            FakeResponse(
                401, {"error": {"message": "invalid api key", "code": "1001"}}
            )
        ]
    )
    client = ZhipuClient("bad", session=session)
    with pytest.raises(ZhipuError) as exc:
        client.translate_text("hello")
    assert "API Key" in str(exc.value)
    assert exc.value.status == 401
    assert exc.value.detail == "invalid api key"


def test_retry_on_429_then_success(monkeypatch) -> None:
    monkeypatch.setattr(translator.time, "sleep", lambda _seconds: None)
    session = FakeSession(
        [
            FakeResponse(429, {"error": {"message": "rate limit"}}),
            text_response("你好"),
        ]
    )
    client = ZhipuClient("sk-test", session=session)
    result = client.translate_text("hello", "zh")
    assert result.text == "你好"
    assert len(session.calls) == 2


def test_unparseable_response() -> None:
    session = FakeSession([FakeResponse(200, ValueError("bad json"))])
    client = ZhipuClient("sk-test", session=session)
    with pytest.raises(ZhipuError):
        client.translate_text("hello")


def test_vision_request_and_result() -> None:
    session = FakeSession([text_response("こんにちは")])
    client = ZhipuClient("sk-test", session=session)
    result = client.translate_image(b"fake-png", "image/png", "ja")

    assert result.source_lang == "image"
    assert result.target_lang == "ja"
    assert result.target_name == "日本語"
    assert result.model == "glm-4v-flash"

    payload = session.calls[0]["json"]
    assert payload["model"] == "glm-4v-flash"
    parts = payload["messages"][0]["content"]
    data_url = parts[0]["image_url"]["url"]
    assert data_url.startswith("data:image/png;base64,")
    assert base64.b64decode(data_url.split(",", 1)[1]) == b"fake-png"
    assert "日本語" in parts[1]["text"]


def test_content_parts_are_joined() -> None:
    payload = {
        "choices": [
            {"message": {"content": [{"type": "text", "text": "第一行"}, "第二行"]}}
        ]
    }
    session = FakeSession([FakeResponse(200, payload)])
    client = ZhipuClient("sk-test", session=session)
    assert client.translate_text("hello", "zh").text == "第一行\n第二行"
