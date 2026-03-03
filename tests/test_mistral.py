"""Tests для aipilot_llm.mistral_provider."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from aipilot_llm.mistral_provider import MistralProvider
from aipilot_llm.base import ProviderOverloaded, ProviderUnavailable
from tests.helpers import make_httpx_response, make_mistral_chat_response


@pytest.fixture()
def provider(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    return MistralProvider()


# ──────────────────────────────────────────────────────────────────────────────

async def test_chat_returns_correct_format(provider):
    """chat() возвращает все обязательные поля с provider=mistral."""
    body = make_mistral_chat_response(text="Bonjour!", prompt_tokens=8, completion_tokens=3)
    mock_resp = make_httpx_response(200, body)

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        result = await provider.chat("system", "hello", "default")

    assert result["text"] == "Bonjour!"
    assert result["provider"] == "mistral"
    assert result["tokens_input"] == 8
    assert result["tokens_output"] == 3
    assert isinstance(result["cost_eur"], float)
    assert isinstance(result["latency_ms"], int)


def test_system_message_injected_first(provider):
    """Mistral: system prompt → первое сообщение {role: system}."""
    messages = provider._build_messages(
        system_prompt="You are helpful.",
        user_message="Hi",
        history=None,
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are helpful."
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Hi"


def test_system_message_with_history(provider):
    """History вставляется ПОСЛЕ system и ПЕРЕД user message."""
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    messages = provider._build_messages("System", "New message", history)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"   # history первый
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"   # новое
    assert messages[3]["content"] == "New message"


async def test_429_raises_ProviderOverloaded(provider):
    """HTTP 429 (rate limit) → ProviderOverloaded."""
    mock_resp = make_httpx_response(429, {"error": "rate limited"})

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        with pytest.raises(ProviderOverloaded) as exc_info:
            await provider.chat("sys", "msg", "default")

    assert exc_info.value.provider_name == "mistral"


async def test_5xx_raises_ProviderUnavailable(provider):
    """HTTP 503 → ProviderUnavailable."""
    mock_resp = make_httpx_response(503, {"error": "service unavailable"})

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        with pytest.raises(ProviderUnavailable) as exc_info:
            await provider.chat("sys", "msg", "default")

    assert exc_info.value.provider_name == "mistral"


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


async def test_tool_format_conversion_anthropic_to_openai(provider):
    """Anthropic tool format → OpenAI/Mistral format конвертация."""
    # Anthropic формат
    anthropic_tools = [{
        "name": "search_kb",
        "description": "Search knowledge base",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }]

    # Мок для проверки что payload содержит конвертированные тулзы
    captured_payload = {}

    async def capture_post(url, json=None, **kwargs):
        captured_payload.update(json or {})
        return make_httpx_response(200, {
            "choices": [{"message": {"content": "ok", "tool_calls": []}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10},
        })

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = capture_post
        mock_getter.return_value = mock_client

        await provider.chat_with_tools("sys", "q", anthropic_tools, "default")

    tools_sent = captured_payload.get("tools", [])
    assert len(tools_sent) == 1
    assert tools_sent[0]["type"] == "function"
    assert tools_sent[0]["function"]["name"] == "search_kb"
    # input_schema → parameters
    assert "parameters" in tools_sent[0]["function"]


async def test_tool_calls_parsed_from_response(provider):
    """tool_calls из Mistral ответа правильно парсятся."""
    body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "tc_123",
                    "type": "function",
                    "function": {
                        "name": "get_vat_rate",
                        "arguments": '{"country": "BY", "category": "food"}',
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 20, "completion_tokens": 30},
    }
    mock_resp = make_httpx_response(200, body)

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        result = await provider.chat_with_tools(
            "sys", "что такое НДС?", [], "default"
        )

    assert len(result["tool_calls"]) == 1
    tc = result["tool_calls"][0]
    assert tc["name"] == "get_vat_rate"
    assert tc["id"] == "tc_123"
    assert tc["input"]["country"] == "BY"


def test_model_resolution_aliases(provider):
    """Model алиасы корректно маппятся."""
    assert provider._resolve_model("fast") == "mistral-small-latest"
    assert provider._resolve_model("default") == "mistral-large-latest"
    assert provider._resolve_model("strong") == "mistral-large-latest"
    assert provider._resolve_model("claude-haiku") == "mistral-small-latest"
    assert provider._resolve_model("claude-sonnet") == "mistral-large-latest"
