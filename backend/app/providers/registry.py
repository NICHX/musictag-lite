"""Provider 注册表：启动时发现 builtin/community 插件，并维护启用状态。"""

from __future__ import annotations

from app.core.logging import get_logger
from app.providers.base import Capability, MetadataProvider

logger = get_logger(__name__)


class ProviderRegistry:
    """登记所有可用 Provider；注册表本身不持有网络配置。"""

    def __init__(self) -> None:
        self._providers: dict[str, MetadataProvider] = {}

    def register(self, provider: MetadataProvider) -> None:
        if provider.key in self._providers:
            logger.warning("provider.duplicate", extra={"key": provider.key})
            return
        self._providers[provider.key] = provider
        logger.info("provider.registered", extra={"key": provider.key})

    def get(self, key: str) -> MetadataProvider | None:
        return self._providers.get(key)

    def all(self) -> list[MetadataProvider]:
        return sorted(self._providers.values(), key=lambda p: (p.default_priority, p.key))

    def by_capability(self, capability: Capability) -> list[MetadataProvider]:
        return [p for p in self.all() if capability in p.capabilities]

    def keys(self) -> list[str]:
        return list(self._providers.keys())


def _discover_builtin() -> list[MetadataProvider]:
    from app.providers.builtin import BUILTIN_PROVIDERS
    from app.providers.community import COMMUNITY_PROVIDERS

    return [*BUILTIN_PROVIDERS, *COMMUNITY_PROVIDERS]


def build_registry() -> ProviderRegistry:
    """构建并填充注册表。"""
    registry = ProviderRegistry()
    for provider in _discover_builtin():
        registry.register(provider)
    return registry


# 全局单例
provider_registry = build_registry()
