"""Вспомогательные функции для тестов — mock builders.

Импортируются из test_*.py напрямую:
    from tests.helpers import make_anthropic_response, make_mistral_chat_response
"""
from unittest.mock import MagicMock
import time
from collections import deque

import aipilot_llm.router as _router_module


def make_anthropic_response(
    text: str = "Test response",
    input_tokens: int = 10,
    output_tokens: int = 20,
    stop_reason: str = "end_turn",
    model: str = "claude-sonnet-4-6",
):
    resp = MagicMock()
    resp.content = [MagicMock()]
    resp.content[0].text = text
    resp.content[0].type = "text"
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    resp.stop_reason = stop_reason
    resp.model = model
    return resp


def make_anthropic_tool_response(
    tool_name: str = "get_info",
    tool_input: dict = None,
    tool_id: str = "tool_abc123",
    text: str = "",
    input_tokens: int = 50,
    output_tokens: int = 30,
):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input or {"query": "test"}
    tool_block.id = tool_id

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    resp = MagicMock()
    resp.content = [tool_block] if not text else [text_block, tool_block]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    resp.stop_reason = "tool_use"
    resp.model = "claude-sonnet-4-6"
    return resp


def make_httpx_response(status_code: int = 200, json_body: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = str(json_body)
    return resp


def make_mistral_chat_response(
    text: str = "Mistral response",
    model: str = "mistral-large-latest",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    finish_reason: str = "stop",
):
    return {
        "id": "chat-test-123",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def make_openai_chat_response(
    text: str = "OpenAI response",
    model: str = "gpt-4o",
    prompt_tokens: int = 10,
    completion_tokens: int = 25,
):
    return {
        "id": "chatcmpl-test-456",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def force_circuit_open(provider_name: str, failures: int = 5):
    """Принудительно открыть circuit breaker для провайдера."""
    now = time.monotonic()
    state = _router_module._get_circuit(provider_name)
    state["failures"] = deque([now - i for i in range(failures)])
    state["open_until"] = now + 30.0


def force_circuit_close(provider_name: str):
    """Принудительно закрыть circuit breaker."""
    state = _router_module._get_circuit(provider_name)
    state["failures"] = deque()
    state["open_until"] = 0.0
