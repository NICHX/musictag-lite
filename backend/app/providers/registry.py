"""Provider 注册表：启动时注册内置源，运行时可动态注册/注销扩展源。"""

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

    def unregister(self, key: str) -> bool:
        """移除一个 Provider（用于卸载扩展）；返回是否确实移除。"""
        if self._providers.pop(key, None) is None:
            return False
        logger.info("provider.unregistered", extra={"key": key})
        return True

    def get(self, key: str) -> MetadataProvider | None:
        return self._providers.get(key)

    def all(self) -> list[MetadataProvider]:
        return sorted(self._providers.values(), key=lambda p: (p.default_priority, p.key))

    def by_capability(self, capability: Capability) -> list[MetadataProvider]:
        return [p for p in self.all() if capability in p.capabilities]

    def keys(self) -> list[str]:
        return list(self._providers.keys())


def build_registry() -> ProviderRegistry:
    """构建并填充注册表（仅内置源；扩展源在启动时由 ExtensionManager 注册）。"""
    from app.providers.builtin import BUILTIN_PROVIDERS

    registry = ProviderRegistry()
    for provider in BUILTIN_PROVIDERS:
        registry.register(provider)
    return registry


# 全局单例
provider_registry = build_registry()
