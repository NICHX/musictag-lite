"""简繁转换（F13）。

基于 OpenCC 的纯 Python 实现（opencc-python-reimplemented），
不引入 C 扩展，也不依赖 ffmpeg。转换器按配置缓存，避免重复加载词表。
"""

from __future__ import annotations

from functools import lru_cache

# 方向 → OpenCC 配置名
DIRECTIONS: dict[str, str] = {
    "s2t": "s2t",  # 简体 → 繁体
    "t2s": "t2s",  # 繁体 → 简体
}

DIRECTION_LABELS: dict[str, str] = {
    "s2t": "简 → 繁",
    "t2s": "繁 → 简",
}


class ConversionUnavailableError(RuntimeError):
    """未安装 OpenCC 依赖。"""


def is_available() -> bool:
    try:
        _converter("s2t")
    except ConversionUnavailableError:
        return False
    return True


@lru_cache(maxsize=len(DIRECTIONS))
def _converter(direction: str):  # noqa: ANN202 - 返回 OpenCC 实例
    try:
        from opencc import OpenCC
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的保护
        raise ConversionUnavailableError(
            "未安装 opencc-python-reimplemented，无法进行简繁转换"
        ) from exc
    config = DIRECTIONS.get(direction)
    if config is None:
        raise ValueError(f"不支持的转换方向：{direction}")
    return OpenCC(config)


def convert(text: str | None, direction: str) -> str | None:
    """按方向转换文本；``None`` / 空串原样返回。"""
    if not text:
        return text
    return _converter(direction).convert(text)
