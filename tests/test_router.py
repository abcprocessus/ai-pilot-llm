"""Tests для aipilot_llm.router — circuit breaker + provider selection."""
import time
from collections import deque
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

import aipilot_llm.router as router_module
from aipilot_llm.router import (
    get_provider,
    get_provider_for_overloaded,
    record_failure,
    record_success,
    cleanup_providers,
    _is_circuit_open,
    _get_circuit,
    FAILURE_THRESHOLD,
    FAILURE_WINDOW_SEC,
    RECOVERY_TIMEOUT_SEC,
)
from aipilot_llm.base import ProviderOverloaded
from tests.helpers import force_circuit_open, force_circuit_close


# ──────────────────────────────────────────────────────────────────────────────
# Circuit Breaker тесты
# ──────────────────────────────────────────────────────────────────────────────

def test_circuit_breaker_opens_after_5_failures_in_60s(monkeypatch):
    """После FAILURE_THRESHOLD фейлов за FAILURE_WINDOW_SEC → circuit open."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    now = time.monotonic()

    for i in range(FAILURE_THRESHOLD):
        assert not _is_circuit_open("anthropic"), f"Circuit opened early at failure {i}"
        record_failure("anthropic")

    assert _is_circuit_open("anthropic"), "Circuit should be OPEN after 5 failures"


def test_circuit_breaker_resets_after_recovery_period(monkeypatch):
    """После RECOVERY_TIMEOUT_SEC circuit переходит в HALF-OPEN."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    # Форсим open state с open_until в прошлом
    state = _get_circuit("anthropic")
    state["open_until"] = time.monotonic() - 1.0  # уже истёк

    # _is_circuit_open должна вернуть False (HALF-OPEN → CLOSED)
    assert not _is_circuit_open("anthropic"), "Expired circuit should reset to HALF-OPEN"
    assert state["open_until"] == 0.0, "open_until should be reset to 0"


def test_circuit_breaker_still_open_before_recovery(monkeypatch):
    """Circuit OPEN пока не истёк recovery timeout."""
    force_circuit_open("anthropic")
    assert _is_circuit_open("anthropic"), "Circuit should be OPEN"


def test_overloaded_529_does_not_count_as_failure(monkeypatch):
    """ProviderOverloaded (529) НЕ должен триггерить circuit breaker.

    record_failure() вызывается только при ProviderUnavailable (5xx/timeout).
    Тест проверяет что после 4 обычных фейлов + 1 "529" circuit ещё CLOSED.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    # 4 реальных фейла (threshold=5, ещё не открылся)
    for _ in range(FAILURE_THRESHOLD - 1):
        record_failure("anthropic")

    assert not _is_circuit_open("anthropic"), \
        "Circuit should still be CLOSED after 4 failures"

    # Имитируем 529: НЕ вызываем record_failure, только get_provider_for_overloaded
    # → circuit остаётся CLOSED
    assert not _is_circuit_open("anthropic"), \
        "Circuit should remain CLOSED after 529 (not counted as failure)"


def test_record_success_resets_failures(monkeypatch):
    """record_success() сбрасывает счётчик фейлов."""
    record_failure("anthropic")
    record_failure("anthropic")
    record_success("anthropic")

    state = _get_circuit("anthropic")
    assert len(state["failures"]) == 0, "Failures deque should be empty after success"
    assert state["open_until"] == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Provider selection тесты
# ──────────────────────────────────────────────────────────────────────────────

def test_router_selects_mistral_for_RU_country(monkeypatch):
    """RU клиенты → Mistral (санкционная защита)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral")

    with patch.object(router_module, "_get_or_create") as mock_create:
        mock_provider = MagicMock()
        mock_provider.supports_tools.return_value = True
        mock_create.return_value = mock_provider

        get_provider(client_country="RU")

        # Первый вызов должен быть для "mistral"
        first_call_name = mock_create.call_args_list[0][0][0]
        assert first_call_name == "mistral", (
            f"Expected 'mistral' for RU client, got '{first_call_name}'"
        )


def test_router_selects_mistral_for_BY_country(monkeypatch):
    """BY клиенты → Mistral (BY = санкционный список Anthropic)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral")

    with patch.object(router_module, "_get_or_create") as mock_create:
        mock_provider = MagicMock()
        mock_provider.supports_tools.return_value = True
        mock_create.return_value = mock_provider

        get_provider(client_country="BY")

        first_call_name = mock_create.call_args_list[0][0][0]
        assert first_call_name == "mistral", (
            f"Expected 'mistral' for BY client, got '{first_call_name}'"
        )


def test_router_selects_anthropic_for_DE_country(monkeypatch):
    """DE (Германия) → Claude (нет ограничений)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral")

    with patch.object(router_module, "_get_or_create") as mock_create:
        mock_provider = MagicMock()
        mock_provider.supports_tools.return_value = True
        mock_create.return_value = mock_provider

        get_provider(client_country="DE")

        first_call_name = mock_create.call_args_list[0][0][0]
        assert first_call_name == "anthropic", (
            f"Expected 'anthropic' for DE client, got '{first_call_name}'"
        )


def test_requires_tools_selects_provider_with_tool_support(monkeypatch):
    """requires_tools=True → провайдер с supports_tools() == True."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    mock_provider = MagicMock()
    mock_provider.supports_tools.return_value = True

    with patch.object(router_module, "_get_or_create", return_value=mock_provider):
        result = get_provider(requires_tools=True)
        assert result.supports_tools(), "Provider must support tools when requires_tools=True"


def test_preferred_provider_override(monkeypatch):
    """preferred='mistral' → Mistral (даже если country=DE)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral")

    with patch.object(router_module, "_get_or_create") as mock_create:
        mock_provider = MagicMock()
        mock_provider.supports_tools.return_value = True
        mock_create.return_value = mock_provider

        get_provider(client_country="DE", preferred="mistral")

        first_call_name = mock_create.call_args_list[0][0][0]
        assert first_call_name == "mistral", (
            f"Expected 'mistral' (preferred), got '{first_call_name}'"
        )


def test_env_override_LLM_PROVIDER(monkeypatch):
    """LLM_PROVIDER=mistral → всегда Mistral (env override)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral")
    monkeypatch.setenv("LLM_PROVIDER", "mistral")

    with patch.object(router_module, "_get_or_create") as mock_create:
        mock_provider = MagicMock()
        mock_provider.supports_tools.return_value = True
        mock_create.return_value = mock_provider

        get_provider(client_country="DE")  # DE — обычно Anthropic

        first_call_name = mock_create.call_args_list[0][0][0]
        assert first_call_name == "mistral", (
            f"LLM_PROVIDER=mistral should override country routing"
        )


async def test_cleanup_providers_calls_close_on_all(monkeypatch):
    """cleanup_providers() вызывает close() на всех инициализированных провайдерах."""
    mock_a = AsyncMock()
    mock_b = AsyncMock()
    router_module._providers["anthropic"] = mock_a
    router_module._providers["mistral"] = mock_b

    await cleanup_providers()

    mock_a.close.assert_called_once()
    mock_b.close.assert_called_once()
    assert len(router_module._providers) == 0, "_providers should be empty after cleanup"


def test_no_provider_raises_runtime_error(monkeypatch):
    """Если нет ни одного API ключа → RuntimeError."""
    # Убираем все ключи
    for key in ["ANTHROPIC_API_KEY", "MISTRAL_API_KEY", "OPENAI_API_KEY", "LOCAL_LLM_URL"]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="No LLM provider available"):
        get_provider()
