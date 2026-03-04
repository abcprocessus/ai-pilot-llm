"""Tests for hybrid routing (complexity classifier + provider selection)."""
import os
from unittest.mock import patch, MagicMock

import pytest

from aipilot_llm.router import classify_complexity, get_provider, _providers, _circuits


# ── classify_complexity tests ──────────────────────────────────────────────


def test_greeting_is_simple():
    assert classify_complexity("Привет!") == "simple"


def test_hello_is_simple():
    assert classify_complexity("Hello") == "simple"


def test_what_can_you_do_is_simple():
    assert classify_complexity("Что ты умеешь?") == "simple"


def test_help_is_simple():
    assert classify_complexity("/help") == "simple"


def test_short_question_is_simple():
    assert classify_complexity("Сколько стоит?") == "simple"


def test_contract_review_is_complex():
    assert classify_complexity("Проверь этот договор на риски") == "complex"


def test_legal_analysis_is_complex():
    assert classify_complexity("Составь документ NDA для клиента") == "complex"


def test_code_review_is_complex():
    assert classify_complexity("Ревью кода на Python, найди баги") == "complex"


def test_tax_review_is_complex():
    assert classify_complexity("Проверка налогов за квартал") == "complex"


def test_audit_is_complex():
    assert classify_complexity("Нужен аудит бухгалтерии") == "complex"


def test_scan_document_is_complex():
    assert classify_complexity("scan-document PDF invoice") == "complex"


def test_requires_tools_always_complex():
    assert classify_complexity("Привет", requires_tools=True) == "complex"


def test_opus_model_hint_is_complex():
    assert classify_complexity("Простой вопрос", model_hint="claude-opus") == "complex"


def test_long_context_is_complex():
    long_msg = "x " * 3000  # >5000 chars total
    assert classify_complexity(long_msg) == "complex"


def test_medium_length_is_medium():
    # 250 chars — not simple, not complex
    msg = "Расскажи подробно про систему налогообложения для ИП в Беларуси, " * 5
    result = classify_complexity(msg)
    assert result == "medium"


def test_complex_system_prompt_detected():
    result = classify_complexity(
        "Как мне быть?",
        system_prompt="Ты юрист. Анализируй договор и составь документ с рисками.",
    )
    assert result == "complex"


def test_medium_with_long_system():
    result = classify_complexity(
        "Проанализируй",
        system_prompt="Контекст: " + "слово " * 200,  # >1000 total
    )
    assert result == "medium"


# ── get_provider with HYBRID_ROUTING tests ─────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_providers():
    """Reset provider singletons between tests."""
    _providers.clear()
    _circuits.clear()
    yield
    _providers.clear()
    _circuits.clear()


@patch.dict(os.environ, {
    "ANTHROPIC_API_KEY": "test-key",
    "LOCAL_LLM_URL": "http://localhost:8000",
    "HYBRID_ROUTING": "true",
})
def test_hybrid_simple_goes_to_local():
    provider = get_provider(user_message="Привет!")
    assert provider.name == "local"


@patch.dict(os.environ, {
    "ANTHROPIC_API_KEY": "test-key",
    "MISTRAL_API_KEY": "test-key",
    "HYBRID_ROUTING": "true",
})
def test_hybrid_medium_goes_to_mistral():
    msg = "Расскажи про налоговую систему Беларуси подробно. " * 5
    provider = get_provider(user_message=msg)
    assert provider.name == "mistral"


@patch.dict(os.environ, {
    "ANTHROPIC_API_KEY": "test-key",
    "HYBRID_ROUTING": "true",
})
def test_hybrid_complex_goes_to_anthropic():
    provider = get_provider(user_message="Проверь этот договор NDA на риски")
    assert provider.name == "anthropic"


@patch.dict(os.environ, {
    "ANTHROPIC_API_KEY": "test-key",
    "HYBRID_ROUTING": "false",
})
def test_hybrid_disabled_goes_to_anthropic():
    # With hybrid off, simple messages still go to Claude
    provider = get_provider(user_message="Привет!")
    assert provider.name == "anthropic"


@patch.dict(os.environ, {
    "ANTHROPIC_API_KEY": "test-key",
    "HYBRID_ROUTING": "true",
})
def test_hybrid_preferred_overrides():
    # preferred= always wins, even with hybrid routing
    provider = get_provider(preferred="anthropic", user_message="Привет!")
    assert provider.name == "anthropic"


@patch.dict(os.environ, {
    "ANTHROPIC_API_KEY": "test-key",
    "HYBRID_ROUTING": "true",
})
def test_hybrid_local_unavailable_falls_through():
    # LOCAL_LLM_URL not set → simple can't go to local → falls to Claude
    provider = get_provider(user_message="Привет!")
    assert provider.name == "anthropic"
