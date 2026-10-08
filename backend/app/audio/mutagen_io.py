"""mutagen 实现（音频核心技术层）。

M0 阶段仅落定接口与结构；具体读写逻辑在 M1 实现（F2–F6）。
本模块实现 ``audio.base.AudioIO`` 协议，**不依赖 ffmpeg**。
"""

from __future__ import annotations

from pathlib import Path

from app.audio.base import AudioDocument, AudioIO, AudioProperties, CoverImage, TagSet
from app.audio.formats import format_name, is_supported

_MILESTONE = "该能力将在 M1 实现"


class UnsupportedFormatError(ValueError):
    """扩展名不受支持。"""


class MutagenIO(AudioIO):
    """基于 mutagen 的音频读写实现。"""

    def read(self, path: str | Path) -> AudioDocument:
        raise NotImplementedError(_MILESTONE)

    def read_properties(self, path: str | Path) -> AudioProperties:
        raise NotImplementedError(_MILESTONE)

    def write_tags(self, path: str | Path, tags: TagSet) -> None:
        raise NotImplementedError(_MILESTONE)

    def read_cover(self, path: str | Path) -> CoverImage | None:
        raise NotImplementedError(_MILESTONE)

    def write_cover(self, path: str | Path, cover: CoverImage) -> None:
        raise NotImplementedError(_MILESTONE)

    def delete_cover(self, path: str | Path) -> bool:
        raise NotImplementedError(_MILESTONE)

    def read_lyrics(self, path: str | Path) -> str | None:
        raise NotImplementedError(_MILESTONE)

    def write_lyrics(self, path: str | Path, content: str) -> None:
        raise NotImplementedError(_MILESTONE)

    # ---- 已可用的辅助能力 ----
    @staticmethod
    def supports(path: str | Path) -> bool:
        """判断扩展名是否受支持。"""
        return is_supported(Path(path).suffix)

    @staticmethod
    def format_of(path: str | Path) -> str:
        """返回格式名（如 FLAC）。"""
        return format_name(Path(path).suffix)


# 默认单例，供服务层注入
audio_io: AudioIO = MutagenIO()
