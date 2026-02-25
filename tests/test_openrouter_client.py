"""Tests for app.core.services.ai.openrouter_client (mocked HTTP client)."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.services.ai.errors import ProviderAuthError, ProviderTransientError, QuotaExceededError
from app.core.services.ai.openrouter_client import OpenRouterClient


class TestOpenRouterClient:
    @patch("app.core.services.ai.openrouter_client.settings")
    def test_is_configured(self, mock_settings):
        mock_settings.OPENROUTER_API_KEY = "or-key"
        assert OpenRouterClient().is_configured() is True

    @patch("app.core.services.ai.openrouter_client.settings")
    def test_generate_success(self, mock_settings):
        mock_settings.OPENROUTER_API_KEY = "or-key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
        mock_settings.OPENROUTER_TIMEOUT_SECONDS = 30
        mock_settings.OPENROUTER_HTTP_REFERER = "http://localhost"
        mock_settings.OPENROUTER_APP_TITLE = "GicaGen"

        response = MagicMock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Texto generado por OpenRouter.",
                    }
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = OpenRouterClient()
        client._session = mock_session

        result = client.generate("Prompt de prueba")
        assert result == "Texto generado por OpenRouter."

    @patch("app.core.services.ai.openrouter_client.settings")
    def test_generate_auth_error(self, mock_settings):
        mock_settings.OPENROUTER_API_KEY = "or-key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
        mock_settings.OPENROUTER_TIMEOUT_SECONDS = 30
        mock_settings.OPENROUTER_HTTP_REFERER = ""
        mock_settings.OPENROUTER_APP_TITLE = ""

        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {"error": {"message": "Unauthorized"}}

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = OpenRouterClient()
        client._session = mock_session

        with pytest.raises(ProviderAuthError):
            client.generate("Prompt auth")

    @patch("app.core.services.ai.openrouter_client.settings")
    def test_generate_credits_exhausted(self, mock_settings):
        mock_settings.OPENROUTER_API_KEY = "or-key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
        mock_settings.OPENROUTER_TIMEOUT_SECONDS = 30
        mock_settings.OPENROUTER_HTTP_REFERER = ""
        mock_settings.OPENROUTER_APP_TITLE = ""

        response = MagicMock()
        response.status_code = 402
        response.json.return_value = {"error": {"message": "Payment required"}}

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = OpenRouterClient()
        client._session = mock_session

        with pytest.raises(QuotaExceededError) as exc_info:
            client.generate("Prompt sin creditos")

        exc = exc_info.value
        assert exc.provider == "openrouter"
        assert exc.status_code == 402
        assert exc.error_type == "exhausted"

    @patch("app.core.services.ai.openrouter_client.settings")
    def test_generate_rate_limited_with_retry_after(self, mock_settings):
        mock_settings.OPENROUTER_API_KEY = "or-key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
        mock_settings.OPENROUTER_TIMEOUT_SECONDS = 30
        mock_settings.OPENROUTER_HTTP_REFERER = ""
        mock_settings.OPENROUTER_APP_TITLE = ""

        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "9"}
        response.json.return_value = {"error": {"message": "Rate limit exceeded"}}

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = OpenRouterClient()
        client._session = mock_session

        with pytest.raises(QuotaExceededError) as exc_info:
            client.generate("Prompt rate")

        exc = exc_info.value
        assert exc.provider == "openrouter"
        assert exc.error_type == "rate_limited"
        assert exc.retry_after == pytest.approx(9.0, rel=1e-3)

    @patch("app.core.services.ai.openrouter_client.settings")
    def test_generate_5xx_is_transient(self, mock_settings):
        mock_settings.OPENROUTER_API_KEY = "or-key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
        mock_settings.OPENROUTER_TIMEOUT_SECONDS = 30
        mock_settings.OPENROUTER_HTTP_REFERER = ""
        mock_settings.OPENROUTER_APP_TITLE = ""

        response = MagicMock()
        response.status_code = 503
        response.json.return_value = {"error": {"message": "Service unavailable"}}

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = OpenRouterClient()
        client._session = mock_session

        with pytest.raises(ProviderTransientError):
            client.generate("Prompt 5xx")

    @patch("app.core.services.ai.openrouter_client.settings")
    def test_probe_status_ok(self, mock_settings):
        mock_settings.OPENROUTER_API_KEY = "or-key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
        mock_settings.OPENROUTER_TIMEOUT_SECONDS = 30
        mock_settings.OPENROUTER_HTTP_REFERER = ""
        mock_settings.OPENROUTER_APP_TITLE = ""

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "data": {
                "limit_requests": 60,
                "remaining_requests": 55,
                "credits_remaining": 1.2,
            }
        }

        mock_session = MagicMock()
        mock_session.get.return_value = response

        client = OpenRouterClient()
        client._session = mock_session

        result = client.probe()
        assert result["status"] == "OK"
        assert isinstance(result.get("meta"), dict)
        assert result["meta"]["remaining_requests"] == 55
