from pathlib import Path

import pytest

from physics_vault_api.services.ai_http_client import (
    AiHttpClient,
    DashScopeNativeOcrClient,
    _normalize_dashscope_native_base_url,
)


def test_parse_document_image_keeps_ai_call_error(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"fake image bytes")
    client = AiHttpClient(
        base_url="https://example.test/v1",
        api_key="test",
        model_name="qwen3.5-ocr",
    )

    def fail_call(*_args, **_kwargs):
        raise RuntimeError("AI API 认证失败 (HTTP 403)：Model access denied")

    monkeypatch.setattr(client, "_call", fail_call)

    with pytest.raises(RuntimeError, match="Model access denied"):
        client.parse_document(str(image), "png")


def test_dashscope_native_ocr_client_parses_json_response(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"fake image bytes")
    client = DashScopeNativeOcrClient(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        api_key="test",
        model_name="qwen-vl-ocr",
    )

    monkeypatch.setattr(
        client,
        "_call_native",
        lambda _content: '{"questions":[{"question_id":"q1","title":"测试题","options":[]}]}',
    )

    result = client.parse_document(str(image), "png")

    assert result["document_type"] == "image"
    assert result["questions"][0]["question_id"] == "q1"


def test_dashscope_native_ocr_client_test_connection_calls_provider(monkeypatch) -> None:
    client = DashScopeNativeOcrClient(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        api_key="test",
        model_name="qwen-vl-ocr",
    )
    seen: dict[str, object] = {}

    def fake_call(content):
        seen["content"] = content
        return "ok"

    monkeypatch.setattr(client, "_call_native", fake_call)

    client.test_connection()

    content = seen["content"]
    assert isinstance(content, list)
    assert content[0]["image"].startswith("https://")
    assert content[1]["text"]


def test_dashscope_native_base_url_migrates_compatible_mode() -> None:
    assert (
        _normalize_dashscope_native_base_url("https://dashscope.aliyuncs.com/compatible-mode/v1")
        == "https://dashscope.aliyuncs.com/api/v1"
    )


def test_parse_content_wraps_json_array_as_items() -> None:
    result = AiHttpClient._parse_content(
        '[{"question_id":"q1","tags":["力学"]},{"question_id":"q2","source":"月考"}]'
    )

    assert result == {
        "items": [
            {"question_id": "q1", "tags": ["力学"]},
            {"question_id": "q2", "source": "月考"},
        ]
    }
