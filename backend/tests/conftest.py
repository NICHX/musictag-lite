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
