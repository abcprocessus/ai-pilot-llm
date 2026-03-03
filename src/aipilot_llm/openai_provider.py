"""OpenAI provider stub — реализация на Этапе 7.

Сейчас: заглушка чтобы router.py мог инициализировать провайдер
при наличии OPENAI_API_KEY в env vars.

Реальная реализация: Этап 7 (Developer Portal + API Platform).
Формат: OpenAI-compatible (идентичен Mistral, почти copy-paste).
"""
import logging

from .base import LLMProvider, ProviderUnavailable

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o / o3 провайдер (stub)."""

    name = "openai"

    MODELS: dict[str, str] = {
        "fast":    "gpt-4o-mini",
        "default": "gpt-4o",
        "strong":  "o3",
        "claude-haiku":  "gpt-4o-mini",
        "claude-sonnet": "gpt-4o",
        "claude-opus":   "o3",
    }

    def supports_tools(self) -> bool:
        return True

    def _not_implemented(self) -> None:
        raise ProviderUnavailable(
            "openai",
            reason="OpenAI provider not yet implemented. Coming in Phase 7."
        )

    async def chat(self, system_prompt, user_message, model, max_tokens=2048,
                   conversation_history=None) -> dict:
        self._not_implemented()

    async def chat_stream(self, system_prompt, user_message, model, max_tokens=2048,
                          conversation_history=None):
        self._not_implemented()
        yield ""  # satisfy AsyncGenerator type

    async def classify(self, text, categories, model=None) -> str:
        self._not_implemented()

    async def close(self) -> None:
        pass  # Ничего закрывать — stub
