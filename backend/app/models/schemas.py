"""Pydantic v2 API schema（请求/响应契约，对应设计文档 §8）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.db import TaskStatus

T = TypeVar("T")

# 单条编辑可写字段白名单（对应 F3）
EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "artist",
    "album",
    "album_artist",
    "composer",
    "genre",
    "track_no",
    "disc_no",
    "year",
    "date",
    "comment",
)

SortField = Literal[
    "filename", "path", "size", "mtime", "duration", "track_no", "title", "artist", "album"
]
SortOrder = Literal["asc", "desc"]
BatchOpKind = Literal["set", "fill_empty", "append", "replace", "zh_convert"]
BatchSource = Literal["manual", "batch", "scrape"]


# --------------------------------------------------------------------------- #
# 通用
# --------------------------------------------------------------------------- #
class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    name: str
    version: str
    environment: str
    ffmpeg: bool = False  # 是否检测到 ffmpeg（核心功能不依赖）


class Page(BaseModel, Generic[T]):
    """统一分页响应。"""

    items: list[T]
    total: int
    page: int = 1
    page_size: int = 50
    pages: int = 1


class NotImplementedDetail(BaseModel):
    detail: str
    milestone: str = "M1"


# --------------------------------------------------------------------------- #
# 库（library）
# --------------------------------------------------------------------------- #
class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    root_path: str = Field(min_length=1)
    enabled: bool = True
    scan_mode: Literal["incremental", "full"] = "incremental"


class LibraryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    root_path: str | None = None
    enabled: bool | None = None
    scan_mode: Literal["incremental", "full"] | None = None


class LibraryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    root_path: str
    enabled: bool
    scan_mode: str
    created_at: datetime
    track_count: int = 0


# --------------------------------------------------------------------------- #
# 曲目（track）
# --------------------------------------------------------------------------- #
class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    library_id: int
    path: str
    dirname: str
    filename: str
    ext: str
    format: str
    size: int
    mtime: datetime
    duration: float | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bit_depth: int | None = None
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
    has_cover: bool = False
    cover_mtime: datetime | None = None
    has_lyrics: bool = False
    tag_status: str = "UNKNOWN"
    created_at: datetime
    updated_at: datetime


class TrackUpdate(BaseModel):
    """单条编辑：仅允许白名单字段，未提供即不变。"""

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


class TrackFacets(BaseModel):
    formats: dict[str, int] = Field(default_factory=dict)
    years: dict[str, int] = Field(default_factory=dict)
    artists: dict[str, int] = Field(default_factory=dict)
    tag_status: dict[str, int] = Field(default_factory=dict)
    has_cover: dict[str, int] = Field(default_factory=dict)
    has_lyrics: dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 批量编辑（F4）
# --------------------------------------------------------------------------- #
class BatchEditOp(BaseModel):
    field: str = Field(description="目标字段，见 EDITABLE_FIELDS")
    op: BatchOpKind = "set"
    value: Any | None = None
    find: str | None = Field(default=None, description="replace 策略的查找串")
    replace: str | None = Field(default=None, description="replace 策略的替换串")
    use_regex: bool = False
    direction: Literal["s2t", "t2s"] | None = Field(
        default=None, description="zh_convert 策略的转换方向：s2t 简→繁，t2s 繁→简"
    )


class BatchEditRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    ops: list[BatchEditOp] = Field(min_length=1)
    strategy: Literal["overwrite", "fill_empty", "append", "replace"] = "overwrite"
    dry_run: bool = False


class FieldDiff(BaseModel):
    field: str
    old_value: Any | None = None
    new_value: Any | None = None


class TrackDiff(BaseModel):
    track_id: int
    path: str
    changes: list[FieldDiff] = Field(default_factory=list)


class BatchPreviewResponse(BaseModel):
    total: int
    changed: int
    items: list[TrackDiff] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 封面（F5）
# --------------------------------------------------------------------------- #
class CoverMeta(BaseModel):
    track_id: int
    available: bool
    source: Literal["embedded", "file", "scraped"] | None = None
    mime: str | None = None
    width: int | None = None
    height: int | None = None


# --------------------------------------------------------------------------- #
# 歌词（F6）
# --------------------------------------------------------------------------- #
class LyricsRead(BaseModel):
    track_id: int
    available: bool
    format: Literal["lrc", "embedded"] = "lrc"
    source: str | None = None
    content: str | None = None


class LyricsWriteRequest(BaseModel):
    content: str
    format: Literal["lrc", "embedded"] = "embedded"
    target: Literal["embedded", "lrc", "both"] = "embedded"
    validate_lrc: bool = True


# --------------------------------------------------------------------------- #
# 刮削（F7 / §9）
# --------------------------------------------------------------------------- #
class ScrapeQueryModel(BaseModel):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    track_no: int | None = None
    duration: int | None = None
    filename_hint: str | None = None
    fingerprint: str | None = None


class ScrapeSearchRequest(BaseModel):
    track_id: int | None = None
    query: ScrapeQueryModel | None = None
    providers: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class CandidateRead(BaseModel):
    provider: str
    external_id: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: str | None = None
    track_no: int | None = None
    score: float = 0.0
    cover_url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ScrapeSearchResponse(BaseModel):
    track_id: int | None = None
    candidates: list[CandidateRead] = Field(default_factory=list)


class ScrapeApplyRequest(BaseModel):
    track_id: int
    candidate_ids: list[str] = Field(default_factory=list, description="形如 provider:external_id")
    candidates: list[CandidateRead] = Field(
        default_factory=list,
        description=(
            "用户实际选中的候选。优先使用它而非按 id 重新 fetch："
            "同一 recording 会出现在多个 release 上，重新 fetch 会取到不同的 release，"
            "导致专辑/年份写错、封面抓不到。"
        ),
    )
    only_missing: bool = False
    apply_cover: bool = False
    apply_lyrics: bool = False


class ScrapeApplyResponse(BaseModel):
    track_id: int
    applied_fields: list[str] = Field(default_factory=list)
    cover_applied: bool = False
    lyrics_applied: bool = False
    diffs: list[FieldDiff] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #
class ProviderRead(BaseModel):
    key: str
    name: str
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = False
    priority: int = 100
    options: dict[str, Any] = Field(default_factory=dict)


class ProviderUpdate(BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    options: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# 日志 / 任务 / 设置
# --------------------------------------------------------------------------- #
class OperationLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    track_id: int | None = None
    action: str
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    source: str
    result: str
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    total: int
    processed: int
    message: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class TaskAccepted(BaseModel):
    task_id: int
    status: TaskStatus = TaskStatus.queued


class SettingsRead(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


# --------------------------------------------------------------------------- #
# 组织 / 转换（P1/P2 契约占位）
# --------------------------------------------------------------------------- #
class OrganizePreviewRequest(BaseModel):
    """整理预演/执行入参；``move=False`` 为同级重命名（F11），``True`` 为移动到分组目录（F15）。"""

    ids: list[int] = Field(default_factory=list)
    template: str = "{albumartist}/{year} - {album}/{track:02d} - {title}"
    move: bool = False


class OrganizePlanItem(BaseModel):
    """用户确认执行的单条计划：以它为准落盘，避免预览与执行之间出现偏差。"""

    track_id: int
    target: str


class OrganizePreviewItem(BaseModel):
    track_id: int
    source: str
    target: str | None = None
    status: Literal["ok", "unchanged", "conflict", "invalid"] = "ok"
    reason: str | None = None
    sidecars: list[str] = Field(default_factory=list, description="将一并处理的边车文件源路径")


class OrganizePreviewResponse(BaseModel):
    total: int = 0
    ok: int = 0
    conflicts: int = 0
    unchanged: int = 0
    invalid: int = 0
    items: list[OrganizePreviewItem] = Field(default_factory=list)


class OrganizeApplyRequest(OrganizePreviewRequest):
    """``plan`` 非空时按用户确认的目标执行；为空时后端按 ids+模板重算。"""

    plan: list[OrganizePlanItem] | None = None


class ConvertRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    target_format: Literal["mp3", "flac", "alac", "wav", "aiff", "opus"] = "mp3"


class Capabilities(BaseModel):
    ffmpeg: bool = False
    fpcalc: bool = False
    ai: bool = False


class AISettingsRead(BaseModel):
    """AI 辅助配置（密钥始终脱敏，不回传明文）。"""

    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    has_api_key: bool = False
    api_key_masked: str | None = None
    available: bool = False


class AISettingsUpdate(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = Field(
        default=None,
        description="省略=不修改；空字符串=清除；否则设置为新密钥",
    )


# --------------------------------------------------------------------------- #
# 文件名解析（F11 的文件名 → 标签方向）
# --------------------------------------------------------------------------- #
class ParseFilenameRequest(BaseModel):
    use_ai: bool = Field(default=False, description="是否调用 AI 辅助（需在设置中配置）")
    apply: bool = Field(default=False, description="是否直接写入标签；false 时仅预览")


class ParsedFields(BaseModel):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    track_no: int | None = None


class ParseFilenameResponse(BaseModel):
    track_id: int
    source: Literal["heuristic", "ai"] = "heuristic"
    confidence: float = 0.0
    note: str | None = None
    fields: ParsedFields
    diffs: list[FieldDiff] = Field(default_factory=list)
    applied: bool = False


class ParseFilenameBatchRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    use_ai: bool = Field(default=False, description="是否调用 AI 辅助（需在设置中配置）")
    strategy: Literal["fill_empty", "overwrite"] = Field(
        default="fill_empty", description="fill_empty 仅补空字段；overwrite 以解析结果为准"
    )


class ParseFilenameBatchItem(BaseModel):
    track_id: int
    path: str
    source: Literal["heuristic", "ai"] = "heuristic"
    confidence: float = 0.0
    note: str | None = None
    fields: ParsedFields
    diffs: list[FieldDiff] = Field(default_factory=list)
    status: Literal["ok", "unchanged", "invalid"] = "ok"


class ParseFilenameBatchResponse(BaseModel):
    total: int = 0
    changed: int = 0
    unchanged: int = 0
    invalid: int = 0
    items: list[ParseFilenameBatchItem] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 封面批量导出
# --------------------------------------------------------------------------- #
class CoverBatchExportRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    target_dir: str | None = None
    filename_template: str = "{artist} - {album}"


class CoverBatchExportResponse(BaseModel):
    exported: int = 0
    files: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 批量刮削作业
# --------------------------------------------------------------------------- #
class ScrapeJobCreateRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    providers: list[str] | None = None
    only_missing: bool = True


class ScrapeJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: str
    status: str
    provider_ids: list[str] = Field(default_factory=list)
    created_at: datetime
