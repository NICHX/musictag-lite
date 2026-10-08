"""曲目列表/详情/facets 与未实现接口的契约（501 + 里程碑头）。"""

from __future__ import annotations


def test_tracks_list_empty_page(client) -> None:
    resp = client.get("/api/tracks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1


def test_tracks_list_accepts_filters(client) -> None:
    resp = client.get(
        "/api/tracks",
        params={
            "q": "hello",
            "format": "FLAC",
            "has_cover": "true",
            "sort": "size",
            "order": "desc",
        },
    )
    assert resp.status_code == 200


def test_tracks_facets(client) -> None:
    resp = client.get("/api/tracks/facets")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("formats", "years", "artists", "tag_status", "has_cover", "has_lyrics"):
        assert key in body


def test_track_not_found(client) -> None:
    assert client.get("/api/tracks/424242").status_code == 404


def test_scrape_search_not_implemented(client) -> None:
    resp = client.post("/api/scrape/search", json={"track_id": 1})
    assert resp.status_code == 501
    assert resp.headers.get("X-Milestone") == "M1"


def test_covers_and_lyrics_not_implemented(client) -> None:
    assert client.get("/api/tracks/1/cover").status_code == 501
    assert client.get("/api/tracks/1/lyrics").status_code == 501


def test_organize_not_implemented_m2(client) -> None:
    resp = client.post("/api/organize/preview", json={"ids": [], "template": "{title}"})
    assert resp.status_code == 501
    assert resp.headers.get("X-Milestone") == "M2"


def test_convert_without_ffmpeg(client) -> None:
    resp = client.post("/api/convert", json={"ids": [], "target_format": "mp3"})
    # 未安装 ffmpeg → 400；若环境已装 ffmpeg → 501
    assert resp.status_code in (400, 501)
