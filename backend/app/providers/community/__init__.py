"""社区刮削源（可选，默认不内置任何高风险源）。

用户可自行在 ``provider.toml`` / 该类属性中声明元信息与默认开闭状态。
此处保持为空，符合"默认仅启用开放数据源"的合规原则。
"""

from __future__ import annotations

from app.providers.base import MetadataProvider

COMMUNITY_PROVIDERS: list[MetadataProvider] = []

__all__ = ["COMMUNITY_PROVIDERS"]
