"""Abstract LLM Provider base class — AI PILOT Multi-LLM Architecture.

Все провайдеры (Anthropic, Mistral, OpenAI, Local) наследуют этот класс
и реализуют единый интерфейс. Агенты работают ТОЛЬКО через этот интерфейс.

Единый формат ответа chat() / chat_with_tools():
    {
        "text":          str,    # ответ модели
        "tokens_input":  int,    # токены входа
        "tokens_output": int,    # токены выхода
        "model":         str,    # реальный model_id (напр. "claude-sonnet-4-6")
        "stop_reason":   str,    # "end_turn" / "max_tokens" / "tool_use" / "stop"
        "provider":      str,    # "anthropic" / "mistral" / "openai" / "local"
        "cost_eur":      float,  # стоимость запроса в EUR
        "latency_ms":    int,    # задержка в мс (time от вызова до первого байта)
    }

Этап 1 из 8: Multi-LLM абстракция.
"""
import time
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class LLMProvider(ABC):
    """Абстрактный LLM провайдер — единый интерфейс для всех моделей.

    Подклассы обязаны реализовать: chat(), chat_stream(), classify().
    chat_with_tools() — опционально (по умолчанию NotImplementedError).
    """

    name: str = "base"  # "anthropic" | "mistral" | "openai" | "local"

    # ──────────────────────────────────────────────
    # Абстрактные методы — ОБЯЗАТЕЛЬНО реализовать
    # ──────────────────────────────────────────────

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int = 2048,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Отправить сообщение и получить ответ (non-streaming).

        Args:
            system_prompt:         Системная инструкция (конституция агента + KB)
            user_message:          Текущее сообщение пользователя
            model:                 Ключ модели (fast|default|strong|claude-sonnet|...)
            max_tokens:            Максимальная длина ответа
            conversation_history:  История [{role, content}, ...]

        Returns:
            dict: {text, tokens_input, tokens_output, model, stop_reason,
                   provider, cost_eur, latency_ms}
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int = 2048,
        conversation_history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming версия chat() — yields SSE events.

        Yields:
            "data: {type: delta, text: chunk}\\n\\n"        — per-token chunk
            "data: {type: done, tokens_input: N, ...}\\n\\n" — итог
            "data: [DONE]\\n\\n"                             — конец стрима
        """
        ...

    @abstractmethod
    async def classify(
        self,
        text: str,
        categories: list[str],
        model: str | None = None,
    ) -> str:
        """Быстрая классификация текста.

        Args:
            text:       Текст для классификации
            categories: Список допустимых категорий
            model:      Модель (None = самая дешёвая у провайдера)

        Returns:
            str: Одна из переданных categories
        """
        ...

    # ──────────────────────────────────────────────
    # Методы с реализацией по умолчанию
    # ──────────────────────────────────────────────

    async def chat_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        model: str,
        max_tokens: int = 4096,
        conversation_history: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> dict:
        """Tool Calling — по умолчанию NotImplementedError.

        Только Anthropic и OpenAI поддерживают нативно.
        Mistral Large поддерживает function calling (переопределяет этот метод).
        Local — через stub (NotImplementedError).

        Returns:
            dict: {text, tool_calls, tokens_input, tokens_output,
                   model, stop_reason, provider, cost_eur, latency_ms}
                  tool_calls: list[{name, input, id}]
        """
        raise NotImplementedError(
            f"Provider '{self.name}' does not support tool calling. "
            f"Use a provider with supports_tools() == True "
            f"(anthropic, mistral, openai)."
        )

    def supports_tools(self) -> bool:
        """True если провайдер поддерживает нативный Tool Calling."""
        return False

    def max_context_window(self) -> int:
        """Максимальное окно контекста в токенах."""
        return 128_000

    async def close(self) -> None:
        """Освободить ресурсы провайдера (httpx клиент, соединения).

        Вызывается в FastAPI lifespan shutdown → cleanup_providers().
        По умолчанию no-op — провайдеры переопределяют если нужен cleanup.
        """
        pass

    # ──────────────────────────────────────────────
    # Вспомогательные методы (утилиты для подклассов)
    # ──────────────────────────────────────────────

    @staticmethod
    def _now_ms() -> float:
        """Текущее время в мс. Используется для замера latency."""
        return time.time() * 1000

    @staticmethod
    def _elapsed_ms(start_ms: float) -> int:
        """Время в мс от start_ms до сейчас."""
        return int(time.time() * 1000 - start_ms)

    def __repr__(self) -> str:
        return f"<LLMProvider name={self.name} tools={self.supports_tools()}>"


class ProviderOverloaded(Exception):
    """Провайдер перегружен (HTTP 529 от Anthropic).

    НЕ считается failure в circuit breaker.
    Router переключит на fallback только для ЭТОГО запроса.
    Следующий запрос снова попробует основной провайдер.
    """
    def __init__(self, provider_name: str, retry_after: int = 30):
        self.provider_name = provider_name
        self.retry_after = retry_after
        super().__init__(
            f"Provider '{provider_name}' is overloaded (HTTP 529). "
            f"Retry after {retry_after}s."
        )


class ProviderUnavailable(Exception):
    """Провайдер недоступен (network error, timeout, 5xx).

    Считается failure в circuit breaker.
    После FAILURE_THRESHOLD таких ошибок → circuit opens.
    """
    def __init__(self, provider_name: str, reason: str = ""):
        self.provider_name = provider_name
        self.reason = reason
        super().__init__(
            f"Provider '{provider_name}' is unavailable: {reason}"
        )
