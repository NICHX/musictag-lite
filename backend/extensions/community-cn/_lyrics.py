"""歌词组合：把「原文 / 译文 / 罗马音」合并为标准 LRC。

标准 LRC 用「相同时间戳的连续多行」即可表达双语/多语对照，普通播放器（Navidrome /
Plex / 手机播放器）都能识别——LDDC 的「多样歌词组合」正是这个思路。
逐字歌词（QRC/KRC）为非标准格式且需解密，此处不涉及。
"""

from __future__ import annotations

import re

# [mm:ss]、[mm:ss.xx]、[mm:ss.xxx]
_TAG = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")


def parse_lrc(text: str | None) -> list[tuple[int, str, str]]:
    """解析 LRC 为 ``[(毫秒, 归一化时间戳, 歌词)]``；一行带多个时间戳会被展开。"""
    if not text:
        return []
    parsed: list[tuple[int, str, str]] = []
    for raw in text.splitlines():
        tags = _TAG.findall(raw)
        if not tags:
            continue
        content = _TAG.sub("", raw).strip()
        for minute, second, frac in tags:
            ms = int(minute) * 60_000 + int(second) * 1_000 + int(((frac or "0") + "00")[:3])
            tag = f"[{int(minute):02d}:{int(second):02d}.{ms % 1000:03d}]"
            parsed.append((ms, tag, content))
    return parsed


def merge_lrc(main: str | None, *extras: str | None) -> str:
    """以主轨（原文）的行序为基准，把译文/罗马音插到同一时间戳之下。

    - 主轨里不含时间戳的行（``[ti:]`` / ``[ar:]`` 等元信息）原样保留在原位置；
    - 没有可用附加轨时不做任何改动，直接返回主轨。
    """
    if not main:
        return main or ""
    extra_maps: list[dict[int, str]] = []
    for track in extras:
        mapping: dict[int, str] = {}
        for ms, _tag, content in parse_lrc(track):
            if content and ms not in mapping:
                mapping[ms] = content
        if mapping:
            extra_maps.append(mapping)
    if not extra_maps:
        return main

    lines: list[str] = []
    for raw in main.splitlines():
        tags = _TAG.findall(raw)
        if not tags:
            lines.append(raw)
            continue
        content = _TAG.sub("", raw).strip()
        for minute, second, frac in tags:
            ms = int(minute) * 60_000 + int(second) * 1_000 + int(((frac or "0") + "00")[:3])
            tag = f"[{int(minute):02d}:{int(second):02d}.{ms % 1000:03d}]"
            lines.append(f"{tag}{content}")
            for mapping in extra_maps:
                extra = mapping.get(ms)
                if extra and extra != content:
                    lines.append(f"{tag}{extra}")
    return "\n".join(lines)
