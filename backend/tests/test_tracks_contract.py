"""曲目列表/详情/facets 与整理/转换接口的契约（输入校验 + 待实现里程碑头）。"""

from __future__ import annotations


def test_tracks_list_empty_page(client) -> None:
    resp = client.get("/api/tracks", params={"library_id": 999999})
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
    for key in (
        "formats",
        "years",
        "artists",
        "tag_status",
        "has_cover",
        "has_lyrics",
        "has_word_lyrics",
    ):
        assert key in body


def test_tracks_ids(client) -> None:
    resp = client.get("/api/tracks/ids", params={"has_cover": "false"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"ids", "total"}
    assert isinstance(body["ids"], list)


def test_track_not_found(client) -> None:
    assert client.get("/api/tracks/424242").status_code == 404


def test_scrape_search_requires_track_or_query(client) -> None:
    # 缺少查询条件 → 400
    assert client.post("/api/scrape/search", json={}).status_code == 400
    # 曲目不存在 → 404（刮削搜索已在 M1 实现，此处不触发网络）
    assert client.post("/api/scrape/search", json={"track_id": 999999}).status_code == 404


def test_covers_and_lyrics_missing_track(client) -> None:
    # 曲目不存在 → 404（封面/歌词读写已在 M1 实现）
    assert client.get("/api/tracks/999999/cover").status_code == 404
    assert client.get("/api/tracks/999999/lyrics").status_code == 404


def test_organize_preview_requires_ids(client) -> None:
    # 整理（F15）已于 M2 落地；缺少目标曲目 → 400
    resp = client.post("/api/organize/preview", json={"ids": [], "template": "{title}"})
    assert resp.status_code == 400


def test_convert_without_ffmpeg(client) -> None:
    resp = client.post("/api/convert", json={"ids": [], "target_format": "mp3"})
    # 未安装 ffmpeg → 400；若环境已装 ffmpeg → 501
    assert resp.status_code in (400, 501)
