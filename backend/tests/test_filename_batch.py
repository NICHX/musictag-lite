"""F11 批量文件名解析：预演（按策略计算差异）与落盘。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.audio.mutagen_io import MutagenIO
from tests.audio_factory import make_flac

io = MutagenIO()
RICH = "Adele - 21 - 03 Rolling.flac"


def _wait_task(client, task_id: int, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/tasks/{task_id}").json()
        if data["status"] in {"succeeded", "failed", "cancelled"}:
            return data
        time.sleep(0.05)
    raise AssertionError(f"任务未在 {timeout}s 内完成：{task_id}")


@pytest.fixture
def library(client, tmp_path: Path) -> dict:
    album = tmp_path / "music" / "Various"
    album.mkdir(parents=True)
    make_flac(album / RICH)
    make_flac(album / "Dua Lipa - Levitating.flac")

    resp = client.post(
        "/api/libraries", json={"name": "解析库", "root_path": str(album.parents[0])}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scan(client, library_id: int) -> None:
    resp = client.post(f"/api/libraries/{library_id}/scan")
    task = _wait_task(client, resp.json()["task_id"])
    assert task["status"] == "succeeded", task


def _track(client, library_id: int) -> dict:
    items = client.get("/api/tracks", params={"library_id": library_id}).json()["items"]
    return next(t for t in items if t["filename"] == RICH)


def test_batch_parse_preview_then_apply(client, library) -> None:
    """启发式解析：预演不写盘，应用后标签落盘。"""
    _scan(client, library["id"])
    track = _track(client, library["id"])

    preview = client.post(
        "/api/tracks/parse-filename/preview",
        json={"ids": [track["id"]], "use_ai": False, "strategy": "fill_empty"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["changed"] == 1
    item = body["items"][0]
    assert item["status"] == "ok" and item["source"] == "heuristic"
    assert {d["field"] for d in item["diffs"]} == {"title", "artist", "album", "track_no"}
    # 预演不写盘
    assert io.read(Path(track["path"])).tags.title is None

    applied = client.post(
        "/api/tracks/parse-filename",
        json={"ids": [track["id"]], "use_ai": False, "strategy": "fill_empty"},
    )
    assert applied.status_code == 200, applied.text
    task = _wait_task(client, applied.json()["task_id"])
    assert task["status"] == "succeeded", task
    assert "写入 1" in (task["message"] or "")

    tags = io.read(Path(track["path"])).tags
    assert (tags.title, tags.artist, tags.album, tags.track_no) == ("Rolling", "Adele", "21", 3)


def test_batch_fill_empty_skips_existing_but_overwrite_replaces(client, library) -> None:
    """fill_empty 不覆盖已有值；overwrite 则以解析结果为准。"""
    _scan(client, library["id"])
    track = _track(client, library["id"])
    client.patch(f"/api/tracks/{track['id']}", json={"title": "Existing"})

    fill = client.post(
        "/api/tracks/parse-filename/preview",
        json={"ids": [track["id"]], "use_ai": False, "strategy": "fill_empty"},
    ).json()
    fill_fields = {d["field"] for d in fill["items"][0]["diffs"]}
    assert "title" not in fill_fields
    assert {"artist", "album", "track_no"} <= fill_fields

    over = client.post(
        "/api/tracks/parse-filename/preview",
        json={"ids": [track["id"]], "use_ai": False, "strategy": "overwrite"},
    ).json()
    title_diff = next(d for d in over["items"][0]["diffs"] if d["field"] == "title")
    assert title_diff["old_value"] == "Existing" and title_diff["new_value"] == "Rolling"


def test_batch_parse_marks_unchanged_after_apply(client, library) -> None:
    """已写入相同值后再次预演（fill_empty）→ 无变更。"""
    _scan(client, library["id"])
    track = _track(client, library["id"])
    applied = client.post(
        "/api/tracks/parse-filename",
        json={"ids": [track["id"]], "use_ai": False, "strategy": "overwrite"},
    )
    _wait_task(client, applied.json()["task_id"])

    again = client.post(
        "/api/tracks/parse-filename/preview",
        json={"ids": [track["id"]], "use_ai": False, "strategy": "fill_empty"},
    ).json()
    assert again["changed"] == 0 and again["unchanged"] == 1
    assert again["items"][0]["status"] == "unchanged"


def test_batch_parse_ai_unavailable_returns_400(client, library) -> None:
    """未配置 AI 时请求 AI 解析 → 400，且不启动任务。"""
    _scan(client, library["id"])
    track = _track(client, library["id"])
    resp = client.post(
        "/api/tracks/parse-filename/preview",
        json={"ids": [track["id"]], "use_ai": True, "strategy": "fill_empty"},
    )
    assert resp.status_code == 400
    assert "AI" in resp.json()["detail"]


def test_batch_parse_requires_ids(client) -> None:
    resp = client.post("/api/tracks/parse-filename/preview", json={"ids": [], "use_ai": False})
    assert resp.status_code == 422
