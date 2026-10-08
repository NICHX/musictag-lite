"""mutagen 实现（音频核心技术层）。

纯 Python，不依赖 ffmpeg。覆盖附录 A 的主流标签容器：

- ID3：MP3 / WAV / AIFF / DSF / TTA
- Vorbis Comment：FLAC / OGG / Opus
- iTunes MP4：M4A
- APEv2：APE / WavPack / Musepack
- ASF：WMA（尽力写）

写入约定：仅应用传入的字段 —— 值为 ``None`` 表示"不修改"，空字符串表示"清除该字段"。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen.apev2 import APEBinaryValue, APEv2
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    TALB,
    TCOM,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TRCK,
    USLT,
)
from mutagen.mp4 import MP4, MP4Cover, MP4Tags

from app.audio.base import AudioDocument, AudioIO, AudioProperties, CoverImage, TagSet
from app.audio.formats import format_name, is_supported

_FRONT = 3  # ID3 APIC / FLAC Picture 的"前置封面"类型
_APE_COVER_KEY = "Cover Art (Front)"
_KIND_TO_PICTURE = {"front": 3, "back": 4, "other": 0}

# 各格式族的音频文件类名 → 标签容器族
_AUDIO_CLASS_KIND = {
    "MP3": "id3",
    "WAVE": "id3",
    "AIFF": "id3",
    "DSF": "id3",
    "TrueAudio": "id3",
    "TTA": "id3",
    "FLAC": "vorbis",
    "OggVorbis": "vorbis",
    "OggOpus": "vorbis",
    "OggFLAC": "vorbis",
    "OggSpeex": "vorbis",
    "MP4": "mp4",
    "MonkeysAudio": "ape",
    "WavPack": "ape",
    "Musepack": "ape",
    "APEv2File": "ape",
    "ASF": "asf",
}


class UnsupportedFormatError(ValueError):
    """扩展名不受支持，或文件无法被识别。"""


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _parse_leading_int(value: Any) -> int | None:
    """解析 "3" / "3/12" 这类音轨号，返回前导整数。"""
    if value is None:
        return None
    head = str(value).split("/")[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _drop(container: Any, key: str) -> None:
    """从各类 mutagen 标签容器中安全删除键。"""
    try:
        container.pop(key, None)
        return
    except (AttributeError, TypeError):
        pass
    try:
        del container[key]
    except (KeyError, TypeError, AttributeError):
        pass


def _kind_from_tags(tags: Any) -> str | None:
    if isinstance(tags, ID3):
        return "id3"
    if isinstance(tags, MP4Tags):
        return "mp4"
    if isinstance(tags, APEv2):
        return "ape"
    name = type(tags).__name__
    if name in {"VComment", "VCFLACDict"}:
        return "vorbis"
    if name in {"ASFTags", "ASF"}:
        return "asf"
    return None


def _tag_kind(audio: Any) -> str | None:
    """判定标签容器族：优先看已存在的标签，其次按音频文件类型推断。"""
    tags = getattr(audio, "tags", None)
    if tags is not None:
        kind = _kind_from_tags(tags)
        if kind is not None:
            return kind
    return _AUDIO_CLASS_KIND.get(type(audio).__name__)


def _ensure_tags(audio: Any) -> Any:
    """确保标签容器存在（FLAC/OGG/MP4 等无标签时 tags 可能为 None）。"""
    if getattr(audio, "tags", None) is None:
        add_tags = getattr(audio, "add_tags", None)
        if callable(add_tags):
            add_tags()
    return getattr(audio, "tags", None)


def _load(path: str | Path) -> Any:
    """加载音频文件；不可识别或损坏时抛 UnsupportedFormatError。"""
    try:
        audio = MutagenFile(str(path))
    except Exception as exc:  # noqa: BLE001 - mutagen 对损坏文件会抛各种异常
        raise UnsupportedFormatError(f"无法解析音频文件：{path}（{exc}）") from exc
    if audio is None:
        raise UnsupportedFormatError(f"无法识别音频文件：{path}")
    return audio


def _guess_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"GIF":
        return "image/gif"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


# --------------------------------------------------------------------------- #
# 实现
# --------------------------------------------------------------------------- #
class MutagenIO(AudioIO):
    """基于 mutagen 的音频读取与写入。"""

    # ---- 读取 ----
    def read(self, path: str | Path) -> AudioDocument:
        p = Path(path)
        if not is_supported(p.suffix):
            raise UnsupportedFormatError(f"不支持的格式：{p.suffix or '(无扩展名)'}")
        audio = _load(p)
        kind = _tag_kind(audio)
        tags = self._read_tags(audio, kind)
        return AudioDocument(
            path=p,
            properties=self._properties(audio),
            tags=tags,
            cover=self._read_cover(audio, kind),
            lyrics=tags.lyrics,
        )

    def read_properties(self, path: str | Path) -> AudioProperties:
        return self._properties(_load(path))

    @staticmethod
    def _properties(audio: Any) -> AudioProperties:
        info = getattr(audio, "info", None)
        if info is None:
            return AudioProperties(format=type(audio).__name__)
        return AudioProperties(
            duration=float(getattr(info, "length", 0.0) or 0.0) or None,
            bitrate=int(getattr(info, "bitrate", 0) or 0) or None,
            sample_rate=int(getattr(info, "sample_rate", 0) or 0) or None,
            channels=int(getattr(info, "channels", 0) or 0) or None,
            bit_depth=int(getattr(info, "bits_per_sample", 0) or 0) or None,
            format=type(audio).__name__,
        )

    def _read_tags(self, audio: Any, kind: str | None) -> TagSet:
        tags = getattr(audio, "tags", None)
        if tags is None:
            return TagSet()
        try:
            if kind == "id3":
                return self._read_id3(tags)
            if kind == "vorbis":
                return self._read_vorbis(tags)
            if kind == "mp4":
                return self._read_mp4(tags)
            if kind == "ape":
                return self._read_ape(tags)
            if kind == "asf":
                return self._read_asf(tags)
        except Exception:  # noqa: BLE001 - 单个文件标签异常不应中断扫描
            return TagSet()
        return TagSet()

    def _read_id3(self, tags: ID3) -> TagSet:
        def text(frame_id: str) -> str | None:
            frame = tags.get(frame_id)
            if frame is None:
                return None
            try:
                return _clean(frame.text[0])
            except (AttributeError, IndexError):
                return None

        date = text("TDRC")
        return TagSet(
            title=text("TIT2"),
            artist=text("TPE1"),
            album=text("TALB"),
            album_artist=text("TPE2"),
            composer=text("TCOM"),
            genre=text("TCON"),
            track_no=_parse_leading_int(text("TRCK")),
            disc_no=_parse_leading_int(text("TPOS")),
            year=date[:4] if date else None,
            date=date,
            comment=self._id3_comment(tags),
            lyrics=self._id3_lyrics(tags),
        )

    @staticmethod
    def _id3_comment(tags: ID3) -> str | None:
        for frame in tags.getall("COMM"):
            if frame.desc in ("", None) and frame.text:
                return _clean(frame.text[0])
        return None

    @staticmethod
    def _id3_lyrics(tags: ID3) -> str | None:
        for frame in tags.getall("USLT"):
            if frame.text:
                return str(frame.text)
        return None

    @staticmethod
    def _read_vorbis(tags: Any) -> TagSet:
        def get(key: str) -> str | None:
            values = tags.get(key)
            if not values:
                return None
            return _clean(values[0])

        date = get("date")
        return TagSet(
            title=get("title"),
            artist=get("artist"),
            album=get("album"),
            album_artist=get("albumartist") or get("album artist"),
            composer=get("composer"),
            genre=get("genre"),
            track_no=_parse_leading_int(get("tracknumber")),
            disc_no=_parse_leading_int(get("discnumber")),
            year=date[:4] if date else None,
            date=date,
            comment=get("comment") or get("description"),
            lyrics=get("lyrics") or get("unsyncedlyrics"),
        )

    @staticmethod
    def _read_mp4(tags: Any) -> TagSet:
        def get(key: str) -> str | None:
            values = tags.get(key)
            if not values:
                return None
            return _clean(values[0])

        def pair(key: str) -> int | None:
            values = tags.get(key)
            if values and values[0]:
                return int(values[0][0]) or None
            return None

        date = get("©day")
        return TagSet(
            title=get("©nam"),
            artist=get("©ART"),
            album=get("©alb"),
            album_artist=get("aART"),
            composer=get("©wtr"),
            genre=get("©gen"),
            track_no=pair("trkn"),
            disc_no=pair("disk"),
            year=date[:4] if date else None,
            date=date,
            comment=get("©cmt"),
            lyrics=get("©lyr"),
        )

    @staticmethod
    def _read_ape(tags: APEv2) -> TagSet:
        def get(key: str) -> str | None:
            item = tags.get(key)
            if item is None:
                return None
            try:
                return _clean(str(item))
            except Exception:  # noqa: BLE001
                return None

        date = get("Year")
        return TagSet(
            title=get("Title"),
            artist=get("Artist"),
            album=get("Album"),
            album_artist=get("Album Artist") or get("AlbumArtist"),
            composer=get("Composer"),
            genre=get("Genre"),
            track_no=_parse_leading_int(get("Track")),
            disc_no=_parse_leading_int(get("Disc")),
            year=date,
            date=date,
            comment=get("Comment"),
            lyrics=get("Lyrics"),
        )

    @staticmethod
    def _read_asf(tags: Any) -> TagSet:
        def get(key: str) -> str | None:
            values = tags.get(key)
            if not values:
                return None
            return _clean(values[0])

        date = get("WM/Year")
        return TagSet(
            title=get("Title"),
            artist=get("Author"),
            album=get("WM/AlbumTitle"),
            album_artist=get("WM/AlbumArtist"),
            composer=get("WM/Composer"),
            genre=get("WM/Genre"),
            track_no=_parse_leading_int(get("WM/TrackNumber")),
            disc_no=_parse_leading_int(get("WM/PartOfSet")),
            year=date,
            date=date,
            comment=get("Description"),
        )

    # ---- 读取封面 ----
    def _read_cover(self, audio: Any, kind: str | None) -> CoverImage | None:
        try:
            if kind == "id3" and getattr(audio, "tags", None) is not None:
                return self._id3_cover(audio.tags)
            if kind == "vorbis":
                return self._vorbis_cover(audio)
            if kind == "mp4" and getattr(audio, "tags", None) is not None:
                return self._mp4_cover(audio)
            if kind == "ape" and getattr(audio, "tags", None) is not None:
                return self._ape_cover(audio.tags)
        except Exception:  # noqa: BLE001
            return None
        return None

    @staticmethod
    def _id3_cover(tags: ID3) -> CoverImage | None:
        frames = tags.getall("APIC")
        if not frames:
            return None
        frames.sort(key=lambda f: 0 if f.type == _FRONT else 1)
        frame = frames[0]
        data = bytes(frame.data)
        return CoverImage(data=data, mime=str(frame.mime) or _guess_mime(data))

    @staticmethod
    def _vorbis_cover(audio: Any) -> CoverImage | None:
        if isinstance(audio, FLAC) and audio.pictures:
            pic = audio.pictures[0]
            return CoverImage(data=bytes(pic.data), mime=pic.mime or _guess_mime(bytes(pic.data)))
        raw = (getattr(audio, "tags", None) or {}).get("metadata_block_picture")
        if raw:
            pic = Picture(base64.b64decode(raw[0]))
            return CoverImage(data=bytes(pic.data), mime=pic.mime or _guess_mime(bytes(pic.data)))
        return None

    @staticmethod
    def _mp4_cover(audio: MP4) -> CoverImage | None:
        covr = audio.tags.get("covr") if audio.tags else None
        if not covr:
            return None
        item = covr[0]
        data = bytes(item)
        mime = "image/png" if int(item.imageformat) == MP4Cover.FORMAT_PNG else "image/jpeg"
        return CoverImage(data=data, mime=mime)

    @staticmethod
    def _ape_cover(tags: APEv2) -> CoverImage | None:
        item = tags.get(_APE_COVER_KEY)
        if item is None:
            return None
        raw = bytes(item.value)
        data = raw.split(b"\x00", 1)[-1]  # 去掉 "cover.jpg\0" 前缀
        return CoverImage(data=data, mime=_guess_mime(data))

    # ---- 写入标签 ----
    def write_tags(self, path: str | Path, tags: TagSet) -> None:
        audio = _load(path)
        values = {k: v for k, v in tags.as_dict().items() if k != "lyrics" and v is not None}
        if "year" in values and "date" not in values:
            values["date"] = values["year"]
        kind = _tag_kind(audio)
        if kind == "id3":
            self._write_id3(audio, values)
        elif kind == "vorbis":
            self._write_vorbis(audio, values)
        elif kind == "mp4":
            self._write_mp4(audio, values)
        elif kind == "ape":
            self._write_ape(audio, values)
        elif kind == "asf":
            self._write_asf(audio, values)
        else:
            raise UnsupportedFormatError(f"该格式暂不支持写入标签：{Path(path).suffix}")
        audio.save()

    def read_cover(self, path: str | Path) -> CoverImage | None:
        return self.read(path).cover

    def write_cover(self, path: str | Path, cover: CoverImage) -> None:
        audio = _load(path)
        kind = _tag_kind(audio)
        if kind == "id3":
            _ensure_tags(audio)
            audio.tags.delall("APIC")
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime=cover.mime,
                    type=_KIND_TO_PICTURE.get(cover.kind, _FRONT),
                    desc="Cover",
                    data=cover.data,
                )
            )
        elif kind == "vorbis":
            pic = Picture()
            pic.type = _KIND_TO_PICTURE.get(cover.kind, _FRONT)
            pic.mime = cover.mime
            pic.desc = "Cover"
            pic.data = cover.data
            if isinstance(audio, FLAC):
                audio.clear_pictures()
                audio.add_picture(pic)
            else:
                _ensure_tags(audio)
                audio.tags["metadata_block_picture"] = [
                    base64.b64encode(pic.write()).decode("ascii")
                ]
        elif kind == "mp4":
            _ensure_tags(audio)
            fmt = MP4Cover.FORMAT_PNG if cover.mime == "image/png" else MP4Cover.FORMAT_JPEG
            audio.tags["covr"] = [MP4Cover(cover.data, imageformat=fmt)]
        elif kind == "ape":
            _ensure_tags(audio)
            audio.tags[_APE_COVER_KEY] = APEBinaryValue(b"cover.jpg\x00" + cover.data)
        else:
            raise UnsupportedFormatError(f"该格式暂不支持写入封面：{Path(path).suffix}")
        audio.save()

    def delete_cover(self, path: str | Path) -> bool:
        audio = _load(path)
        kind = _tag_kind(audio)
        tags = getattr(audio, "tags", None)
        removed = False
        if kind == "vorbis":
            if isinstance(audio, FLAC):
                removed = bool(audio.pictures)
                audio.clear_pictures()
            elif tags is not None:
                removed = "metadata_block_picture" in tags
                if removed:
                    _drop(tags, "metadata_block_picture")
        elif kind == "id3" and tags is not None:
            removed = bool(tags.getall("APIC"))
            tags.delall("APIC")
        elif kind == "mp4" and tags is not None:
            removed = "covr" in tags
            if removed:
                _drop(tags, "covr")
        elif kind == "ape" and tags is not None:
            removed = _APE_COVER_KEY in tags
            if removed:
                _drop(tags, _APE_COVER_KEY)
        if removed:
            audio.save()
        return removed

    def read_lyrics(self, path: str | Path) -> str | None:
        return self.read(path).tags.lyrics

    def write_lyrics(self, path: str | Path, content: str) -> None:
        audio = _load(path)
        kind = _tag_kind(audio)
        if kind == "id3":
            _ensure_tags(audio)
            audio.tags.delall("USLT")
            audio.tags.add(USLT(encoding=3, lang="eng", desc="", text=content))
        elif kind == "vorbis":
            _ensure_tags(audio)
            audio.tags["lyrics"] = [content]
        elif kind == "mp4":
            _ensure_tags(audio)
            audio.tags["©lyr"] = [content]
        elif kind == "ape":
            _ensure_tags(audio)
            audio.tags["Lyrics"] = content
        else:
            raise UnsupportedFormatError(f"该格式暂不支持写入歌词：{Path(path).suffix}")
        audio.save()

    # ---- 各容器写入实现 ----
    def _write_id3(self, audio: Any, values: dict[str, Any]) -> None:
        _ensure_tags(audio)
        tags: ID3 = audio.tags
        simple = {
            "title": ("TIT2", TIT2),
            "artist": ("TPE1", TPE1),
            "album": ("TALB", TALB),
            "album_artist": ("TPE2", TPE2),
            "composer": ("TCOM", TCOM),
            "genre": ("TCON", TCON),
        }
        for field, (frame_id, frame_cls) in simple.items():
            if field not in values:
                continue
            tags.delall(frame_id)
            if values[field] != "":
                tags.add(frame_cls(encoding=3, text=[str(values[field])]))
        if "date" in values:
            tags.delall("TDRC")
            if values["date"] != "":
                tags.add(TDRC(encoding=3, text=[str(values["date"])]))
        if "track_no" in values:
            tags.delall("TRCK")
            if values["track_no"] not in ("", None):
                tags.add(TRCK(encoding=3, text=[str(values["track_no"])]))
        if "disc_no" in values:
            tags.delall("TPOS")
            if values["disc_no"] not in ("", None):
                tags.add(TPOS(encoding=3, text=[str(values["disc_no"])]))
        if "comment" in values:
            tags.delall("COMM")
            if values["comment"] != "":
                tags.add(COMM(encoding=3, lang="eng", desc="", text=[str(values["comment"])]))

    def _write_vorbis(self, audio: Any, values: dict[str, Any]) -> None:
        tags = _ensure_tags(audio)
        mapping = {
            "title": "title",
            "artist": "artist",
            "album": "album",
            "album_artist": "albumartist",
            "composer": "composer",
            "genre": "genre",
            "track_no": "tracknumber",
            "disc_no": "discnumber",
            "date": "date",
            "comment": "comment",
        }
        for field, key in mapping.items():
            if field not in values:
                continue
            if values[field] == "":
                _drop(tags, key)
            else:
                tags[key] = [str(values[field])]

    def _write_mp4(self, audio: Any, values: dict[str, Any]) -> None:
        tags = _ensure_tags(audio)
        mapping = {
            "title": "©nam",
            "artist": "©ART",
            "album": "©alb",
            "album_artist": "aART",
            "composer": "©wtr",
            "genre": "©gen",
            "date": "©day",
            "comment": "©cmt",
        }
        for field, key in mapping.items():
            if field not in values:
                continue
            if values[field] == "":
                _drop(tags, key)
            else:
                tags[key] = [str(values[field])]
        for field, key in (("track_no", "trkn"), ("disc_no", "disk")):
            if field not in values:
                continue
            if values[field] in ("", None):
                _drop(tags, key)
            else:
                tags[key] = [(int(values[field]), 0)]

    def _write_ape(self, audio: Any, values: dict[str, Any]) -> None:
        tags = _ensure_tags(audio)
        mapping = {
            "title": "Title",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Album Artist",
            "composer": "Composer",
            "genre": "Genre",
            "track_no": "Track",
            "disc_no": "Disc",
            "date": "Year",
            "comment": "Comment",
        }
        for field, key in mapping.items():
            if field not in values:
                continue
            if values[field] == "":
                _drop(tags, key)
            else:
                tags[key] = str(values[field])

    def _write_asf(self, audio: Any, values: dict[str, Any]) -> None:
        tags = _ensure_tags(audio)
        mapping = {
            "title": "Title",
            "artist": "Author",
            "album": "WM/AlbumTitle",
            "album_artist": "WM/AlbumArtist",
            "composer": "WM/Composer",
            "genre": "WM/Genre",
            "track_no": "WM/TrackNumber",
            "disc_no": "WM/PartOfSet",
            "date": "WM/Year",
            "comment": "Description",
        }
        for field, key in mapping.items():
            if field not in values:
                continue
            if values[field] == "":
                _drop(tags, key)
            else:
                tags[key] = [str(values[field])]

    # ---- 辅助 ----
    @staticmethod
    def supports(path: str | Path) -> bool:
        return is_supported(Path(path).suffix)

    @staticmethod
    def format_of(path: str | Path) -> str:
        return format_name(Path(path).suffix)


# 默认单例，供服务层注入
audio_io: AudioIO = MutagenIO()
