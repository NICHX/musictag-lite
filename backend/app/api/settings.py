"""应用设置：通用键值读写（§8.4）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models.db import Setting
from app.models.schemas import (
    AcoustIDSettingsRead,
    AcoustIDSettingsUpdate,
    AISettingsRead,
    AISettingsUpdate,
    ApiTokenRead,
    ApiTokenUpdate,
    SettingsRead,
    SettingsUpdate,
)
from app.services import acoustid_config, ai_config, api_token

router = APIRouter(prefix="/settings", tags=["settings"])


def _load(session: Session) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for row in session.exec(select(Setting)).all():
        if row.value_json is None:
            values[row.key] = None
            continue
        try:
            values[row.key] = json.loads(row.value_json)
        except json.JSONDecodeError:
            values[row.key] = row.value_json
    return values


@router.get("", response_model=SettingsRead)
def get_settings(session: Session = Depends(get_session)) -> SettingsRead:
    return SettingsRead(values=_load(session))


@router.patch("", response_model=SettingsRead)
def update_settings(
    payload: SettingsUpdate, session: Session = Depends(get_session)
) -> SettingsRead:
    for key, value in payload.values.items():
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key)
        row.value_json = json.dumps(value, ensure_ascii=False)
        row.updated_at = datetime.now(UTC)
        session.add(row)
    session.commit()
    return SettingsRead(values=_load(session))


def _ai_read(session: Session) -> AISettingsRead:
    config = ai_config.resolve(session)
    return AISettingsRead(
        enabled=config.enabled,
        base_url=config.base_url,
        model=config.model,
        has_api_key=bool(config.api_key),
        api_key_masked=ai_config.mask_key(config.api_key),
        available=config.available,
    )


@router.get("/ai", response_model=AISettingsRead)
def get_ai_settings(session: Session = Depends(get_session)) -> AISettingsRead:
    """读取 AI 辅助配置（密钥脱敏）。"""
    return _ai_read(session)


@router.patch("/ai", response_model=AISettingsRead)
def update_ai_settings(
    payload: AISettingsUpdate, session: Session = Depends(get_session)
) -> AISettingsRead:
    """更新 AI 辅助配置；``api_key`` 省略表示不修改，传空串表示清除。"""
    current = ai_config.resolve(session)
    key_provided = "api_key" in payload.model_fields_set
    effective_key = payload.api_key if key_provided else current.api_key
    effective_enabled = current.enabled if payload.enabled is None else payload.enabled

    if payload.base_url and not payload.base_url.strip().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Base URL 必须以 http:// 或 https:// 开头")
    if effective_enabled and not effective_key:
        raise HTTPException(status_code=400, detail="启用 AI 辅助前请先填写 API Key")

    ai_config.update(
        session,
        enabled=payload.enabled,
        base_url=payload.base_url,
        model=payload.model,
        **({"api_key": payload.api_key} if key_provided else {}),
    )
    return _ai_read(session)


def _acoustid_read(session: Session) -> AcoustIDSettingsRead:
    config = acoustid_config.resolve(session)
    return AcoustIDSettingsRead(
        has_api_key=bool(config.api_key),
        api_key_masked=acoustid_config.mask_key(config.api_key),
        available=config.available,
    )


@router.get("/acoustid", response_model=AcoustIDSettingsRead)
def get_acoustid_settings(session: Session = Depends(get_session)) -> AcoustIDSettingsRead:
    """读取 AcoustID 配置（密钥脱敏）。"""
    return _acoustid_read(session)


@router.patch("/acoustid", response_model=AcoustIDSettingsRead)
def update_acoustid_settings(
    payload: AcoustIDSettingsUpdate, session: Session = Depends(get_session)
) -> AcoustIDSettingsRead:
    """更新 AcoustID API Key；省略 ``api_key`` 表示不修改，传空串表示清除。"""
    if "api_key" in payload.model_fields_set:
        acoustid_config.update(session, api_key=payload.api_key)
    return _acoustid_read(session)


def _api_token_read(session: Session) -> ApiTokenRead:
    config = api_token.ensure(session)
    return ApiTokenRead(
        enabled=config.enabled,
        token=config.token,
        base_url="/api/open",
    )


@router.get("/api-token", response_model=ApiTokenRead)
def get_api_token(session: Session = Depends(get_session)) -> ApiTokenRead:
    """读取对外 API 令牌（首次访问自动生成；管理面板可见明文）。"""
    return _api_token_read(session)


@router.patch("/api-token", response_model=ApiTokenRead)
def update_api_token(
    payload: ApiTokenUpdate, session: Session = Depends(get_session)
) -> ApiTokenRead:
    """更新对外 API 令牌：可启用/停用，或重新生成（``regenerate=true``）。"""
    api_token.update(session, enabled=payload.enabled, regenerate=payload.regenerate)
    return _api_token_read(session)
