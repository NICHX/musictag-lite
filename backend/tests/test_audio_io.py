"""音频核心读写往返测试（FLAC=Vorbis Comment，WAV=ID3）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.audio.base import CoverImage, TagSet
from app.audio.mutagen_io import MutagenIO, UnsupportedFormatError
from tests.audio_factory import JPEG_BYTES, make_flac, make_wav

io = MutagenIO()

FACTORIES = {"flac": make_flac, "wav": make_wav}


@pytest.fixture(params=sorted(FACTORIES))
def audio_path(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    return FACTORIES[request.param](tmp_path / f"song.{request.param}")


def test_read_empty(audio_path: Path) -> None:
    doc = io.read(audio_path)
    assert doc.tags.title is None
    assert doc.properties.duration
    assert doc.cover is None
    assert doc.lyrics is None


def test_tag_roundtrip(audio_path: Path) -> None:
    io.write_tags(
        audio_path,
        TagSet(
            title="夜曲",
            artist="周杰伦",
            album="十一月的萧邦",
            album_artist="周杰伦",
            composer="周杰伦",
            genre="Pop",
            track_no=3,
            disc_no=1,
            year="2005",
            comment="试听",
        ),
    )
    tags = io.read(audio_path).tags
    assert tags.title == "夜曲"
    assert tags.artist == "周杰伦"
    assert tags.album == "十一月的萧邦"
    assert tags.album_artist == "周杰伦"
    assert tags.composer == "周杰伦"
    assert tags.genre == "Pop"
    assert tags.track_no == 3
    assert tags.disc_no == 1
    assert tags.year == "2005"
    assert tags.comment == "试听"


def test_partial_update_keeps_other_fields(audio_path: Path) -> None:
    io.write_tags(audio_path, TagSet(title="A", artist="B"))
    io.write_tags(audio_path, TagSet(album="C"))
    tags = io.read(audio_path).tags
    assert (tags.title, tags.artist, tags.album) == ("A", "B", "C")


def test_empty_string_clears_field(audio_path: Path) -> None:
    io.write_tags(audio_path, TagSet(title="A"))
    io.write_tags(audio_path, TagSet(title=""))
    assert io.read(audio_path).tags.title is None


def test_cover_roundtrip(audio_path: Path) -> None:
    assert io.read_cover(audio_path) is None

    io.write_cover(audio_path, CoverImage(data=JPEG_BYTES, mime="image/jpeg"))
    cover = io.read_cover(audio_path)
    assert cover is not None
    assert cover.data == JPEG_BYTES
    assert cover.mime == "image/jpeg"

    assert io.delete_cover(audio_path) is True
    assert io.read_cover(audio_path) is None


def test_lyrics_roundtrip(audio_path: Path) -> None:
    lrc = "[00:01.00]第一行\n[00:05.50]第二行"
    io.write_lyrics(audio_path, lrc)
    assert io.read_lyrics(audio_path) == lrc


def test_properties(audio_path: Path) -> None:
    props = io.read_properties(audio_path)
    is_flac = audio_path.suffix == ".flac"
    assert props.sample_rate == (44100 if is_flac else 8000)
    assert props.channels == (2 if is_flac else 1)
    assert props.duration and props.duration > 0


def test_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("hi")
    with pytest.raises(UnsupportedFormatError):
        io.read(path)


def test_unrecognized_audio(tmp_path: Path) -> None:
    path = tmp_path / "broken.flac"
    path.write_bytes(b"not really a flac")
    with pytest.raises(UnsupportedFormatError):
        io.read(path)
