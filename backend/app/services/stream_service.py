"""音频流式播放（F10）。

不依赖 ffmpeg：按 HTTP Range 直接读取原始文件字节区间，
使浏览器的 <audio> 能拖动定位、边下边播。
"""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")
_CHUNK_SIZE = 256 * 1024

_AUDIO_TYPES = {
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".ape": "audio/x-ape",
    ".wv": "audio/x-wavpack",
    ".dsf": "audio/x-dsf",
    ".dff": "audio/x-dff",
    ".wma": "audio/x-ms-wma",
}


def guess_media_type(path: Path) -> str:
    return (
        _AUDIO_TYPES.get(path.suffix.lower())
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """解析 ``bytes=start-end``；无法满足时返回 None。

    支持三种形式：``bytes=0-99``、``bytes=100-``、``bytes=-50``（末尾 50 字节）。
    """
    if not header or size <= 0:
        return None
    match = _RANGE.fullmatch(header.strip())
    if match is None:
        return None
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return None
    if not start_text:  # 后缀范围
        length = int(end_text)
        if length <= 0:
            return None
        return max(size - length, 0), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start >= size or start > end:
        return None
    return start, min(end, size - 1)


def iter_range(path: Path, start: int, end: int, chunk_size: int = _CHUNK_SIZE) -> Iterator[bytes]:
    """按块产出 [start, end] 区间内的字节。"""
    remaining = end - start + 1
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            data = handle.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def build_stream_response(request: Request, path: Path) -> StreamingResponse:
    """构造 200（全量）或 206（Range）流式响应。"""
    size = path.stat().st_size
    media_type = guess_media_type(path)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}

    range_header = request.headers.get("range")
    if range_header:
        parsed = parse_range(range_header, size)
        if parsed is None:
            raise HTTPException(
                status_code=416,
                detail="请求的字节范围无法满足",
                headers={"Content-Range": f"bytes */{size}"},
            )
        start, end = parsed
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            iter_range(path, start, end),
            status_code=206,
            media_type=media_type,
            headers=headers,
        )

    headers["Content-Length"] = str(size)
    return StreamingResponse(
        iter_range(path, 0, size - 1),
        status_code=200,
        media_type=media_type,
        headers=headers,
    )
