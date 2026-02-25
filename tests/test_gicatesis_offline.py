"""Tests for GicaTesis offline handling — Policy A (explicit) and Policy B (strict)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.services.gicatesis_status import GicaTesisStatus, gicatesis_status
from app.integrations.gicatesis.errors import UpstreamUnavailable
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_gicatesis_status():
    """Reset module-level singleton before each test."""
    gicatesis_status.online = True
    gicatesis_status.last_success_at = None
    gicatesis_status.last_error = None
    gicatesis_status.data_source = "none"
    yield
    gicatesis_status.online = True
    gicatesis_status.last_success_at = None
    gicatesis_status.last_error = None
    gicatesis_status.data_source = "none"


# ---------------------------------------------------------------------------
# GicaTesisStatus unit tests
# ---------------------------------------------------------------------------


class TestGicaTesisStatusUnit:
    def test_record_success(self):
        st = GicaTesisStatus()
        st.record_success(source="live")
        assert st.online is True
        assert st.data_source == "live"
        assert st.last_error is None
        assert st.last_success_at is not None

    def test_record_failure(self):
        st = GicaTesisStatus()
        st.record_failure("connection refused", source="cache")
        assert st.online is False
        assert st.data_source == "cache"
        assert st.last_error == "connection refused"

    def test_to_dict(self):
        st = GicaTesisStatus()
        st.record_failure("timeout")
        d = st.to_dict()
        assert d["online"] is False
        assert d["last_error"] == "timeout"
        assert "data_source" in d
        assert "last_success_at" in d


# ---------------------------------------------------------------------------
# /api/formats — Policy A (offline explicit, default)
# ---------------------------------------------------------------------------


class TestFormatsEndpointPolicyA:
    """When GICAGEN_STRICT_GICATESIS is False (default), stale cache -> 200 + headers."""

    def test_formats_online_returns_headers(self, client):
        """When upstream is available, response includes X-Data-Source and X-Upstream-Online."""
        fake_result = {
            "formats": [{"id": "fmt-1", "title": "Test"}],
            "stale": False,
            "cachedAt": "2026-01-01T00:00:00",
            "source": "cache",
        }

        with patch(
            "app.modules.api.router.formats.list_formats",
            new_callable=AsyncMock,
            return_value=fake_result,
        ):
            gicatesis_status.record_success(source="live")
            r = client.get("/api/formats")

        assert r.status_code == 200
        assert r.headers.get("X-Data-Source") == "cache"
        assert r.headers.get("X-Upstream-Online") == "true"
        body = r.json()
        assert len(body["formats"]) == 1

    def test_formats_offline_cache_returns_200_with_offline_header(self, client):
        """When upstream is down but cache is available, 200 + X-Upstream-Online: false."""
        fake_result = {
            "formats": [{"id": "fmt-1", "title": "Cached"}],
            "stale": True,
            "cachedAt": "2026-01-01T00:00:00",
            "source": "cache",
        }

        with (
            patch(
                "app.modules.api.router.formats.list_formats",
                new_callable=AsyncMock,
                return_value=fake_result,
            ),
            patch(
                "app.modules.api.router.settings",
            ) as mock_settings,
        ):
            mock_settings.GICAGEN_STRICT_GICATESIS = False
            mock_settings.GICATESIS_BASE_URL = "http://localhost:8000/api/v1"
            gicatesis_status.record_failure("connection refused", source="cache")
            r = client.get("/api/formats")

        assert r.status_code == 200
        assert r.headers.get("X-Upstream-Online") == "false"
        assert r.headers.get("X-Data-Source") == "cache"

    def test_formats_no_cache_no_upstream_returns_503(self, client):
        """When upstream is down AND no cache, should raise 503."""
        with patch(
            "app.modules.api.router.formats.list_formats",
            new_callable=AsyncMock,
            side_effect=UpstreamUnavailable("connection refused"),
        ):
            r = client.get("/api/formats")

        assert r.status_code == 503


# ---------------------------------------------------------------------------
# /api/formats — Policy B (strict mode)
# ---------------------------------------------------------------------------


class TestFormatsEndpointPolicyB:
    """When GICAGEN_STRICT_GICATESIS is True, stale cache triggers 503."""

    def test_formats_stale_strict_returns_503(self, client):
        """Strict mode: stale data is rejected with 503."""
        fake_result = {
            "formats": [{"id": "fmt-1", "title": "Cached"}],
            "stale": True,
            "cachedAt": "2026-01-01T00:00:00",
            "source": "cache",
        }

        with (
            patch(
                "app.modules.api.router.formats.list_formats",
                new_callable=AsyncMock,
                return_value=fake_result,
            ),
            patch(
                "app.modules.api.router.settings",
            ) as mock_settings,
        ):
            mock_settings.GICAGEN_STRICT_GICATESIS = True
            mock_settings.GICATESIS_BASE_URL = "http://localhost:8000/api/v1"
            gicatesis_status.record_failure("connection refused", source="cache")
            r = client.get("/api/formats")

        assert r.status_code == 503
        body = r.json()
        assert "modo estricto" in body["detail"].lower()

    def test_formats_fresh_strict_returns_200(self, client):
        """Strict mode: fresh (non-stale) data returns 200 normally."""
        fake_result = {
            "formats": [{"id": "fmt-1", "title": "Live"}],
            "stale": False,
            "cachedAt": "2026-01-01T00:00:00",
            "source": "live",
        }

        with (
            patch(
                "app.modules.api.router.formats.list_formats",
                new_callable=AsyncMock,
                return_value=fake_result,
            ),
            patch(
                "app.modules.api.router.settings",
            ) as mock_settings,
        ):
            mock_settings.GICAGEN_STRICT_GICATESIS = True
            mock_settings.GICATESIS_BASE_URL = "http://localhost:8000/api/v1"
            gicatesis_status.record_success(source="live")
            r = client.get("/api/formats")

        assert r.status_code == 200


# ---------------------------------------------------------------------------
# /api/assets — 503 instead of 502
# ---------------------------------------------------------------------------


class TestAssetsEndpoint:
    def test_asset_offline_known_returns_503(self, client):
        """When gicatesis_status is offline, asset proxy returns 503 immediately."""
        gicatesis_status.record_failure("down")
        r = client.get("/api/assets/logos/test.png")
        assert r.status_code == 503
        body = r.json()
        assert "offline" in body["detail"].lower()

    def test_asset_connection_error_returns_503(self, client):
        """When upstream connection fails, return 503 (not 502)."""
        import httpx

        gicatesis_status.record_success()  # online, but network fails

        with patch(
            "app.modules.api.router.httpx.AsyncClient",
        ) as MockAsyncClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockAsyncClient.return_value = mock_ctx

            r = client.get("/api/assets/logos/test.png")

        assert r.status_code == 503
        assert "502" not in str(r.status_code)

    def test_asset_404_still_returns_404(self, client):
        """Asset not found should still be 404."""
        gicatesis_status.record_success()  # online

        mock_resp = AsyncMock()
        mock_resp.status_code = 404

        with patch(
            "app.modules.api.router.httpx.AsyncClient",
        ) as MockAsyncClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockAsyncClient.return_value = mock_ctx

            r = client.get("/api/assets/logos/test.png")

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/gicatesis/status endpoint
# ---------------------------------------------------------------------------


class TestGicaTesisStatusEndpoint:
    def test_status_online(self, client):
        gicatesis_status.record_success(source="live")
        r = client.get("/api/gicatesis/status")
        assert r.status_code == 200
        body = r.json()
        assert body["online"] is True
        assert body["data_source"] == "live"

    def test_status_offline(self, client):
        gicatesis_status.record_failure("connection refused", source="cache")
        r = client.get("/api/gicatesis/status")
        assert r.status_code == 200
        body = r.json()
        assert body["online"] is False
        assert body["last_error"] == "connection refused"
        assert body["data_source"] == "cache"


# ---------------------------------------------------------------------------
# /api/providers/status includes gicatesis field
# ---------------------------------------------------------------------------


class TestProvidersStatusIncludesGicaTesis:
    def test_providers_status_has_gicatesis_key(self, client):
        gicatesis_status.record_failure("down", source="cache")
        r = client.get("/api/providers/status")
        assert r.status_code == 200
        body = r.json()
        assert "gicatesis" in body
        assert body["gicatesis"]["online"] is False
