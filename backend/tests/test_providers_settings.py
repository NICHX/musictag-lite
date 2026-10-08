"""Provider 注册表暴露与设置读写。"""

from __future__ import annotations


def test_list_providers(client) -> None:
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    providers = {item["key"]: item for item in resp.json()}
    assert {"musicbrainz", "coverart", "lrclib", "acoustid"} <= set(providers)
    assert providers["musicbrainz"]["enabled"] is True
    assert "metadata" in providers["musicbrainz"]["capabilities"]
    assert providers["acoustid"]["enabled"] is False  # 需 Key，默认关闭
    assert providers["lrclib"]["capabilities"] == ["lyrics"]


def test_update_provider(client) -> None:
    resp = client.patch("/api/providers/lrclib", json={"enabled": False, "priority": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["priority"] == 5

    # 未知 Provider → 404
    assert client.patch("/api/providers/unknown", json={"enabled": True}).status_code == 404

    # 还原
    client.patch("/api/providers/lrclib", json={"enabled": True, "priority": 30})


def test_settings_roundtrip(client) -> None:
    resp = client.patch("/api/settings", json={"values": {"theme": "dark", "language": "zh-CN"}})
    assert resp.status_code == 200
    assert resp.json()["values"]["theme"] == "dark"

    fetched = client.get("/api/settings").json()["values"]
    assert fetched["language"] == "zh-CN"


def test_logs_empty_page(client) -> None:
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
