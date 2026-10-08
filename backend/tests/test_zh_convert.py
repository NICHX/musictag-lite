"""F13 简繁转换：转换能力、批量 op 集成与预演接口。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session

from app.core.db import engine
from app.models.db import Library, Track
from app.models.schemas import BatchEditOp
from app.services import zh_convert
from app.services.tag_service import apply_batch_ops


def test_convert_both_directions() -> None:
    assert zh_convert.convert("容祖兒", "t2s") == "容祖儿"
    assert zh_convert.convert("容祖儿", "s2t") == "容祖兒"
    assert zh_convert.convert("周杰伦", "s2t") == "周杰倫"
    assert zh_convert.convert("黄霄雲", "t2s") == "黄霄云"


def test_convert_empty_and_none_are_passthrough() -> None:
    assert zh_convert.convert("", "t2s") == ""
    assert zh_convert.convert(None, "t2s") is None


def test_convert_is_idempotent() -> None:
    once = zh_convert.convert("黄霄雲", "t2s")
    assert zh_convert.convert(once, "t2s") == once


def test_convert_rejects_unknown_direction() -> None:
    with pytest.raises(ValueError):
        zh_convert.convert("x", "bogus")


def test_apply_batch_ops_with_zh_convert() -> None:
    current = {"artist": "容祖兒", "album": "心之科學", "title": None}
    ops = [
        BatchEditOp(field="artist", op="zh_convert", direction="t2s"),
        BatchEditOp(field="album", op="zh_convert", direction="t2s"),
        BatchEditOp(field="title", op="zh_convert", direction="t2s"),
    ]
    result = apply_batch_ops(current, ops)
    assert result["artist"] == "容祖儿"
    assert result["album"] == "心之科学"
    assert result["title"] is None  # 空值不处理


def test_apply_batch_ops_skips_when_direction_missing() -> None:
    result = apply_batch_ops({"artist": "容祖兒"}, [BatchEditOp(field="artist", op="zh_convert")])
    assert result["artist"] == "容祖兒"


def _insert_track(tmp_path: Path, name: str, artist: str) -> int:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / "song.flac"
    file_path.write_bytes(b"x")
    with Session(engine) as session:
        library = Library(name=f"zh-{name}", root_path=str(root))
        session.add(library)
        session.commit()
        session.refresh(library)
        track = Track(
            library_id=library.id,
            path=str(file_path),
            filename=file_path.name,
            title="心之科學",
            artist=artist,
            size=1,
            format="FLAC",
        )
        session.add(track)
        session.commit()
        session.refresh(track)
        return track.id


def test_batch_preview_reports_zh_convert_changes(client, tmp_path: Path) -> None:
    track_id = _insert_track(tmp_path, "trad", "容祖兒")
    resp = client.post(
        "/api/tracks/batch/preview",
        json={
            "ids": [track_id],
            "ops": [{"field": "artist", "op": "zh_convert", "direction": "t2s"}],
            "strategy": "overwrite",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changed"] == 1
    assert body["items"][0]["changes"] == [
        {"field": "artist", "old_value": "容祖兒", "new_value": "容祖儿"}
    ]
