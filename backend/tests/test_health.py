"""健康检查与元信息接口。"""

from __future__ import annotations


def test_health(client) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["name"] == "MusicTag Lite"
    assert isinstance(body["ffmpeg"], bool)


def test_version_and_capabilities(client) -> None:
    assert client.get("/api/version").status_code == 200
    caps = client.get("/api/capabilities").json()
    assert set(caps) >= {"ffmpeg", "fpcalc"}


def test_openapi_schema(client) -> None:
    schema = client.get("/api/openapi.json").json()
    assert schema["info"]["title"] == "MusicTag Lite"
    # 关键路径均已纳入契约
    paths = schema["paths"]
    for path in (
        "/api/libraries",
        "/api/tracks",
        "/api/tracks/batch",
        "/api/providers",
        "/api/scrape/search",
        "/api/settings",
        "/api/logs",
        "/api/tasks",
    ):
        assert path in paths, path
