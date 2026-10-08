"""文件名解析测试（纯离线启发式）。"""

from __future__ import annotations

from app.services.filename_parser import parse_filename


def test_track_prefix_and_title_only() -> None:
    parsed = parse_filename("07 - 夜曲.flac")
    assert parsed.track_no == 7
    assert parsed.title == "夜曲"
    assert parsed.artist is None


def test_title_artist_default_order() -> None:
    parsed = parse_filename("1965 - Zella Day.flac")
    assert (parsed.title, parsed.artist) == ("1965", "Zella Day")


def test_known_artist_flips_order() -> None:
    known = {"dua lipa"}
    parsed = parse_filename("Dua Lipa - Levitating.flac", known)
    assert (parsed.artist, parsed.title) == ("Dua Lipa", "Levitating")
    assert parsed.confidence > 0.9


def test_known_artist_keeps_title_first_order() -> None:
    known = {"zella day"}
    parsed = parse_filename("1965 - Zella Day.flac", known)
    assert (parsed.title, parsed.artist) == ("1965", "Zella Day")


def test_three_parts_artist_album_title() -> None:
    parsed = parse_filename("Adele - 21 - 03 Rolling in the Deep.flac")
    assert parsed.artist == "Adele"
    assert parsed.album == "21"
    assert parsed.track_no == 3
    assert parsed.title == "Rolling in the Deep"


def test_noise_brackets_removed() -> None:
    parsed = parse_filename("Adios - EVERGLOW [FLAC].mp3")
    assert (parsed.title, parsed.artist) == ("Adios", "EVERGLOW")
    assert "FLAC" not in (parsed.title or "") + (parsed.artist or "")


def test_number_kept_when_not_a_track_prefix() -> None:
    # "1965" 是标题的一部分，不应被当音轨号
    parsed = parse_filename("1965 - Zella Day.flac")
    assert parsed.track_no is None
    assert parsed.title == "1965"


def test_parentheses_in_title_are_preserved() -> None:
    parsed = parse_filename("Escape (Beat Saber Teaser) - Jaroslav Beck.flac")
    assert parsed.title == "Escape (Beat Saber Teaser)"
    assert parsed.artist == "Jaroslav Beck"


def test_en_dash_and_em_dash() -> None:
    assert parse_filename("A – B.flac").title == "A"
    assert parse_filename("A — B.flac").artist == "B"
