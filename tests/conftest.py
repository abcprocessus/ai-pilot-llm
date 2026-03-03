"""pytest fixtures для aipilot-llm тестов.

Xелперы (make_anthropic_response, force_circuit_open и т.д.) — в tests/helpers.py.
Все тесты — async (asyncio_mode="auto" в pyproject.toml).
"""
import pytest
from unittest.mock import AsyncMock
import aipilot_llm.router as _router_module


# ──────────────────────────────────────────────────────────────────────────────
# Основной fixture: сброс глобального state роутера между тестами
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_router_state():
    """Очищать _providers и _circuits перед каждым тестом.

    autouse=True — применяется ко ВСЕМ тестам автоматически.
    Без этого circuit state из одного теста будет «протекать» в следующий.
    """
    _router_module._providers.clear()
    _router_module._circuits.clear()
    yield
    _router_module._providers.clear()
    _router_module._circuits.clear()


# ──────────────────────────────────────────────────────────────────────────────
# ENV фикстуры — API ключи
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def set_anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")


@pytest.fixture()
def set_mistral_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")


@pytest.fixture()
def set_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")


@pytest.fixture()
def set_local_url(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_URL", "http://localhost:8000")


@pytest.fixture()
def all_providers_available(monkeypatch):
    """Все 4 провайдера доступны (все ключи проставлены)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("LOCAL_LLM_URL", "http://localhost:8000")



