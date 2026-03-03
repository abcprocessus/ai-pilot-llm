"""Mistral AI provider — fallback провайдер для RU/BY клиентов.

Реализован через httpx (НЕ mistralai SDK) — httpx уже есть в requirements.txt.
Mistral API = OpenAI-compatible формат:
  POST https://api.mistral.ai/v1/chat/completions
  Authorization: Bearer MISTRAL_API_KEY
  Content-Type: application/json
  {"model": "mistral-large-latest", "messages": [...], "max_tokens": N}

Ключевые отличия от Anthropic (важно при реализации):
  - System prompt: первым сообщением {role: "system"}, НЕ отдельным полем
  - Stop reason: finish_reason "stop" / "length" / "tool_calls"
  - Token count: prompt_tokens / completion_tokens (НЕ input_tokens/output_tokens)
  - Response: choices[0].message.content (НЕ content[0].text)
  - Tool calling: OpenAI format {type: "function", function: {name, description, parameters}}

Этап 1 из 8: Multi-LLM абстракция.
"""
import json
import logging
import os
from typing import AsyncGenerator, Optional

import httpx

from .base import LLMProvider, ProviderOverloaded, ProviderUnavailable

logger = logging.getLogger(__name__)

_MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)

# Прайс-лист Mistral (EUR, март 2026, ~×0.92 от USD)
_COST_PER_1K_INPUT = {
    "mistral-small-latest":  0.000184,  # $0.20/M × 0.92 / 1000
    "mistral-large-latest":  0.00184,   # $2.00/M × 0.92 / 1000
}
_COST_PER_1K_OUTPUT = {
    "mistral-small-latest":  0.000552,  # $0.60/M × 0.92 / 1000
    "mistral-large-latest":  0.00552,   # $6.00/M × 0.92 / 1000
}


class MistralProvider(LLMProvider):
    """Mistral AI провайдер (httpx, OpenAI-compatible)."""

    name = "mistral"

    MODELS: dict[str, str] = {
        # Универсальные алиасы
        "fast":    "mistral-small-latest",
        "default": "mistral-large-latest",
        "strong":  "mistral-large-latest",
        # Кросс-провайдерный маппинг claude-алиасов → Mistral
        "claude-haiku":  "mistral-small-latest",
        "claude-sonnet": "mistral-large-latest",
        "claude-opus":   "mistral-large-latest",
        # Прямые названия
        "mistral-small-latest": "mistral-small-latest",
        "mistral-large-latest": "mistral-large-latest",
    }
    DEFAULT_MODEL = "mistral-large-latest"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            api_key = os.getenv("MISTRAL_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "MISTRAL_API_KEY not set. "
                    "Get one at https://console.mistral.ai/ — BY/RU accounts allowed."
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
        cost_in = _COST_PER_1K_INPUT.get(model_id, 0.0) * tokens_in / 1000
        cost_out = _COST_PER_1K_OUTPUT.get(model_id, 0.0) * tokens_out / 1000
        return round(cost_in + cost_out, 8)

    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict] | None,
    ) -> list[dict]:
        """Mistral: system prompt — первое сообщение с role=system."""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        if user_message:
            messages.append({"role": "user", "content": user_message})
        return messages

    def supports_tools(self) -> bool:
        return True  # Mistral Large поддерживает function calling

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("MistralProvider: client closed")

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
                _MISTRAL_API_URL,
                json={"model": model_id, "messages": messages, "max_tokens": max_tokens},
            )
        except httpx.TimeoutException as e:
            raise ProviderUnavailable("mistral", reason=f"timeout: {e}") from e
        except httpx.RequestError as e:
            raise ProviderUnavailable("mistral", reason=f"network error: {e}") from e

        if resp.status_code == 429:
            raise ProviderOverloaded("mistral", retry_after=60)
        if resp.status_code >= 500:
            raise ProviderUnavailable("mistral", reason=f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise ProviderUnavailable("mistral", reason=f"HTTP {resp.status_code}: {resp.text[:200]}")

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
                _MISTRAL_API_URL,
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as resp:
                if resp.status_code == 429:
                    raise ProviderOverloaded("mistral", retry_after=60)
                if resp.status_code != 200:
                    raise ProviderUnavailable("mistral", reason=f"HTTP {resp.status_code}")

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
                        choice = chunk["choices"][0]
                        delta_text = choice.get("delta", {}).get("content") or ""
                        if delta_text:
                            yield f"data: {json.dumps({'type': 'delta', 'text': delta_text})}\n\n"
                        # Mistral включает usage в последний chunk
                        if chunk.get("usage"):
                            tokens_in = chunk["usage"].get("prompt_tokens", 0)
                            tokens_out = chunk["usage"].get("completion_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue

                yield f"data: {json.dumps({'type': 'done', 'tokens_input': tokens_in, 'tokens_output': tokens_out, 'provider': self.name, 'latency_ms': self._elapsed_ms(start_ms)})}\n\n"
                yield "data: [DONE]\n\n"

        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise ProviderUnavailable("mistral", reason=str(e)) from e

    # ── classify() ───────────────────────────────────────────────────────────

    async def classify(
        self,
        text: str,
        categories: list[str],
        model: str | None = None,
    ) -> str:
        # Для классификации всегда small — дешевле
        result = await self.chat(
            system_prompt=(
                f"You are a classifier. Classify the text into ONE of: "
                f"{', '.join(categories)}. Reply ONLY with the category name."
            ),
            user_message=text,
            model=model or "mistral-small-latest",
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
        """Mistral function calling (OpenAI format).

        Mistral принимает tools в формате:
        [{type: "function", function: {name, description, parameters}}]

        Anthropic-формат {name, description, input_schema} → конвертируем.
        """
        client = self._get_client()
        model_id = self._resolve_model(model)
        start_ms = self._now_ms()
        messages = self._build_messages(system_prompt, user_message, conversation_history)

        # Конвертация Anthropic tool format → OpenAI/Mistral format
        mistral_tools = []
        for t in tools:
            mistral_tools.append({
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
            "tools":      mistral_tools,
        }
        if tool_choice:
            payload["tool_choice"] = tool_choice

        try:
            resp = await client.post(_MISTRAL_API_URL, json=payload)
        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise ProviderUnavailable("mistral", reason=str(e)) from e

        if resp.status_code == 429:
            raise ProviderOverloaded("mistral", retry_after=60)
        if resp.status_code != 200:
            raise ProviderUnavailable("mistral", reason=f"HTTP {resp.status_code}: {resp.text[:200]}")

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
