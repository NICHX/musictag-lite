"""纯函数单元测试：标签状态、批量策略、模板渲染、LRC 校验、路径安全、增量判定。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.audio.base import TagSet
from app.audio.formats import ALLOWED_EXTENSIONS, format_name, is_supported
from app.core.security import (
    PathSecurityError,
    ensure_within_roots,
    hash_password,
    safe_filename,
    safe_join,
    verify_password,
)
from app.models.db import TagStatus
from app.models.schemas import BatchEditOp
from app.services.lyrics_service import validate_lrc
from app.services.organize_service import render_template
from app.services.scanner import iter_audio_files, needs_rescan
from app.services.tag_service import apply_batch_ops, compute_tag_status, diff_fields


def test_format_registry() -> None:
    assert ".flac" in ALLOWED_EXTENSIONS and ".mp3" in ALLOWED_EXTENSIONS
    assert is_supported(".FLAC")
    assert not is_supported(".txt")
    assert format_name(".m4a") == "M4A/MP4"


def test_compute_tag_status() -> None:
    assert compute_tag_status(TagSet(title="a", artist="b", album="c")) == TagStatus.ok
    assert compute_tag_status(TagSet()) == TagStatus.missing_tags
    assert compute_tag_status(TagSet(artist="b", album="c")) == TagStatus.missing_title
    assert compute_tag_status(TagSet(title="a", album="c")) == TagStatus.missing_artist
    assert compute_tag_status(TagSet(title="a", artist="b")) == TagStatus.missing_album


def test_apply_batch_ops_overwrite_and_fill() -> None:
    current = {"album": "Old", "genre": None}

    ops = [BatchEditOp(field="album", op="set", value="New")]
    assert apply_batch_ops(current, ops, "overwrite")["album"] == "New"

    # fill_empty 不覆盖已有值
    assert apply_batch_ops(current, ops, "fill_empty")["album"] == "Old"
    # fill_empty 填充空值
    ops_genre = [BatchEditOp(field="genre", op="set", value="Rock")]
    assert apply_batch_ops(current, ops_genre, "fill_empty")["genre"] == "Rock"


def test_apply_batch_ops_append_and_replace() -> None:
    current = {"artist": "Radiohead"}
    appended = apply_batch_ops(
        current, [BatchEditOp(field="artist", op="set", value=" / feat")], "append"
    )
    assert appended["artist"] == "Radiohead / feat"

    replaced = apply_batch_ops(
        {"title": "Song (Remastered 2011)"},
        [BatchEditOp(field="title", op="replace", find=" (Remastered 2011)", replace="")],
    )
    assert replaced["title"] == "Song"

    regexed = apply_batch_ops(
        {"title": "Track 07"},
        [BatchEditOp(field="title", op="replace", find=r"\d+", replace="X", use_regex=True)],
    )
    assert regexed["title"] == "Track X"


def test_diff_fields() -> None:
    before = {"album": "A", "genre": "Rock"}
    after = {"album": "B", "genre": "Rock"}
    changes = diff_fields(before, after)
    assert changes == [{"field": "album", "old_value": "A", "new_value": "B"}]


def test_render_template() -> None:
    values = {
        "albumartist": "Adele",
        "year": "2011",
        "album": "21",
        "track_no": 3,
        "title": "Rolling",
    }
    rendered = render_template("{albumartist}/{year} - {album}/{track:02d} - {title}", values)
    assert rendered == "Adele/2011 - 21/03 - Rolling"
    # 缺失字段 → 清理空段
    assert render_template("{artist}/{missing}/{title}", {"artist": "X", "title": "Y"}) == "X/Y"


def test_validate_lrc() -> None:
    assert validate_lrc("[00:12.34]hello\n[00:20.00]world")
    assert not validate_lrc("no timestamps here")
    assert not validate_lrc("")


def test_path_security(tmp_path: Path) -> None:
    root = tmp_path / "music"
    root.mkdir()
    inside = root / "a" / "b.flac"
    inside.parent.mkdir()
    inside.write_bytes(b"x")

    assert ensure_within_roots(inside, [root]) == inside.resolve()

    with pytest.raises(PathSecurityError):
        ensure_within_roots(tmp_path / "elsewhere.flac", [root])
    with pytest.raises(PathSecurityError):
        ensure_within_roots(inside, [])
    with pytest.raises(PathSecurityError):
        safe_join(root, "..", "escape.flac")

    assert safe_join(root, "sub", "ok.flac").name == "ok.flac"
    assert safe_filename("../../evil?.mp3") == "evil_.mp3"


def test_password_hash_roundtrip() -> None:
    stored = hash_password("s3cret")
    assert stored.startswith("scrypt$")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", "garbage")


def test_iter_audio_files_and_incremental(music_dir: Path) -> None:
    found = {p.name for p in iter_audio_files(music_dir)}
    assert found == {"track01.flac", "track02.mp3"}  # 忽略隐藏文件与 .txt

    target = music_dir / "Artist" / "Album" / "track01.flac"
    size = target.stat().st_size
    mtime = target.stat().st_mtime
    # 无索引记录 → 需要扫描
    assert needs_rescan(None, size, mtime)

    class _FakeTrack:
        def __init__(self) -> None:
            self.size = size
            from datetime import UTC, datetime

            self.mtime = datetime.fromtimestamp(mtime, tz=UTC)

    assert not needs_rescan(_FakeTrack(), size, mtime)
    assert needs_rescan(_FakeTrack(), size + 1, mtime)
