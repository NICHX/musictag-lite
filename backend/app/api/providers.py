"""Provider：列出与配置启用状态/优先级/选项（§9.3）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models.db import ProviderConfig
from app.models.schemas import ProviderRead, ProviderUpdate
from app.providers.registry import provider_registry

router = APIRouter(prefix="/providers", tags=["providers"])


def _options(cfg: ProviderConfig | None) -> dict[str, Any]:
    if cfg is None or not cfg.options_json:
        return {}
    try:
        return json.loads(cfg.options_json)
    except json.JSONDecodeError:
        return {}


def _to_read(session: Session, provider, cfg: ProviderConfig | None) -> ProviderRead:  # noqa: ANN001
    if cfg is None:
        cfg = session.exec(
            select(ProviderConfig).where(ProviderConfig.provider_key == provider.key)
        ).first()
    return ProviderRead(
        key=provider.key,
        name=provider.name,
        capabilities=sorted(provider.capabilities),
        enabled=cfg.enabled if cfg else provider.default_enabled,
        priority=cfg.priority if cfg else provider.default_priority,
        options=_options(cfg),
    )


@router.get("", response_model=list[ProviderRead])
def list_providers(session: Session = Depends(get_session)) -> list[ProviderRead]:
    configs = {c.provider_key: c for c in session.exec(select(ProviderConfig)).all()}
    return [
        _to_read(session, provider, configs.get(provider.key))
        for provider in provider_registry.all()
    ]


@router.patch("/{key}", response_model=ProviderRead)
def update_provider(
    key: str, payload: ProviderUpdate, session: Session = Depends(get_session)
) -> ProviderRead:
    provider = provider_registry.get(key)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider 不存在：{key}")

    cfg = session.exec(select(ProviderConfig).where(ProviderConfig.provider_key == key)).first()
    if cfg is None:
        cfg = ProviderConfig(
            provider_key=key,
            enabled=provider.default_enabled,
            priority=provider.default_priority,
        )

    data = payload.model_dump(exclude_unset=True)
    if data.get("enabled") is not None:
        cfg.enabled = bool(data["enabled"])
    if data.get("priority") is not None:
        cfg.priority = int(data["priority"])
    if data.get("options") is not None:
        cfg.options_json = json.dumps(data["options"], ensure_ascii=False)

    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return _to_read(session, provider, cfg)
