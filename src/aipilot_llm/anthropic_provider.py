"""Anthropic Claude provider — основной LLM провайдер AI PILOT.

Полная реализация LLMProvider для Anthropic API.
Логика перенесена из v2/backend/app/ai/claude.py.

Модели (актуальные на март 2026):
  claude-haiku-4-5-20251001  — быстрый, дешёвый (FAQ, классификация)
  claude-sonnet-4-6          — основной (все агенты по умолчанию)
  claude-opus-4-6            — мощный (webmaster, boss, сложные задачи)

Маппинг универсальных алиасов (fast/default/strong):
  fast    → haiku   (самый дешёвый)
  default → sonnet  (баланс цена/качество)
  strong  → opus    (максимальное качество)

Этап 1 из 8: Multi-LLM абстракция.
"""
import json
import logging
import os
from typing import AsyncGenerator, Optional

from anthropic import AsyncAnthropic, APIStatusError, APIConnectionError

from .base import LLMProvider, ProviderOverloaded, ProviderUnavailable

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Прайс-лист Anthropic (EUR, март 2026)
# Цены в USD из документации, конвертация ×0.92
# ──────────────────────────────────────────────
_COST_PER_1K_INPUT = {
    "claude-haiku-4-5-20251001": 0.00023,   # $0.25/M input  × 0.92 / 1000
    "claude-sonnet-4-6":         0.00277,   # $3.00/M input  × 0.92 / 1000
    "claude-opus-4-6":           0.01384,   # $15.00/M input × 0.92 / 1000
}
_COST_PER_1K_OUTPUT = {
    "claude-haiku-4-5-20251001": 0.00115,   # $1.25/M output × 0.92 / 1000
    "claude-sonnet-4-6":         0.01384,   # $15.00/M output × 0.92 / 1000
    "claude-opus-4-6":           0.06912,   # $75.00/M output × 0.92 / 1000
}


class AnthropicProvider(LLMProvider):
    """Anthropic Claude провайдер.

    Единственный singleton — создаётся через router._get_or_create("anthropic").
    """

    name = "anthropic"

    # Маппинг ключей → реальные model ID
    # ПРАВИЛО: НЕ менять model ID без согласования с Claude Code!
    # claude-sonnet-4-6 и claude-opus-4-6 — РЕАЛЬНЫЕ модели production 2026.
    MODELS: dict[str, str] = {
        # Полные имена
        "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6":         "claude-sonnet-4-6",
        "claude-opus-4-6":           "claude-opus-4-6",
        # Короткие алиасы
        "claude-haiku":  "claude-haiku-4-5-20251001",
        "claude-sonnet": "claude-sonnet-4-6",
        "claude-opus":   "claude-opus-4-6",
        # Алиасы обратной совместимости
        "claude-sonnet-4-5":  "claude-sonnet-4-6",
        "claude-haiku-4-5":   "claude-haiku-4-5-20251001",
        "haiku":              "claude-haiku-4-5-20251001",
        "sonnet":             "claude-sonnet-4-6",
        "opus":               "claude-opus-4-6",
        # Универсальные алиасы (кросс-провайдерный маппинг)
        "fast":    "claude-haiku-4-5-20251001",
        "default": "claude-sonnet-4-6",
        "strong":  "claude-opus-4-6",
    }

    DEFAULT_MODEL = "claude-sonnet"

    def __init__(self) -> None:
        self._client: Optional[AsyncAnthropic] = None

    def _get_client(self) -> AsyncAnthropic:
        """Lazy init AsyncAnthropic singleton."""
        if self._client is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. "
                    "Add to Railway env vars: ANTHROPIC_API_KEY=sk-ant-..."
                )
            # AsyncAnthropic — НЕ блокирует event loop (в отличие от Anthropic)
            self._client = AsyncAnthropic(api_key=api_key)
        return self._client

    def _resolve_model(self, model: str) -> str:
        """Преобразовать алиас → реальный model ID."""
        return self.MODELS.get(model, self.MODELS[self.DEFAULT_MODEL])

    def _calc_cost(
        self, model_id: str, tokens_input: int, tokens_output: int
    ) -> float:
        """Рассчитать стоимость запроса в EUR."""
        cost_in = _COST_PER_1K_INPUT.get(model_id, 0.0) * tokens_input / 1000
        cost_out = _COST_PER_1K_OUTPUT.get(model_id, 0.0) * tokens_output / 1000
        return round(cost_in + cost_out, 8)

    def supports_tools(self) -> bool:
        return True

    def max_context_window(self) -> int:
        return 200_000  # Claude 4.x имеет 200K контекст

    async def close(self) -> None:
        """Закрыть AsyncAnthropic клиент."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("AnthropicProvider: client closed")

    # ──────────────────────────────────────────────
    # chat()
    # ──────────────────────────────────────────────

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int = 2048,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        client = self._get_client()
        model_id = self._resolve_model(model)
        start_ms = self._now_ms()

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        try:
            response = await client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
        except APIStatusError as e:
            if e.status_code == 529:
                raise ProviderOverloaded("anthropic", retry_after=30) from e
            raise ProviderUnavailable("anthropic", reason=str(e)) from e
        except (APIConnectionError, Exception) as e:
            raise ProviderUnavailable("anthropic", reason=str(e)) from e

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens

        return {
            "text":          response.content[0].text,
            "tokens_input":  tokens_in,
            "tokens_output": tokens_out,
            "model":         model_id,
            "stop_reason":   response.stop_reason,
            "provider":      self.name,
            "cost_eur":      self._calc_cost(model_id, tokens_in, tokens_out),
            "latency_ms":    self._elapsed_ms(start_ms),
        }

    # ──────────────────────────────────────────────
    # chat_stream()
    # ──────────────────────────────────────────────

    async def chat_stream(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int = 2048,
        conversation_history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        client = self._get_client()
        model_id = self._resolve_model(model)
        start_ms = self._now_ms()

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        try:
            async with client.messages.stream(
                model=model_id,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    yield f"data: {json.dumps({'type': 'delta', 'text': text_chunk})}\n\n"

                final_msg = await stream.get_final_message()
                tokens_in = final_msg.usage.input_tokens
                tokens_out = final_msg.usage.output_tokens

                yield f"data: {json.dumps({'type': 'done', 'tokens_input': tokens_in, 'tokens_output': tokens_out, 'provider': self.name, 'latency_ms': self._elapsed_ms(start_ms)})}\n\n"
                yield "data: [DONE]\n\n"

        except APIStatusError as e:
            if e.status_code == 529:
                raise ProviderOverloaded("anthropic", retry_after=30) from e
            raise ProviderUnavailable("anthropic", reason=str(e)) from e
        except (APIConnectionError, Exception) as e:
            raise ProviderUnavailable("anthropic", reason=str(e)) from e

    # ──────────────────────────────────────────────
    # classify()
    # ──────────────────────────────────────────────

    async def classify(
        self,
        text: str,
        categories: list[str],
        model: str | None = None,
    ) -> str:
        client = self._get_client()
        # Для классификации всегда Haiku — самый дешёвый
        model_id = self._resolve_model(model or "claude-haiku")

        system = (
            f"You are a classifier. Classify the following text into ONE of these categories:\n"
            f"{', '.join(categories)}\n\n"
            f"Reply with ONLY the category name, nothing else."
        )

        try:
            response = await client.messages.create(
                model=model_id,
                max_tokens=50,
                system=system,
                messages=[{"role": "user", "content": text}],
            )
        except APIStatusError as e:
            if e.status_code == 529:
                raise ProviderOverloaded("anthropic", retry_after=30) from e
            raise ProviderUnavailable("anthropic", reason=str(e)) from e
        except Exception as e:
            raise ProviderUnavailable("anthropic", reason=str(e)) from e

        result = response.content[0].text.strip().lower()
        for cat in categories:
            if cat.lower() in result:
                return cat
        return categories[0]  # fallback: первая категория

    # ──────────────────────────────────────────────
    # chat_with_tools()
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
        """Anthropic Tool Calling — для Boss Bot и Router.

        Returns:
            dict: {text, tool_calls, tokens_input, tokens_output,
                   model, stop_reason, provider, cost_eur, latency_ms}
                  tool_calls: list[{name, input, id}]
        """
        client = self._get_client()
        model_id = self._resolve_model(model)
        start_ms = self._now_ms()

        messages = list(conversation_history or [])
        # user_message может быть "" при повторном agentic вызове
        # (когда conversation_history уже заканчивается на role=user с tool_results)
        if user_message:
            messages.append({"role": "user", "content": user_message})

        create_kwargs: dict = dict(
            model=model_id,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        if tool_choice:
            create_kwargs["tool_choice"] = tool_choice

        try:
            response = await client.messages.create(**create_kwargs)
        except APIStatusError as e:
            if e.status_code == 529:
                raise ProviderOverloaded("anthropic", retry_after=30) from e
            raise ProviderUnavailable("anthropic", reason=str(e)) from e
        except Exception as e:
            raise ProviderUnavailable("anthropic", reason=str(e)) from e

        # Разбираем: Claude может вернуть текст + tool_use блоки одновременно
        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "name":  block.name,
                    "input": block.input,
                    "id":    block.id,
                })

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens

        return {
            "text":          text,
            "tool_calls":    tool_calls,
            "tokens_input":  tokens_in,
            "tokens_output": tokens_out,
            "model":         model_id,
            "stop_reason":   response.stop_reason,
            "provider":      self.name,
            "cost_eur":      self._calc_cost(model_id, tokens_in, tokens_out),
            "latency_ms":    self._elapsed_ms(start_ms),
        }
