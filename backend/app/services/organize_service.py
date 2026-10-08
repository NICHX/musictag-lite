"""整理服务：按模板重命名/移动文件（F15，P1）。

M0 提供模板渲染纯函数；实际移动与冲突检测在 M1/M2 完成。
"""

from __future__ import annotations

from typing import Any

_MILESTONE = "整理落盘将在 M1/M2 实现"

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


def render_template(template: str, values: dict[str, Any]) -> str:
    """渲染路径模板，支持 ``{track:02d}`` 之类的格式说明符。

    缺失字段渲染为空串，并清理多余的分隔与空白。
    """
    safe_values = {k: ("" if v is None else v) for k, v in values.items()}
    if "album_artist" in safe_values and "albumartist" not in safe_values:
        safe_values["albumartist"] = safe_values["album_artist"]
    if "track_no" in safe_values and "track" not in safe_values:
        safe_values["track"] = safe_values["track_no"]

    class _Default(dict):
        def __missing__(self, key: str) -> str:  # noqa: D105
            return ""

    try:
        rendered = template.format_map(_Default(safe_values))
    except (ValueError, KeyError):
        rendered = template

    # 规范化路径分隔与空白
    parts = [segment.strip() for segment in rendered.replace("\\", "/").split("/")]
    return "/".join(segment for segment in parts if segment)


class OrganizeService:
    """重命名/移动（M1/M2 实现）。"""

    def preview(self, ids: list[int], template: str, *, move: bool = False) -> list[dict[str, Any]]:
        raise NotImplementedError(_MILESTONE)

    def apply(self, ids: list[int], template: str, *, move: bool = False) -> list[dict[str, Any]]:
        raise NotImplementedError(_MILESTONE)
