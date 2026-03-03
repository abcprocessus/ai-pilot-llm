"""Tests для aipilot_llm.base — abstract class contract."""
import pytest
from aipilot_llm.base import LLMProvider, ProviderOverloaded, ProviderUnavailable


# ──────────────────────────────────────────────────────────────────────────────
# Конкретный тестовый провайдер для проверки базового класса
# ──────────────────────────────────────────────────────────────────────────────

class MinimalProvider(LLMProvider):
    """Минимальная реализация для теста абстрактного класса."""
    name = "test"

    async def chat(self, system_prompt, user_message, model, max_tokens=2048,
                   conversation_history=None) -> dict:
        return {
            "text": "ok", "tokens_input": 1, "tokens_output": 1,
            "model": model, "stop_reason": "end_turn",
            "provider": self.name, "cost_eur": 0.0, "latency_ms": 10,
        }

    async def chat_stream(self, system_prompt, user_message, model, max_tokens=2048,
                          conversation_history=None):
        yield f"data: {{\"type\": \"delta\", \"text\": \"ok\"}}\n\n"
        yield "data: [DONE]\n\n"

    async def classify(self, text, categories, model=None) -> str:
        return categories[0]


# ──────────────────────────────────────────────────────────────────────────────

def test_abstract_class_cannot_be_instantiated():
    """LLMProvider — абстрактный класс, нельзя создать напрямую."""
    with pytest.raises(TypeError):
        LLMProvider()


def test_minimal_provider_can_be_instantiated():
    """Конкретный провайдер с 3 методами успешно создаётся."""
    provider = MinimalProvider()
    assert provider.name == "test"


def test_default_supports_tools_is_false():
    """По умолчанию supports_tools() == False."""
    provider = MinimalProvider()
    assert provider.supports_tools() is False


def test_default_max_context_window():
    """По умолчанию max_context_window() == 128_000."""
    provider = MinimalProvider()
    assert provider.max_context_window() == 128_000


async def test_default_chat_with_tools_raises_not_implemented():
    """По умолчанию chat_with_tools() → NotImplementedError (провайдер без tools)."""
    provider = MinimalProvider()

    with pytest.raises(NotImplementedError):
        await provider.chat_with_tools("sys", "msg", [], "default")


async def test_close_is_nooop_by_default():
    """По умолчанию close() — no-op (не кидает исключение)."""
    provider = MinimalProvider()
    await provider.close()  # Не должно бросать


def test_timer_utilities():
    """_now_ms() и _elapsed_ms() работают корректно."""
    import time

    provider = MinimalProvider()
    start = provider._now_ms()
    time.sleep(0.01)  # 10ms
    elapsed = provider._elapsed_ms(start)

    assert elapsed >= 5, f"Expected >=5ms, got {elapsed}ms"
    assert elapsed < 500, f"Expected <500ms, got {elapsed}ms"


def test_provider_overloaded_attributes():
    """ProviderOverloaded имеет нужные атрибуты."""
    exc = ProviderOverloaded("anthropic", retry_after=60)
    assert exc.provider_name == "anthropic"
    assert exc.retry_after == 60
    assert "anthropic" in str(exc)
    assert "529" in str(exc)


def test_provider_unavailable_attributes():
    """ProviderUnavailable имеет нужные атрибуты."""
    exc = ProviderUnavailable("mistral", reason="connection refused")
    assert exc.provider_name == "mistral"
    assert exc.reason == "connection refused"
    assert "mistral" in str(exc)


def test_provider_overloaded_is_not_provider_unavailable():
    """ProviderOverloaded и ProviderUnavailable — разные исключения."""
    ovl = ProviderOverloaded("anthropic")
    una = ProviderUnavailable("anthropic")

    assert not isinstance(ovl, ProviderUnavailable)
    assert not isinstance(una, ProviderOverloaded)
    assert isinstance(ovl, Exception)
    assert isinstance(una, Exception)
