"""OpenAI GPT-4o / o3 provider — реализация через httpx (OpenAI-compatible API).

Формат запросов идентичен Mistral (OpenAI-compatible).
POST https://api.openai.com/v1/chat/completions
Authorization: Bearer OPENAI_API_KEY

Этап 1 из 8: Multi-LLM абстракция.
"""
import json
import logging
import os
from typing import AsyncGenerator, Optional

import httpx

from .base import LLMProvider, ProviderOverloaded, ProviderUnavailable

logger = logging.getLogger(__name__)

_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)

# Прайс-лист OpenAI (EUR, март 2026, ×0.92 от USD)
_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini":  {"input": 0.00013,  "output": 0.00053},
    "gpt-4o":       {"input": 0.0022,   "output": 0.0088},
    "gpt-4-turbo":  {"input": 0.0083,   "output": 0.0332},
    "o3":           {"input": 0.0088,   "output": 0.035},
    "o3-mini":      {"input": 0.00097,  "output": 0.0039},
}


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o / o3 провайдер (httpx, OpenAI-compatible)."""

    name = "openai"

    MODELS: dict[str, str] = {
        # Универсальные алиасы
        "fast":    "gpt-4o-mini",
        "default": "gpt-4o",
        "strong":  "o3",
        # Кросс-провайдерный маппинг claude-алиасов
        "claude-haiku":  "gpt-4o-mini",
        "claude-sonnet": "gpt-4o",
        "claude-opus":   "o3",
        # Прямые имена
        "gpt-4o-mini":  "gpt-4o-mini",
        "gpt-4o":       "gpt-4o",
        "gpt-4-turbo":  "gpt-4-turbo",
        "o3":           "o3",
        "o3-mini":      "o3-mini",
    }
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY not set. "
                    "Get key at https://platform.openai.com/api-keys"
                )
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
            )
        return self._client

    def _resolve_model(self, model: str) -> str:
        return self.MODELS.get(model, self.DEFAULT_MODEL)

    def _calc_cost(self, model_id: str, tokens_in: int, tokens_out: int) -> float:
        pricing = _PRICING.get(model_id, {"input": 0.0, "output": 0.0})
        cost = pricing["input"] * tokens_in / 1000 + pricing["output"] * tokens_out / 1000
        return round(cost, 8)

    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict] | None,
    ) -> list[dict]:
        """OpenAI: system prompt первым сообщением с role=system."""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        if user_message:
            messages.append({"role": "user", "content": user_message})
        return messages

    def supports_tools(self) -> bool:
        return True

    def max_context_window(self) -> int:
        return 128_000

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("OpenAIProvider: client closed")

    # ── chat() ───────────────────────────────────────────────────────────────

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
        messages = self._build_messages(system_prompt, user_message, conversation_history)

        try:
            resp = await client.post(
                _OPENAI_API_URL,
                json={"model": model_id, "messages": messages, "max_tokens": max_tokens},
            )
        except httpx.TimeoutException as e:
            raise ProviderUnavailable("openai", reason=f"timeout: {e}") from e
        except httpx.RequestError as e:
            raise ProviderUnavailable("openai", reason=f"network error: {e}") from e

        if resp.status_code == 429:
            raise ProviderOverloaded("openai", retry_after=60)
        if resp.status_code >= 500:
            raise ProviderUnavailable("openai", reason=f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise ProviderUnavailable("openai", reason=f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        return {
            "text":          choice["message"]["content"] or "",
            "tokens_input":  tokens_in,
            "tokens_output": tokens_out,
            "model":         model_id,
            "stop_reason":   choice.get("finish_reason", "stop"),
            "provider":      self.name,
            "cost_eur":      self._calc_cost(model_id, tokens_in, tokens_out),
            "latency_ms":    self._elapsed_ms(start_ms),
        }

    # ── chat_stream() ────────────────────────────────────────────────────────

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
        messages = self._build_messages(system_prompt, user_message, conversation_history)

        try:
            async with client.stream(
                "POST",
                _OPENAI_API_URL,
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "stream": True,
                    "stream_options": {"include_usage": True},  # OpenAI специфика
                },
            ) as resp:
                if resp.status_code == 429:
                    raise ProviderOverloaded("openai", retry_after=60)
                if resp.status_code != 200:
                    raise ProviderUnavailable("openai", reason=f"HTTP {resp.status_code}")

                tokens_in = 0
                tokens_out = 0

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        choice = chunk["choices"][0] if chunk.get("choices") else None
                        if choice:
                            delta_text = choice.get("delta", {}).get("content") or ""
                            if delta_text:
                                yield f"data: {json.dumps({'type': 'delta', 'text': delta_text})}\n\n"
                        # stream_options: usage в последнем chunk
                        if chunk.get("usage"):
                            tokens_in = chunk["usage"].get("prompt_tokens", 0)
                            tokens_out = chunk["usage"].get("completion_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue

                yield f"data: {json.dumps({'type': 'done', 'tokens_input': tokens_in, 'tokens_output': tokens_out, 'provider': self.name, 'latency_ms': self._elapsed_ms(start_ms)})}\n\n"
                yield "data: [DONE]\n\n"

        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise ProviderUnavailable("openai", reason=str(e)) from e

    # ── classify() ───────────────────────────────────────────────────────────

    async def classify(
        self,
        text: str,
        categories: list[str],
        model: str | None = None,
    ) -> str:
        result = await self.chat(
            system_prompt=(
                f"You are a classifier. Classify the text into ONE of: "
                f"{', '.join(categories)}. Reply ONLY with the category name."
            ),
            user_message=text,
            model=model or "gpt-4o-mini",
            max_tokens=50,
        )
        text_result = result["text"].strip().lower()
        for cat in categories:
            if cat.lower() in text_result:
                return cat
        return categories[0]

    # ── chat_with_tools() ────────────────────────────────────────────────────

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
        """OpenAI native tool calling (формат совпадает с Mistral, без конвертации)."""
        client = self._get_client()
        model_id = self._resolve_model(model)
        start_ms = self._now_ms()
        messages = self._build_messages(system_prompt, user_message, conversation_history)

        # OpenAI принимает тот же формат что Mistral
        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name":        t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters":  t.get("input_schema", t.get("parameters", {})),
                },
            })

        payload: dict = {
            "model":      model_id,
            "messages":   messages,
            "max_tokens": max_tokens,
        }
        if openai_tools:
            payload["tools"] = openai_tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        try:
            resp = await client.post(_OPENAI_API_URL, json=payload)
        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise ProviderUnavailable("openai", reason=str(e)) from e

        if resp.status_code == 429:
            raise ProviderOverloaded("openai", retry_after=60)
        if resp.status_code != 200:
            raise ProviderUnavailable("openai", reason=f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        text = msg.get("content") or ""
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "name":  fn.get("name", ""),
                "input": args,
                "id":    tc.get("id", ""),
            })

        return {
            "text":          text,
            "tool_calls":    tool_calls,
            "tokens_input":  tokens_in,
            "tokens_output": tokens_out,
            "model":         model_id,
            "stop_reason":   choice.get("finish_reason", "stop"),
            "provider":      self.name,
            "cost_eur":      self._calc_cost(model_id, tokens_in, tokens_out),
            "latency_ms":    self._elapsed_ms(start_ms),
        }
