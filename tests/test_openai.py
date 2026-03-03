"""Tests для aipilot_llm.openai_provider."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from aipilot_llm.openai_provider import OpenAIProvider
from aipilot_llm.base import ProviderOverloaded, ProviderUnavailable
from tests.helpers import make_httpx_response, make_openai_chat_response


@pytest.fixture()
def provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")
    return OpenAIProvider()


# ──────────────────────────────────────────────────────────────────────────────

async def test_chat_returns_correct_format(provider):
    """chat() возвращает все обязательные поля с provider=openai."""
    body = make_openai_chat_response(text="Hello from GPT!", prompt_tokens=10, completion_tokens=5)
    mock_resp = make_httpx_response(200, body)

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        result = await provider.chat("system", "hello", "default")

    assert result["text"] == "Hello from GPT!"
    assert result["provider"] == "openai"
    assert result["tokens_input"] == 10
    assert result["tokens_output"] == 5
    assert isinstance(result["cost_eur"], float)
    assert isinstance(result["latency_ms"], int)


async def test_429_raises_ProviderOverloaded(provider):
    """HTTP 429 (rate limit) → ProviderOverloaded."""
    mock_resp = make_httpx_response(429, {"error": "rate limited"})

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        with pytest.raises(ProviderOverloaded) as exc_info:
            await provider.chat("sys", "msg", "default")

    assert exc_info.value.provider_name == "openai"


async def test_5xx_raises_ProviderUnavailable(provider):
    """HTTP 503 → ProviderUnavailable."""
    mock_resp = make_httpx_response(503, {"error": "service unavailable"})

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        with pytest.raises(ProviderUnavailable) as exc_info:
            await provider.chat("sys", "msg", "default")

    assert exc_info.value.provider_name == "openai"


async def test_timeout_raises_ProviderUnavailable(provider):
    """httpx.TimeoutException → ProviderUnavailable."""
    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("timeout", request=MagicMock())
        )
        mock_getter.return_value = mock_client

        with pytest.raises(ProviderUnavailable):
            await provider.chat("sys", "msg", "default")


def test_model_resolution(provider):
    """Model алиасы корректно маппятся."""
    assert provider._resolve_model("fast") == "gpt-4o-mini"
    assert provider._resolve_model("default") == "gpt-4o"
    assert provider._resolve_model("strong") == "o3"
    assert provider._resolve_model("claude-haiku") == "gpt-4o-mini"
    assert provider._resolve_model("claude-sonnet") == "gpt-4o"
    assert provider._resolve_model("claude-opus") == "o3"


def test_system_message_injected_first(provider):
    """OpenAI: system prompt → первое сообщение {role: system}."""
    messages = provider._build_messages("You are helpful.", "Hi", None)
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"


def test_cost_calculation(provider):
    """cost_eur правильно считается для gpt-4o."""
    # gpt-4o: input=0.0022/1K, output=0.0088/1K
    cost = provider._calc_cost("gpt-4o", 1000, 1000)
    expected = 0.0022 + 0.0088
    assert abs(cost - expected) < 0.0001


def test_supports_tools_true(provider):
    assert provider.supports_tools() is True


def test_max_context_window(provider):
    assert provider.max_context_window() == 128_000


async def test_close_clears_client(provider, monkeypatch):
    """close() закрывает и обнуляет httpx клиент."""
    mock_client = AsyncMock()
    mock_client.is_closed = False
    provider._client = mock_client

    await provider.close()

    mock_client.aclose.assert_called_once()
    assert provider._client is None
