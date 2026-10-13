"""扩展（可安装的刮削源插件）子包。"""

from app.extensions.manager import (
    ExtensionError,
    ExtensionInfo,
    ExtensionManager,
    extension_manager,
)

__all__ = ["ExtensionError", "ExtensionInfo", "ExtensionManager", "extension_manager"]
