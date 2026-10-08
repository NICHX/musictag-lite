"""数据库：SQLite(engine) + WAL 模式 + Session 依赖。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import BACKEND_DIR, get_settings

_settings = get_settings()

engine: Engine = create_engine(
    _settings.sqlalchemy_url,
    echo=False,
    connect_args={"check_same_thread": False}
    if _settings.sqlalchemy_url.startswith("sqlite")
    else {},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    """启用 WAL、外键约束与合理的 busy_timeout。"""
    if not _settings.sqlalchemy_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个 Session。"""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """后台任务中使用的事务上下文。"""
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def init_db(*, create_all: bool = False) -> None:
    """确保数据目录存在；create_all 仅用于测试（生产用 Alembic 迁移）。"""
    _settings.ensure_data_dir()
    if create_all:
        import app.models.db  # noqa: F401  注册所有表

        SQLModel.metadata.create_all(engine)


def run_migrations() -> None:
    """编程式执行 Alembic 迁移至 head（开发模式启动时自动调用）。

    使用不带 ini 文件的 Config，避免 Alembic 的 fileConfig 覆盖应用的结构化日志。
    生产（Docker）在容器启动命令中显式执行 `alembic upgrade head`。
    """
    from alembic.config import Config

    from alembic import command

    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", _settings.sqlalchemy_url)
    command.upgrade(config, "head")
