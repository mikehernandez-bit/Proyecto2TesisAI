"""Tests for app.core.services.ai.gemini_client (with mocked SDK)."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.services.ai.errors import ProviderAuthError, QuotaExceededError
from app.core.services.ai.gemini_client import GeminiClient


class TestIsConfigured:
    def test_configured_when_key_set(self):
        with patch("app.core.services.ai.gemini_client.settings") as s:
            s.GEMINI_API_KEY = "test-key-abc"
            client = GeminiClient()
            assert client.is_configured() is True

    def test_not_configured_when_key_empty(self):
        with patch("app.core.services.ai.gemini_client.settings") as s:
            s.GEMINI_API_KEY = ""
            client = GeminiClient()
            assert client.is_configured() is False

    def test_not_configured_when_key_none(self):
        with patch("app.core.services.ai.gemini_client.settings") as s:
            s.GEMINI_API_KEY = None
            client = GeminiClient()
            assert client.is_configured() is False


class TestGenerate:
    def _make_client_with_mock_model(self):
        """Helper: return (client, mock_model) with settings patched."""
        client = GeminiClient()
        mock_model = MagicMock()
        client._model = mock_model  # skip lazy init
        return client, mock_model

    @patch("app.core.services.ai.gemini_client.settings")
    def test_success_first_try(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_RETRY_MAX = 3
        mock_settings.GEMINI_RETRY_BACKOFF = 0.01  # fast for tests

        client, mock_model = self._make_client_with_mock_model()
        mock_response = MagicMock()
        mock_response.text = "Generated content here."
        mock_model.generate_content.return_value = mock_response

        result = client.generate("Test prompt")
        assert result == "Generated content here."
        mock_model.generate_content.assert_called_once()

    @patch("app.core.services.ai.gemini_client.time.sleep")
    @patch("app.core.services.ai.gemini_client.settings")
    def test_retries_on_error_then_succeeds(self, mock_settings, mock_sleep):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_RETRY_MAX = 3
        mock_settings.GEMINI_RETRY_BACKOFF = 2.0

        client, mock_model = self._make_client_with_mock_model()

        # Fail twice, succeed third time
        mock_response = MagicMock()
        mock_response.text = "Success on retry."
        mock_model.generate_content.side_effect = [
            RuntimeError("API Error 1"),
            RuntimeError("API Error 2"),
            mock_response,
        ]

        result = client.generate("Retry prompt")
        assert result == "Success on retry."
        assert mock_model.generate_content.call_count == 3
        # Verify backoff was called
        assert mock_sleep.call_count == 2

    @patch("app.core.services.ai.gemini_client.time.sleep")
    @patch("app.core.services.ai.gemini_client.settings")
    def test_exhausts_retries_raises_error(self, mock_settings, mock_sleep):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_RETRY_MAX = 3
        mock_settings.GEMINI_RETRY_BACKOFF = 0.01

        client, mock_model = self._make_client_with_mock_model()
        mock_model.generate_content.side_effect = RuntimeError("Persistent error")

        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            client.generate("Failing prompt")

        assert mock_model.generate_content.call_count == 3

    @patch("app.core.services.ai.gemini_client.settings")
    def test_quota_error_raises_custom_exception(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_RETRY_MAX = 3
        mock_settings.GEMINI_RETRY_BACKOFF = 0.01

        client, mock_model = self._make_client_with_mock_model()
        mock_model.generate_content.side_effect = RuntimeError(
            "429 You exceeded your current quota. Please retry in 41.2s."
        )

        with pytest.raises(QuotaExceededError) as exc_info:
            client.generate("Quota prompt")

        exc = exc_info.value
        assert exc.status_code == 429
        assert exc.provider == "gemini"
        assert exc.error_type == "exhausted"
        assert exc.retry_after is None
        # Quota errors should fail-fast and avoid noisy retries.
        assert mock_model.generate_content.call_count == 1

    @patch("app.core.services.ai.gemini_client.settings")
    def test_rate_limited_error_sets_retry_after(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_RETRY_MAX = 2
        mock_settings.GEMINI_RETRY_BACKOFF = 0.01

        client, mock_model = self._make_client_with_mock_model()
        mock_model.generate_content.side_effect = RuntimeError("429 rate limit. Please retry in 8s.")

        with pytest.raises(QuotaExceededError) as exc_info:
            client.generate("Rate prompt")

        exc = exc_info.value
        assert exc.provider == "gemini"
        assert exc.error_type == "rate_limited"
        assert exc.retry_after == pytest.approx(8.0, rel=1e-3)

    @patch("app.core.services.ai.gemini_client.settings")
    def test_auth_error_raises_provider_auth_error(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_RETRY_MAX = 2
        mock_settings.GEMINI_RETRY_BACKOFF = 0.01

        client, mock_model = self._make_client_with_mock_model()
        mock_model.generate_content.side_effect = RuntimeError("403 Permission denied")

        with pytest.raises(ProviderAuthError):
            client.generate("Auth prompt")

    @patch("app.core.services.ai.gemini_client.time.sleep")
    @patch("app.core.services.ai.gemini_client.settings")
    def test_retries_on_empty_content(self, mock_settings, mock_sleep):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_RETRY_MAX = 2
        mock_settings.GEMINI_RETRY_BACKOFF = 0.01

        client, mock_model = self._make_client_with_mock_model()

        empty_response = MagicMock()
        empty_response.text = ""
        ok_response = MagicMock()
        ok_response.text = "Content."

        mock_model.generate_content.side_effect = [empty_response, ok_response]

        result = client.generate("Empty then OK")
        assert result == "Content."
        assert mock_model.generate_content.call_count == 2

    @patch("app.core.services.ai.gemini_client.settings")
    def test_raises_when_not_configured(self, mock_settings):
        mock_settings.GEMINI_API_KEY = ""
        client = GeminiClient()

        with pytest.raises(RuntimeError, match="not configured"):
            client.generate("Should fail")


class TestGetModel:
    @patch("app.core.services.ai.gemini_client.settings")
    def test_lazy_initialization(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_TEMPERATURE = 0.7
        mock_settings.GEMINI_TOP_P = 0.95
        mock_settings.GEMINI_MAX_OUTPUT_TOKENS = 8192

        client = GeminiClient()
        assert client._model is None  # not initialized yet

        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = MagicMock()

        with patch.dict("sys.modules", {"google.generativeai": mock_genai}):
            model = client._get_model()

        assert model is not None
        mock_genai.configure.assert_called_once_with(api_key="test-key")
        mock_genai.GenerativeModel.assert_called_once()

    @patch("app.core.services.ai.gemini_client.settings")
    def test_reuses_model_on_second_call(self, mock_settings):
        client = GeminiClient()
        mock_model = MagicMock()
        client._model = mock_model

        result = client._get_model()
        assert result is mock_model  # same object, no re-init


class TestProbe:
    @patch("app.core.services.ai.gemini_client.settings")
    def test_probe_unverified_when_not_configured(self, mock_settings):
        mock_settings.GEMINI_API_KEY = ""
        client = GeminiClient()
        result = client.probe()
        assert result["status"] == "UNVERIFIED"

    @patch("app.core.services.ai.gemini_client.settings")
    def test_probe_ok(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_TEMPERATURE = 0.7
        mock_settings.GEMINI_TOP_P = 0.95
        mock_settings.GEMINI_MAX_OUTPUT_TOKENS = 8192

        client = GeminiClient()
        model = MagicMock()
        response = MagicMock()
        response.text = "pong"
        model.generate_content.return_value = response
        client._model = model

        result = client.probe()
        assert result["status"] == "OK"

    @patch("app.core.services.ai.gemini_client.settings")
    def test_probe_rate_limited(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "key"
        mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
        mock_settings.GEMINI_TEMPERATURE = 0.7
        mock_settings.GEMINI_TOP_P = 0.95
        mock_settings.GEMINI_MAX_OUTPUT_TOKENS = 8192

        client = GeminiClient()
        model = MagicMock()
        model.generate_content.side_effect = RuntimeError("429 rate-limited. retry in 12s")
        client._model = model

        result = client.probe()
        assert result["status"] == "RATE_LIMITED"
        assert result["retry_after_s"] == 12
