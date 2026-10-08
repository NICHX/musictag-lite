"""F15 智能整理：预演（old → new）与落盘（重命名 / 移动 / 冲突 / 边车）。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.audio_factory import JPEG_BYTES, make_flac

LRC = "[00:01.00]第一行"


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
    """临时库：music/Adele/21 下两首 FLAC + 边车歌词与封面。"""
    album = tmp_path / "music" / "Adele" / "21"
    album.mkdir(parents=True)
    make_flac(album / "01 Rolling.flac")
    make_flac(album / "02 Untagged.flac")
    (album / "01 Rolling.lrc").write_text(LRC, encoding="utf-8")
    (album / "cover.jpg").write_bytes(JPEG_BYTES)

    resp = client.post(
        "/api/libraries", json={"name": "整理库", "root_path": str(album.parents[1])}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scan(client, library_id: int) -> None:
    resp = client.post(f"/api/libraries/{library_id}/scan")
    assert resp.status_code == 200, resp.text
    task = _wait_task(client, resp.json()["task_id"])
    assert task["status"] == "succeeded", task


def _tracks(client, library_id: int) -> list[dict]:
    return client.get("/api/tracks", params={"library_id": library_id}).json()["items"]


def _tag(client, track_id: int, **fields: object) -> None:
    resp = client.patch(f"/api/tracks/{track_id}", json=fields)
    assert resp.status_code == 200, resp.text


def test_organize_rename_preview_then_apply(client, library) -> None:
    """move=False：同级重命名，预演不写盘，应用后文件与索引同步更新。"""
    _scan(client, library["id"])
    track = next(t for t in _tracks(client, library["id"]) if t["filename"] == "01 Rolling.flac")
    _tag(client, track["id"], title="Rolling", artist="Adele", track_no=1)
    source = Path(track["path"])

    preview = client.post(
        "/api/organize/preview",
        json={"ids": [track["id"]], "template": "{track:02d} - {title}", "move": False},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["ok"] == 1 and body["conflicts"] == 0
    item = body["items"][0]
    assert item["status"] == "ok"
    assert Path(item["target"]).name == "01 - Rolling.flac"
    assert Path(item["target"]).parent == source.parent
    # 预演不写盘
    assert source.exists() and not Path(item["target"]).exists()

    applied = client.post(
        "/api/organize/apply",
        json={
            "ids": [track["id"]],
            "template": "{track:02d} - {title}",
            "move": False,
            "plan": [{"track_id": track["id"], "target": item["target"]}],
        },
    )
    assert applied.status_code == 200, applied.text
    task = _wait_task(client, applied.json()["task_id"])
    assert task["status"] == "succeeded", task
    assert "成功 1" in (task["message"] or "")

    target = Path(item["target"])
    assert target.exists() and not source.exists()

    refreshed = client.get(f"/api/tracks/{track['id']}").json()
    assert refreshed["path"] == str(target)
    assert refreshed["filename"] == "01 - Rolling.flac"

    logs = client.get("/api/logs", params={"track_id": track["id"]}).json()
    assert "organize.rename" in {entry["action"] for entry in logs["items"]}


def test_organize_conflict_is_skipped_not_overwritten(client, library) -> None:
    """目标已存在 → 预演标冲突；即便用户误确认，执行时也跳过、绝不覆盖。"""
    _scan(client, library["id"])
    track = next(t for t in _tracks(client, library["id"]) if t["filename"] == "01 Rolling.flac")
    _tag(client, track["id"], title="Rolling", track_no=1)
    source = Path(track["path"])

    occupied = source.parent / "01 - Rolling.flac"
    occupied.write_bytes(b"keep-me")

    preview = client.post(
        "/api/organize/preview",
        json={"ids": [track["id"]], "template": "{track:02d} - {title}", "move": False},
    ).json()
    assert preview["conflicts"] == 1 and preview["ok"] == 0
    assert preview["items"][0]["status"] == "conflict"

    applied = client.post(
        "/api/organize/apply",
        json={
            "ids": [track["id"]],
            "template": "{track:02d} - {title}",
            "move": False,
            "plan": [{"track_id": track["id"], "target": str(occupied)}],
        },
    )
    task = _wait_task(client, applied.json()["task_id"])
    assert task["status"] == "succeeded", task
    assert "跳过 1" in (task["message"] or "")

    assert occupied.read_bytes() == b"keep-me"
    assert source.exists()


def test_organize_move_carries_sidecars(client, library) -> None:
    """move=True：移动到分组目录；同名歌词跟随移动，目录级封面复制过去。"""
    _scan(client, library["id"])
    track = next(t for t in _tracks(client, library["id"]) if t["filename"] == "01 Rolling.flac")
    _tag(
        client,
        track["id"],
        title="Rolling",
        artist="Adele",
        album="21",
        album_artist="Adele",
        year="2011",
        track_no=1,
    )
    source = Path(track["path"])
    source_lrc = source.parent / "01 Rolling.lrc"

    preview = client.post(
        "/api/organize/preview",
        json={
            "ids": [track["id"]],
            "template": "{albumartist}/{year} - {album}/{track:02d} - {title}",
            "move": True,
        },
    ).json()
    assert preview["ok"] == 1, preview
    item = preview["items"][0]
    target = Path(item["target"])
    assert target == source.parent.parent / "2011 - 21" / "01 - Rolling.flac"
    assert str(source_lrc) in item["sidecars"]

    applied = client.post(
        "/api/organize/apply",
        json={
            "ids": [track["id"]],
            "template": "{albumartist}/{year} - {album}/{track:02d} - {title}",
            "move": True,
            "plan": [{"track_id": track["id"], "target": str(target)}],
        },
    )
    task = _wait_task(client, applied.json()["task_id"])
    assert task["status"] == "succeeded", task

    assert target.exists() and not source.exists()
    assert (target.parent / "01 - Rolling.lrc").exists() and not source_lrc.exists()
    assert (target.parent / "cover.jpg").exists() and (source.parent / "cover.jpg").exists()

    assert client.get(f"/api/tracks/{track['id']}").json()["path"] == str(target)


def test_organize_invalid_when_template_empty(client, library) -> None:
    """标签为空且模板渲染不出文件名 → 无效，不执行。"""
    _scan(client, library["id"])
    untagged = next(
        t for t in _tracks(client, library["id"]) if t["filename"] == "02 Untagged.flac"
    )

    preview = client.post(
        "/api/organize/preview",
        json={
            "ids": [untagged["id"]],
            "template": "{albumartist}/{year} - {album}/{track:02d} - {title}",
            "move": True,
        },
    ).json()
    assert preview["invalid"] == 1 and preview["ok"] == 0
    assert preview["items"][0]["status"] == "invalid"
    assert preview["items"][0]["reason"]
