"""歌词服务：内嵌歌词 + .lrc 边车读取/写入，LRC 时间轴校验（F6）。

M0 提供 LRC 校验纯函数；读写落盘在 M1 完成。
"""

from __future__ import annotations

import re

_MILESTONE = "歌词读写将在 M1 实现"

# 形如 [mm:ss.xx] 或 [mm:ss]
_LRC_TIME_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def validate_lrc(content: str) -> bool:
    """校验歌词是否为合法 LRC：至少含一行时间轴。"""
    if not content or not content.strip():
        return False
    return any(_LRC_TIME_RE.search(line) for line in content.splitlines())


def is_lrc(content: str) -> bool:
    return validate_lrc(content)


class LyricsService:
    """歌词读写（M1 实现）。"""

    def read(self, track_id: int) -> tuple[str | None, str | None]:
        """返回 (content, source)。"""
        raise NotImplementedError(_MILESTONE)

    def write(self, track_id: int, content: str, *, target: str = "embedded") -> None:
        raise NotImplementedError(_MILESTONE)
