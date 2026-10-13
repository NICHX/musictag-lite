"""SQLModel 表定义（对应设计文档 §7 数据模型）。

约定：
- 文件系统为唯一事实来源，Track 仅是可随时重建的索引快照。
- 复杂结构（如刮削候选 payload、Provider 选项）以 JSON 文本存于 *Text 字段，
  由服务层负责序列化/反序列化，避免迁移对 dialect 的额外依赖。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """带时区的当前时间（UTC）。"""
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# 枚举（以字符串存储，便于筛选与迁移）
# --------------------------------------------------------------------------- #
class ScanMode(StrEnum):
    incremental = "incremental"
    full = "full"


class TagStatus(StrEnum):
    ok = "OK"
    missing_title = "MISSING_TITLE"
    missing_artist = "MISSING_ARTIST"
    missing_album = "MISSING_ALBUM"
    missing_tags = "MISSING_TAGS"
    unknown = "UNKNOWN"


class TaskType(StrEnum):
    scan = "scan"
    batch_edit = "batch_edit"
    parse_filename = "parse_filename"
    scrape = "scrape"
    organize = "organize"
    convert = "convert"
    cover_export = "cover_export"
    cover_write = "cover_write"
    lyrics_write = "lyrics_write"


class TaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class LogSource(StrEnum):
    manual = "manual"
    batch = "batch"
    scrape = "scrape"
    system = "system"


class LogResult(StrEnum):
    success = "success"
    failure = "failure"
    skipped = "skipped"


class CoverSource(StrEnum):
    embedded = "embedded"
    file = "file"
    scraped = "scraped"


class LyricsFormat(StrEnum):
    lrc = "lrc"
    embedded = "embedded"


# --------------------------------------------------------------------------- #
# 表
# --------------------------------------------------------------------------- #
class Library(SQLModel, table=True):
    """音乐库根目录配置。"""

    __tablename__ = "library"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    root_path: str = Field(index=True, unique=True)
    enabled: bool = Field(default=True)
    scan_mode: str = Field(default=ScanMode.incremental)
    created_at: datetime = Field(default_factory=utcnow)


class Track(SQLModel, table=True):
    """曲目索引快照。"""

    __tablename__ = "track"

    id: int | None = Field(default=None, primary_key=True)
    library_id: int = Field(foreign_key="library.id", index=True)

    path: str = Field(index=True, unique=True)
    dirname: str = Field(default="")
    filename: str = Field(default="")
    ext: str = Field(default="")
    format: str = Field(default="", index=True)
    size: int = Field(default=0)
    mtime: datetime = Field(default_factory=utcnow)

    # 技术参数（只读）
    duration: float | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bit_depth: int | None = None

    # 常用标签
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    composer: str | None = None
    genre: str | None = None
    track_no: int | None = None
    disc_no: int | None = None
    year: str | None = None
    date: str | None = None
    comment: str | None = None

    # 状态
    has_cover: bool = Field(default=False)
    cover_mtime: datetime | None = None
    has_lyrics: bool = Field(default=False)
    has_embedded_lyrics: bool = Field(default=False)
    has_lyrics_file: bool = Field(default=False)
    has_word_lyrics: bool = Field(default=False)
    tag_status: str = Field(default=TagStatus.unknown, index=True)
    scan_hash: str | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CoverCache(SQLModel, table=True):
    """封面缓存记录（大文件不入库，仅存元信息与磁盘路径）。"""

    __tablename__ = "cover_cache"

    id: int | None = Field(default=None, primary_key=True)
    track_id: int = Field(foreign_key="track.id", index=True)
    mime: str = Field(default="image/jpeg")
    width: int | None = None
    height: int | None = None
    cached_path: str | None = None
    source: str = Field(default=CoverSource.embedded)
    created_at: datetime = Field(default_factory=utcnow)


class LyricsAsset(SQLModel, table=True):
    """歌词资源记录（内嵌 / .lrc 边车）。"""

    __tablename__ = "lyrics_asset"

    id: int | None = Field(default=None, primary_key=True)
    track_id: int = Field(foreign_key="track.id", index=True)
    format: str = Field(default=LyricsFormat.lrc)
    content_ref: str | None = None
    source: str = Field(default="embedded")
    created_at: datetime = Field(default_factory=utcnow)


class ScrapeJob(SQLModel, table=True):
    """刮削作业（单条/批量）。"""

    __tablename__ = "scrape_job"

    id: int | None = Field(default=None, primary_key=True)
    scope: str = Field(default="single")
    provider_ids: str | None = None  # JSON 数组文本
    status: str = Field(default=TaskStatus.queued, index=True)
    query_json: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ScrapeCandidate(SQLModel, table=True):
    """刮削候选结果。"""

    __tablename__ = "scrape_candidate"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="scrape_job.id", index=True)
    track_id: int | None = Field(default=None, foreign_key="track.id", index=True)
    provider: str = Field(default="")
    external_id: str = Field(default="")
    score: float = Field(default=0.0)
    payload_json: str | None = None
    selected: bool = Field(default=False)


class Task(SQLModel, table=True):
    """后台任务状态。"""

    __tablename__ = "task"

    id: int | None = Field(default=None, primary_key=True)
    type: str = Field(default=TaskType.scan, index=True)
    status: str = Field(default=TaskStatus.queued, index=True)
    total: int = Field(default=0)
    processed: int = Field(default=0)
    message: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class OperationLog(SQLModel, table=True):
    """操作审计日志：记录每次写入的前后值。"""

    __tablename__ = "operation_log"

    id: int | None = Field(default=None, primary_key=True)
    track_id: int | None = Field(default=None, foreign_key="track.id", index=True)
    action: str = Field(default="")
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    source: str = Field(default=LogSource.manual, index=True)
    result: str = Field(default=LogResult.success, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class ProviderConfig(SQLModel, table=True):
    """刮削 Provider 的启用状态与优先级。"""

    __tablename__ = "provider_config"

    id: int | None = Field(default=None, primary_key=True)
    provider_key: str = Field(index=True, unique=True)
    enabled: bool = Field(default=False)
    priority: int = Field(default=100)
    options_json: str | None = None


class Setting(SQLModel, table=True):
    """通用键值设置。"""

    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value_json: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class User(SQLModel, table=True):
    """用户（P2 鉴权预留）。"""

    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str = Field(default="")
    role: str = Field(default="admin")
    created_at: datetime = Field(default_factory=utcnow)
