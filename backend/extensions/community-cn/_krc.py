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


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _normalize_words(raw: list[tuple[str, int, int]], start: int) -> list[dict[str, Any]]:
    """把 ``[(text, 起点ms, 时长ms)]`` 规整为逐字结构（``start`` 为行起点，用于换算相对偏移）。

    平台常在**每个字之间**插入一个独立空格段作为分词/分隔符；但**稀疏空格是真实内容**。因此：
    仅当该行几乎每个字之间都有空格段时，才把它们当分隔符去掉（拉丁词间补空格）；否则原样保留。
    """
    content = [(text.strip(), ms, dur) for text, ms, dur in raw if text.strip()]
    blanks = len(raw) - len(content)
    dense = blanks > 0 and blanks >= max(1, len(content) - 1)

    if dense:
        words: list[dict[str, Any]] = []
        for index, (token, ms, dur) in enumerate(content):
            if index > 0 and _is_latin(content[index - 1][0][-1]) and _is_latin(token[0]):
                words.append({"offset": ms - start, "duration": 0, "text": " "})
            words.append({"offset": ms - start, "duration": dur, "text": token})
        return words

    words = []
    for text, ms, dur in raw:
        token = text if text.strip() else " "
        if token:
            words.append({"offset": ms - start, "duration": dur, "text": token})
    return words


def parse_krc(text: str) -> list[dict[str, Any]]:
    """解析为逐行逐字结构：``[{start, duration, text, words:[{offset,duration,text}]}]``。"""
    lines: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        match = _WORD_LINE.match(line)
        if match:
            start, duration, body = int(match.group(1)), int(match.group(2)), match.group(3)
            raw_tokens = [
                (chunk, int(offset), int(word_duration))
                for offset, word_duration, chunk in _WORD.findall(body)
            ]
            words = _normalize_words(raw_tokens, 0)  # KRC 字偏移已是相对行首
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
                {
                    "start": ms,
                    "duration": 0,
                    "text": content,
                    "words": [{"offset": 0, "duration": 0, "text": content}],
                }
            )
    return lines
