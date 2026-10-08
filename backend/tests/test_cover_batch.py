"""F20 封面批量替换：优先级链匹配预演 + 按指派写入内嵌封面。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.audio.mutagen_io import MutagenIO
from tests.audio_factory import JPEG_BYTES, make_flac

io = MutagenIO()

ALBUM_A = "01 Rolling.flac"
ALBUM_A2 = "02 Someone.flac"
ALBUM_B = "1965.flac"


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
    album_a = tmp_path / "music" / "Adele" / "21"
    album_a.mkdir(parents=True)
    make_flac(album_a / ALBUM_A)
    make_flac(album_a / ALBUM_A2)
    album_b = tmp_path / "music" / "Zella Day" / "Kicker"
    album_b.mkdir(parents=True)
    make_flac(album_b / ALBUM_B)

    resp = client.post(
        "/api/libraries", json={"name": "封面库", "root_path": str(album_a.parents[1])}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scan(client, library_id: int) -> None:
    resp = client.post(f"/api/libraries/{library_id}/scan")
    task = _wait_task(client, resp.json()["task_id"])
    assert task["status"] == "succeeded", task


def _tag(client, track: dict, **fields: object) -> None:
    assert client.patch(f"/api/tracks/{track['id']}", json=fields).status_code == 200


def _setup(client, library_id: int) -> dict[str, dict]:
    _scan(client, library_id)
    items = client.get("/api/tracks", params={"library_id": library_id, "page_size": 100}).json()[
        "items"
    ]
    by_name = {t["filename"]: t for t in items}
    a1, a2 = by_name[ALBUM_A], by_name[ALBUM_A2]
    _tag(client, a1, album_artist="Adele", artist="Adele", album="21")
    _tag(client, a2, album_artist="Adele", artist="Adele", album="21")
    _tag(client, by_name[ALBUM_B], album_artist="Zella Day", artist="Zella Day", album="Kicker")
    return by_name


def test_cover_batch_preview_priority_chain(client, library) -> None:
    by_name = _setup(client, library["id"])
    ids = [t["id"] for t in by_name.values()]

    resp = client.post(
        "/api/covers/batch-preview",
        json={
            "ids": ids,
            "filenames": ["01 Rolling.jpg", "Adele - 21.jpg", "Kicker.jpg", "nothing.jpg"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    matches = {m["index"]: m for m in body["matches"]}

    # 规则 1：与音频同 stem
    assert matches[0]["status"] == "ok" and matches[0]["match"] == "stem"
    assert matches[0]["track_ids"] == [by_name[ALBUM_A]["id"]]
    # 规则 2：{专辑艺术家} - {专辑}
    assert matches[1]["status"] == "ok" and matches[1]["match"] == "album"
    assert set(matches[1]["track_ids"]) == {by_name[ALBUM_A]["id"], by_name[ALBUM_A2]["id"]}
    # 规则 3：专辑名
    assert matches[2]["status"] == "ok" and matches[2]["match"] == "album_name"
    assert matches[2]["track_ids"] == [by_name[ALBUM_B]["id"]]
    # 规则 4：未命中
    assert matches[3]["status"] == "unmatched" and matches[3]["track_ids"] == []

    labels = {group["label"] for group in body["albums"]}
    assert labels == {"Adele - 21", "Zella Day - Kicker"}


def test_cover_batch_replace_writes_embedded_and_logs(client, library) -> None:
    by_name = _setup(client, library["id"])
    a1, a2 = by_name[ALBUM_A], by_name[ALBUM_A2]

    assignments = [{"index": 0, "track_ids": [a1["id"], a2["id"]]}]
    resp = client.post(
        "/api/covers/batch-replace",
        data={"assignments": json.dumps(assignments)},
        files=[("files", ("cover.jpg", JPEG_BYTES, "image/jpeg"))],
    )
    assert resp.status_code == 200, resp.text
    task = _wait_task(client, resp.json()["task_id"])
    assert task["status"] == "succeeded", task
    assert "成功 2" in (task["message"] or "")

    assert io.read_cover(Path(a1["path"])) is not None
    assert io.read_cover(Path(a2["path"])) is not None
    assert client.get(f"/api/tracks/{a1['id']}").json()["has_cover"] is True

    logs = client.get("/api/logs", params={"track_id": a1["id"]}).json()
    assert "cover.write" in {entry["action"] for entry in logs["items"]}


def test_cover_batch_replace_skips_empty_assignment(client, library) -> None:
    by_name = _setup(client, library["id"])
    a1 = by_name[ALBUM_A]

    resp = client.post(
        "/api/covers/batch-replace",
        data={"assignments": json.dumps([{"index": 0, "track_ids": []}])},
        files=[("files", ("cover.jpg", JPEG_BYTES, "image/jpeg"))],
    )
    assert resp.status_code == 400
    assert io.read_cover(Path(a1["path"])) is None


def test_cover_batch_replace_rejects_non_image(client, library) -> None:
    by_name = _setup(client, library["id"])
    a1 = by_name[ALBUM_A]

    resp = client.post(
        "/api/covers/batch-replace",
        data={"assignments": json.dumps([{"index": 0, "track_ids": [a1["id"]]}])},
        files=[("files", ("cover.txt", b"not an image", "text/plain"))],
    )
    assert resp.status_code == 400
    assert "不是图片" in resp.json()["detail"]
    assert io.read_cover(Path(a1["path"])) is None


def test_cover_batch_preview_requires_ids(client) -> None:
    resp = client.post("/api/covers/batch-preview", json={"ids": [], "filenames": ["a.jpg"]})
    assert resp.status_code == 422
