"""F14 指纹识别：fpcalc 解析、AcoustID Provider、设置项与接口防护。"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.providers.base import Candidate, ScrapeQuery
from app.providers.builtin.acoustid import AcoustIDProvider
from app.services import fingerprint
from app.services.acoustid_config import AcoustIDConfig
from tests.audio_factory import make_flac


def _client(handler) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------- #
# fpcalc 解析
# --------------------------------------------------------------------------- #
def test_compute_fingerprint_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fingerprint, "fpcalc_available", lambda: True)

    class _Result:
        returncode = 0
        stdout = '{"duration": 210.5, "fingerprint": "AQAAabc"}'
        stderr = ""

    monkeypatch.setattr(fingerprint.subprocess, "run", lambda *a, **k: _Result())
    result = fingerprint.compute_fingerprint("/music/a.flac")
    assert result.duration == 210 and result.value == "AQAAabc"


def test_compute_fingerprint_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fingerprint, "fpcalc_available", lambda: False)
    with pytest.raises(fingerprint.FingerprintUnavailable):
        fingerprint.compute_fingerprint("/music/a.flac")


# --------------------------------------------------------------------------- #
# AcoustID Provider
# --------------------------------------------------------------------------- #
async def test_identify_parses_results() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "results": [
                    {
                        "id": "aid-1",
                        "score": 0.97,
                        "recordings": [
                            {
                                "id": "rec-1",
                                "title": "Rolling in the Deep",
                                "artists": [{"name": "Adele"}],
                                "releasegroups": [
                                    {"id": "rg-1", "title": "21", "first-release-date": "2011"}
                                ],
                            }
                        ],
                    }
                ],
            },
        )

    provider = AcoustIDProvider()
    provider.bind(_client(handler))
    provider.configure("test-key")
    candidates = await provider.identify("FP123", 201)

    assert seen["method"] == "POST"
    assert "client=test-key" in seen["body"] and "fingerprint=FP123" in seen["body"]
    assert len(candidates) == 1
    item = candidates[0]
    assert (item.external_id, item.title, item.artist, item.album, item.year) == (
        "rec-1",
        "Rolling in the Deep",
        "Adele",
        "21",
        "2011",
    )
    assert item.score == pytest.approx(0.97)


async def test_search_without_fingerprint_returns_empty() -> None:
    provider = AcoustIDProvider()
    provider.configure("test-key")
    assert await provider.search(ScrapeQuery(title="x", artist="y")) == []


async def test_identify_without_key_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "acoustid_api_key", None, raising=False)
    provider = AcoustIDProvider()  # 未 configure，且环境变量为空
    assert await provider.identify("FP123", 200) == []


# --------------------------------------------------------------------------- #
# 接口
# --------------------------------------------------------------------------- #
def test_capabilities_includes_acoustid(client) -> None:
    body = client.get("/api/capabilities").json()
    assert "acoustid" in body


def test_acoustid_settings_roundtrip(client) -> None:
    try:
        saved = client.patch("/api/settings/acoustid", json={"api_key": "abcdefgh1234"}).json()
        assert saved["has_api_key"] is True and saved["available"] is True
        assert saved["api_key_masked"] and "abcdefgh1234" not in saved["api_key_masked"]
        assert client.get("/api/settings/acoustid").json()["has_api_key"] is True
    finally:
        cleared = client.patch("/api/settings/acoustid", json={"api_key": ""}).json()
    assert cleared["has_api_key"] is False


@pytest.fixture
def library(client, tmp_path: Path) -> dict:
    album = tmp_path / "music"
    album.mkdir(parents=True)
    make_flac(album / "track.flac")
    resp = client.post("/api/libraries", json={"name": "指纹库", "root_path": str(album)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scanned_track(client, library_id: int) -> dict:
    resp = client.post(f"/api/libraries/{library_id}/scan")
    deadline = time.time() + 30
    while time.time() < deadline:
        data = client.get(f"/api/tasks/{resp.json()['task_id']}").json()
        if data["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    return client.get("/api/tracks", params={"library_id": library_id}).json()["items"][0]


def test_fingerprint_endpoint_requires_fpcalc(
    client, library, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = _scanned_track(client, library["id"])
    monkeypatch.setattr("app.api.scrape.fpcalc_available", lambda: False)
    resp = client.post("/api/scrape/fingerprint", json={"track_id": track["id"]})
    assert resp.status_code == 400
    assert "fpcalc" in resp.json()["detail"]


def test_fingerprint_endpoint_requires_key(
    client, library, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = _scanned_track(client, library["id"])
    monkeypatch.setattr("app.api.scrape.fpcalc_available", lambda: True)
    monkeypatch.setattr(
        "app.api.scrape.acoustid_config.resolve", lambda session: AcoustIDConfig(api_key=None)
    )
    resp = client.post("/api/scrape/fingerprint", json={"track_id": track["id"]})
    assert resp.status_code == 400
    assert "AcoustID" in resp.json()["detail"]


def test_fingerprint_endpoint_returns_candidates(
    client, library, monkeypatch: pytest.MonkeyPatch
) -> None:
    track = _scanned_track(client, library["id"])
    monkeypatch.setattr("app.api.scrape.fpcalc_available", lambda: True)
    monkeypatch.setattr(
        "app.api.scrape.acoustid_config.resolve", lambda session: AcoustIDConfig(api_key="k")
    )

    async def fake_identify(session, target, **_kwargs):  # noqa: ANN001
        return [
            Candidate(provider="acoustid", external_id="rec-9", title="T", artist="A", score=0.9)
        ]

    monkeypatch.setattr("app.api.scrape.scrape_orchestrator.identify", fake_identify)
    body = client.post("/api/scrape/fingerprint", json={"track_id": track["id"]}).json()
    assert body["track_id"] == track["id"]
    assert body["candidates"][0]["external_id"] == "rec-9"
