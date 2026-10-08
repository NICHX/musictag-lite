"""内置刮削源（默认启用，均为开放合规数据源）。"""

from app.providers.builtin.acoustid import AcoustIDProvider
from app.providers.builtin.coverart import CoverArtArchiveProvider
from app.providers.builtin.lrclib import LRCLIBProvider
from app.providers.builtin.musicbrainz import MusicBrainzProvider

BUILTIN_PROVIDERS = [
    MusicBrainzProvider(),
    CoverArtArchiveProvider(),
    LRCLIBProvider(),
    AcoustIDProvider(),
]

__all__ = [
    "BUILTIN_PROVIDERS",
    "MusicBrainzProvider",
    "CoverArtArchiveProvider",
    "LRCLIBProvider",
    "AcoustIDProvider",
]
