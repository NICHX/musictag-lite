"""AI 设置接口：脱敏读取、持久化、校验与生效性。"""

from __future__ import annotations

import pytest


@pytest.fixture
def ai_reset(client):
    """用例前后把 AI 设置恢复为默认关闭（数据库为 session 级共享）。"""

    def _reset() -> None:
        client.patch("/api/settings/ai", json={"enabled": False, "api_key": ""})

    _reset()
    yield
    _reset()


def test_default_is_off_and_no_key(client, ai_reset) -> None:
    body = client.get("/api/settings/ai").json()
    assert body["enabled"] is False
    assert body["has_api_key"] is False
    assert body["api_key_masked"] is None
    assert body["available"] is False
    assert client.get("/api/capabilities").json()["ai"] is False


def test_enable_without_key_is_rejected(client, ai_reset) -> None:
    resp = client.patch("/api/settings/ai", json={"enabled": True})
    assert resp.status_code == 400
    assert "API Key" in resp.json()["detail"]


def test_invalid_base_url_is_rejected(client, ai_reset) -> None:
    resp = client.patch("/api/settings/ai", json={"base_url": "ftp://example.com"})
    assert resp.status_code == 400
    assert "http" in resp.json()["detail"]


def test_key_is_masked_and_never_returned(client, ai_reset) -> None:
    resp = client.patch(
        "/api/settings/ai",
        json={"api_key": "sk-test-1234567890", "base_url": "https://ai.example/v1", "model": "m1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_api_key"] is True
    assert body["api_key_masked"] == "sk-***7890"
    assert "sk-test-1234567890" not in resp.text  # 不回传明文


def test_set_key_then_enable_makes_it_available(client, ai_reset) -> None:
    client.patch("/api/settings/ai", json={"api_key": "sk-abcdefghijk"})
    enabled = client.patch("/api/settings/ai", json={"enabled": True})
    assert enabled.json()["available"] is True
    assert client.get("/api/capabilities").json()["ai"] is True


def test_omitted_key_is_kept_and_empty_key_clears(client, ai_reset) -> None:
    client.patch("/api/settings/ai", json={"api_key": "sk-abcdefghijk"})

    kept = client.patch("/api/settings/ai", json={"model": "m2"}).json()
    assert kept["has_api_key"] is True
    assert kept["model"] == "m2"

    cleared = client.patch("/api/settings/ai", json={"api_key": ""}).json()
    assert cleared["has_api_key"] is False


def test_settings_persist_across_requests(client, ai_reset) -> None:
    client.patch("/api/settings/ai", json={"api_key": "sk-persist-9999", "model": "persisted"})
    body = client.get("/api/settings/ai").json()
    assert body["model"] == "persisted"
    assert body["has_api_key"] is True
    assert body["api_key_masked"] == "sk-***9999"
