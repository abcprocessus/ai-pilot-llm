"""Local LLM provider stub — для self-hosted AI PILOT LLM.

Будет использоваться когда собственная модель будет обучена (Этапы 3-4).
Формат: OpenAI-compatible (vLLM и Ollama оба поддерживают этот формат).

Подключение:
  LOCAL_LLM_URL=http://localhost:8000/v1/chat/completions  — vLLM
  LOCAL_LLM_URL=http://localhost:11434/v1/chat/completions — Ollama

Этап 4 из 8: Деплой и тестирование AI PILOT LLM.
"""
import logging

from .base import LLMProvider, ProviderUnavailable

logger = logging.getLogger(__name__)


class LocalProvider(LLMProvider):
    """Self-hosted AI PILOT LLM провайдер (stub, Этап 4)."""

    name = "local"

    MODELS: dict[str, str] = {
        "fast":    "ai-pilot-llm-1.0",
        "default": "ai-pilot-llm-1.0",
        "strong":  "ai-pilot-llm-1.0",
        "claude-haiku":  "ai-pilot-llm-1.0",
        "claude-sonnet": "ai-pilot-llm-1.0",
        "claude-opus":   "ai-pilot-llm-1.0",
    }

    def supports_tools(self) -> bool:
        return False  # Собственная модель пока не обучена на tool calling

    def max_context_window(self) -> int:
        return 32_000  # Llama 4 Scout 17B

    def _not_implemented(self) -> None:
        raise ProviderUnavailable(
            "local",
            reason=(
                "Local LLM not yet available. "
                "Set LOCAL_LLM_URL after deploying AI PILOT LLM v1.0 (Phase 4). "
                "vLLM: http://host:8000/v1/chat/completions"
            )
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
        pass  # Stub
