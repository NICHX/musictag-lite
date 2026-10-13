"""社区刮削源（非官方、可选、默认关闭）。

均声明 ``default_enabled = False``：符合设计文档「默认仅启用开放数据源」的合规原则，
用户需在「设置 → 数据源」中显式启用后才会参与匹配。接口为第三方所有，可能随时变更
（咪咕旧接口已失效，故未收录）。
"""

from __future__ import annotations

from app.providers.base import MetadataProvider
from app.providers.community.kugou import KugouProvider
from app.providers.community.netease import NeteaseProvider
from app.providers.community.qqmusic import QQMusicProvider

COMMUNITY_PROVIDERS: list[MetadataProvider] = [
    NeteaseProvider(),
    QQMusicProvider(),
    KugouProvider(),
]

__all__ = [
    "COMMUNITY_PROVIDERS",
    "NeteaseProvider",
    "QQMusicProvider",
    "KugouProvider",
]
