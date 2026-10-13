"""对外 API 的访问令牌（Token 鉴权）配置与持久化。

令牌只保存在本地数据库，仅用于 ``/api/open/*`` 对外接口；管理面板可见明文以便复制给
外部系统，业务日志中不记录明文。
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session

from app.models.db import Setting

SETTING_KEY = "api_token"


@dataclass
class ApiTokenConfig:
    token: str | None = None
    enabled: bool = True

    @property
    def active(self) -> bool:
        """启用且已生成令牌时，对外 API 才可用。"""
        return self.enabled and bool(self.token)


def generate_token() -> str:
    """生成一个 URL 安全的高熵令牌。"""
    return secrets.token_urlsafe(32)


def mask(token: str | None) -> str | None:
    """脱敏展示：保留前 4 位与后 4 位。"""
    if not token:
        return None
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}…{token[-4:]}"


def resolve(session: Session | None) -> ApiTokenConfig:
    """读取当前令牌配置；无记录时返回「未启用且无令牌」。"""
    if session is None:
        return ApiTokenConfig(token=None, enabled=False)
    row = session.get(Setting, SETTING_KEY)
    if row is None or not row.value_json:
        return ApiTokenConfig(token=None, enabled=False)
    try:
        data = json.loads(row.value_json)
    except json.JSONDecodeError:
        return ApiTokenConfig(token=None, enabled=False)
    if not isinstance(data, dict):
        return ApiTokenConfig(token=None, enabled=False)
    token = data.get("token")
    return ApiTokenConfig(
        token=str(token) if token else None,
        enabled=bool(data.get("enabled", True)),
    )


def _store(session: Session, config: ApiTokenConfig) -> ApiTokenConfig:
    row = session.get(Setting, SETTING_KEY)
    if row is None:
        row = Setting(key=SETTING_KEY)
    row.value_json = json.dumps(
        {"token": config.token, "enabled": config.enabled}, ensure_ascii=False
    )
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return config


def ensure(session: Session) -> ApiTokenConfig:
    """首次访问时自动生成令牌，开箱即可用（默认启用）。"""
    config = resolve(session)
    if not config.token:
        config.token = generate_token()
        config.enabled = True
        _store(session, config)
    return config


def update(
    session: Session, *, enabled: bool | None = None, regenerate: bool = False
) -> ApiTokenConfig:
    """部分更新：``enabled`` 省略表示不变；``regenerate`` 为真时换发新令牌。"""
    config = resolve(session)
    if regenerate or not config.token:
        config.token = generate_token()
    if enabled is not None:
        config.enabled = enabled
    return _store(session, config)
