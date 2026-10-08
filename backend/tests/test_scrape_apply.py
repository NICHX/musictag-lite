"""刮削应用：候选必须作为权威数据源（避免 release 漂移）。"""

from __future__ import annotations

from app.providers.base import Candidate
from app.services.scrape_orchestrator import ScrapeOrchestrator


def _candidate(**overrides) -> Candidate:
    defaults = {
        "provider": "musicbrainz",
        "external_id": "rec-1965",
        "title": "1965",
        "artist": "Zella Day",
        "album": "Kicker",
        "year": "2015",
        "track_no": None,
        "score": 1.0,
        "cover_url": "https://coverartarchive.org/release/74c7e588/front-500",
        "payload": {"release_id": "74c7e588"},
    }
    defaults.update(overrides)
    return Candidate(**defaults)


def test_bundle_from_candidates_keeps_candidate_release() -> None:
    """bundle 必须取自候选本身，而不是重新 fetch 得到的其他 release。"""
    bundle = ScrapeOrchestrator._bundle_from_candidates([_candidate()])
    assert bundle.title == "1965"
    assert bundle.artist == "Zella Day"
    assert bundle.album == "Kicker"
    assert bundle.year == "2015"
    assert bundle.extra["release_id"] == "74c7e588"
    assert bundle.cover_url == "https://coverartarchive.org/release/74c7e588/front-500"


def test_cover_url_variants() -> None:
    variants = ScrapeOrchestrator._cover_url_variants
    assert variants("https://caa/release/x/front-500") == [
        "https://caa/release/x/front-500",
        "https://caa/release/x/front",
    ]
    assert variants("https://caa/release/x/front") == [
        "https://caa/release/x/front",
        "https://caa/release/x/front-500",
    ]
    assert variants(None) == []
    assert variants("https://example.com/cover.jpg") == ["https://example.com/cover.jpg"]
