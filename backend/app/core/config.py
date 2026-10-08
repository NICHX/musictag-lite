"""应用配置：环境变量 + .env，前缀无（沿用文档中的 APP_SECRET_KEY / DATA_DIR / MUSIC_ROOT）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录与仓库根目录（用于推导默认路径）
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

# 附录 A：支持写入的主流音频格式扩展名（扫描白名单）
DEFAULT_SCAN_EXTENSIONS: set[str] = {
    ".mp3",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".m4a",
    ".mp4",
    ".m4b",
    ".wma",
    ".asf",
    ".ape",
    ".wv",
    ".wav",
    ".aiff",
    ".aif",
    ".dsf",
    ".mpc",
    ".tta",
}

# 扫描时忽略的常见临时/隐藏文件
DEFAULT_SCAN_IGNORE: set[str] = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".tmp",
    ".temp",
    ".part",
    ".crdownload",
    ".partial",
}


class Settings(BaseSettings):
    """全局配置。字段可用同名大写环境变量覆盖。"""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    app_name: str = "MusicTag Lite"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | production
    debug: bool = True
    app_secret_key: str = "dev-insecure-change-me"

    # ---- 服务 ----
    host: str = "0.0.0.0"
    port: int = 8000
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # ---- 存储 ----
    data_dir: Path = REPO_ROOT / "data"
    database_url: str | None = None  # 留空则推导为 SQLite(data_dir/musictag.db)
    music_root: str | None = None  # Docker 场景的默认库根目录（/music）

    # ---- 前端静态资源（生产单镜像托管）----
    serve_frontend: bool = True
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    # ---- 扫描 ----
    scan_extensions: set[str] = Field(default_factory=lambda: set(DEFAULT_SCAN_EXTENSIONS))
    scan_ignore_names: set[str] = Field(default_factory=lambda: set(DEFAULT_SCAN_IGNORE))
    scan_max_concurrency: int = 4

    # ---- 网络 / 刮削 ----
    http_timeout: float = 15.0
    http_retries: int = 3
    http_cache_ttl: int = 86400  # 秒
    musicbrainz_user_agent: str = "MusicTagLite/0.1.0 ( https://github.com/musictag-lite )"
    musicbrainz_rate_limit: float = 1.0  # 每秒请求数上限
    acoustid_api_key: str | None = None  # 可选，P1 指纹识别

    # ---- 鉴权（P2，默认关闭）----
    auth_enabled: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value  # 交由 pydantic 解析 JSON
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("scan_extensions", "scan_ignore_names", mode="before")
    @classmethod
    def _split_set(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return {item.strip() for item in stripped.split(",") if item.strip()}
        return value

    @property
    def sqlite_path(self) -> Path:
        """SQLite 数据库文件路径。"""
        return self.data_dir / "musictag.db"

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy 连接串；显式配置 database_url 时优先。"""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.sqlite_path}"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    def ensure_data_dir(self) -> Path:
        """确保数据目录存在并返回。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


@lru_cache
def get_settings() -> Settings:
    """获取（缓存的）全局配置单例。"""
    return Settings()
