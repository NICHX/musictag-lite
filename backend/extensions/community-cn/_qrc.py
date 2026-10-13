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


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _normalize_words(raw: list[tuple[str, int, int]], start: int) -> list[dict[str, Any]]:
    """把 ``[(text, 起点ms, 时长ms)]`` 规整为逐字结构。

    平台常在**每个字之间**插入一个独立空格段作为分词/分隔符（其渲染器不显示），
    但**稀疏的空格是真实歌词内容**（如「坚持 经已」）。因此：

    - 若该行几乎每个字之间都有空格段 → 视为分隔符：去掉空格段，仅在两个拉丁词之间补空格；
    - 否则 → 原样保留（空格段作为内容），不做增删。
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


def parse_qrc(content: str) -> list[dict[str, Any]]:
    """解析为与 ``_krc`` 一致的逐行逐字结构（``offset`` 为相对行首毫秒）。"""
    lines: list[dict[str, Any]] = []
    for raw in content.splitlines():
        match = _LINE.match(raw.strip())
        if not match:
            continue
        start, duration = int(match.group(1)), int(match.group(2))
        raw_tokens = [
            (text, int(w_start), int(w_duration))
            for text, w_start, w_duration in _WORD.findall(match.group(3))
        ]
        words = _normalize_words(raw_tokens, start)
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
