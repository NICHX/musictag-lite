"""格式与标签容器映射（对应设计文档 附录 A）。

核心原则：仅依赖 mutagen（纯 Python），不引入 ffmpeg。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatInfo:
    """某音频格式的标签容器与能力描述。"""

    ext: str
    name: str
    mutagen_module: str
    tag_container: str
    cover_kind: str | None  # 封面所在字段/机制，None 表示不支持封面
    lyrics_kind: str | None  # 歌词所在字段/机制，None 表示不支持歌词
    writable: bool = True  # False 表示只读/不保证写入


# 扩展名 -> 格式信息
FORMATS: dict[str, FormatInfo] = {
    ".mp3": FormatInfo(".mp3", "MP3", "mutagen.id3", "ID3v2.3/2.4", "APIC", "USLT"),
    ".flac": FormatInfo(".flac", "FLAC", "mutagen.flac", "Vorbis Comment", "PICTURE", "LYRICS"),
    ".ogg": FormatInfo(
        ".ogg",
        "OGG Vorbis",
        "mutagen.oggvorbis",
        "Vorbis Comment",
        "METADATA_BLOCK_PICTURE",
        "LYRICS",
    ),
    ".oga": FormatInfo(
        ".oga",
        "OGG Vorbis",
        "mutagen.oggvorbis",
        "Vorbis Comment",
        "METADATA_BLOCK_PICTURE",
        "LYRICS",
    ),
    ".opus": FormatInfo(
        ".opus", "Opus", "mutagen.oggopus", "Vorbis Comment", "METADATA_BLOCK_PICTURE", "LYRICS"
    ),
    ".m4a": FormatInfo(".m4a", "M4A/MP4", "mutagen.mp4", "iTunes MP4", "covr", "©lyr"),
    ".mp4": FormatInfo(".mp4", "MP4", "mutagen.mp4", "iTunes MP4", "covr", "©lyr"),
    ".m4b": FormatInfo(".m4b", "MP4 Audiobook", "mutagen.mp4", "iTunes MP4", "covr", "©lyr"),
    ".wma": FormatInfo(".wma", "WMA/ASF", "mutagen.asf", "ASF", "WM/Picture", None, writable=False),
    ".asf": FormatInfo(".asf", "ASF", "mutagen.asf", "ASF", "WM/Picture", None, writable=False),
    ".ape": FormatInfo(".ape", "APE", "mutagen.apev2", "APEv2", "Cover Art", "Lyrics"),
    ".wv": FormatInfo(".wv", "WavPack", "mutagen.wavpack", "APEv2", "Cover Art", "Lyrics"),
    ".wav": FormatInfo(".wav", "WAV", "mutagen.wave", "ID3/INFO", "APIC", "USLT"),
    ".aiff": FormatInfo(".aiff", "AIFF", "mutagen.aiff", "ID3", "APIC", "USLT"),
    ".aif": FormatInfo(".aif", "AIFF", "mutagen.aiff", "ID3", "APIC", "USLT"),
    ".dsf": FormatInfo(".dsf", "DSF", "mutagen.dsf", "ID3", "APIC", "USLT"),
    ".mpc": FormatInfo(".mpc", "Musepack", "mutagen.musepack", "APEv2", "Cover Art", "Lyrics"),
    ".tta": FormatInfo(".tta", "TrueAudio", "mutagen.tta", "ID3", "APIC", "USLT"),
}

# 扫描白名单扩展名
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(FORMATS.keys())


def get_format(ext: str) -> FormatInfo | None:
    """按扩展名（含点，大小写不敏感）查询格式信息。"""
    return FORMATS.get(ext.lower())


def is_supported(ext: str) -> bool:
    """扩展名是否为受支持的可识别音频格式。"""
    return ext.lower() in FORMATS


def format_name(ext: str) -> str:
    """返回人类可读的格式名，未知返回大写扩展名。"""
    info = get_format(ext)
    return info.name if info else ext.lstrip(".").upper()
