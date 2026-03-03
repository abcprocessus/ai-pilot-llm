"""Tests для aipilot_llm.anthropic_provider."""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic import APIStatusError, APIConnectionError

from aipilot_llm.anthropic_provider import AnthropicProvider
from aipilot_llm.base import ProviderOverloaded, ProviderUnavailable
from tests.helpers import make_anthropic_response, make_anthropic_tool_response


@pytest.fixture()
def provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    return AnthropicProvider()


# ──────────────────────────────────────────────────────────────────────────────

async def test_chat_returns_correct_format(provider):
    """chat() возвращает все обязательные поля."""
    mock_resp = make_anthropic_response(text="Hello!", input_tokens=10, output_tokens=5)

    with patch.object(provider, "_get_client") as mock_client_getter:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_resp)
        mock_client_getter.return_value = mock_client

        result = await provider.chat(
            system_prompt="You are helpful.",
            user_message="Hi",
            model="claude-sonnet",
        )

    required_fields = {"text", "tokens_input", "tokens_output", "model",
                       "stop_reason", "provider", "cost_eur", "latency_ms"}
    assert required_fields.issubset(result.keys()), (
        f"Missing fields: {required_fields - result.keys()}"
    )
    assert result["text"] == "Hello!"
    assert result["tokens_input"] == 10
    assert result["tokens_output"] == 5
    assert result["provider"] == "anthropic"
    assert isinstance(result["cost_eur"], float)
    assert isinstance(result["latency_ms"], int)


async def test_chat_stream_yields_delta_and_done(provider):
    """chat_stream() yields delta chunks + done event + [DONE]."""
    # Мокируем AsyncAnthropic.messages.stream context manager
    async def fake_text_stream():
        for chunk in ["Hello", ", ", "world"]:
            yield chunk

    mock_final = make_anthropic_response("Hello, world", input_tokens=12, output_tokens=3)

    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.text_stream = fake_text_stream()
    mock_stream.get_final_message = AsyncMock(return_value=mock_final)

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream
        mock_getter.return_value = mock_client

        events = []
        async for event in provider.chat_stream(
            system_prompt="System",
            user_message="Hi",
            model="claude-sonnet",
        ):
            events.append(event)

    # Должны быть delta события, done событие и [DONE]
    delta_events = [e for e in events if '"type": "delta"' in e]
    done_events = [e for e in events if '"type": "done"' in e]
    final_events = [e for e in events if "[DONE]" in e]

    assert len(delta_events) == 3, f"Expected 3 delta events, got {len(delta_events)}"
    assert len(done_events) == 1, "Expected 1 done event"
    assert len(final_events) == 1, "Expected [DONE] marker"


async def test_classify_returns_category(provider):
    """classify() возвращает одну из переданных категорий."""
    mock_resp = make_anthropic_response(text="бухгалтерия")

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        result = await provider.classify(
            text="Помогите с балансом",
            categories=["бухгалтерия", "юридика", "продажи"],
        )

    assert result == "бухгалтерия"


async def test_chat_with_tools_parses_tool_use(provider):
    """chat_with_tools() правильно парсит tool_use блоки."""
    mock_resp = make_anthropic_tool_response(
        tool_name="search_kb",
        tool_input={"query": "НДС по УСН"},
        tool_id="toolu_abc123",
    )

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        tools = [{
            "name": "search_kb",
            "description": "Search knowledge base",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        }]
        result = await provider.chat_with_tools(
            system_prompt="You are helpful",
            user_message="НДС?",
            tools=tools,
            model="claude-sonnet",
        )

    assert "tool_calls" in result
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "search_kb"
    assert result["tool_calls"][0]["input"]["query"] == "НДС по УСН"
    assert result["tool_calls"][0]["id"] == "toolu_abc123"
    assert result["provider"] == "anthropic"


async def test_529_raises_ProviderOverloaded(provider):
    """HTTP 529 → ProviderOverloaded (НЕ ProviderUnavailable)."""
    import httpx as _httpx

    # APIStatusError требует реальный httpx.Response в конструкторе
    httpx_response = _httpx.Response(
        status_code=529,
        request=_httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    real_error = APIStatusError(
        message="Overloaded",
        response=httpx_response,
        body={"type": "error", "error": {"type": "overloaded_error"}},
    )

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=real_error)
        mock_getter.return_value = mock_client

        with pytest.raises(ProviderOverloaded) as exc_info:
            await provider.chat("system", "message", "claude-sonnet")

    assert exc_info.value.provider_name == "anthropic"


async def test_connection_error_raises_ProviderUnavailable(provider):
    """APIConnectionError → ProviderUnavailable."""
    # Патчим сам класс APIConnectionError чтобы сделать его mock-friendly
    class FakeConnectionError(APIConnectionError):
        def __init__(self):
            super().__init__(request=MagicMock())

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=FakeConnectionError()
        )
        mock_getter.return_value = mock_client

        with pytest.raises(ProviderUnavailable) as exc_info:
            await provider.chat("system", "message", "claude-sonnet")

    assert exc_info.value.provider_name == "anthropic"


async def test_cost_eur_calculated_correctly(provider):
    """cost_eur корректно считается по формуле input+output."""
    # claude-sonnet-4-6: input=0.00277/1K, output=0.01384/1K
    mock_resp = make_anthropic_response(
        text="ok", input_tokens=1000, output_tokens=1000
    )

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        result = await provider.chat("sys", "msg", model="claude-sonnet-4-6")

    # 1000 input × 0.00277 + 1000 output × 0.01384 = 0.00277 + 0.01384 = 0.01661
    expected = 0.00277 + 0.01384
    assert abs(result["cost_eur"] - expected) < 0.0001, (
        f"Expected cost_eur ≈ {expected}, got {result['cost_eur']}"
    )


async def test_latency_ms_tracked(provider):
    """latency_ms должен быть > 0 и разумным (< 10 000ms в тесте)."""
    mock_resp = make_anthropic_response()

    with patch.object(provider, "_get_client") as mock_getter:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_resp)
        mock_getter.return_value = mock_client

        result = await provider.chat("sys", "msg", "claude-sonnet")

    assert result["latency_ms"] >= 0
    assert result["latency_ms"] < 10_000, "Latency shouldn't exceed 10s in test"


def test_model_resolution(provider):
    """Алиасы корректно резолвятся в реальные model ID."""
    assert provider._resolve_model("fast") == "claude-haiku-4-5-20251001"
    assert provider._resolve_model("default") == "claude-sonnet-4-6"
    assert provider._resolve_model("strong") == "claude-opus-4-6"
    assert provider._resolve_model("claude-sonnet") == "claude-sonnet-4-6"
    assert provider._resolve_model("claude-haiku") == "claude-haiku-4-5-20251001"
