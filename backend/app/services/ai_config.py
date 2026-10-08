"""AI 辅助配置的解析与持久化。

优先级：**界面设置（数据库） > 环境变量**。
密钥只保存在本地数据库；对外读取时始终脱敏，不回传明文。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session

from app.core.config import get_settings
from app.models.db import Setting

SETTING_KEY = "ai"
_UNSET: object = object()


@dataclass
class AIConfig:
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    timeout: float = 30.0

    @property
    def available(self) -> bool:
        """已启用且配置了密钥才算可用。"""
        return bool(self.enabled and self.api_key)


def mask_key(key: str | None) -> str | None:
    """脱敏展示：保留前 3 位与后 4 位。"""
    if not key:
        return None
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-4:]}"


def _from_env() -> AIConfig:
    settings = get_settings()
    return AIConfig(
        enabled=settings.ai_enabled,
        base_url=settings.ai_base_url,
        model=settings.ai_model,
        api_key=settings.ai_api_key,
        timeout=settings.ai_timeout,
    )


def resolve(session: Session | None) -> AIConfig:
    """读取生效配置；数据库中没有记录时回退到环境变量。"""
    config = _from_env()
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
    return AIConfig(
        enabled=bool(data.get("enabled", config.enabled)),
        base_url=str(data.get("base_url") or config.base_url),
        model=str(data.get("model") or config.model),
        api_key=str(api_key) if api_key else None,
        timeout=config.timeout,
    )


def update(
    session: Session,
    *,
    enabled: bool | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: object = _UNSET,
) -> AIConfig:
    """部分更新并持久化。``api_key`` 传入 ``_UNSET`` 表示不修改，传空串表示清除。"""
    current = resolve(session)
    if api_key is _UNSET:
        key = current.api_key
    else:
        text = str(api_key).strip() if api_key else ""
        key = text or None
    config = AIConfig(
        enabled=current.enabled if enabled is None else enabled,
        base_url=(base_url or current.base_url).strip(),
        model=(model or current.model).strip(),
        api_key=key,
        timeout=current.timeout,
    )

    row = session.get(Setting, SETTING_KEY)
    if row is None:
        row = Setting(key=SETTING_KEY)
    row.value_json = json.dumps(
        {
            "enabled": config.enabled,
            "base_url": config.base_url,
            "model": config.model,
            "api_key": config.api_key,
        },
        ensure_ascii=False,
    )
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return config


def is_ai_available(session: Session | None = None) -> bool:
    return resolve(session).available
