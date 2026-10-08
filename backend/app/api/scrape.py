"""在线刮削（F7）：搜索候选、应用候选、批量作业。编排在 M1。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import not_implemented
from app.core.db import get_session
from app.models.db import ScrapeJob
from app.models.schemas import (
    ScrapeApplyRequest,
    ScrapeApplyResponse,
    ScrapeJobCreateRequest,
    ScrapeJobRead,
    ScrapeSearchRequest,
    ScrapeSearchResponse,
    TaskAccepted,
)

router = APIRouter(prefix="/scrape", tags=["scrape"])


@router.post("/search", response_model=ScrapeSearchResponse)
def search(payload: ScrapeSearchRequest) -> ScrapeSearchResponse:
    raise not_implemented("M1", "在线刮削搜索（MusicBrainz/CAA/LRCLIB）将在 M1 实现")


@router.post("/apply", response_model=ScrapeApplyResponse)
def apply(payload: ScrapeApplyRequest) -> ScrapeApplyResponse:
    raise not_implemented("M1", "候选应用（含仅补空值）将在 M1 实现")


@router.post("/jobs", response_model=TaskAccepted)
def create_job(payload: ScrapeJobCreateRequest) -> TaskAccepted:
    raise not_implemented("M1", "批量刮削任务将在 M1 实现")


@router.get("/jobs/{job_id}", response_model=ScrapeJobRead)
def get_job(job_id: int, session: Session = Depends(get_session)) -> ScrapeJobRead:
    job = session.get(ScrapeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="刮削作业不存在")
    provider_ids: list[str] = []
    if job.provider_ids:
        try:
            provider_ids = json.loads(job.provider_ids)
        except json.JSONDecodeError:
            provider_ids = []
    return ScrapeJobRead(
        id=job.id,  # type: ignore[arg-type]
        scope=job.scope,
        status=job.status,
        provider_ids=provider_ids,
        created_at=job.created_at,
    )
