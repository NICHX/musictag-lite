"""AcoustID API Key 的解析与持久化（F14）。

优先级：**界面设置（数据库） > 环境变量 ACOUSTID_API_KEY**。
密钥只保存在本地数据库；对外读取时始终脱敏，不回传明文。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.config import get_settings
from app.models.db import Setting

SETTING_KEY = "acoustid"
_UNSET: object = object()


@dataclass
class AcoustIDConfig:
    api_key: str | None = None

    @property
    def available(self) -> bool:
        """配置了 API Key 即可用（是否启用由 Provider 开关决定）。"""
        return bool(self.api_key)


def mask_key(key: str | None) -> str | None:
    """脱敏展示：保留前 3 位与后 4 位。"""
    if not key:
        return None
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-4:]}"


def resolve(session: Session | None) -> AcoustIDConfig:
    """读取生效配置；数据库没有记录时回退到环境变量。"""
    env_key = get_settings().acoustid_api_key
    config = AcoustIDConfig(api_key=env_key)
    if session is None:
        return config
    row = session.get(Setting, SETTING_KEY)
    if row is None or not row.value_json:
        return config
    try:
        data = json.loads(row.value_json)
    except json.JSONDecodeError:
        return config
    if not isinstance(data, dict):
        return config
    api_key = data.get("api_key")
    return AcoustIDConfig(api_key=str(api_key) if api_key else None)


def update(session: Session, *, api_key: object = _UNSET) -> AcoustIDConfig:
    """部分更新并持久化。``api_key`` 传 ``_UNSET`` 表示不修改，传空串表示清除。"""
    current = resolve(session)
    if api_key is _UNSET:
        key = current.api_key
    else:
        text = str(api_key).strip() if api_key else ""
        key = text or None
    config = AcoustIDConfig(api_key=key)

    row = session.get(Setting, SETTING_KEY)
    if row is None:
        row = Setting(key=SETTING_KEY)
    row.value_json = json.dumps({"api_key": config.api_key}, ensure_ascii=False)
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return config


def is_available(session: Session | None = None) -> bool:
    return resolve(session).available
