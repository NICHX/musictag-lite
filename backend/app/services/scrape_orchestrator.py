"""刮削编排：并发查询多 Provider、打分合并、应用候选（F7 / §9.4）。"""

from __future__ import annotations

import asyncio
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
from sqlmodel import Session, select

from app.audio.base import CoverImage
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.db import ProviderConfig, Track
from app.providers.base import AlbumBundle, Candidate, CoverBytes, ScrapeQuery
from app.providers.registry import ProviderRegistry, provider_registry
from app.services import acoustid_config
from app.services.cover_service import CoverService
from app.services.filename_parser import parse_filename
from app.services.fingerprint import compute_fingerprint
from app.services.lyrics_service import LyricsService
from app.services.tag_service import SOURCE_SCRAPE, TagService

logger = get_logger(__name__)

# 文件名开头的音轨号 / 序号噪声，如 "01 - "、"03."、"12_"
_FILENAME_NOISE = re.compile(r"^\s*\d{1,3}[\s._-]+")
# 分词：保留字母/数字/中日韩字符（用于与分隔符无关的覆盖率打分）
_TOKEN_RE = re.compile(r"[0-9a-z\u4e00-\u9fff]+")


def _similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower().strip(), right.lower().strip()).ratio()


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return set(_TOKEN_RE.findall(text.lower()))


def coverage_score(query_text: str | None, candidate: Candidate) -> float:
    """查询词覆盖率：对「文件名兜底」尤其有效，且不依赖 Title/Artist 的先后顺序。"""
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return 0.0
    candidate_tokens = _tokens(
        " ".join(part for part in (candidate.title, candidate.artist, candidate.album) if part)
    )
    return len(query_tokens & candidate_tokens) / len(query_tokens)


def score_candidate(candidate: Candidate, query: ScrapeQuery) -> float:
    """综合打分：来源匹配分 + 查询词覆盖率 + 标题/艺术家相似度 + 音轨号一致性。"""
    query_text = (
        " ".join(part for part in (query.title, query.artist, query.album) if part)
        or query.filename_hint
        or ""
    )
    score = (
        0.25 * candidate.score
        + 0.45 * coverage_score(query_text, candidate)
        + 0.20 * _similarity(query.title or query.filename_hint, candidate.title)
        + 0.10 * _similarity(query.artist, candidate.artist)
    )
    if query.track_no and candidate.track_no == query.track_no:
        score += 0.05
    return round(min(1.0, score), 4)


class ScrapeOrchestrator:
    """统一出口：所有 Provider 共用同一 httpx 客户端（超时/UA/限流）。"""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or provider_registry
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None
        self._artists_cache: set[str] = set()
        self._artists_at: float = 0.0

    # ---- 网络客户端 ----
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._settings.http_timeout,
                headers={"User-Agent": self._settings.musicbrainz_user_agent},
                follow_redirects=True,
            )
            self._bind_providers()
        return self._client

    def _bind_providers(self) -> None:
        if self._client is None:
            return
        for provider in self.registry.all():
            bind = getattr(provider, "bind", None)
            if callable(bind):
                bind(self._client)

    def _configure_acoustid(self, session: Session | None) -> None:
        """把生效的 AcoustID Key（界面设置 > 环境变量）注入 Provider。"""
        provider = self.registry.get("acoustid")
        configure = getattr(provider, "configure", None)
        if callable(configure):
            configure(acoustid_config.resolve(session).api_key)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---- 查询 ----
    def known_artists(self, session: Session | None, *, ttl: float = 60.0) -> set[str]:
        """曲库中已标注过的艺术家（小写集合），用于消解文件名「A - B」的顺序歧义。"""
        if session is None:
            return set()
        now = time.monotonic()
        if self._artists_cache and now - self._artists_at < ttl:
            return self._artists_cache
        rows = session.exec(select(Track.artist).where(Track.artist.is_not(None)).distinct()).all()
        self._artists_cache = {
            str(name).strip().casefold() for name in rows if name and str(name).strip()
        }
        self._artists_at = now
        return self._artists_cache

    @staticmethod
    def build_query(track: Track, known_artists: set[str] | None = None) -> ScrapeQuery:
        """构造查询：优先已有标签，缺失字段用文件名解析补全（§9.4）。"""
        stem = Path(track.filename).stem
        hint = _FILENAME_NOISE.sub("", stem).strip() or stem
        parsed = parse_filename(track.filename, known_artists)
        return ScrapeQuery(
            title=track.title or parsed.title,
            artist=track.artist or parsed.artist,
            album=track.album or parsed.album,
            track_no=track.track_no or parsed.track_no,
            duration=int(track.duration) if track.duration else None,
            filename_hint=hint,
        )

    def select_providers(
        self,
        session: Session | None,
        capability: str,
        providers: list[str] | None = None,
    ) -> list[Any]:
        """按能力与启用状态筛选 Provider（注册表默认值 + DB 覆盖）。"""
        configs: dict[str, ProviderConfig] = {}
        if session is not None:
            configs = {c.provider_key: c for c in session.exec(select(ProviderConfig)).all()}
        chosen: list[Any] = []
        for provider in self.registry.by_capability(capability):
            if providers is not None and provider.key not in providers:
                continue
            config = configs.get(provider.key)
            enabled = config.enabled if config else provider.default_enabled
            if enabled:
                chosen.append(provider)
        return chosen

    async def search(
        self,
        session: Session,
        query: ScrapeQuery,
        *,
        providers: list[str] | None = None,
        limit: int = 10,
    ) -> list[Candidate]:
        """并发查询多个元数据源，合并并打分排序。"""
        chosen = self.select_providers(session, "metadata", providers)
        if not chosen:
            return []
        self.client()
        self._configure_acoustid(session)
        results = await asyncio.gather(
            *(provider.search(query) for provider in chosen), return_exceptions=True
        )

        candidates: list[Candidate] = []
        for provider, result in zip(chosen, results, strict=False):
            if isinstance(result, Exception):
                logger.warning(
                    "scrape.search_failed",
                    extra={"provider": provider.key, "error": str(result)},
                )
                continue
            candidates.extend(result)

        for candidate in candidates:
            candidate.score = score_candidate(candidate, query)
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:limit]

    async def identify(
        self, session: Session, track: Track, *, enrich: bool = True, limit: int = 5
    ) -> list[Candidate]:
        """指纹识别（F14）：本地 fpcalc → AcoustID → 回填 MusicBrainz。

        仅发送指纹与时长（不上传音频）；供「标签与文件名都不可靠」时兜底使用。
        """
        provider = self.registry.get("acoustid")
        if provider is None:
            return []
        self.client()
        self._configure_acoustid(session)
        fingerprint = await asyncio.to_thread(compute_fingerprint, track.path)
        candidates = await provider.identify(fingerprint.value, fingerprint.duration)
        candidates = candidates[:limit]
        if enrich and candidates:
            await self._enrich_with_musicbrainz(candidates)
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates

    async def _enrich_with_musicbrainz(self, candidates: list[Candidate]) -> None:
        """用 MusicBrainz recording id 补齐专辑/年份/封面。"""
        musicbrainz = self.registry.get("musicbrainz")
        if musicbrainz is None:
            return
        for candidate in candidates:
            try:
                bundle = await musicbrainz.fetch(candidate.external_id)
            except Exception as exc:  # noqa: BLE001 - 单条回填失败不影响识别
                logger.warning(
                    "fingerprint.enrich_failed",
                    extra={"id": candidate.external_id, "error": str(exc)},
                )
                continue
            if bundle.title and not candidate.title:
                candidate.title = bundle.title
            if bundle.artist and not candidate.artist:
                candidate.artist = bundle.artist
            if bundle.album and not candidate.album:
                candidate.album = bundle.album
            if bundle.year and not candidate.year:
                candidate.year = bundle.year
            if bundle.cover_url:
                candidate.cover_url = bundle.cover_url
            release_id = bundle.extra.get("release_id")
            if release_id:
                candidate.payload["release_id"] = release_id

    async def apply(
        self,
        session: Session,
        track: Track,
        candidate_ids: list[str],
        *,
        candidates: list[Candidate] | None = None,
        only_missing: bool = False,
        apply_cover: bool = False,
        apply_lyrics: bool = False,
    ) -> dict[str, Any]:
        """应用选中候选：写标签（可仅补空值）、封面、歌词。

        ``candidates`` 为用户实际选中的候选；提供时直接以它为准构造 bundle。
        否则回退到按 id 重新 ``fetch()``（注意：同一 recording 存在于多个 release，
        重新 fetch 可能取到不同 release，从而写错专辑/年份或抓不到封面）。
        """
        self.client()
        picked = [item for item in (candidates or []) if item.external_id]
        bundle = (
            self._bundle_from_candidates(picked)
            if picked
            else await self._merge_bundles(candidate_ids)
        )

        values = self._bundle_to_values(bundle)
        if only_missing:
            values = {
                key: value
                for key, value in values.items()
                if getattr(track, key, None) in (None, "")
            }

        diffs: list[dict[str, Any]] = []
        if values:
            diffs = TagService().apply_single(session, track, values, source=SOURCE_SCRAPE)

        cover_applied = False
        if apply_cover:
            cover = await self._fetch_cover(bundle)
            if cover is not None:
                CoverService().write(
                    session,
                    track,
                    CoverImage(data=cover.data, mime=cover.mime),
                    source=SOURCE_SCRAPE,
                )
                cover_applied = True

        lyrics_applied = False
        if apply_lyrics:
            content = await self._fetch_lyrics(session, track)
            if content:
                LyricsService().write(
                    session, track, content, target="embedded", source=SOURCE_SCRAPE
                )
                lyrics_applied = True

        return {
            "applied_fields": [item["field"] for item in diffs],
            "diffs": diffs,
            "cover_applied": cover_applied,
            "lyrics_applied": lyrics_applied,
        }

    # ---- 内部 ----
    @staticmethod
    def _bundle_from_candidates(candidates: list[Candidate]) -> AlbumBundle:
        """直接由选中的候选构造 bundle（不重新 fetch，避免 release 漂移）。"""
        bundle = AlbumBundle()
        for candidate in candidates:
            payload = candidate.payload or {}
            for field in ("title", "artist", "album", "year", "track_no"):
                value = getattr(candidate, field, None)
                if getattr(bundle, field) in (None, "") and value not in (None, ""):
                    setattr(bundle, field, value)
            if not bundle.cover_url and candidate.cover_url:
                bundle.cover_url = candidate.cover_url
            release_id = payload.get("release_id")
            if release_id and not bundle.extra.get("release_id"):
                bundle.extra["release_id"] = release_id
            for key, value in payload.items():
                if value and key not in bundle.extra:
                    bundle.extra[key] = value
        return bundle

    async def _merge_bundles(self, candidate_ids: list[str]) -> AlbumBundle:
        merged = AlbumBundle()
        for uid in candidate_ids:
            provider_key, _, external_id = uid.partition(":")
            provider = self.registry.get(provider_key)
            if provider is None or not external_id:
                continue
            try:
                fetched = await provider.fetch(external_id)
            except Exception as exc:  # noqa: BLE001 - 单源失败不影响其他源
                logger.warning(
                    "scrape.fetch_failed",
                    extra={"provider": provider_key, "external_id": external_id, "error": str(exc)},
                )
                continue
            for field in (
                "title",
                "artist",
                "album",
                "album_artist",
                "year",
                "genre",
                "track_no",
                "disc_no",
            ):
                if getattr(merged, field) in (None, "") and getattr(fetched, field) not in (
                    None,
                    "",
                ):
                    setattr(merged, field, getattr(fetched, field))
            if not merged.cover_url and fetched.cover_url:
                merged.cover_url = fetched.cover_url
            merged.extra.update({k: v for k, v in fetched.extra.items() if v})
        return merged

    @staticmethod
    def _bundle_to_values(bundle: AlbumBundle) -> dict[str, Any]:
        mapping = {
            "title": bundle.title,
            "artist": bundle.artist,
            "album": bundle.album,
            "album_artist": bundle.album_artist,
            "year": bundle.year,
            "genre": bundle.genre,
            "track_no": bundle.track_no,
            "disc_no": bundle.disc_no,
        }
        return {key: value for key, value in mapping.items() if value not in (None, "")}

    async def _fetch_cover(self, bundle: AlbumBundle) -> CoverBytes | None:
        coverart = self.registry.get("coverart")
        release_id = bundle.extra.get("release_id")
        if coverart is not None and release_id:
            try:
                cover = await coverart.fetch_cover(str(release_id))
                if cover is not None:
                    return cover
            except Exception as exc:  # noqa: BLE001
                logger.warning("scrape.cover_failed", extra={"error": str(exc)})

        # 回退：直接按封面地址下载（含 /front 与 /front-500 变体）
        for url in self._cover_url_variants(bundle.cover_url):
            try:
                response = await self.client().get(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "scrape.cover_download_failed", extra={"url": url, "error": str(exc)}
                )
                continue
            if response.status_code == 200 and response.content:
                mime = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                return CoverBytes(data=response.content, mime=mime or "image/jpeg")
        return None

    @staticmethod
    def _cover_url_variants(url: str | None) -> list[str]:
        """CAA 的 /front 与 /front-500 互为备选，任一可用即可。"""
        if not url:
            return []
        if url.endswith("/front-500"):
            return [url, url[: -len("-500")]]
        if url.endswith("/front"):
            return [url, f"{url}-500"]
        return [url]

    async def _fetch_lyrics(self, session: Session | None, track: Track) -> str | None:
        query = self.build_query(track, self.known_artists(session))
        for provider in self.select_providers(session, "lyrics"):
            try:
                lyrics = await provider.fetch_lyrics(query)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "scrape.lyrics_failed",
                    extra={"provider": provider.key, "error": str(exc)},
                )
                continue
            if lyrics is not None and lyrics.content:
                return lyrics.content
        return None


# 全局单例
scrape_orchestrator = ScrapeOrchestrator()
