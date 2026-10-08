"""转换服务：ffmpeg 转码（F18，P2，可选）。

核心功能不依赖 ffmpeg；本模块仅在其可用时启用。
"""

from __future__ import annotations

import shutil

_MILESTONE = "转码将在 M2 实现（需 ffmpeg）"


def ffmpeg_available() -> bool:
    """检测系统是否安装 ffmpeg（用于设置页展示与入口开关）。"""
    return shutil.which("ffmpeg") is not None


def fpcalc_available() -> bool:
    """检测 Chromaprint 的 fpcalc（P1 指纹识别可选依赖）。"""
    return shutil.which("fpcalc") is not None


class ConvertService:
    """转码任务（M2 实现）。"""

    def convert(self, ids: list[int], target_format: str) -> list[dict[str, object]]:
        if not ffmpeg_available():
            raise RuntimeError("未检测到 ffmpeg，转码功能不可用（核心功能不受影响）")
        raise NotImplementedError(_MILESTONE)
