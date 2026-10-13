"""pytest 全局配置：独立临时数据目录 + 建表 + TestClient。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# 必须在导入应用模块之前设置环境变量（Settings 会在首次导入时缓存）
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="musictag-test-data-")
os.environ["DATA_DIR"] = _TMP_DATA_DIR
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"
os.environ["SERVE_FRONTEND"] = "false"


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    """建表（测试用 create_all，生产走 Alembic 迁移）。"""
    from app.core.db import init_db

    init_db(create_all=True)


@pytest.fixture(autouse=True)
def _clear_response_cache() -> None:
    """每个用例前清空刮削响应缓存，避免跨用例命中导致请求计数断言失真。"""
    from app.core.cache import response_cache

    response_cache().clear()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def music_dir(tmp_path: Path) -> Path:
    """构造一个含若干音频文件的临时库目录。"""
    (tmp_path / "Artist" / "Album").mkdir(parents=True)
    (tmp_path / "Artist" / "Album" / "track01.flac").write_bytes(b"not-a-real-flac")
    (tmp_path / "Artist" / "Album" / "track02.mp3").write_bytes(b"not-a-real-mp3")
    (tmp_path / "Artist" / "Album" / "cover.jpg").write_bytes(b"fake-jpg")
    (tmp_path / "Artist" / "Album" / ".hidden.mp3").write_bytes(b"hidden")
    (tmp_path / "Artist" / "Album" / "notes.txt").write_text("ignore me")
    return tmp_path


@pytest.fixture
def track_factory():
    """构造内存中的 Track 对象（不落库），便于纯函数测试。"""
    from app.models.db import Track

    def _make(**kwargs):
        defaults = {"library_id": 1, "path": "/music/song.flac", "filename": "song.flac"}
        defaults.update(kwargs)
        return Track(**defaults)

    return _make
