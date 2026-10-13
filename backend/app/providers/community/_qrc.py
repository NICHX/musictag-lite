"""QQ 音乐 QRC（逐字歌词）解析。

QQ 返回的是加密 hex（见 ``_crypto.decrypt_qrc``）；解密后是 XML，歌词正文位于
``LyricContent`` 属性内。正文行格式：``[行起点ms,行时长ms]字(字起点ms,字时长ms)字(…)``，
其中**字时间为绝对毫秒**。
"""

from __future__ import annotations

import html
import re
from typing import Any

_LYRIC_CONTENT = re.compile(r'LyricContent="(.*)"', re.S)
_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_WORD = re.compile(r"([^(\[]*)\((\d+),(\d+)\)")


def extract_qrc(xml_text: str) -> str:
    """从 QRC XML 中取出歌词正文（去掉 XML 外壳并反转义）。"""
    match = _LYRIC_CONTENT.search(xml_text)
    return html.unescape(match.group(1)) if match else xml_text


def parse_qrc(content: str) -> list[dict[str, Any]]:
    """解析为与 ``_krc`` 一致的逐行逐字结构（``offset`` 为相对行首毫秒）。"""
    lines: list[dict[str, Any]] = []
    for raw in content.splitlines():
        match = _LINE.match(raw.strip())
        if not match:
            continue
        start, duration = int(match.group(1)), int(match.group(2))
        words = [
            {"offset": int(w_start) - start, "duration": int(w_duration), "text": text}
            for text, w_start, w_duration in _WORD.findall(match.group(3))
            if text
        ]
        if words:
            lines.append(
                {
                    "start": start,
                    "duration": duration,
                    "text": "".join(word["text"] for word in words),
                    "words": words,
                }
            )
    return lines
