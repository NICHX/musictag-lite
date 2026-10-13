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
# 「翻唱/伴奏/纯音乐/live」等非原唱版本标记：命中即降级，避免翻唱压过原唱
_VERSION_NOISE = re.compile(
    r"(cover|翻唱|伴奏|纯音乐|off\s*vocal|instrumental|karaoke|remix|remaster|re-?record|"
    r"和声|合唱|对唱|女声|男声|抖音|tribute|演唱会|现场|\blive\b|dj\s*版|改编)",
    re.IGNORECASE,
)

# 综合打分权重（缺失信号不计分）：
# 弱化"平台/MB 相关性"（名次高≠原唱），提高"艺术家"权重（区分原唱/翻唱的关键）
_W_RELEVANCE = 0.15
_W_COVERAGE = 0.35
_W_TITLE = 0.20
_W_ARTIST = 0.30


async def _none() -> None:
    """占位协程：未启用的分支也返回一个 awaitable，便于统一 gather。"""
    return None


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
    """综合打分：来源相关性 + 查询词覆盖率 + 标题/艺术家相似度 + 时长接近度（§9.4）。

    针对"翻唱压过原唱"做的取舍：
    - 弱化平台/MB 相关性（搜索名次高 ≠ 原唱）；
    - 提高艺术家权重，且**艺术家明显不符时降级**（翻唱最常见特征）；
    - 标题/专辑带「翻唱/伴奏/纯音乐/live…」标记时降级（用户未主动检索该版本时）；
    - 时长差异过大时降级（不同版本时长通常不同）。
    """
    query_text = (
        " ".join(part for part in (query.title, query.artist, query.album) if part)
        or query.filename_hint
        or ""
    )
    artist_similarity = _similarity(query.artist, candidate.artist) if query.artist else None

    score = (
        _W_RELEVANCE * min(1.0, max(0.0, candidate.score))
        + _W_COVERAGE * coverage_score(query_text, candidate)
        + _W_TITLE * _similarity(query.title or query.filename_hint, candidate.title)
    )
    if artist_similarity is not None:
        score += _W_ARTIST * artist_similarity

    # 艺术家明显不符（原唱 vs 翻唱的关键差异）→ 大幅降级
    if artist_similarity is not None and candidate.artist and artist_similarity < 0.34:
        score *= 0.55
    # 标题/专辑含版本标记 → 降级（除非用户本就在检索该版本）
    version_text = " ".join(part for part in (candidate.title, candidate.album) if part)
    if _VERSION_NOISE.search(version_text) and not _VERSION_NOISE.search(query_text):
        score *= 0.7
    # 时长接近度：差异越大越可疑
    if query.duration and candidate.duration:
        low, high = sorted((int(query.duration), int(candidate.duration)))
        if high:
            score *= 0.75 + 0.25 * (low / high)
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

    def rebind(self) -> None:
        """安装/卸载扩展后，把新注册的 Provider 绑定到共享 HTTP 客户端。"""
        if self._client is not None and not self._client.is_closed:
            self._bind_providers()

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
        """按能力与启用状态筛选 Provider，并按**生效优先级**排序。

        优先级 = DB 覆盖值（设置页可自定义）> 注册表默认值；数值越小越先参与。
        元数据检索与歌词回退都按此顺序执行。
        """
        configs: dict[str, ProviderConfig] = {}
        if session is not None:
            configs = {c.provider_key: c for c in session.exec(select(ProviderConfig)).all()}
        chosen: list[tuple[int, str, Any]] = []
        for provider in self.registry.by_capability(capability):
            if providers is not None and provider.key not in providers:
                continue
            config = configs.get(provider.key)
            enabled = config.enabled if config else provider.default_enabled
            if not enabled:
                continue
            priority = config.priority if config else provider.default_priority
            chosen.append((priority, provider.key, provider))
        chosen.sort(key=lambda item: (item[0], item[1]))
        return [provider for _priority, _key, provider in chosen]

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
        fields: list[str] | None = None,
        apply_cover: bool = False,
        apply_lyrics: bool = False,
        write_word_lyrics: bool = False,
    ) -> dict[str, Any]:
        """应用选中候选：写标签（可限定字段/仅补空值）、封面、歌词。

        ``candidates`` 为用户实际选中的候选；提供时直接以它为准构造 bundle。
        否则回退到按 id 重新 ``fetch()``（注意：同一 recording 存在于多个 release，
        重新 fetch 可能取到不同 release，从而写错专辑/年份或抓不到封面）。
        ``fields`` 为字段白名单（逐字段勾选）；``None`` 表示写入候选提供的全部字段。
        """
        self.client()
        picked = [item for item in (candidates or []) if item.external_id]
        bundle = (
            self._bundle_from_candidates(picked)
            if picked
            else await self._merge_bundles(candidate_ids)
        )

        values = self._bundle_to_values(bundle)
        if fields is not None:
            allowed = set(fields)
            values = {key: value for key, value in values.items() if key in allowed}
        if only_missing:
            values = {
                key: value
                for key, value in values.items()
                if getattr(track, key, None) in (None, "")
            }

        diffs: list[dict[str, Any]] = []
        if values:
            diffs = TagService().apply_single(session, track, values, source=SOURCE_SCRAPE)

        # 封面 / 歌词 / 逐字歌词互不依赖，并发拉取可省掉串行的网络往返
        # 注意：歌词与元数据来源相互独立（歌词按 lyrics 能力源顺序抓取，与所选候选无关）
        cover, lyrics_result, word_bundle = await asyncio.gather(
            self._fetch_cover(bundle) if apply_cover else _none(),
            self._fetch_lyrics(session, track) if apply_lyrics else _none(),
            self.word_lyrics_bundle(session, track) if write_word_lyrics else _none(),
        )
        content, lyrics_source = lyrics_result if lyrics_result is not None else (None, None)

        cover_applied = False
        if cover is not None:
            CoverService().write(
                session,
                track,
                CoverImage(data=cover.data, mime=cover.mime),
                source=SOURCE_SCRAPE,
            )
            cover_applied = True

        word_found = False
        word_written = False
        word_source: str | None = None
        if word_bundle is not None:
            source_key, plain, word = word_bundle
            word_found = bool(word)
            if word:
                word_source = source_key or None
                # 逐字歌词（若数据源歌词含译文，则并入）写「内嵌 + 同名 .nilyric」
                from app.services.word_lyrics import merge_word_translation

                merged = merge_word_translation(word, content or plain)
                LyricsService().write_final(
                    session, track, merged, targets=["embedded", "nilyric"], source=SOURCE_SCRAPE
                )
                word_written = True

        lyrics_found = bool(content)
        lyrics_applied = False
        # 已写逐字歌词时，内嵌已是最终产物，不再单独写逐行
        if content and not word_written:
            LyricsService().write(session, track, content, target="embedded", source=SOURCE_SCRAPE)
            lyrics_applied = True

        return {
            "applied_fields": [item["field"] for item in diffs],
            "diffs": diffs,
            "cover_applied": cover_applied,
            "lyrics_applied": lyrics_applied,
            "lyrics_found": lyrics_found,
            "lyrics_source": lyrics_source if lyrics_found else None,
            "word_found": word_found,
            "word_written": word_written,
            "word_lyrics_source": word_source if word_found else None,
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

    def word_lyrics_providers(self, session: Session | None) -> list[Any]:
        """已启用且支持逐字的歌词源（按生效优先级），供「未找到」时区分原因。"""
        return [
            provider
            for provider in self.select_providers(session, "lyrics")
            if callable(getattr(provider, "fetch_word_lyrics", None))
        ]

    async def word_lyrics(
        self, session: Session | None, track: Track
    ) -> tuple[str, list[dict[str, Any]]]:
        """逐字歌词（只读预览）：按 Provider 顺序取第一个支持逐字的源。"""
        self.client()
        query = self.build_query(track, self.known_artists(session))
        for provider in self.word_lyrics_providers(session):
            fetch = getattr(provider, "fetch_word_lyrics", None)
            try:
                lines = await fetch(query)
            except Exception as exc:  # noqa: BLE001 - 单源失败不影响其他源
                logger.warning(
                    "scrape.word_lyrics_failed",
                    extra={"provider": provider.key, "error": str(exc)},
                )
                continue
            if lines:
                return provider.key, lines
        return "", []

    async def word_lyrics_bundle(self, session: Session | None, track: Track) -> tuple[str, str, str]:
        """逐字歌词 → ``(来源, 逐行 LRC, 逐字 LRC)``（后者为 LDDC / lx-music 格式）。"""
        from app.services.word_lyrics import to_plain_lrc, to_word_lrc

        source, lines = await self.word_lyrics(session, track)
        if not lines:
            return source, "", ""
        return source, to_plain_lrc(lines), to_word_lrc(lines)

    async def _fetch_lyrics(
        self, session: Session | None, track: Track
    ) -> tuple[str | None, str | None]:
        """返回 ``(歌词文本, 来源)``：按 lyrics 能力源顺序取第一个命中的源。

        来源即实际提供歌词的 Provider key（与元数据候选的来源无关）。
        """
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
                return lyrics.content, (lyrics.source or provider.key)
        return None, None

    async def fetch_lyrics_text(self, session: Session | None, track: Track) -> str | None:
        """按启用顺序抓取歌词文本（部分源如网易云/QQ 已含译文，返回双语 LRC）。"""
        self.client()
        content, _source = await self._fetch_lyrics(session, track)
        return content

    async def word_lyrics_final(
        self,
        session: Session | None,
        track: Track,
        *,
        translation: str = "source",
        translate_target: str = "zh",
    ) -> str | None:
        """抓取逐字歌词并（按 ``translation`` 模式）并入译文，返回最终文本。

        单文件编辑与批量**共用此实现**，确保写入内容一致：

        - ``none``：只逐字；
        - ``source``：并入数据源自带译文（网易云 / QQ，免费）；
        - ``ai``：显式调用 AI 生成译文（可能产生费用），AI 不可用时抛 ``LyricsTranslateError``。

        无逐字歌词时返回 ``None``。
        """
        from app.services.word_lyrics import has_translation, merge_word_translation

        _source, plain, word = await self.word_lyrics_bundle(session, track)
        if not word:
            return None

        text: str | None = None
        if translation == "source":
            bilingual = await self.fetch_lyrics_text(session, track)
            if has_translation(word, bilingual):
                text = bilingual
        elif translation == "ai":
            from app.services import ai_config
            from app.services.lyrics_translate import LyricsTranslateError, translate_lyrics

            config = ai_config.resolve(session)
            if not config.available:
                raise LyricsTranslateError("AI 未启用：无法生成译文（可在「设置」中配置）")
            text = await translate_lyrics(plain, target=translate_target, config=config)

        return merge_word_translation(word, text or "")


# 全局单例
scrape_orchestrator = ScrapeOrchestrator()
