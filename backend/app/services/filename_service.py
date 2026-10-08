"""批量文件名解析（F11 的「文件名 → 标签」方向）。

复用单条接口的解析链路：本地启发式（默认）或可选 AI（逐首调用，需显式开启）。
预览与落盘共用同一套「按策略计算差异」逻辑，保证所见即所写。
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlmodel import Session

from app.models.db import Track
from app.services.ai_config import AIConfig
from app.services.ai_parser import AIUnavailableError, parse_filename_with_ai
from app.services.filename_parser import ParsedFilename, parse_filename
from app.services.scrape_orchestrator import scrape_orchestrator
from app.services.tag_service import SOURCE_BATCH, TagService

# 解析可写字段（与单条接口一致）
PARSE_FIELDS: tuple[str, ...] = ("title", "artist", "album", "track_no")

# 预览状态
STATUS_OK = "ok"
STATUS_UNCHANGED = "unchanged"
STATUS_INVALID = "invalid"


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _has_fields(parsed: ParsedFilename) -> bool:
    return any(getattr(parsed, field) is not None for field in PARSE_FIELDS)


def compute_diffs(track: Track, parsed: ParsedFilename, strategy: str) -> list[dict[str, Any]]:
    """按策略计算将写入的字段差异。

    - ``fill_empty``：仅当当前字段为空时写入（不覆盖已有人工/刮削标签）；
    - ``overwrite``：以解析结果为准。
    """
    diffs: list[dict[str, Any]] = []
    for field in PARSE_FIELDS:
        new_value = getattr(parsed, field)
        if new_value is None:
            continue
        old_value = getattr(track, field)
        if strategy == "fill_empty" and not _is_empty(old_value):
            continue
        if old_value == new_value:
            continue
        diffs.append({"field": field, "old_value": old_value, "new_value": new_value})
    return diffs


def load_tracks(session: Session, ids: list[int]) -> list[Track]:
    return [track for track in (session.get(Track, track_id) for track_id in ids) if track]


async def parse_one(
    filename: str, known: set[str], *, use_ai: bool, config: AIConfig | None
) -> tuple[ParsedFilename, str, str | None]:
    """解析单个文件名，返回 (解析结果, 来源, 说明)。"""
    if use_ai:
        try:
            parsed = await parse_filename_with_ai(filename, config=config)
            return parsed, "ai", parsed.note
        except AIUnavailableError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            parsed = parse_filename(filename, known)
            return parsed, "heuristic", f"AI 解析失败，已回退到本地解析：{exc}"
    parsed = parse_filename(filename, known)
    return parsed, "heuristic", parsed.note or None


class FilenameParseService:
    """批量文件名解析。"""

    async def preview(
        self,
        session: Session,
        ids: list[int],
        *,
        use_ai: bool = False,
        strategy: str = "fill_empty",
        config: AIConfig | None = None,
    ) -> dict[str, Any]:
        """dry-run：返回每首的解析结果与将写入的字段差异。"""
        known = scrape_orchestrator.known_artists(session)
        items: list[dict[str, Any]] = []
        summary = {"total": 0, "changed": 0, "unchanged": 0, "invalid": 0}
        for track in load_tracks(session, ids):
            summary["total"] += 1
            parsed, source, note = await parse_one(
                track.filename, known, use_ai=use_ai, config=config
            )
            diffs = compute_diffs(track, parsed, strategy)
            if diffs:
                status = STATUS_OK
            elif _has_fields(parsed):
                status = STATUS_UNCHANGED
            else:
                status = STATUS_INVALID
            summary["changed" if status == STATUS_OK else status] += 1
            items.append(
                {
                    "track_id": track.id,
                    "path": track.path,
                    "source": source,
                    "confidence": parsed.confidence,
                    "note": note,
                    "fields": {
                        "title": parsed.title,
                        "artist": parsed.artist,
                        "album": parsed.album,
                        "track_no": parsed.track_no,
                    },
                    "diffs": diffs,
                    "status": status,
                }
            )
        return {**summary, "items": items}

    async def apply(
        self,
        session: Session,
        ids: list[int],
        *,
        use_ai: bool = False,
        strategy: str = "fill_empty",
        config: AIConfig | None = None,
    ) -> dict[str, int]:
        """按策略写回标签；单首失败不影响整批。"""
        known = scrape_orchestrator.known_artists(session)
        tag_service = TagService()
        stats = {"total": 0, "changed": 0, "unchanged": 0, "invalid": 0, "failed": 0}
        for track in load_tracks(session, ids):
            stats["total"] += 1
            parsed, _source, _note = await parse_one(
                track.filename, known, use_ai=use_ai, config=config
            )
            diffs = compute_diffs(track, parsed, strategy)
            if not diffs:
                stats["unchanged" if _has_fields(parsed) else "invalid"] += 1
                continue
            values = {diff["field"]: diff["new_value"] for diff in diffs}
            try:
                tag_service.apply_single(session, track, values, source=SOURCE_BATCH)
            except Exception:  # noqa: BLE001 - 单首失败不影响整批
                stats["failed"] += 1
                continue
            stats["changed"] += 1
        return stats
