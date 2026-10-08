"""应用设置：通用键值读写（§8.4）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.db import get_session
from app.models.db import Setting
from app.models.schemas import SettingsRead, SettingsUpdate

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
