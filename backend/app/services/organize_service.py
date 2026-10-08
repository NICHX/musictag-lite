"""整理服务：按模板重命名/移动文件（F15，P1；F11 的「标签→文件名」分支）。

- ``render_template``：纯函数模板渲染，被 :class:`CoverService` 复用。
- ``OrganizeService``：预演（绝不写盘）与落盘（重命名 / 移动 + 同名边车文件）。

约定：
- 目标路径必须落在曲目所属库根目录内，否则判为无效；
- 目标已存在、批次内目标重名、同名歌词已存在一律判为冲突，执行时跳过、绝不覆盖；
- 目录级封面（cover/folder/front）为同目录多曲目共享，采用「复制」而非「移动」，
  避免影响原目录其他曲目。
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.core.security import PathSecurityError, ensure_within_roots
from app.models.db import Library, Track, utcnow
from app.services import oplog

# 模板可用字段
TEMPLATE_FIELDS: tuple[str, ...] = (
    "albumartist",
    "album_artist",
    "artist",
    "album",
    "year",
    "track",
    "track_no",
    "disc",
    "disc_no",
    "title",
    "genre",
    "composer",
)

# 预演状态
STATUS_OK = "ok"
STATUS_UNCHANGED = "unchanged"
STATUS_CONFLICT = "conflict"
STATUS_INVALID = "invalid"

# 模板占位符：{field} 或 {field:spec}（字段名限定为标识符，避免属性/下标访问）
_FIELD_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(:[^{}]*)?\}")
# 渲染结果是否含有实质内容（剔除分隔符/空白后仍有字符）
_CONTENT_RE = re.compile(r"[^\s._/\\-]")


def render_template(template: str, values: dict[str, Any]) -> str:
    """渲染路径模板，支持 ``{track:02d}`` 之类的格式说明符。

    - 缺失字段与空值渲染为空串；
    - 格式说明符对空值不生效（如缺音轨号时 ``{track:02d}`` 直接留空），
      避免因 ``"" 无法按 :02d 格式化`` 而误留原始模板；
    - 逐字段替换，杜绝 ``str.format`` 的属性/下标访问面。
    """
    safe_values = {k: ("" if v is None else v) for k, v in values.items()}
    if "album_artist" in safe_values and "albumartist" not in safe_values:
        safe_values["albumartist"] = safe_values["album_artist"]
    if "track_no" in safe_values and "track" not in safe_values:
        safe_values["track"] = safe_values["track_no"]

    def _substitute(match: re.Match[str]) -> str:
        key, spec = match.group(1), match.group(2)
        if key not in safe_values:
            return ""
        value = safe_values[key]
        if value == "" or value is None:
            return ""
        try:
            return format(value, spec[1:]) if spec else format(value)
        except (ValueError, TypeError):
            return str(value)

    rendered = _FIELD_RE.sub(_substitute, template)

    # 规范化路径分隔与空白
    parts = [segment.strip() for segment in rendered.replace("\\", "/").split("/")]
    return "/".join(segment for segment in parts if segment)


def _sidecar_cover_names() -> tuple[str, ...]:
    """复用封面服务的兜底封面文件名（延迟导入以避免循环依赖）。"""
    from app.services.cover_service import SIDECAR_COVER_NAMES

    return SIDECAR_COVER_NAMES


def _find_case_insensitive(directory: Path, stem: str, suffixes: tuple[str, ...]) -> Path | None:
    """在目录下按「主名不区分大小写 + 指定后缀」查找文件。"""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    target = stem.lower()
    for entry in entries:
        if entry.is_file() and entry.suffix.lower() in suffixes and entry.stem.lower() == target:
            return entry
    return None


@dataclass
class _Resolved:
    """单条曲目的整理计划（预演与执行共用）。"""

    track: Track
    source: Path
    target: Path | None
    status: str
    reason: str | None = None
    sidecars: list[dict[str, str]] = field(default_factory=list)


class OrganizeService:
    """重命名/移动（F15 / F11 的标签→文件名分支）。"""

    def preview(
        self, session: Session, ids: list[int], template: str, *, move: bool = False
    ) -> dict[str, Any]:
        """按模板预演路径变更，返回汇总与逐条明细（不写盘）。"""
        resolved = self._resolve(session, ids, template, move=move)
        items: list[dict[str, Any]] = []
        summary = {
            "total": len(resolved),
            "ok": 0,
            "conflicts": 0,
            "unchanged": 0,
            "invalid": 0,
        }
        for item in resolved:
            key = "conflicts" if item.status == STATUS_CONFLICT else item.status
            summary[key] += 1
            items.append(
                {
                    "track_id": item.track.id,
                    "source": str(item.source),
                    "target": str(item.target) if item.target else None,
                    "status": item.status,
                    "reason": item.reason,
                    "sidecars": [sidecar["source"] for sidecar in item.sidecars],
                }
            )
        return {**summary, "items": items}

    def apply(
        self,
        session: Session,
        ids: list[int],
        template: str,
        *,
        move: bool = False,
        plan: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """执行整理。

        ``plan`` 非空时以用户确认的 ``{track_id, target}`` 为准（仍会重新校验冲突）；
        否则按 ids + 模板重算，只执行状态为 ``ok`` 的条目。
        """
        roots = [lib.root_path for lib in session.exec(select(Library)).all()]
        resolved = self._resolve(session, ids, template, move=move)
        wanted = self._pick(resolved, plan)

        stats: dict[str, Any] = {"total": len(wanted), "moved": 0, "skipped": 0, "failed": 0}
        records: list[dict[str, Any]] = []
        for item in wanted:
            record = self._apply_one(session, item, roots)
            stats[record["result"]] += 1
            records.append(record)
        session.commit()
        stats["items"] = records
        return stats

    # ---- 内部：解析 ----
    def _resolve(
        self, session: Session, ids: list[int], template: str, *, move: bool
    ) -> list[_Resolved]:
        roots = [lib.root_path for lib in session.exec(select(Library)).all()]
        resolved: list[_Resolved] = []
        for track in self._tracks(session, ids):
            source = Path(track.path)
            root = self._library_root(session, track)
            target, reason = self._target_for(track, template, move=move, root=root, roots=roots)
            if target is None:
                resolved.append(_Resolved(track, source, None, STATUS_INVALID, reason))
                continue

            current = source.resolve(strict=False)
            wanted = target.resolve(strict=False)
            if wanted == current:
                resolved.append(_Resolved(track, source, target, STATUS_UNCHANGED))
                continue
            if not source.exists():
                resolved.append(_Resolved(track, source, target, STATUS_INVALID, "源文件不存在"))
                continue
            if wanted.exists():
                resolved.append(_Resolved(track, source, target, STATUS_CONFLICT, "目标已存在"))
                continue

            sidecars = self._sidecars(source, target)
            if any(self._sidecar_conflict(sidecar) for sidecar in sidecars):
                resolved.append(
                    _Resolved(track, source, target, STATUS_CONFLICT, "同名歌词已存在", sidecars)
                )
            else:
                resolved.append(_Resolved(track, source, target, STATUS_OK, None, sidecars))

        return self._mark_duplicates(resolved)

    def _pick(
        self, resolved: list[_Resolved], plan: list[dict[str, Any]] | None
    ) -> list[_Resolved]:
        """选出待执行条目：有计划时以计划为准，否则取 ok 项。"""
        if not plan:
            return [item for item in resolved if item.status == STATUS_OK]

        by_id = {item.track.id: item for item in resolved}
        picked: list[_Resolved] = []
        for entry in plan:
            item = by_id.get(entry.get("track_id"))
            if item is None or not entry.get("target"):
                continue
            target = Path(entry["target"])
            picked.append(
                _Resolved(
                    track=item.track,
                    source=item.source,
                    target=target,
                    status=STATUS_OK,
                    sidecars=self._sidecars(item.source, target),
                )
            )
        return picked

    # ---- 内部：落盘 ----
    def _apply_one(self, session: Session, item: _Resolved, roots: list[str]) -> dict[str, Any]:
        record: dict[str, Any] = {
            "track_id": item.track.id,
            "source": str(item.source),
            "target": str(item.target) if item.target else None,
            "result": "skipped",
            "reason": None,
        }
        target = item.target
        if target is None:
            record["reason"] = "无目标路径"
            return record

        source = item.source
        if target.resolve(strict=False) == source.resolve(strict=False):
            record["reason"] = "路径未变化"
            return record
        if not source.exists():
            record["reason"] = "源文件不存在"
            return record
        try:
            ensure_within_roots(target, roots)
        except PathSecurityError:
            record["reason"] = "目标超出库根目录"
            return record
        if target.resolve(strict=False).exists():
            record["reason"] = "目标已存在，已跳过"
            return record

        try:
            moved = source.parent.resolve(strict=False) != target.parent.resolve(strict=False)
            _move_file(source, target)
            self._apply_sidecars(item.sidecars)
        except OSError as exc:
            record["result"] = "failed"
            record["reason"] = str(exc)
            return record

        track = item.track
        track.path = str(target)
        track.dirname = str(target.parent)
        track.filename = target.name
        track.updated_at = utcnow()
        session.add(track)
        oplog.record(
            session,
            track_id=track.id,
            action="organize.move" if moved else "organize.rename",
            field="path",
            old=str(source),
            new=str(target),
            source="batch",
        )
        record["result"] = "moved"
        return record

    def _apply_sidecars(self, sidecars: list[dict[str, str]]) -> None:
        """移动同名歌词、复制目录级封面；目标已存在则跳过，绝不覆盖。"""
        for sidecar in sidecars:
            source = Path(sidecar["source"])
            target = Path(sidecar["target"])
            if not source.exists() or target.resolve(strict=False).exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if sidecar.get("action") == "copy":
                shutil.copy2(source, target)
            else:
                _move_file(source, target)

    # ---- 内部：辅助 ----
    @staticmethod
    def _tracks(session: Session, ids: list[int]) -> list[Track]:
        tracks: list[Track] = []
        for track_id in ids:
            track = session.get(Track, track_id)
            if track is not None:
                tracks.append(track)
        return tracks

    @staticmethod
    def _library_root(session: Session, track: Track) -> str | None:
        library = session.get(Library, track.library_id)
        return library.root_path if library else None

    @staticmethod
    def _values(track: Track) -> dict[str, Any]:
        return {
            "albumartist": track.album_artist,
            "album_artist": track.album_artist,
            "artist": track.artist,
            "album": track.album,
            "year": track.year,
            "track": track.track_no,
            "track_no": track.track_no,
            "disc": track.disc_no,
            "disc_no": track.disc_no,
            "title": track.title,
            "genre": track.genre,
            "composer": track.composer,
        }

    def _target_for(
        self,
        track: Track,
        template: str,
        *,
        move: bool,
        root: str | None,
        roots: list[str],
    ) -> tuple[Path | None, str | None]:
        rendered = render_template(template, self._values(track))
        if not _CONTENT_RE.search(rendered):
            return None, "模板渲染出空文件名"
        parts = [segment for segment in rendered.split("/") if segment]
        if not parts:
            return None, "模板渲染出空文件名"

        ext = track.ext or Path(track.path).suffix
        if ext and not ext.startswith("."):
            ext = f".{ext}"

        if move:
            base = Path(root) if root else Path(track.path).parent
            directory = base.joinpath(*parts[:-1]) if len(parts) > 1 else base
        else:
            # 同级重命名：只取模板最后一段作为文件名，忽略目录层级
            directory = Path(track.path).parent

        target = directory / f"{parts[-1]}{ext}"
        try:
            ensure_within_roots(target, roots)
        except PathSecurityError:
            return None, "目标超出库根目录"
        return target, None

    def _sidecars(self, source: Path, target: Path) -> list[dict[str, str]]:
        """计算随曲目处理的边车文件（歌词移动 / 封面复制）。"""
        sidecars: list[dict[str, str]] = []
        source_dir, target_dir = source.parent, target.parent

        lrc_source = _find_case_insensitive(source_dir, source.stem, (".lrc",))
        if lrc_source is not None:
            lrc_target = target_dir / f"{target.stem}{lrc_source.suffix.lower()}"
            if lrc_source.resolve(strict=False) != lrc_target.resolve(strict=False):
                sidecars.append(
                    {"source": str(lrc_source), "target": str(lrc_target), "action": "move"}
                )

        if source_dir.resolve(strict=False) != target_dir.resolve(strict=False):
            for name in _sidecar_cover_names():
                cover = source_dir / name
                if cover.is_file():
                    sidecars.append(
                        {"source": str(cover), "target": str(target_dir / name), "action": "copy"}
                    )
        return sidecars

    @staticmethod
    def _sidecar_conflict(sidecar: dict[str, str]) -> bool:
        """仅「移动」类边车的目标被占用才算冲突（复制类跳过即可）。"""
        if sidecar.get("action") != "move":
            return False
        return Path(sidecar["target"]).resolve(strict=False).exists()

    @staticmethod
    def _mark_duplicates(items: list[_Resolved]) -> list[_Resolved]:
        """批次内多个曲目映射到同一目标 → 全部标记为冲突。"""
        groups: dict[str, list[_Resolved]] = {}
        for item in items:
            if item.status == STATUS_OK and item.target is not None:
                groups.setdefault(str(item.target.resolve(strict=False)), []).append(item)
        for group in groups.values():
            if len(group) > 1:
                for item in group:
                    item.status = STATUS_CONFLICT
                    item.reason = "批次内目标重名"
        return items


def _move_file(source: Path, target: Path) -> None:
    """移动/重命名文件；跨文件系统时回退到 shutil.move。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        source.rename(target)
    except OSError:
        shutil.move(str(source), str(target))
