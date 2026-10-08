"""AI 辅助解析测试（httpx.MockTransport，不产生真实请求）。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import get_settings
from app.services import ai_parser


def _client(handler) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def ai_settings(monkeypatch: pytest.MonkeyPatch):
    """临时把 AI 配置置为可用。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", True, raising=False)
    monkeypatch.setattr(settings, "ai_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "ai_base_url", "https://ai.example/v1", raising=False)
    monkeypatch.setattr(settings, "ai_model", "test-model", raising=False)
    return settings


async def test_parse_with_ai_sends_only_filename_and_parses_json(ai_settings) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"title":"1965","artist":"Zella Day",'
                            '"album":"Kicker","track_no":"3"}\n```'
                        }
                    }
                ]
            },
        )

    parsed = await ai_parser.parse_filename_with_ai(
        "1965 - Zella Day.flac", client=_client(handler)
    )

    assert seen["path"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "test-model"
    # 只发送文件名，不含路径
    assert seen["body"]["messages"][-1]["content"] == "1965 - Zella Day.flac"
    assert (parsed.title, parsed.artist, parsed.album, parsed.track_no) == (
        "1965",
        "Zella Day",
        "Kicker",
        3,
    )


async def test_parse_with_ai_handles_null_fields(ai_settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"title":"X","artist":null,"album":null,"track_no":null}'
                        }
                    }
                ]
            },
        )

    parsed = await ai_parser.parse_filename_with_ai("x.flac", client=_client(handler))
    assert parsed.title == "X"
    assert parsed.artist is None
    assert parsed.track_no is None


async def test_parse_with_ai_raises_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", False, raising=False)
    with pytest.raises(ai_parser.AIUnavailableError):
        await ai_parser.parse_filename_with_ai(
            "x.flac", client=_client(lambda r: httpx.Response(200))
        )


async def test_parse_with_ai_raises_on_bad_json(ai_settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "抱歉，我无法解析"}}]})

    with pytest.raises(ValueError):
        await ai_parser.parse_filename_with_ai("x.flac", client=_client(handler))


def test_is_ai_available_reflects_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", True, raising=False)
    monkeypatch.setattr(settings, "ai_api_key", "k", raising=False)
    assert ai_parser.is_ai_available() is True
    monkeypatch.setattr(settings, "ai_api_key", None, raising=False)
    assert ai_parser.is_ai_available() is False
