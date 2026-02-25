"""Tests for app.core.services.ai.mistral_client (mocked HTTP client)."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.services.ai.errors import ProviderAuthError, QuotaExceededError
from app.core.services.ai.mistral_client import MistralClient


class TestMistralClient:
    @patch("app.core.services.ai.mistral_client.settings")
    def test_is_configured(self, mock_settings):
        mock_settings.MISTRAL_API_KEY = "mistral-key"
        assert MistralClient().is_configured() is True

    @patch("app.core.services.ai.mistral_client.settings")
    def test_generate_success(self, mock_settings):
        mock_settings.MISTRAL_API_KEY = "mistral-key"
        mock_settings.MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
        mock_settings.MISTRAL_MODEL = "mistral-medium-2505"
        mock_settings.MISTRAL_TEMPERATURE = 0.7
        mock_settings.MISTRAL_MAX_TOKENS = 2048
        mock_settings.MISTRAL_RETRY_MAX = 2
        mock_settings.MISTRAL_RETRY_BACKOFF = 0.01

        response = MagicMock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Texto generado por Mistral.",
                    }
                }
            ]
        }

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = MistralClient()
        client._session = mock_session

        result = client.generate("Prompt de prueba")

        assert result == "Texto generado por Mistral."

    @patch("app.core.services.ai.mistral_client.settings")
    def test_generate_429_raises_quota_error(self, mock_settings):
        mock_settings.MISTRAL_API_KEY = "mistral-key"
        mock_settings.MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
        mock_settings.MISTRAL_MODEL = "mistral-medium-2505"
        mock_settings.MISTRAL_TEMPERATURE = 0.7
        mock_settings.MISTRAL_MAX_TOKENS = 2048
        mock_settings.MISTRAL_RETRY_MAX = 1
        mock_settings.MISTRAL_RETRY_BACKOFF = 0.01

        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "12"}
        response.json.return_value = {"message": "Rate limit exceeded"}

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = MistralClient()
        client._session = mock_session

        with pytest.raises(QuotaExceededError) as exc_info:
            client.generate("Prompt de cuota")

        exc = exc_info.value
        assert exc.status_code == 429
        assert exc.provider == "mistral"
        assert exc.retry_after == pytest.approx(12.0, rel=1e-3)
        assert exc.error_type == "rate_limited"

    @patch("app.core.services.ai.mistral_client.settings")
    def test_generate_auth_error(self, mock_settings):
        mock_settings.MISTRAL_API_KEY = "mistral-key"
        mock_settings.MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
        mock_settings.MISTRAL_MODEL = "mistral-medium-2505"
        mock_settings.MISTRAL_TEMPERATURE = 0.7
        mock_settings.MISTRAL_MAX_TOKENS = 2048
        mock_settings.MISTRAL_RETRY_MAX = 1
        mock_settings.MISTRAL_RETRY_BACKOFF = 0.01

        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {"message": "Unauthorized"}

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = MistralClient()
        client._session = mock_session

        with pytest.raises(ProviderAuthError):
            client.generate("Prompt auth")

    @patch("app.core.services.ai.mistral_client.settings")
    def test_probe_exhausted(self, mock_settings):
        mock_settings.MISTRAL_API_KEY = "mistral-key"
        mock_settings.MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
        mock_settings.MISTRAL_MODEL = "mistral-medium-2505"

        response = MagicMock()
        response.status_code = 429
        response.headers = {}
        response.json.return_value = {"message": "Quota exceeded"}

        mock_session = MagicMock()
        mock_session.post.return_value = response

        client = MistralClient()
        client._session = mock_session
        result = client.probe()

        assert result["status"] == "EXHAUSTED"
