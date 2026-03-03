"""LLM Router — выбор провайдера и circuit breaker.

Логика выбора провайдера (приоритет по порядку):
  1. preferred — явно указанный провайдер (если доступен)
  2. requires_tools=True → фильтруем провайдеры без supports_tools()
  3. client_country в ANTHROPIC_RESTRICTED → Mistral (санкционная защита)
  4. LLM_PROVIDER env var → глобальный override
  5. Claude (по умолчанию, если доступен и circuit не open)
  6. Fallback chain: Mistral → OpenAI → Local

Circuit Breaker (per provider):
  FAILURE_THRESHOLD = 5 фейлов за FAILURE_WINDOW_SEC = 60 сек
  После threshold → OPEN (провайдер выключен)
  Через RECOVERY_TIMEOUT_SEC = 30 сек → HALF-OPEN (пробный запрос)
  Успех → CLOSED | Фейл → OPEN снова

HTTP 529 Overloaded (Anthropic):
  НЕ считается failure в circuit breaker.
  Немедленный fallback только для ТЕКУЩЕГО запроса.
  Следующий запрос снова попробует Claude.

Этап 1 из 8: Multi-LLM абстракция.
"""
import logging
import os
import time
from collections import deque
from typing import Optional

from .base import LLMProvider, ProviderOverloaded

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Страны с ограничениями Anthropic
# Источник: https://www.anthropic.com/supported-countries (обновлено 2026-03)
# ──────────────────────────────────────────────
ANTHROPIC_RESTRICTED: frozenset[str] = frozenset({
    "RU", "BY", "CN", "IR", "KP", "CU", "SY", "VE",
    "MM", "SD", "SS", "ZW", "CF", "CD", "SO", "YE",
    "LB", "LY", "IQ", "AF",
})

# ──────────────────────────────────────────────
# Circuit Breaker параметры
# ──────────────────────────────────────────────
FAILURE_THRESHOLD: int = 5      # кол-во фейлов до открытия цепи
FAILURE_WINDOW_SEC: int = 60    # окно наблюдения в секундах
RECOVERY_TIMEOUT_SEC: int = 30  # время до half-open состояния

# ──────────────────────────────────────────────
# Синглтоны: провайдеры + circuit breaker состояние
# ──────────────────────────────────────────────
_providers: dict[str, LLMProvider] = {}

# circuit state per provider: {"anthropic": {"failures": deque, "open_until": float}}
_circuits: dict[str, dict] = {}


# ──────────────────────────────────────────────
# Публичный API
# ──────────────────────────────────────────────

def get_provider(
    client_country: str | None = None,
    agent_type: str | None = None,
    preferred: str | None = None,
    requires_tools: bool = False,
) -> LLMProvider:
    """Выбрать LLM провайдер на основе контекста.

    Args:
        client_country:  ISO код страны клиента (из GeoIP middleware)
        agent_type:      Тип агента (lisa, marina, boss, ...) — зарезервировано
        preferred:       Форсировать конкретный провайдер (anthropic|mistral|openai|local)
        requires_tools:  True если агент использует Tool Calling (Boss Bot, Router)

    Returns:
        LLMProvider: Готовый к использованию singleton провайдера

    Raises:
        RuntimeError: Если ни один провайдер недоступен
    """
    available = _get_available()

    if not available:
        raise RuntimeError(
            "No LLM provider available! "
            "Check env vars: ANTHROPIC_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY"
        )

    # 1. Явный preferred (если доступен и circuit не open)
    if preferred and preferred in available and not _is_circuit_open(preferred):
        return _get_or_create(preferred)

    # 2. requires_tools → фильтруем провайдеры без tool support
    #    Boss Bot / Router ДОЛЖНЫ получить провайдера с tools
    #    При этом санкционная защита имеет МЕНЬШИЙ приоритет чем корректность
    if requires_tools:
        return _get_provider_with_tools(client_country, available)

    # 3. Restricted country → Mistral (санкционная защита)
    if client_country and client_country.upper() in ANTHROPIC_RESTRICTED:
        if "mistral" in available and not _is_circuit_open("mistral"):
            logger.info(
                f"Client from {client_country} → routing to Mistral "
                f"(Anthropic restriction)"
            )
            return _get_or_create("mistral")
        # Mistral недоступен → падаем дальше по chain
        logger.warning(
            f"Client from {client_country} but Mistral unavailable, "
            f"trying fallback chain"
        )

    # 4. Глобальный env override (LLM_PROVIDER=mistral)
    env_provider = os.getenv("LLM_PROVIDER", "").lower().strip()
    if env_provider and env_provider in available and not _is_circuit_open(env_provider):
        return _get_or_create(env_provider)

    # 5. Claude (основной провайдер)
    if "anthropic" in available and not _is_circuit_open("anthropic"):
        return _get_or_create("anthropic")

    # 6. Fallback chain
    for fallback in ["mistral", "openai", "local"]:
        if fallback in available and not _is_circuit_open(fallback):
            logger.warning(
                f"Anthropic circuit open or unavailable → falling back to '{fallback}'"
            )
            return _get_or_create(fallback)

    raise RuntimeError(
        "All LLM providers are unavailable or circuit-open. "
        "Check provider health and API keys."
    )


def get_provider_for_overloaded(primary_name: str) -> LLMProvider:
    """Получить fallback провайдер когда primary вернул 529 Overloaded.

    Используется ТОЛЬКО при ProviderOverloaded exception.
    НЕ изменяет circuit breaker state (529 ≠ failure).
    Следующий обычный запрос снова пойдёт через primary.

    Args:
        primary_name: Имя перегруженного провайдера ("anthropic")

    Returns:
        LLMProvider: Fallback провайдер

    Raises:
        RuntimeError: Если fallback не найден
    """
    available = _get_available()
    fallback_order = ["mistral", "openai", "anthropic", "local"]

    for name in fallback_order:
        if name != primary_name and name in available and not _is_circuit_open(name):
            logger.warning(
                f"Provider '{primary_name}' overloaded (529) → "
                f"one-time fallback to '{name}'"
            )
            return _get_or_create(name)

    raise RuntimeError(
        f"Provider '{primary_name}' is overloaded and no fallback available."
    )


def record_success(provider_name: str) -> None:
    """Записать успешный вызов — сдвигает circuit к CLOSED."""
    state = _get_circuit(provider_name)
    # Успех в half-open → полный сброс
    state["failures"] = deque()
    logger.debug(f"Circuit '{provider_name}': success recorded, circuit CLOSED")


def record_failure(provider_name: str) -> None:
    """Записать неуспешный вызов — может открыть circuit.

    Вызывать при ProviderUnavailable (timeout, 5xx, network error).
    НЕ вызывать при ProviderOverloaded (529).
    """
    now = time.monotonic()
    state = _get_circuit(provider_name)
    failures: deque = state["failures"]

    # Удаляем старые фейлы за пределами окна
    while failures and (now - failures[0]) > FAILURE_WINDOW_SEC:
        failures.popleft()

    failures.append(now)

    if len(failures) >= FAILURE_THRESHOLD:
        open_until = now + RECOVERY_TIMEOUT_SEC
        state["open_until"] = open_until
        logger.error(
            f"Circuit '{provider_name}' OPENED after {len(failures)} failures "
            f"in {FAILURE_WINDOW_SEC}s. Will retry in {RECOVERY_TIMEOUT_SEC}s."
        )
    else:
        logger.warning(
            f"Circuit '{provider_name}': failure {len(failures)}/{FAILURE_THRESHOLD}"
        )


async def cleanup_providers() -> None:
    """Закрыть все провайдеры — вызывается в FastAPI lifespan shutdown.

    Освобождает httpx.AsyncClient и другие ресурсы.
    """
    for name, provider in _providers.items():
        try:
            await provider.close()
            logger.info(f"Provider '{name}' closed successfully")
        except Exception as e:
            logger.warning(f"Provider '{name}' close error (non-fatal): {e}")
    _providers.clear()
    _circuits.clear()
    logger.info("All LLM providers cleaned up")


# ──────────────────────────────────────────────
# Внутренние функции
# ──────────────────────────────────────────────

def _is_circuit_open(provider_name: str) -> bool:
    """True если circuit breaker открыт (провайдер недоступен)."""
    state = _get_circuit(provider_name)
    open_until = state.get("open_until", 0.0)

    if open_until == 0.0:
        return False  # CLOSED

    now = time.monotonic()
    if now >= open_until:
        # Переходим в HALF-OPEN: сбрасываем open_until, даём один пробный запрос
        state["open_until"] = 0.0
        state["failures"] = deque()
        logger.info(
            f"Circuit '{provider_name}' → HALF-OPEN "
            f"(recovery timeout elapsed, sending probe)"
        )
        return False

    return True  # OPEN


def _get_circuit(provider_name: str) -> dict:
    """Получить или инициализировать circuit state для провайдера."""
    if provider_name not in _circuits:
        _circuits[provider_name] = {
            "failures": deque(),   # timestamp каждого failure
            "open_until": 0.0,    # 0.0 = CLOSED; >0 = время recovery
        }
    return _circuits[provider_name]


def _is_available(provider_name: str) -> bool:
    """Проверить наличие API ключа для провайдера."""
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "mistral":   "MISTRAL_API_KEY",
        "openai":    "OPENAI_API_KEY",
        "local":     "LOCAL_LLM_URL",
    }
    env_key = key_map.get(provider_name)
    return bool(env_key and os.getenv(env_key))


def _get_available() -> set[str]:
    """Множество провайдеров у которых есть API ключ."""
    return {
        p for p in ["anthropic", "mistral", "openai", "local"]
        if _is_available(p)
    }


def _get_or_create(name: str) -> LLMProvider:
    """Получить или создать singleton провайдера."""
    if name not in _providers:
        if name == "anthropic":
            from .anthropic_provider import AnthropicProvider
            _providers[name] = AnthropicProvider()
        elif name == "mistral":
            from .mistral_provider import MistralProvider
            _providers[name] = MistralProvider()
        elif name == "openai":
            from .openai_provider import OpenAIProvider
            _providers[name] = OpenAIProvider()
        elif name == "local":
            from .local_provider import LocalProvider
            _providers[name] = LocalProvider()
        else:
            raise ValueError(f"Unknown LLM provider: '{name}'")
        logger.info(f"LLM provider '{name}' initialized")
    return _providers[name]


def _get_provider_with_tools(
    client_country: str | None,
    available: set[str],
) -> LLMProvider:
    """Выбрать провайдера с поддержкой Tool Calling.

    Порядок для RU/BY: Mistral Large (supports_tools=True) → Anthropic
    Порядок для остальных: Anthropic → Mistral → OpenAI
    Если ни один не поддерживает tools → RuntimeError
    """
    # Проверим страну: если restricted — сначала Mistral, потом Claude
    is_restricted = (
        client_country and client_country.upper() in ANTHROPIC_RESTRICTED
    )

    # Кандидаты в порядке приоритета
    if is_restricted:
        candidates = ["mistral", "anthropic", "openai"]
    else:
        candidates = ["anthropic", "mistral", "openai"]

    for name in candidates:
        if name not in available:
            continue
        if _is_circuit_open(name):
            continue
        provider = _get_or_create(name)
        if provider.supports_tools():
            if is_restricted and name == "anthropic":
                logger.warning(
                    f"Client from {client_country}: requires_tools=True, "
                    f"Mistral unavailable → falling back to Anthropic (tool call needed)"
                )
            return provider

    raise RuntimeError(
        "No LLM provider with tool calling support is available. "
        "Boss Bot requires a provider with supports_tools() == True."
    )
