"""M1 端到端：扫描 → 列表筛选 → 单条编辑落盘 → 封面 → 歌词 → 批量 → 日志。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.audio.mutagen_io import MutagenIO
from tests.audio_factory import JPEG_BYTES, make_flac, make_wav

io = MutagenIO()
LRC = "[00:01.00]第一行\n[00:05.50]第二行"


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
    """构造一个含 FLAC/WAV + 边车封面/歌词的临时库并登记。"""
    album = tmp_path / "music" / "Adele" / "21"
    album.mkdir(parents=True)
    make_flac(album / "01 Rolling.flac")
    make_flac(album / "02 Someone.flac")
    make_wav(album / "03 Wav.wav")
    (album / "cover.jpg").write_bytes(JPEG_BYTES)
    (album / "01 Rolling.lrc").write_text(LRC, encoding="utf-8")

    resp = client.post(
        "/api/libraries", json={"name": "测试库", "root_path": str(album.parents[1])}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scan(client, library_id: int) -> dict:
    resp = client.post(f"/api/libraries/{library_id}/scan")
    assert resp.status_code == 200, resp.text
    task = _wait_task(client, resp.json()["task_id"])
    assert task["status"] == "succeeded", task
    return task


def test_scan_list_edit_cover_lyrics_batch(client, library) -> None:
    lib_id = library["id"]

    # 1) 扫描并入库
    _scan(client, lib_id)
    page = client.get("/api/tracks", params={"library_id": lib_id}).json()
    assert page["total"] == 3

    # 2) 筛选（边车 cover.jpg 使 3 首均视为有封面）
    assert (
        client.get("/api/tracks", params={"library_id": lib_id, "has_cover": True}).json()["total"]
        == 3
    )
    assert (
        client.get("/api/tracks", params={"library_id": lib_id, "has_cover": False}).json()["total"]
        == 0
    )
    facets = client.get("/api/tracks/facets").json()
    assert {"FLAC", "WAV"} <= set(facets["formats"])

    # 3) 增量：再扫一次应全部未变
    assert "未变 3" in (_scan(client, lib_id)["message"] or "")

    # 4) 单条编辑并落盘
    flac = next(t for t in page["items"] if t["filename"].endswith("01 Rolling.flac"))
    resp = client.patch(
        f"/api/tracks/{flac['id']}",
        json={
            "title": "Rolling in the Deep",
            "artist": "Adele",
            "album": "21",
            "album_artist": "Adele",
            "year": "2011",
            "track_no": 1,
            "genre": "Soul",
        },
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["title"] == "Rolling in the Deep"
    assert updated["tag_status"] == "OK"

    doc = io.read(Path(updated["path"]))
    assert doc.tags.title == "Rolling in the Deep"
    assert doc.tags.album == "21"
    assert doc.tags.track_no == 1
    assert doc.tags.year == "2011"

    # 5) 操作日志留痕
    logs = client.get("/api/logs", params={"track_id": flac["id"]}).json()
    assert logs["total"] >= 3
    assert {"title", "artist"} <= {item["field"] for item in logs["items"]}

    # 6) 封面：边车兜底 → 上传内嵌 → 删除
    assert client.get(f"/api/tracks/{flac['id']}/cover").headers["X-Cover-Source"] == "file"
    put = client.put(
        f"/api/tracks/{flac['id']}/cover",
        files={"file": ("c.jpg", JPEG_BYTES, "image/jpeg")},
    )
    assert put.status_code == 200, put.text
    assert client.get(f"/api/tracks/{flac['id']}/cover").headers["X-Cover-Source"] == "embedded"
    assert client.delete(f"/api/tracks/{flac['id']}/cover").json()["removed"] is True
    assert io.read_cover(Path(updated["path"])) is None

    # 7) 歌词：读取 .lrc 边车 → 写入内嵌
    got = client.get(f"/api/tracks/{flac['id']}/lyrics").json()
    assert got["available"] is True and got["source"] == "lrc"
    put_lyr = client.put(
        f"/api/tracks/{flac['id']}/lyrics",
        json={"content": LRC, "format": "lrc", "target": "embedded"},
    )
    assert put_lyr.status_code == 200, put_lyr.text
    assert io.read_lyrics(Path(updated["path"])) == LRC

    # 8) 批量：预演 + 应用
    other = next(t for t in page["items"] if t["filename"].endswith("02 Someone.flac"))
    ops = [{"field": "album", "op": "set", "value": "21"}]
    preview = client.post(
        "/api/tracks/batch/preview",
        json={"ids": [other["id"]], "strategy": "overwrite", "ops": ops},
    ).json()
    assert preview["changed"] == 1
    assert preview["items"][0]["changes"][0]["field"] == "album"

    applied = client.post(
        "/api/tracks/batch", json={"ids": [other["id"]], "strategy": "overwrite", "ops": ops}
    )
    assert applied.status_code == 200
    task = _wait_task(client, applied.json()["task_id"])
    assert task["status"] == "succeeded", task
    assert io.read(Path(other["path"])).tags.album == "21"
