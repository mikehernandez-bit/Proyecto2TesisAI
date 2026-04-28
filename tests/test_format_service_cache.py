from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.services.format_service import FormatService
from app.integrations.gicatesis.cache.format_cache import FormatCache
from app.integrations.gicatesis.errors import UpstreamUnavailable
from app.integrations.gicatesis.types import CatalogVersionResponse, FormatDetail, FormatSummary


def _service_with_cache(tmp_path) -> tuple[FormatService, FormatCache]:
    cache = FormatCache(tmp_path / "gicatesis_cache.json")
    service = FormatService()
    service.cache = cache
    return service, cache


def _summary(version: str) -> FormatSummary:
    return FormatSummary(
        id="fmt-1",
        title="Formato",
        university="unac",
        category="maestria",
        documentType="tesis",
        version=version,
    )


def _detail(version: str, chapter_count: int) -> FormatDetail:
    return FormatDetail(
        id="fmt-1",
        title="Formato",
        university="unac",
        category="maestria",
        documentType="tesis",
        version=version,
        fields=[],
        assets=[],
        definition={"cuerpo": [{"titulo": f"Capitulo {index}"} for index in range(chapter_count)]},
    )


def _client(*, catalog_version: str = "catalog-v1", detail: FormatDetail | None = None):
    client = type("FakeGicaTesisClient", (), {})()
    client.get_catalog_version = AsyncMock(
        return_value=CatalogVersionResponse(version=catalog_version, generatedAt="2026-04-25T00:00:00Z")
    )
    client.list_formats = AsyncMock(return_value=(200, [_summary(detail.version if detail else "format-v1")], None))
    client.get_format_detail = AsyncMock(return_value=detail)
    return client


@pytest.mark.asyncio
async def test_get_format_detail_uses_cache_when_detail_version_matches_catalog(tmp_path) -> None:
    service, cache = _service_with_cache(tmp_path)
    cache.set_catalog("catalog-v1", None, [_summary("format-v1")])
    cache.set_detail("fmt-1", _detail("format-v1", chapter_count=6))
    service.client = _client(detail=_detail("format-v2", chapter_count=8))

    detail = await service.get_format_detail("fmt-1")

    assert detail is not None
    assert detail.version == "format-v1"
    assert len(detail.definition["cuerpo"]) == 6
    service.client.get_format_detail.assert_not_called()


@pytest.mark.asyncio
async def test_get_format_detail_refreshes_when_detail_version_lags_catalog(tmp_path) -> None:
    service, cache = _service_with_cache(tmp_path)
    cache.set_catalog("catalog-v1", None, [_summary("format-v2")])
    cache.set_detail("fmt-1", _detail("format-v1", chapter_count=6))
    service.client = _client(detail=_detail("format-v2", chapter_count=8))

    detail = await service.get_format_detail("fmt-1")

    assert detail is not None
    assert detail.version == "format-v2"
    assert len(detail.definition["cuerpo"]) == 8
    service.client.get_format_detail.assert_awaited_once_with("fmt-1")


@pytest.mark.asyncio
async def test_get_format_detail_falls_back_to_stale_cache_when_refresh_fails(tmp_path) -> None:
    service, cache = _service_with_cache(tmp_path)
    cache.set_catalog("catalog-v1", None, [_summary("format-v2")])
    cache.set_detail("fmt-1", _detail("format-v1", chapter_count=6))
    client = _client(detail=_detail("format-v2", chapter_count=8))
    client.get_format_detail.side_effect = UpstreamUnavailable("down")
    service.client = client

    detail = await service.get_format_detail("fmt-1")

    assert detail is not None
    assert detail.version == "format-v1"
    assert len(detail.definition["cuerpo"]) == 6
