"""aipilot_llm — Multi-LLM абстракция AI PILOT.

Публичный API пакета:

    from aipilot_llm import get_provider, cleanup_providers
    from aipilot_llm.base import LLMProvider, ProviderOverloaded, ProviderUnavailable

Пример использования:
    from aipilot_llm import get_provider
    provider = get_provider(client_country="RU")
    result = await provider.chat(
        system_prompt=system,
        user_message=message,
        model="claude-sonnet",
    )
    # result["provider"] == "mistral" (для RU клиентов)
    # result["cost_eur"] — стоимость запроса
    # result["latency_ms"] — задержка в мс

Провайдеры:
    anthropic — Claude Haiku/Sonnet/Opus (основной)
    mistral   — Mistral Small/Large (RU/BY клиенты, fallback)
    openai    — GPT-4o/o3 (stub)
    local     — AI PILOT LLM self-hosted (stub)
"""
from .router import (
    get_provider, cleanup_providers, record_success, record_failure,
    classify_complexity,
)
from .base import LLMProvider, ProviderOverloaded, ProviderUnavailable
from .health import router as health_router

__version__ = "0.3.0"

__all__ = [
    "get_provider",
    "cleanup_providers",
    "record_success",
    "record_failure",
    "classify_complexity",
    "LLMProvider",
    "ProviderOverloaded",
    "ProviderUnavailable",
    "health_router",
]
