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


def test_openapi_schema_only_public(client) -> None:
    """默认 /docs 只发布对外 /api/open，内部接口不进入契约（避免过度暴露）。"""
    schema = client.get("/api/openapi.json").json()
    assert schema["info"]["title"] == "MusicTag Lite"

    paths = schema["paths"]
    for path in (
        "/api/open/tracks",
        "/api/open/tracks/{track_id}",
        "/api/open/scrape/search",
        "/api/open/scrape/apply",
        "/api/open/providers",
    ):
        assert path in paths, path

    for internal in (
        "/api/libraries",
        "/api/tracks/batch",
        "/api/providers",
        "/api/settings",
        "/api/tasks",
        "/api/logs",
    ):
        assert internal not in paths, internal
