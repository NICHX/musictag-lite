"""库管理 CRUD（真实落库，验证 DB + 迁移可用）。"""

from __future__ import annotations

from pathlib import Path


def test_library_crud(client, music_dir: Path) -> None:
    # 创建
    resp = client.post("/api/libraries", json={"name": "我的曲库", "root_path": str(music_dir)})
    assert resp.status_code == 201, resp.text
    created = resp.json()
    library_id = created["id"]
    assert created["track_count"] == 0
    assert created["scan_mode"] == "incremental"

    # 重复根目录 → 409
    assert (
        client.post("/api/libraries", json={"name": "dup", "root_path": str(music_dir)}).status_code
        == 409
    )

    # 不存在目录 → 400
    assert (
        client.post(
            "/api/libraries", json={"name": "bad", "root_path": "/nope/missing"}
        ).status_code
        == 400
    )

    # 列表包含
    listing = client.get("/api/libraries").json()
    assert any(item["id"] == library_id for item in listing)

    # 详情
    assert client.get(f"/api/libraries/{library_id}").status_code == 200
    assert client.get("/api/libraries/999999").status_code == 404

    # 更新
    updated = client.patch(f"/api/libraries/{library_id}", json={"name": "重命名库"}).json()
    assert updated["name"] == "重命名库"
    assert updated["root_path"] == str(music_dir.resolve())

    # 触发扫描：返回后台任务（M1）
    scan = client.post(f"/api/libraries/{library_id}/scan")
    assert scan.status_code == 200
    assert isinstance(scan.json()["task_id"], int)

    # 删除
    assert client.delete(f"/api/libraries/{library_id}").status_code == 204
    assert client.get(f"/api/libraries/{library_id}").status_code == 404
