"""逐字歌词 → LRC 的通用转换与解析（与具体数据源无关的核心工具）。

逐字歌词以统一结构表示：``[{start, duration, text, words:[{offset, duration, text}]}]``
（毫秒为单位的行起点、字相对行首的偏移）。
"""

from __future__ import annotations

import re
from typing import Any

_LINE_TAG = re.compile(r"^\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\](.*)$")
_WORD_TAG = re.compile(r"\[\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]\]")


def ms_to_lrc_time(ms: int) -> str:
    """毫秒 → ``mm:ss.cc``（厘秒，与 LDDC / lx-music 一致）。"""
    total = max(0, int(ms)) // 1000
    return f"{total // 60:02d}:{total % 60:02d}.{(max(0, int(ms)) % 1000) // 10:02d}"


def _tag_ms(minute: str, second: str, frac: str | None) -> int:
    return int(minute) * 60_000 + int(second) * 1_000 + int(((frac or "0") + "00")[:3])


def to_plain_lrc(lines: list[dict[str, Any]]) -> str:
    """逐行逐字结构 → 标准逐行 LRC（不带逐字标记，普通播放器通用）。"""
    out: list[str] = []
    for line in lines:
        text = str(line.get("text") or "").strip()
        if text:
            out.append(f"[{ms_to_lrc_time(line.get('start') or 0)}]{text}")
    return "\n".join(out)


def to_word_lrc(lines: list[dict[str, Any]]) -> str:
    """逐行逐字结构 → 逐字标记 LRC：``[行时间][[字时间]]字[[字时间]]字…``。

    与 LDDC 的「逐字 LRC」一致；单字行不加逐字标记。
    """
    out: list[str] = []
    for line in lines:
        words = line.get("words") or []
        start = int(line.get("start") or 0)
        parts: list[str] = []
        for word in words:
            text = str(word.get("text") or "")
            if not text:
                continue
            if len(words) > 1:
                moment = start + int(word.get("offset") or 0)
                parts.append(f"[[{ms_to_lrc_time(moment)}]]{text}")
            else:
                parts.append(text)
        body = "".join(parts)
        if body:
            out.append(f"[{ms_to_lrc_time(start)}]{body}")
    return "\n".join(out)


def parse_word_lrc(text: str | None) -> list[dict[str, Any]]:
    """逐字标记 LRC（``[行][[字]]字``）→ 统一的逐行逐字结构。"""
    lines: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        match = _LINE_TAG.match(raw.strip())
        if not match:
            continue
        start = _tag_ms(match.group(1), match.group(2), match.group(3))
        body = match.group(4)
        tags = list(_WORD_TAG.finditer(body))
        if not tags:
            content = body.strip()
            if content:
                lines.append(
                    {
                        "start": start,
                        "duration": 0,
                        "text": content,
                        "words": [{"offset": 0, "duration": 0, "text": content}],
                    }
                )
            continue
        words = []
        for index, tag in enumerate(tags):
            end = tags[index + 1].start() if index + 1 < len(tags) else len(body)
            piece = body[tag.end() : end]
            if piece:
                words.append(
                    {
                        "offset": _tag_ms(*tag.groups()) - start,
                        "duration": 0,
                        "text": piece,
                    }
                )
        if words:
            lines.append(
                {
                    "start": start,
                    "duration": 0,
                    "text": "".join(word["text"] for word in words),
                    "words": words,
                }
            )
    return lines


def _lrc_index(text: str | None) -> dict[int, str]:
    """把普通 LRC 解析为 ``{行起点ms: 文本}``；同一时间戳多行取最后一个。

    双语对照 LRC 里同一时间戳先原文、后译文，因此"最后一个"即译文行。
    """
    index: dict[int, str] = {}
    for raw in (text or "").splitlines():
        match = _LINE_TAG.match(raw.strip())
        if not match:
            continue
        start = _tag_ms(match.group(1), match.group(2), match.group(3))
        content = match.group(4).strip()
        if content:
            index[start] = content
    return index


def has_translation(word_lrc: str, translation_lrc: str | None) -> bool:
    """判断 ``translation_lrc`` 相对逐字行是否确实带有译文（至少一行与原文不同）。"""
    index = _lrc_index(translation_lrc)
    if not index:
        return False
    for line in parse_word_lrc(word_lrc):
        text = str(line.get("text") or "").strip()
        translated = index.get(int(line.get("start") or 0))
        if translated and translated != text:
            return True
    return False


def merge_word_translation(word_lrc: str, translation_lrc: str) -> str:
    """把逐字 LRC 与译文（双语对照 LRC）合并为单份 LRC。

    每条逐字行后紧跟同时间的译文行；即为 LDDC / 椒盐音乐等可**同时渲染逐字与译文**
    的播放器所读取的格式。
    """
    index = _lrc_index(translation_lrc)
    out: list[str] = []
    for line in parse_word_lrc(word_lrc):
        start = int(line.get("start") or 0)
        out.append(to_word_lrc([line]))
        translated = index.get(start)
        if translated and translated != str(line.get("text") or "").strip():
            out.append(f"[{ms_to_lrc_time(start)}]{translated}")
    return "\n".join(part for part in out if part)
