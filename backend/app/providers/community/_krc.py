"""酷狗 KRC（逐字歌词）解密与解析。

KRC 结构：``krc1`` 魔数 + 逐字节循环异或 16 字节密钥的 zlib 流。
解压后为文本，行格式：``[行起点ms,行时长ms]<字偏移ms,字时长ms,0>字<...>``。
"""

from __future__ import annotations

import re
import zlib
from typing import Any

_KRC_KEY = bytes(
    [0x40, 0x47, 0x61, 0x77, 0x5E, 0x32, 0x74, 0x47, 0x51, 0x36, 0x31, 0x2D, 0xCE, 0xD2, 0x6E, 0x69]
)
_WORD_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_WORD = re.compile(r"<(\d+),(\d+),\d+>([^<]*)")
_LRC_LINE = re.compile(r"^\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\](.*)$")


class KRCError(ValueError):
    """KRC 数据非法（魔数不符或解压失败）。"""


def decrypt_krc(data: bytes) -> str:
    """解密 KRC 并返回文本；非法数据抛 ``KRCError``。"""
    if len(data) < 8 or data[:4] != b"krc1":
        raise KRCError("不是 KRC 数据")
    payload = bytearray(data[4:])
    for i in range(len(payload)):
        payload[i] ^= _KRC_KEY[i % 16]
    try:
        plain = zlib.decompress(bytes(payload))
    except zlib.error as exc:  # noqa: BLE001 - 统一转成业务异常
        raise KRCError(f"KRC 解压失败：{exc}") from exc
    return plain.decode("utf-8", errors="replace")


def parse_krc(text: str) -> list[dict[str, Any]]:
    """解析为逐行逐字结构：``[{start, duration, text, words:[{offset,duration,text}]}]``。"""
    lines: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        match = _WORD_LINE.match(line)
        if match:
            start, duration, body = int(match.group(1)), int(match.group(2)), match.group(3)
            words = [
                {"offset": int(o), "duration": int(d), "text": chunk}
                for o, d, chunk in _WORD.findall(body)
                if chunk
            ]
            if words:
                lines.append(
                    {
                        "start": start,
                        "duration": duration,
                        "text": "".join(w["text"] for w in words),
                        "words": words,
                    }
                )
            continue
        lrc = _LRC_LINE.match(line)
        if lrc:
            ms = int(lrc.group(1)) * 60_000 + int(lrc.group(2)) * 1_000
            content = lrc.group(4).strip()
            lines.append(
                {"start": ms, "duration": 0, "text": content, "words": [{"offset": 0, "duration": 0, "text": content}]}
            )
    return lines


def ms_to_lrc_time(ms: int) -> str:
    """毫秒 → ``mm:ss.cc``（厘秒，与 LDDC / lx-music 一致）。"""
    total = max(0, int(ms)) // 1000
    return f"{total // 60:02d}:{total % 60:02d}.{(max(0, int(ms)) % 1000) // 10:02d}"


def to_plain_lrc(lines: list[dict[str, Any]]) -> str:
    """逐行逐字结构 → 标准逐行 LRC（不带逐字标记，普通播放器通用）。"""
    out: list[str] = []
    for line in lines:
        text = str(line.get("text") or "").strip()
        if text:
            out.append(f"[{ms_to_lrc_time(line.get('start') or 0)}]{text}")
    return "\n".join(out)


_LINE_TAG = re.compile(r"^\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\](.*)$")
_WORD_TAG = re.compile(r"\[\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]\]")


def _tag_ms(minute: str, second: str, frac: str | None) -> int:
    return int(minute) * 60_000 + int(second) * 1_000 + int(((frac or "0") + "00")[:3])


def parse_word_lrc(text: str | None) -> list[dict[str, Any]]:
    """逐字标记 LRC（``[行][[字]]字``）→ 与 ``parse_krc`` 一致的逐行逐字结构。"""
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
