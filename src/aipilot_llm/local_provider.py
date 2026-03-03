"""Local LLM provider — self-hosted AI PILOT LLM (vLLM / Ollama).

Подключается к OpenAI-compatible API endpoint на своём сервере.
vLLM: http://host:8000/v1/chat/completions
Ollama: http://host:11434/v1/chat/completions

Env var: LOCAL_LLM_URL (например http://localhost:8000 или http://hetzner-gpu:8000)
Timeout: 30s (первый inference может быть медленным при холодном старте)

Этап 4 из 8: Деплой и тестирование AI PILOT LLM.
"""
import json
import logging
import os
from typing import AsyncGenerator, Optional

import httpx

from .base import LLMProvider, ProviderUnavailable

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class LocalProvider(LLMProvider):
    """Self-hosted AI PILOT LLM провайдер (vLLM / Ollama, OpenAI-compatible)."""

    name = "local"

    MODELS: dict[str, str] = {
        # Все алиасы → одна модель (наша собственная)
        "fast":              "ai-pilot-llm-1.0",
        "default":           "ai-pilot-llm-1.0",
        "strong":            "ai-pilot-llm-1.0",
        "claude-haiku":      "ai-pilot-llm-1.0",
        "claude-sonnet":     "ai-pilot-llm-1.0",
        "claude-opus":       "ai-pilot-llm-1.0",
        "ai-pilot-llm":      "ai-pilot-llm-1.0",
        "ai-pilot-fast":     "ai-pilot-llm-1.0",
        "ai-pilot-strong":   "ai-pilot-llm-1.0",
        "ai-pilot-llm-1.0":  "ai-pilot-llm-1.0",
    }
    DEFAULT_MODEL = "ai-pilot-llm-1.0"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    def _get_base_url(self) -> str:
        url = os.getenv("LOCAL_LLM_URL", "").rstrip("/")
        if not url:
            raise ProviderUnavailable(
                "local",
                reason=(
                    "LOCAL_LLM_URL not configured. "
                    "Set LOCAL_LLM_URL=http://your-gpu-server:8000 "
                    "after deploying AI PILOT LLM v1.0 (Phase 4)."
                ),
            )
        return url

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Content-Type": "application/json"},
                timeout=_TIMEOUT,
            )
        return self._client

    def _resolve_model(self, model: str) -> str:
        return self.MODELS.get(model, self.DEFAULT_MODEL)

    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict] | None,
    ) -> list[dict]:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        if user_message:
            messages.append({"role": "user", "content": user_message})
        return messages

    def supports_tools(self) -> bool:
        # AI PILOT LLM v1.0 не обучена на tool calling
        return False

    def max_context_window(self) -> int:
        # Llama 4 Scout 17B — 32K контекст
        return 32_000

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("LocalProvider: client closed")

    # ── chat() ───────────────────────────────────────────────────────────────

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int = 2048,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        base_url = self._get_base_url()
        client = self._get_client()
        model_id = self._resolve_model(model)
        start_ms = self._now_ms()
        messages = self._build_messages(system_prompt, user_message, conversation_history)

        try:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
            )
        except httpx.TimeoutException as e:
            raise ProviderUnavailable("local", reason=f"timeout ({_TIMEOUT.read}s): {e}") from e
        except httpx.RequestError as e:
            raise ProviderUnavailable("local", reason=f"connection error to {base_url}: {e}") from e

        if resp.status_code >= 500:
            raise ProviderUnavailable("local", reason=f"HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code != 200:
            raise ProviderUnavailable("local", reason=f"HTTP {resp.status_code}: {resp.text[:200]}")

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
            "cost_eur":      0.0,   # Свой сервер — нет затрат на API
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
        base_url = self._get_base_url()
        client = self._get_client()
        model_id = self._resolve_model(model)
        start_ms = self._now_ms()
        messages = self._build_messages(system_prompt, user_message, conversation_history)

        try:
            async with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as resp:
                if resp.status_code != 200:
                    raise ProviderUnavailable("local", reason=f"HTTP {resp.status_code}")

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
                        if chunk.get("usage"):
                            tokens_in = chunk["usage"].get("prompt_tokens", 0)
                            tokens_out = chunk["usage"].get("completion_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue

                yield f"data: {json.dumps({'type': 'done', 'tokens_input': tokens_in, 'tokens_output': tokens_out, 'provider': self.name, 'latency_ms': self._elapsed_ms(start_ms)})}\n\n"
                yield "data: [DONE]\n\n"

        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise ProviderUnavailable("local", reason=str(e)) from e

    # ── classify() ───────────────────────────────────────────────────────────

    async def classify(
        self,
        text: str,
        categories: list[str],
        model: str | None = None,
    ) -> str:
        result = await self.chat(
            system_prompt=(
                f"Classify the text into ONE of: {', '.join(categories)}. "
                "Reply ONLY with the category name."
            ),
            user_message=text,
            model=model or self.DEFAULT_MODEL,
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
        """Tool calling не реализован — AI PILOT LLM v1.0 не обучена.

        Будет реализовано в v2.0 после RLHF/DPO (Этап 6).
        """
        raise NotImplementedError(
            "Tool calling not available in AI PILOT LLM v1.0. "
            "Use Anthropic or Mistral provider for tool calling. "
            "Tool support is planned for AI PILOT LLM v2.0 (Phase 6)."
        )
