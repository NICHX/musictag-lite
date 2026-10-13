"""对外 API（/api/open）与 Token 鉴权。"""

from __future__ import annotations


def test_open_api_requires_token(client) -> None:
    # 未生成令牌前，对外 API 不可用
    assert client.get("/api/open/health").status_code == 403

    # 读取令牌（首次访问自动生成并启用）
    token_body = client.get("/api/settings/api-token").json()
    token = token_body["token"]
    assert token
    assert token_body["enabled"] is True

    # 无令牌 → 401
    assert client.get("/api/open/health").status_code == 401

    # 错误令牌 → 401
    assert (
        client.get("/api/open/health", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )

    # Bearer 正确令牌 → 200
    ok = client.get("/api/open/health", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200

    # X-API-Token 亦可
    ok2 = client.get("/api/open/health", headers={"X-API-Token": token})
    assert ok2.status_code == 200


def test_open_api_index_and_regenerate(client) -> None:
    token = client.get("/api/settings/api-token").json()["token"]

    index = client.get("/api/open", headers={"X-API-Token": token})
    assert index.status_code == 200
    assert "endpoints" in index.json()

    # 重新生成令牌后旧令牌失效
    new_token = client.patch("/api/settings/api-token", json={"regenerate": True}).json()["token"]
    assert new_token != token
    assert client.get("/api/open", headers={"X-API-Token": token}).status_code == 401
    assert client.get("/api/open", headers={"X-API-Token": new_token}).status_code == 200


def test_open_api_can_be_disabled(client) -> None:
    token = client.get("/api/settings/api-token").json()["token"]
    client.patch("/api/settings/api-token", json={"enabled": False})
    assert client.get("/api/open/health", headers={"X-API-Token": token}).status_code == 403
    # 还原
    client.patch("/api/settings/api-token", json={"enabled": True})
    assert client.get("/api/open/health", headers={"X-API-Token": token}).status_code == 200
