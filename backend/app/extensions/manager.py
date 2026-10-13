"""扩展（可安装的刮削源插件）体系。

约定：一个扩展就是一个目录，内含 ``extension.json`` 清单与若干 Provider 模块；
运行时从已安装目录（默认 ``<data_dir>/extensions/<key>``）动态导入并注册到
``provider_registry``。随镜像分发的 ``backend/extensions/`` 作为**可安装目录（catalog）**，
用户可一键安装或卸载，社区源不再随核心代码硬编码启用。
"""

from __future__ import annotations

import importlib
import importlib.machinery
import json
import re
import shutil
import sys
import types
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import MetadataProvider
from app.providers.registry import ProviderRegistry, provider_registry

logger = get_logger(__name__)

MANIFEST_NAME = "extension.json"
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ExtensionError(ValueError):
    """扩展清单非法、安装冲突或加载失败。"""


def _module_prefix(key: str) -> str:
    return f"musictag_ext_{key}"


@dataclass
class ExtensionManifest:
    key: str
    name: str
    version: str = "0.0.0"
    description: str | None = None
    author: str | None = None
    providers: list[str] = field(default_factory=list)  # ["module.ClassName", ...]

    @classmethod
    def from_dict(cls, data: Any) -> ExtensionManifest:
        if not isinstance(data, dict):
            raise ExtensionError("扩展清单必须是 JSON 对象")
        key = str(data.get("key") or "").strip()
        if not _KEY_RE.match(key):
            raise ExtensionError("扩展 key 非法（仅允许小写字母、数字、- 与 _）")
        name = str(data.get("name") or key).strip()
        providers = data.get("providers") or []
        if not isinstance(providers, list) or not providers:
            raise ExtensionError("扩展清单缺少 providers")
        return cls(
            key=key,
            name=name,
            version=str(data.get("version") or "0.0.0").strip(),
            description=(str(data["description"]).strip() if data.get("description") else None),
            author=(str(data["author"]).strip() if data.get("author") else None),
            providers=[str(item).strip() for item in providers if str(item).strip()],
        )


@dataclass
class ExtensionInfo:
    key: str
    name: str
    version: str
    description: str | None
    author: str | None
    installed: bool
    builtin: bool
    providers: list[str] = field(default_factory=list)


@dataclass
class _LoadedExtension:
    manifest: ExtensionManifest
    path: Path
    provider_keys: list[str] = field(default_factory=list)


class ExtensionManager:
    """已安装扩展的发现 / 动态加载 / 安装 / 卸载。"""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._registry = registry or provider_registry
        self._loaded: dict[str, _LoadedExtension] = {}

    # ---- 目录 ----
    @property
    def installed_dir(self) -> Path:
        return get_settings().installed_extensions_dir

    @property
    def builtin_dir(self) -> Path:
        return get_settings().builtin_extensions_dir

    # ---- 启动加载 ----
    def load_all(self) -> list[str]:
        """加载已安装目录中的全部扩展；返回成功加载的扩展 key 列表。"""
        loaded: list[str] = []
        for path in self._iter_dirs(self.installed_dir):
            try:
                self._load_dir(path)
                loaded.append(path.name)
            except Exception:  # noqa: BLE001 - 单个扩展失败不影响其他扩展
                logger.exception("extension.load_failed", extra={"path": str(path)})
        if loaded:
            logger.info("extension.loaded", extra={"keys": loaded})
        return loaded

    # ---- 查询 ----
    def installed(self) -> list[ExtensionInfo]:
        infos: list[ExtensionInfo] = []
        for path in self._iter_dirs(self.installed_dir):
            manifest = self._try_manifest(path)
            if manifest is None:
                continue
            loaded = self._loaded.get(manifest.key)
            infos.append(
                ExtensionInfo(
                    key=manifest.key,
                    name=manifest.name,
                    version=manifest.version,
                    description=manifest.description,
                    author=manifest.author,
                    installed=True,
                    builtin=(self.builtin_dir / manifest.key / MANIFEST_NAME).is_file(),
                    providers=loaded.provider_keys if loaded else [],
                )
            )
        return infos

    def catalog(self) -> list[ExtensionInfo]:
        installed_keys = {info.key for info in self.installed()}
        infos: list[ExtensionInfo] = []
        for path in self._iter_dirs(self.builtin_dir):
            manifest = self._try_manifest(path)
            if manifest is None:
                continue
            infos.append(
                ExtensionInfo(
                    key=manifest.key,
                    name=manifest.name,
                    version=manifest.version,
                    description=manifest.description,
                    author=manifest.author,
                    installed=manifest.key in installed_keys,
                    builtin=True,
                    providers=[],
                )
            )
        return infos

    def loaded_provider_keys(self, key: str) -> list[str]:
        loaded = self._loaded.get(key)
        return list(loaded.provider_keys) if loaded else []

    # ---- 安装 / 卸载 ----
    def install_from_catalog(self, key: str) -> ExtensionInfo:
        src = self.builtin_dir / key
        if not (src / MANIFEST_NAME).is_file():
            raise ExtensionError(f"内置扩展不存在：{key}")
        dest = self.installed_dir / key
        if dest.exists():
            raise ExtensionError(f"扩展已安装：{key}")
        self.installed_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        return self._info_for(self._load_dir(dest))

    def install_from_zip(self, data: bytes) -> ExtensionInfo:
        try:
            archive = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ExtensionError("不是有效的 zip 压缩包") from exc

        with archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            manifest_names = [n for n in names if Path(n).name == MANIFEST_NAME]
            if not manifest_names:
                raise ExtensionError(f"压缩包中未找到 {MANIFEST_NAME}")
            manifest_names.sort(key=lambda n: n.count("/"))
            manifest_name = manifest_names[0]
            root = manifest_name[: -len(MANIFEST_NAME)]

            for name in names:
                parts = Path(name).parts
                if name.startswith("/") or ".." in parts:
                    raise ExtensionError("压缩包包含非法路径")
                if root and not name.startswith(root):
                    raise ExtensionError(
                        "压缩包结构非法：扩展应打包为单一顶层目录（内含 extension.json）"
                    )

            manifest = ExtensionManifest.from_dict(json.loads(archive.read(manifest_name)))
            dest = self.installed_dir / manifest.key
            if dest.exists():
                raise ExtensionError(f"扩展已安装：{manifest.key}")

            dest.mkdir(parents=True, exist_ok=True)
            try:
                for name in names:
                    rel = name[len(root):] if root else name
                    if not rel:
                        continue
                    target = (dest / rel).resolve()
                    if dest.resolve() not in target.parents:
                        raise ExtensionError("压缩包包含非法路径")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
                return self._info_for(self._load_dir(dest))
            except Exception:
                shutil.rmtree(dest, ignore_errors=True)
                raise

    def uninstall(self, key: str) -> list[str]:
        """卸载扩展：注销其 Provider 并删除目录；返回被移除的 Provider key。"""
        dest = self.installed_dir / key
        if not dest.exists():
            raise ExtensionError(f"扩展未安装：{key}")
        removed = self._unload(key)
        shutil.rmtree(dest)
        return removed

    # ---- 内部 ----
    def _iter_dirs(self, root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return [
            child
            for child in sorted(root.iterdir())
            if child.is_dir() and (child / MANIFEST_NAME).is_file()
        ]

    def _try_manifest(self, path: Path) -> ExtensionManifest | None:
        try:
            return self._read_manifest(path)
        except Exception:  # noqa: BLE001 - 清单损坏时跳过但保留目录
            logger.warning("extension.manifest_invalid", extra={"path": str(path)})
            return None

    @staticmethod
    def _read_manifest(path: Path) -> ExtensionManifest:
        raw = (path / MANIFEST_NAME).read_text(encoding="utf-8")
        return ExtensionManifest.from_dict(json.loads(raw))

    def _load_dir(self, path: Path) -> ExtensionManifest:
        manifest = self._read_manifest(path)
        if manifest.key in self._loaded:
            return manifest

        prefix = _module_prefix(manifest.key)
        if prefix not in sys.modules:
            package = types.ModuleType(prefix)
            package.__path__ = [str(path)]  # type: ignore[attr-defined]
            package.__package__ = prefix
            package.__spec__ = importlib.machinery.ModuleSpec(prefix, None, is_package=True)
            sys.modules[prefix] = package

        provider_keys: list[str] = []
        for spec in manifest.providers:
            module_name, _, class_name = spec.rpartition(".")
            target = (
                importlib.import_module(f"{prefix}.{module_name}")
                if module_name
                else sys.modules[prefix]
            )
            provider: MetadataProvider = getattr(target, class_name)()
            if self._registry.get(provider.key) is not None:
                logger.warning(
                    "extension.provider_duplicate",
                    extra={"extension": manifest.key, "provider": provider.key},
                )
                continue
            self._registry.register(provider)
            provider_keys.append(provider.key)

        self._loaded[manifest.key] = _LoadedExtension(manifest, path, provider_keys)
        logger.info(
            "extension.registered",
            extra={"extension": manifest.key, "providers": provider_keys},
        )
        return manifest

    def _info_for(self, manifest: ExtensionManifest) -> ExtensionInfo:
        loaded = self._loaded.get(manifest.key)
        return ExtensionInfo(
            key=manifest.key,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            author=manifest.author,
            installed=True,
            builtin=(self.builtin_dir / manifest.key / MANIFEST_NAME).is_file(),
            providers=loaded.provider_keys if loaded else [],
        )

    def _unload(self, key: str) -> list[str]:
        loaded = self._loaded.pop(key, None)
        removed: list[str] = []
        if loaded is not None:
            for provider_key in loaded.provider_keys:
                if self._registry.unregister(provider_key):
                    removed.append(provider_key)
        prefix = _module_prefix(key)
        for name in list(sys.modules):
            if name == prefix or name.startswith(f"{prefix}."):
                sys.modules.pop(name, None)
        return removed


extension_manager = ExtensionManager()
