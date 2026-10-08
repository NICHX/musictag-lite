"""F10 试听：HTTP Range 解析与流式响应。"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.core.db import engine
from app.models.db import Library, Track
from app.services.stream_service import parse_range

PAYLOAD = bytes(range(256)) * 8  # 2048 字节，内容可校验


def _make_track(tmp_path: Path, name: str) -> tuple[int, Path]:
    """直接建库+曲目记录（不经扫描，便于精确断言字节）。"""
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / "song.flac"
    file_path.write_bytes(PAYLOAD)
    with Session(engine) as session:
        library = Library(name=f"stream-{name}", root_path=str(root))
        session.add(library)
        session.commit()
        session.refresh(library)
        track = Track(
            library_id=library.id,
            path=str(file_path),
            filename=file_path.name,
            size=len(PAYLOAD),
            format="FLAC",
        )
        session.add(track)
        session.commit()
        session.refresh(track)
        return track.id, file_path


# ---- 纯函数：Range 解析 ----


def test_parse_range_full_and_open_ended() -> None:
    size = 2048
    assert parse_range("bytes=0-99", size) == (0, 99)
    assert parse_range("bytes=100-", size) == (100, 2047)
    assert parse_range("bytes=-50", size) == (1998, 2047)
    # 结束位置超出实际大小时收敛到末尾
    assert parse_range("bytes=2000-9999", size) == (2000, 2047)


def test_parse_range_invalid_returns_none() -> None:
    size = 2048
    assert parse_range(None, size) is None
    assert parse_range("", size) is None
    assert parse_range("bytes=", size) is None
    assert parse_range("items=0-10", size) is None
    assert parse_range("bytes=3000-", size) is None  # 起点越界
    assert parse_range("bytes=100-50", size) is None  # 起点大于终点
    assert parse_range("bytes=-0", size) is None
    assert parse_range("bytes=0-10", 0) is None  # 空文件


# ---- 接口：流式响应 ----


def test_stream_full_returns_200_and_all_bytes(client, tmp_path: Path) -> None:
    track_id, _ = _make_track(tmp_path, "full")
    resp = client.get(f"/api/tracks/{track_id}/stream")
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-type"].startswith("audio/flac")
    assert resp.content == PAYLOAD


def test_stream_range_returns_206_with_slice(client, tmp_path: Path) -> None:
    track_id, _ = _make_track(tmp_path, "range")
    resp = client.get(f"/api/tracks/{track_id}/stream", headers={"Range": "bytes=0-99"})
    assert resp.status_code == 206
    assert resp.headers["content-range"] == f"bytes 0-99/{len(PAYLOAD)}"
    assert resp.headers["content-length"] == "100"
    assert resp.content == PAYLOAD[:100]

    tail = client.get(f"/api/tracks/{track_id}/stream", headers={"Range": "bytes=-16"})
    assert tail.status_code == 206
    assert tail.content == PAYLOAD[-16:]


def test_stream_unsatisfiable_range_returns_416(client, tmp_path: Path) -> None:
    track_id, _ = _make_track(tmp_path, "bad")
    resp = client.get(f"/api/tracks/{track_id}/stream", headers={"Range": "bytes=99999-"})
    assert resp.status_code == 416
    assert resp.headers["content-range"] == f"bytes */{len(PAYLOAD)}"


def test_stream_missing_file_returns_404(client, tmp_path: Path) -> None:
    track_id, file_path = _make_track(tmp_path, "gone")
    file_path.unlink()
    assert client.get(f"/api/tracks/{track_id}/stream").status_code == 404
