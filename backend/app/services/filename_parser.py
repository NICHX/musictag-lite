"""文件名解析（F11 的「文件名 → 标签」方向）。

纯离线启发式，不依赖任何外部服务。可选传入「已知艺术家」集合
（取自曲库中已标注的艺术家），用于消解「A - B」谁在前谁在后的歧义。

命名惯例在不同曲库中并不统一，例如：
- ``1965 - Zella Day``        → 标题在前
- ``Dua Lipa - Levitating``   → 艺术家在前
- ``Adele - 21 - 03 Rolling`` → 艺术家 - 专辑 - 音轨 标题
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 音质/来源标记（整段括号内容命中即删除）
_NOISE_WORDS = (
    r"flac|ape|wav|wave|mp3|m4a|aac|ogg|opus|dsf|dff|"
    r"320k?bps?|128k?bps?|hires|hi-?res|24-?bit|16-?bit|dsd|sacd|lossless|无损|"
    r"official\s*(?:music\s*)?video|official\s*audio|lyric\s*video|mv|hd|hq"
)
_NOISE_BRACKET = re.compile(rf"\s*[\[【(（]\s*(?:{_NOISE_WORDS})\s*[\]】)）]\s*", re.IGNORECASE)

# 音轨号前缀，如 "01 - "、"07."、"12_"
_TRACK_PREFIX = re.compile(r"^\s*(\d{1,3})\s*[\s._\-]+\s*")

# 两侧带空白的连接符：" - "、en dash、em dash
_SEPARATOR = re.compile(r"\s+[-\u2013\u2014]\s+")


@dataclass
class ParsedFilename:
    """文件名解析结果。"""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    track_no: int | None = None
    confidence: float = 0.0
    note: str = ""


def _strip_noise(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = _NOISE_BRACKET.sub(" ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _split_track_prefix(text: str) -> tuple[int | None, str]:
    match = _TRACK_PREFIX.match(text)
    if not match:
        return None, text
    return int(match.group(1)), text[match.end() :].strip()


def _match_known(name: str | None, known: set[str]) -> bool:
    return bool(name) and name.strip().casefold() in known


def parse_filename(filename: str, known_artists: set[str] | None = None) -> ParsedFilename:
    """把文件名解析为结构化字段。

    ``known_artists`` 为小写艺术家集合；命中时用于判定哪个片段是艺术家，
    从而在「艺术家 - 标题」与「标题 - 艺术家」两种惯例间自动选择。
    """
    known = known_artists or set()
    stem = Path(filename).stem
    cleaned = _strip_noise(stem)

    track_no, cleaned = _split_track_prefix(cleaned)
    parts = [part.strip() for part in _SEPARATOR.split(cleaned) if part.strip()]

    if not parts:
        return ParsedFilename(confidence=0.0, note="空文件名")

    if len(parts) == 1:
        return ParsedFilename(title=parts[0], track_no=track_no, confidence=0.4, note="仅标题")

    if len(parts) == 2:
        left, right = parts
        left_known, right_known = _match_known(left, known), _match_known(right, known)
        if left_known and not right_known:
            artist, title, confidence, note = left, right, 0.95, "命中已知艺术家（艺术家在前）"
        elif right_known and not left_known:
            title, artist, confidence, note = left, right, 0.95, "命中已知艺术家（艺术家在后）"
        else:
            # 无法判定：按「标题 - 艺术家」默认（多数曲库的常见写法）
            title, artist, confidence, note = left, right, 0.6, "默认标题在前"
        sub_track, title2 = _split_track_prefix(title)
        return ParsedFilename(
            title=title2 or title,
            artist=artist,
            track_no=track_no or sub_track,
            confidence=confidence,
            note=note,
        )

    # 3 段及以上：艺术家 - （专辑）… - 标题
    artist, title = parts[0], parts[-1]
    album = " - ".join(parts[1:-1]) or None
    sub_track, title2 = _split_track_prefix(title)
    return ParsedFilename(
        title=title2 or title,
        artist=artist,
        album=album,
        track_no=track_no or sub_track,
        confidence=0.8,
        note="多段：艺术家-专辑-标题",
    )
