"""在线刮削（F7）：搜索候选、应用候选、批量作业；指纹识别（F14）。"""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import ensure_track_path, get_track_or_404
from app.core.db import get_session, session_scope
from app.core.logging import get_logger
from app.core.tasks import task_manager
from app.models.db import ScrapeJob, TaskStatus, Track
from app.models.schemas import (
    CandidateRead,
    FieldDiff,
    FingerprintRequest,
    ScrapeApplyRequest,
    ScrapeApplyResponse,
    ScrapeJobCreateRequest,
    ScrapeJobRead,
    ScrapeSearchRequest,
    ScrapeSearchResponse,
    TaskAccepted,
)
from app.providers.base import Candidate, ScrapeQuery
from app.services import acoustid_config
from app.services.fingerprint import FingerprintUnavailable, fpcalc_available
from app.services.scrape_orchestrator import scrape_orchestrator

router = APIRouter(prefix="/scrape", tags=["scrape"])
logger = get_logger(__name__)

# 批量自动应用的最低置信度（§9.4：高置信自动应用，且仅补空值）
AUTO_APPLY_THRESHOLD = 0.6


def _candidate_read(item: Candidate) -> CandidateRead:
    return CandidateRead(
        provider=item.provider,
        external_id=item.external_id,
        title=item.title,
        artist=item.artist,
        album=item.album,
        year=item.year,
        track_no=item.track_no,
        score=item.score,
        cover_url=item.cover_url,
        payload=item.payload,
    )


async def _fingerprint_fallback(session: Session, track: Track) -> list[Candidate]:
    """F16 兜底：标签/文件名都无命中时用指纹识别（需 fpcalc + Key + 已启用该源）。"""
    if not fpcalc_available() or not acoustid_config.resolve(session).available:
        return []
    if not scrape_orchestrator.select_providers(session, "fingerprint"):
        return []
    try:
        return await scrape_orchestrator.identify(session, track)
    except FingerprintUnavailable:
        return []


@router.post("/search", response_model=ScrapeSearchResponse)
async def search(
    payload: ScrapeSearchRequest, session: Session = Depends(get_session)
) -> ScrapeSearchResponse:
    """按 track_id 或直接查询词搜索候选（多源并发 + 打分排序）。"""
    track: Track | None = None
    if payload.track_id is not None:
        track = get_track_or_404(session, payload.track_id)
        ensure_track_path(session, track)
        query = scrape_orchestrator.build_query(track, scrape_orchestrator.known_artists(session))
    elif payload.query is not None:
        query = ScrapeQuery(**payload.query.model_dump())
    else:
        raise HTTPException(status_code=400, detail="需要提供 track_id 或 query")

    candidates = await scrape_orchestrator.search(
        session, query, providers=payload.providers, limit=payload.limit
    )
    # F16 多源兜底：标签/文件名都无命中时，尝试指纹识别（需已启用该源并配置好 Key）
    if not candidates and track is not None:
        candidates = await _fingerprint_fallback(session, track)

    return ScrapeSearchResponse(
        track_id=payload.track_id,
        candidates=[_candidate_read(item) for item in candidates],
    )


@router.post("/fingerprint", response_model=ScrapeSearchResponse)
async def fingerprint(
    payload: FingerprintRequest, session: Session = Depends(get_session)
) -> ScrapeSearchResponse:
    """指纹识别（F14，手动触发）：fpcalc → AcoustID → 回填 MusicBrainz。

    仅发送指纹与时长，不上传音频本体。需镜像内可用 fpcalc 且已配置 API Key。
    """
    track = get_track_or_404(session, payload.track_id)
    ensure_track_path(session, track)

    if not fpcalc_available():
        raise HTTPException(
            status_code=400, detail="未安装 fpcalc（Chromaprint），无法进行指纹识别"
        )
    if not acoustid_config.resolve(session).available:
        raise HTTPException(
            status_code=400,
            detail="未配置 AcoustID API Key（可在设置页填写或设置 ACOUSTID_API_KEY）",
        )
    try:
        candidates = await scrape_orchestrator.identify(session, track)
    except FingerprintUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"指纹识别失败：{exc}") from exc

    return ScrapeSearchResponse(
        track_id=track.id,
        candidates=[_candidate_read(item) for item in candidates],
    )


@router.post("/apply", response_model=ScrapeApplyResponse)
async def apply(
    payload: ScrapeApplyRequest, session: Session = Depends(get_session)
) -> ScrapeApplyResponse:
    """应用选中的候选（可仅补空值、附带封面/歌词）。"""
    track = get_track_or_404(session, payload.track_id)
    ensure_track_path(session, track)
    if not payload.candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids 不能为空")

    result = await scrape_orchestrator.apply(
        session,
        track,
        payload.candidate_ids,
        candidates=[
            Candidate(
                provider=item.provider,
                external_id=item.external_id,
                title=item.title,
                artist=item.artist,
                album=item.album,
                year=item.year,
                track_no=item.track_no,
                score=item.score,
                cover_url=item.cover_url,
                payload=item.payload,
            )
            for item in payload.candidates
        ]
        or None,
        only_missing=payload.only_missing,
        apply_cover=payload.apply_cover,
        apply_lyrics=payload.apply_lyrics,
    )
    return ScrapeApplyResponse(
        track_id=track.id,  # type: ignore[arg-type]
        applied_fields=result["applied_fields"],
        cover_applied=result["cover_applied"],
        lyrics_applied=result["lyrics_applied"],
        diffs=[FieldDiff(**item) for item in result["diffs"]],
    )


@router.post("/jobs", response_model=TaskAccepted)
async def create_job(payload: ScrapeJobCreateRequest) -> TaskAccepted:
    """批量刮削：对每首取最高分候选，达到阈值即自动应用（仅补空值 + 封面）。"""
    with session_scope() as session:
        job = ScrapeJob(
            scope="batch",
            provider_ids=json.dumps(payload.providers or [], ensure_ascii=False),
            status=str(TaskStatus.queued),
            query_json=json.dumps({"ids": payload.ids}, ensure_ascii=False),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    async def runner(ctx) -> None:  # noqa: ANN001
        await ctx.set_total(len(payload.ids))
        applied = 0
        for track_id in payload.ids:
            try:
                with session_scope() as session:
                    track = session.get(Track, track_id)
                    if track is not None:
                        query = scrape_orchestrator.build_query(
                            track, scrape_orchestrator.known_artists(session)
                        )
                        candidates = await scrape_orchestrator.search(
                            session, query, providers=payload.providers, limit=5
                        )
                        if candidates and candidates[0].score >= AUTO_APPLY_THRESHOLD:
                            await scrape_orchestrator.apply(
                                session,
                                track,
                                [candidates[0].uid],
                                candidates=[candidates[0]],
                                only_missing=payload.only_missing,
                                apply_cover=True,
                            )
                            applied += 1
            except Exception:  # noqa: BLE001 - 单条失败不影响整批
                logger.exception("scrape.job.item_failed", extra={"track_id": track_id})
            await ctx.advance(current=f"track {track_id}")

        with session_scope() as session:
            stored = session.get(ScrapeJob, job_id) if job_id is not None else None
            if stored is not None:
                stored.status = str(TaskStatus.succeeded)
                session.add(stored)
        await ctx.message(f"批量刮削完成：应用 {applied} / 共 {len(payload.ids)}")

    task_id = await task_manager.run("scrape", runner, total=len(payload.ids))
    return TaskAccepted(task_id=task_id)


@router.get("/jobs/{job_id}", response_model=ScrapeJobRead)
def get_job(job_id: int, session: Session = Depends(get_session)) -> ScrapeJobRead:
    job = session.get(ScrapeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="刮削作业不存在")
    try:
        provider_ids = json.loads(job.provider_ids) if job.provider_ids else []
    except json.JSONDecodeError:
        provider_ids = []
    return ScrapeJobRead(
        id=job.id,  # type: ignore[arg-type]
        scope=job.scope,
        status=job.status,
        provider_ids=provider_ids,
        created_at=job.created_at,
    )
