"""路径安全：库根目录白名单校验、防路径穿越、上传文件名净化。"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class PathSecurityError(ValueError):
    """路径不在允许的库根目录内，或存在穿越风险。"""


def _normalized_roots(roots: list[str | Path]) -> list[Path]:
    normalized: list[Path] = []
    for root in roots:
        try:
            normalized.append(Path(root).expanduser().resolve(strict=False))
        except OSError:
            continue
    return normalized


def is_within_roots(path: str | Path, roots: list[str | Path]) -> bool:
    """判断 path 是否位于任一库根目录内（含根目录本身）。"""
    target = Path(path).expanduser().resolve(strict=False)
    for root in _normalized_roots(roots):
        if target == root or root in target.parents:
            return True
    return False


def ensure_within_roots(path: str | Path, roots: list[str | Path]) -> Path:
    """校验并返回解析后的绝对路径；越界则抛 PathSecurityError。"""
    if not roots:
        raise PathSecurityError("未配置任何库根目录，拒绝文件访问")
    target = Path(path).expanduser().resolve(strict=False)
    if not is_within_roots(target, roots):
        raise PathSecurityError(f"路径越界：{target}")
    return target


def safe_filename(name: str, *, fallback: str = "file") -> str:
    """净化上传/生成的文件名，去除目录分隔与非法字符。"""
    cleaned = _UNSAFE_CHARS.sub("_", os.path.basename(name)).strip(" .")
    return cleaned or fallback


def safe_join(root: str | Path, *parts: str) -> Path:
    """在 root 下安全拼接路径，阻断 `..` 穿越。"""
    base = Path(root).resolve(strict=False)
    candidate = base.joinpath(*parts).resolve(strict=False)
    if candidate != base and base not in candidate.parents:
        raise PathSecurityError(f"路径越界：{candidate}")
    return candidate


def hash_password(password: str, *, salt: str | None = None) -> str:
    """基于 scrypt 的密码哈希（P2 鉴权预留），格式 `scrypt$salt$hash`。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"), n=2**14, r=8, p=1)
    return f"scrypt${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码是否匹配已存储的哈希。"""
    try:
        scheme, salt, _ = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    return hmac.compare_digest(hash_password(password, salt=salt), stored)
