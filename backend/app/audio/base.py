"""音频 IO 抽象：统一的数据结构与读写接口。

所有格式的读写最终由 mutagen 实现（见 ``mutagen_io.MutagenIO``），
上层服务只依赖本模块的抽象，便于测试与替换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class TagSet:
    """可读写的核心标签集合。"""

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
    lyrics: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class AudioProperties:
    """只读技术参数。"""

    duration: float | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bit_depth: int | None = None
    format: str | None = None
    codec: str | None = None


@dataclass
class CoverImage:
    """封面图像数据。"""

    data: bytes
    mime: str = "image/jpeg"
    width: int | None = None
    height: int | None = None
    kind: str = "front"  # front | back | other


@dataclass
class AudioDocument:
    """一次读取的完整结果（标签 + 技术参数 + 封面 + 歌词）。"""

    path: Path
    properties: AudioProperties = field(default_factory=AudioProperties)
    tags: TagSet = field(default_factory=TagSet)
    cover: CoverImage | None = None
    lyrics: str | None = None


@runtime_checkable
class AudioIO(Protocol):
    """音频读写协议；所有实现须为纯 Python（mutagen）。"""

    def read(self, path: str | Path) -> AudioDocument: ...

    def read_properties(self, path: str | Path) -> AudioProperties: ...

    def write_tags(self, path: str | Path, tags: TagSet) -> None: ...

    def read_cover(self, path: str | Path) -> CoverImage | None: ...

    def write_cover(self, path: str | Path, cover: CoverImage) -> None: ...

    def delete_cover(self, path: str | Path) -> bool: ...

    def read_lyrics(self, path: str | Path) -> str | None: ...

    def write_lyrics(self, path: str | Path, content: str) -> None: ...
