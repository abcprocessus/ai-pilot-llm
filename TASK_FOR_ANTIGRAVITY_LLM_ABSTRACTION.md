# ЗАДАНИЕ ДЛЯ АНТИГРАВИТИ: AI PILOT LLM — Этап 1 (Multi-LLM абстракция)

> **Приоритет:** СТРАТЕГИЧЕСКИЙ
> **Цель:** Абстрагировать LLM-провайдер, чтобы агенты могли работать на Claude / Mistral / OpenAI / локальной модели
> **Срок:** 2 недели
> **Результат:** Все 9 агентов работают через абстрактный LLM provider. Claude = основной, Mistral = fallback для RU/BY клиентов

---

## ЗАЧЕМ

BY и RU в списке 20 запрещённых стран Anthropic. Сейчас 100% агентов зависят от Claude.
Если Anthropic заблокирует наш ключ — ВСЁ ляжет за секунду.

Multi-LLM даёт:
1. **Санкционная защита** — RU/BY клиенты через Mistral (Франция, 0 ограничений)
2. **Fallback** — если Claude API down → автопереключение на Mistral
3. **Подготовка к AI PILOT LLM** — своя модель подключится как ещё один провайдер
4. **Экономия** — простые запросы (FAQ, статус) можно отправлять на дешёвую модель

---

## ТЕКУЩАЯ АРХИТЕКТУРА (что менять)

### `v2/backend/app/ai/claude.py` — единственный LLM клиент
```
Экспортирует:
- chat(system_prompt, user_message, model, max_tokens, conversation_history) → dict
- chat_stream(same args) → AsyncGenerator[str]  (SSE events)
- classify(text, categories, model) → str
- chat_with_tools(system_prompt, user_message, tools, ...) → dict
- Константы: HAIKU, SONNET, OPUS, MODELS dict
- Singleton: get_claude() → AsyncAnthropic
```

### `v2/backend/app/agents/base.py` — базовый класс агентов
```python
# Строка 194: прямой вызов Claude
from ..ai.claude import chat as claude_chat
result = await claude_chat(system_prompt=..., user_message=..., model=self.model, ...)

# Строка 276: прямой вызов стриминга
from ..ai.claude import chat_stream
async for event in chat_stream(system_prompt=..., user_message=..., model=self.model, ...):

# self.model = "claude-sonnet" (строка 56)
```

### Агенты (все 9 файлов в `app/agents/`):
- `lisa.py`, `marina.py`, `iryna.py`, `leon.py`, `kira.py`, `vlad.py`, `daniil.py`, `anna.py`, `webmaster.py`
- Каждый задаёт `model = "claude-sonnet"` или `"claude-opus"` (webmaster)
- Некоторые переопределяют `process_message()` и вызывают `claude_chat` / `chat_with_tools` напрямую
- **boss.py** использует `chat_with_tools` (Tool Calling)

### `requirements.txt`:
```
anthropic==0.43.0   # единственный LLM SDK
```

---

## ЧТО СОЗДАТЬ

### 1. Папка `v2/backend/app/llm/`

```
v2/backend/app/llm/
├── __init__.py          # экспорт get_provider, ProviderType
├── base.py              # абстрактный LLMProvider
├── router.py            # выбор провайдера (по стране, agent_type, fallback)
├── anthropic_provider.py  # Claude (текущая логика из ai/claude.py)
├── mistral_provider.py    # Mistral Large / Small
├── openai_provider.py     # GPT-4o / o3 (опционально, можно stub)
└── local_provider.py      # vLLM / Ollama (stub для будущего AI PILOT LLM)
```

### 2. `base.py` — абстрактный класс

```python
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

class LLMProvider(ABC):
    """Абстрактный LLM провайдер — единый интерфейс для всех моделей."""

    name: str = "base"  # "anthropic", "mistral", "openai", "local"

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        max_tokens: int = 2048,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """
        Returns: {text, tokens_input, tokens_output, model, stop_reason, provider}
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
        """Yields SSE events: data: {type: delta/done/[DONE]}"""
        ...

    @abstractmethod
    async def classify(
        self,
        text: str,
        categories: list[str],
        model: str | None = None,
    ) -> str:
        """Quick classification — returns one category."""
        ...

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
        """Tool calling — по умолчанию NotImplementedError.

        Только Anthropic и OpenAI поддерживают нативно.
        Mistral и Local — через fallback (text → JSON parse).
        """
        raise NotImplementedError(f"{self.name} does not support tool calling")

    def supports_tools(self) -> bool:
        """True если провайдер поддерживает нативный Tool Calling."""
        return False

    def max_context_window(self) -> int:
        """Максимальное окно контекста в токенах."""
        return 128_000
```

### 3. `anthropic_provider.py`

**Перенести ВСЮЛОГИКУ из `ai/claude.py` сюда.**

```python
class AnthropicProvider(LLMProvider):
    name = "anthropic"

    # Model mapping
    MODELS = {
        "claude-haiku":  "claude-haiku-4-5-20251001",
        "claude-sonnet": "claude-sonnet-4-6",
        "claude-opus":   "claude-opus-4-6",
        # Алиасы
        "haiku":  "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus":   "claude-opus-4-6",
        # Кросс-провайдерные маппинги
        "fast":    "claude-haiku-4-5-20251001",     # самая дешёвая
        "default": "claude-sonnet-4-6",              # баланс
        "strong":  "claude-opus-4-6",                # самая умная
    }

    def supports_tools(self) -> bool:
        return True  # Claude нативно поддерживает

    # Реализация chat(), chat_stream(), classify(), chat_with_tools()
    # = текущий код из ai/claude.py
    # + добавить "provider": "anthropic" в каждый return dict
```

### 4. `mistral_provider.py`

```python
class MistralProvider(LLMProvider):
    name = "mistral"

    MODELS = {
        "fast":    "mistral-small-latest",    # дёшево, быстро
        "default": "mistral-large-latest",     # основная
        "strong":  "mistral-large-latest",     # лучшая у Mistral
        # Маппинг Claude-имён → Mistral
        "claude-haiku":  "mistral-small-latest",
        "claude-sonnet": "mistral-large-latest",
        "claude-opus":   "mistral-large-latest",
    }

    # API: https://api.mistral.ai/v1/chat/completions
    # Формат: OpenAI-compatible (messages array, system prompt в первом message)
    # SDK: pip install mistralai
    # ИЛИ httpx (проще, без лишних зависимостей):
    #   POST https://api.mistral.ai/v1/chat/completions
    #   Authorization: Bearer MISTRAL_API_KEY
    #   {"model": "mistral-large-latest", "messages": [...], "max_tokens": N, "stream": bool}

    def supports_tools(self) -> bool:
        return True  # Mistral Large поддерживает function calling
```

**ВАЖНО:** Mistral API = OpenAI-compatible формат. System prompt передаётся как `{"role": "system", "content": "..."}` в начале messages (НЕ отдельным полем как у Anthropic).

### 5. `openai_provider.py`

```python
class OpenAIProvider(LLMProvider):
    name = "openai"

    MODELS = {
        "fast":    "gpt-4o-mini",
        "default": "gpt-4o",
        "strong":  "o3",
        "claude-haiku":  "gpt-4o-mini",
        "claude-sonnet": "gpt-4o",
        "claude-opus":   "o3",
    }

    # SDK: pip install openai
    # ИЛИ httpx:
    #   POST https://api.openai.com/v1/chat/completions
    #   Authorization: Bearer OPENAI_API_KEY

    def supports_tools(self) -> bool:
        return True
```

### 6. `local_provider.py` (STUB)

```python
class LocalProvider(LLMProvider):
    """Провайдер для self-hosted моделей (vLLM / Ollama).

    Будет использоваться для AI PILOT LLM.
    Формат API: OpenAI-compatible (vLLM и Ollama оба поддерживают).
    """
    name = "local"

    MODELS = {
        "fast":    "ai-pilot-llm-1.0",
        "default": "ai-pilot-llm-1.0",
        "strong":  "ai-pilot-llm-1.0",
    }

    # URL: os.getenv("LOCAL_LLM_URL", "http://localhost:8000/v1/chat/completions")
    # Формат: OpenAI-compatible

    def supports_tools(self) -> bool:
        return False  # Пока нет
```

### 7. `router.py` — САМОЕ ВАЖНОЕ

```python
import os
import logging
from typing import Optional
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider
from .mistral_provider import MistralProvider

logger = logging.getLogger(__name__)

# Синглтоны провайдеров
_providers: dict[str, LLMProvider] = {}

# Страны с ограничениями Anthropic
ANTHROPIC_RESTRICTED = {"RU", "BY", "CN", "IR", "KP", "CU", "SY", "VE",
                         "MM", "SD", "SS", "ZW", "CF", "CD", "SO", "YE",
                         "LB", "LY", "IQ", "AF"}

def get_provider(
    client_country: str | None = None,
    agent_type: str | None = None,
    preferred: str | None = None,
) -> LLMProvider:
    """Выбрать LLM провайдер на основе контекста.

    Приоритет:
    1. preferred (явно указанный) — если передан
    2. Клиент из restricted страны → Mistral
    3. env var LLM_PROVIDER → глобальный override
    4. Claude (по умолчанию)
    5. Fallback: Mistral → OpenAI

    Returns:
        LLMProvider instance (singleton)
    """

    # 1. Явный override
    if preferred and preferred in _get_available():
        return _get_or_create(preferred)

    # 2. Restricted country → Mistral
    if client_country and client_country.upper() in ANTHROPIC_RESTRICTED:
        if _is_available("mistral"):
            logger.info(f"Client from {client_country} → routing to Mistral")
            return _get_or_create("mistral")

    # 3. Global env override
    env_provider = os.getenv("LLM_PROVIDER", "").lower()
    if env_provider and env_provider in _get_available():
        return _get_or_create(env_provider)

    # 4. Default: Claude
    if _is_available("anthropic"):
        return _get_or_create("anthropic")

    # 5. Fallback chain
    for fallback in ["mistral", "openai", "local"]:
        if _is_available(fallback):
            logger.warning(f"Anthropic unavailable, falling back to {fallback}")
            return _get_or_create(fallback)

    raise RuntimeError("No LLM provider available! Check API keys in env vars.")


def _is_available(provider_name: str) -> bool:
    """Проверить доступность провайдера (есть ли API ключ)."""
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "mistral":   "MISTRAL_API_KEY",
        "openai":    "OPENAI_API_KEY",
        "local":     "LOCAL_LLM_URL",
    }
    env_key = key_map.get(provider_name)
    return bool(env_key and os.getenv(env_key))


def _get_available() -> set[str]:
    """Список доступных провайдеров."""
    return {p for p in ["anthropic", "mistral", "openai", "local"] if _is_available(p)}


def _get_or_create(name: str) -> LLMProvider:
    """Получить или создать провайдер (singleton)."""
    if name not in _providers:
        if name == "anthropic":
            _providers[name] = AnthropicProvider()
        elif name == "mistral":
            _providers[name] = MistralProvider()
        elif name == "openai":
            from .openai_provider import OpenAIProvider
            _providers[name] = OpenAIProvider()
        elif name == "local":
            from .local_provider import LocalProvider
            _providers[name] = LocalProvider()
        else:
            raise ValueError(f"Unknown LLM provider: {name}")
    return _providers[name]
```

---

## ЧТО ИЗМЕНИТЬ (РЕФАКТОРИНГ)

### A. `app/ai/claude.py` → оставить как thin wrapper

**НЕ УДАЛЯТЬ** `ai/claude.py` — слишком много импортов по всему коду. Вместо этого:

```python
"""Backward-compatible wrapper — delegates to LLM provider system.

Все новые вызовы должны использовать:
    from app.llm import get_provider
    provider = get_provider(client_country=...)
    result = await provider.chat(...)

Этот файл сохранён для обратной совместимости.
"""
from ..llm.router import get_provider
from ..llm.anthropic_provider import AnthropicProvider

# Backward-compatible constants
HAIKU  = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS   = "claude-opus-4-6"
MODELS = AnthropicProvider.MODELS
DEFAULT_MODEL = "claude-sonnet"

async def chat(**kwargs) -> dict:
    provider = get_provider()  # default = Claude
    return await provider.chat(**kwargs)

async def chat_stream(**kwargs):
    provider = get_provider()
    async for event in provider.chat_stream(**kwargs):
        yield event

async def classify(**kwargs) -> str:
    provider = get_provider()
    return await provider.classify(**kwargs)

async def chat_with_tools(**kwargs) -> dict:
    provider = get_provider()
    return await provider.chat_with_tools(**kwargs)

# Legacy singleton
def get_claude():
    p = get_provider(preferred="anthropic")
    return p._client  # для прямого доступа если кто-то использует
```

### B. `app/agents/base.py` — добавить провайдер

В `process_message()` и `stream_message()` **добавить** параметр `client_country`:

```python
async def process_message(
    self,
    message: str,
    client_id: int,
    session_id: Optional[str] = None,
    tier: str = "free",
    client_country: Optional[str] = None,  # NEW
) -> dict:
    ...
    from ..llm.router import get_provider
    provider = get_provider(client_country=client_country, agent_type=self.agent_type)
    result = await provider.chat(
        system_prompt=system_prompt,
        user_message=message,
        model=self.model,
        max_tokens=2048,
        conversation_history=conversation_history,
    )
    ...
```

**То же самое для `stream_message()`.**

### C. `requirements.txt` — добавить

```
# Multi-LLM (Этап 1)
mistralai==1.5.0       # или httpx (уже есть) — выбрать один подход
# openai==1.60.0       # опционально, можно через httpx
```

**Рекомендация:** Mistral и OpenAI оба поддерживают OpenAI-compatible формат. Можно обойтись **только httpx** (уже в requirements) без отдельных SDK. Это уменьшает зависимости.

### D. ENV VARS — добавить в Railway + GKE

```env
# Существующие:
ANTHROPIC_API_KEY=sk-ant-...          # уже есть

# Новые:
MISTRAL_API_KEY=                       # Валерий создаёт на mistral.ai
# OPENAI_API_KEY=                      # опционально, потом
# LOCAL_LLM_URL=http://host:8000/v1    # для AI PILOT LLM (Этап 4)
# LLM_PROVIDER=                        # глобальный override (пусто = auto)
```

---

## МОДЕЛЬНЫЙ МАППИНГ (УНИВЕРСАЛЬНЫЙ)

Каждый агент задаёт `self.model = "claude-sonnet"`. Роутер маппит:

| Agent model | Anthropic | Mistral | OpenAI | Local |
|-------------|-----------|---------|--------|-------|
| `claude-haiku` / `fast` | Haiku 4.5 | mistral-small | gpt-4o-mini | ai-pilot-llm |
| `claude-sonnet` / `default` | Sonnet 4.6 | mistral-large | gpt-4o | ai-pilot-llm |
| `claude-opus` / `strong` | Opus 4.6 | mistral-large | o3 | ai-pilot-llm |

**Правило:** Агенты НЕ знают какой провайдер используется. Они задают уровень (`fast`/`default`/`strong`), роутер выбирает конкретную модель.

---

## ФОРМАТ ОТВЕТА (ЕДИНЫЙ)

Все провайдеры возвращают одинаковый dict:

```python
{
    "text": str,              # ответ модели
    "tokens_input": int,      # токены входа
    "tokens_output": int,     # токены выхода
    "model": str,             # реальный model_id
    "stop_reason": str,       # end_turn / max_tokens / tool_use
    "provider": str,          # "anthropic" / "mistral" / "openai" / "local"
}
```

---

## РАЗЛИЧИЯ МЕЖДУ API (АНТИГРАВИТИ — ЗАПОМНИ)

| Аспект | Anthropic | Mistral / OpenAI |
|--------|-----------|-----------------|
| System prompt | Отдельное поле `system=` | `{"role": "system"}` в messages |
| Streaming | `client.messages.stream()` context manager | `stream=True` в request body |
| Tool Calling | `tools=[{name, description, input_schema}]` | `tools=[{type:"function", function:{name, description, parameters}}]` |
| Stop reason | `stop_reason: "end_turn"` | `finish_reason: "stop"` |
| Response | `response.content[0].text` | `response.choices[0].message.content` |
| Token count | `response.usage.input_tokens` / `output_tokens` | `response.usage.prompt_tokens` / `completion_tokens` |

**Провайдер ОБЯЗАН нормализовать** ответ к единому формату (см. выше).

---

## ТЕСТИРОВАНИЕ

### Минимальный тест (обязательно):
```bash
# 1. Claude работает как раньше (регрессия):
curl -X POST https://ai-pilot-api-production.up.railway.app/api/v1/agents/lisa/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет", "client_id": 1}'
# Ожидание: 200 OK, ответ Лизы, provider: "anthropic"

# 2. Mistral fallback (когда будет ключ):
curl -X POST .../api/v1/agents/lisa/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет", "client_id": 1, "client_country": "RU"}'
# Ожидание: 200 OK, ответ через Mistral, provider: "mistral"

# 3. Streaming:
curl -N .../api/v1/agents/lisa/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет", "client_id": 1}'
# Ожидание: SSE events, type: delta/done/[DONE]
```

### Что НЕ должно сломаться:
- Все 9 агентов отвечают через chat и stream
- Boss Bot с Tool Calling работает
- Billing (use_agent_resource) работает
- Knowledge Base загружается
- Delegation [AGENT:xxx] работает

---

## ПОРЯДОК РАБОТЫ

1. **Создать** `app/llm/` с 6 файлами (base, router, anthropic, mistral, openai stub, local stub)
2. **Перенести** логику из `ai/claude.py` → `anthropic_provider.py`
3. **Сделать** `ai/claude.py` thin wrapper (backward compat)
4. **Реализовать** `mistral_provider.py` через httpx (OpenAI-compatible API)
5. **Добавить** `client_country` параметр в base.py process_message / stream_message
6. **Добавить** `mistralai` или использовать httpx в requirements.txt
7. **Создать** `do_copy.ps1` скрипт
8. **Тестировать** — все 9 агентов через Claude, затем Mistral (если ключ есть)

---

## КРИТЕРИИ ПРИЁМКИ

- [ ] `app/llm/` — 6 файлов созданы
- [ ] `anthropic_provider.py` — полная реализация (chat, stream, classify, tools)
- [ ] `mistral_provider.py` — рабочая реализация (chat, stream, classify)
- [ ] `router.py` — маршрутизация по стране + fallback chain
- [ ] `ai/claude.py` — thin wrapper, backward compat, все старые импорты работают
- [ ] `base.py` — client_country параметр, вызовы через provider
- [ ] Регрессия: все 9 агентов отвечают через Claude как раньше
- [ ] Provider field: каждый ответ содержит `"provider": "anthropic"/"mistral"/...`
- [ ] `do_copy.ps1` готов к запуску

---

## ФАЙЛЫ (для справки)

| Файл | Действие | Строки |
|------|----------|--------|
| `v2/backend/app/llm/__init__.py` | СОЗДАТЬ | ~10 |
| `v2/backend/app/llm/base.py` | СОЗДАТЬ | ~80 |
| `v2/backend/app/llm/router.py` | СОЗДАТЬ | ~100 |
| `v2/backend/app/llm/anthropic_provider.py` | СОЗДАТЬ | ~200 |
| `v2/backend/app/llm/mistral_provider.py` | СОЗДАТЬ | ~150 |
| `v2/backend/app/llm/openai_provider.py` | СОЗДАТЬ (stub) | ~50 |
| `v2/backend/app/llm/local_provider.py` | СОЗДАТЬ (stub) | ~50 |
| `v2/backend/app/ai/claude.py` | ИЗМЕНИТЬ → thin wrapper | ~40 |
| `v2/backend/app/agents/base.py` | ИЗМЕНИТЬ → provider routing | ~10 строк diff |
| `v2/backend/requirements.txt` | ДОБАВИТЬ mistralai или нет | 1 строка |

**Итого:** ~7 новых файлов, 2 изменённых.

---

---

## БОЛЬШАЯ КАРТИНА (для контекста Антигравити)

**Этот task (Этап 1) — фундамент для трёх продуктов AI PILOT:**

```
AI PILOT
├── 1. ПЛАТФОРМА (ai-pilot.by)              — 8 AI-сотрудников для бизнеса
│   └── Клиенты: бизнесы (€39-249/мес per agent)
│
├── 2. API (api.ai-pilot.by)                 — AI PILOT LLM для разработчиков
│   ├── console.ai-pilot.by                  — Developer Portal (ключи, биллинг, playground)
│   ├── docs.ai-pilot.by                     — Документация + SDK (Python/JS/PHP/1С)
│   ├── 7 модулей: Бухгалтерия/Юридика/Продажи/HR/Маркетинг/Реклама/Веб
│   └── Клиенты: разработчики 1С/CRM/LegalTech (€49-999/мес)
│
└── 3. ПРИЛОЖЕНИЕ (App Store / Google Play)  — AI PILOT Scanner
    ├── Камера → OCR → распознавание → автопроводки → экспорт в 1С
    └── Клиенты: бухгалтеры, юристы, менеджеры (Free → €9.99/мес)
```

**Ключевой рынок:** 1С-разработчики (500K человек, 6M компаний-пользователей).
Скан накладной → один API-вызов → готовые проводки. **Никто этого не делает.**

**Этап 1 (этот task) закладывает:**
- Абстрактный LLMProvider → потом подключится AI PILOT LLM (Этап 4)
- Единый формат ответа → потом станет публичным API (Этап 7)
- Router по стране → потом маршрутизация по сложности запроса (Этап 5)

**Детальный план всех 8 этапов:** `memory/llm-contingency-plan.md`

**Мнение Антигравити приветствуется:** что добавить, что улучшить, где мы заблуждаемся?

---

---

## ОТВЕТ НА КРИТИКУ АНТИГРАВИТИ (2026-03-03)

> Антигравити дал подробный разбор этого документа. Вот наш ответ и исправления.
> **Формат:** 🔴 = его критика → ✅ = наше исправление | ❌ = отвергнуто с пояснением

---

### 🔴 #1: GeoIP Middleware — `client_country` неоткуда взять
**Статус:** ✅ ПРИНЯТО — валидная критика

**Решение — GeoIP Middleware для FastAPI:**

```python
# v2/backend/app/middleware/geoip.py
"""GeoIP middleware — определяет страну клиента по IP.

Два источника (в порядке приоритета):
1. Cloudflare CF-IPCountry header (бесплатно, если трафик через CF)
2. ip-api.com fallback (бесплатно до 45 req/min, кеш 24h)
"""
import httpx
from functools import lru_cache
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Кеш IP→Country на 24 часа (макс 10K записей)
_ip_cache: dict[str, str] = {}
_MAX_CACHE = 10_000

class GeoIPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Cloudflare header (Railway/GKE с CF Proxy)
        country = request.headers.get("CF-IPCountry")

        # 2. X-Real-IP / X-Forwarded-For → ip-api.com
        if not country:
            ip = (
                request.headers.get("X-Real-IP")
                or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or request.client.host
            )
            country = await _resolve_country(ip)

        # Записываем в request.state — доступно во всех route handlers
        request.state.client_country = country or "XX"
        return await call_next(request)


async def _resolve_country(ip: str) -> str | None:
    """Определить страну по IP (кеш + ip-api.com fallback)."""
    if ip in _ip_cache:
        return _ip_cache[ip]

    # Не запрашиваем для localhost/private
    if ip.startswith(("127.", "10.", "192.168.", "172.")) or ip == "::1":
        return None

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip}?fields=countryCode")
            if resp.status_code == 200:
                code = resp.json().get("countryCode")
                if code and len(_ip_cache) < _MAX_CACHE:
                    _ip_cache[ip] = code
                return code
    except Exception:
        return None
```

**Подключение в `main.py`:**
```python
from app.middleware.geoip import GeoIPMiddleware
app.add_middleware(GeoIPMiddleware)
```

**Использование в route handler:**
```python
@router.post("/api/v1/agents/{agent_type}/chat")
async def agent_chat(request: Request, agent_type: str, body: ChatRequest):
    country = getattr(request.state, "client_country", None)
    provider = get_provider(client_country=country, agent_type=agent_type)
    ...
```

---

### 🔴 #2: requires_tools Guard — boss.py сломается на Mistral
**Статус:** ✅ ПРИНЯТО — критическая точка

Boss Bot использует `chat_with_tools()`. Если router пошлёт на провайдер без tool calling → crash.

**Решение — параметр `requires_tools` в router + guard:**

```python
# router.py — ОБНОВЛЁННЫЙ get_provider()

def get_provider(
    client_country: str | None = None,
    agent_type: str | None = None,
    preferred: str | None = None,
    requires_tools: bool = False,           # ← НОВЫЙ параметр
) -> LLMProvider:
    """Выбрать LLM провайдер с учётом capabilities.

    Если requires_tools=True — НИКОГДА не выдавать провайдер без supports_tools().
    """

    # Формируем кандидатов
    candidates = _build_candidate_list(client_country, preferred)

    # Фильтруем по capabilities
    if requires_tools:
        candidates = [c for c in candidates if _get_or_create(c).supports_tools()]
        if not candidates:
            raise RuntimeError(
                "No LLM provider available with tool calling support! "
                "Required for: boss, router agents."
            )

    return _get_or_create(candidates[0])
```

**Где вызывать с `requires_tools=True`:**
- `boss.py` → `get_provider(requires_tools=True)`
- Любой агент с Tool Calling (пока только Boss)

**ВАЖНО для Антигравити:** Mistral Large 2 **ПОДДЕРЖИВАЕТ** function calling (нативно), поэтому `supports_tools()=True` в `mistral_provider.py`. Проблема только с Local/stub провайдерами.

---

### 🔴 #3: Singleton State Leak — _providers dict не очищается
**Статус:** ✅ ПРИНЯТО

**Решение — lifespan cleanup в `main.py`:**

```python
# main.py
from contextlib import asynccontextmanager
from app.llm.router import cleanup_providers

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — ничего особенного
    yield
    # Shutdown — закрыть все httpx clients
    await cleanup_providers()

app = FastAPI(lifespan=lifespan)
```

```python
# router.py — добавить cleanup функцию
async def cleanup_providers():
    """Закрыть httpx clients при shutdown."""
    for name, provider in _providers.items():
        if hasattr(provider, "_client") and hasattr(provider._client, "close"):
            await provider._client.close()
    _providers.clear()
```

---

### 🟡 #4: Circuit Breaker — нет runtime fallback
**Статус:** ✅ ПРИНЯТО

Текущий `_is_available()` проверяет только наличие env var. Если Claude API лежит — мы это узнаём только по timeout.

**Решение — простой circuit breaker:**

```python
# router.py — добавить в начало файла
import time

# Circuit breaker state
_failure_counts: dict[str, int] = {}
_last_failure: dict[str, float] = {}
FAILURE_THRESHOLD = 3         # 3 фейла подряд → circuit open
RECOVERY_TIMEOUT = 60.0       # 60 сек → попробовать снова

def _is_circuit_open(provider_name: str) -> bool:
    """True если провайдер 'сломан' (3+ последних запроса failed)."""
    count = _failure_counts.get(provider_name, 0)
    if count < FAILURE_THRESHOLD:
        return False
    # Проверяем: прошло ли recovery_timeout
    last = _last_failure.get(provider_name, 0)
    if time.time() - last > RECOVERY_TIMEOUT:
        # Half-open: разрешаем одну попытку
        _failure_counts[provider_name] = 0
        return False
    return True

def record_success(provider_name: str):
    """Сбросить failure counter после успешного запроса."""
    _failure_counts[provider_name] = 0

def record_failure(provider_name: str):
    """Увеличить failure counter."""
    _failure_counts[provider_name] = _failure_counts.get(provider_name, 0) + 1
    _last_failure[provider_name] = time.time()
```

**Использование в base.py (после каждого LLM вызова):**
```python
try:
    result = await provider.chat(...)
    record_success(provider.name)
except Exception as e:
    record_failure(provider.name)
    # Retry с fallback провайдером
    fallback = get_provider(client_country=country, exclude=[provider.name])
    result = await fallback.chat(...)
```

---

### 🟡 #5: Cost Tracking / Observability
**Статус:** ✅ ПРИНЯТО

**Решение — добавить `cost_eur` в return dict + логирование:**

```python
# Каждый provider.chat() возвращает:
{
    "text": str,
    "tokens_input": int,
    "tokens_output": int,
    "model": str,
    "stop_reason": str,
    "provider": str,
    "cost_eur": float,         # ← НОВОЕ: расчёт стоимости
    "latency_ms": int,         # ← НОВОЕ: время запроса
}
```

**Таблица стоимостей (в router.py):**
```python
# EUR за 1M tokens (input / output)
COST_TABLE = {
    "anthropic": {
        "claude-haiku-4-5-20251001": (0.80, 4.00),
        "claude-sonnet-4-6":        (3.00, 15.00),
        "claude-opus-4-6":          (15.00, 75.00),
    },
    "mistral": {
        "mistral-small-latest":     (0.10, 0.30),
        "mistral-large-latest":     (2.00, 6.00),
    },
    "openai": {
        "gpt-4o-mini":              (0.15, 0.60),
        "gpt-4o":                   (2.50, 10.00),
    },
    "local": {},  # €0 (только GPU cost)
}
```

**Логирование в `agent_learning_log`:**
- Уже есть поля `tokens_used` — добавить `provider`, `cost_eur`, `latency_ms`

---

### 🟡 #6: Model IDs "вымышленные"
**Статус:** ❌ ОТВЕРГНУТО — Антигравити ошибается

> Антигравити написал что `claude-sonnet-4-6` и `claude-opus-4-6` — вымышленные модели.

**Это НЕПРАВДА.** Вот наш реальный код из `v2/backend/app/ai/claude.py` (строки 18-25):

```python
# Model mapping — актуальные версии (CLAUDE.md 2026-02-25)
MODELS = {
    "claude-haiku":        "claude-haiku-4-5-20251001",
    "claude-sonnet":       "claude-sonnet-4-6",
    "claude-opus":         "claude-opus-4-6",
    # Алиасы для обратной совместимости
    "claude-sonnet-4-5":   "claude-sonnet-4-6",   # старые agent классы → актуальная
    "claude-haiku-4-5":    "claude-haiku-4-5-20251001",
}
```

Эти модели **реально существуют** и используются в production на Railway прямо сейчас (март 2026).

**Причина ошибки Антигравити:** его знания обрезаны на начале 2025 года. Claude 4.5 вышел в октябре 2025, Claude 4.6 — в начале 2026. Антигравити просто не знает о них.

**Никаких изменений не нужно.** Model IDs корректны.

---

### 🟢 #7: 1С — синхронные endpoints
**Статус:** ✅ ПРИНЯТО — важное дополнение

1С (платформа 8.3.x) использует:
- `HTTP-Соединение` / `HTTPСоединение` — **синхронный**, блокирующий вызов
- НЕ поддерживает streaming, async, SSE, WebSocket
- Тайм-аут по умолчанию: 60 секунд

**Решение — отдельный синхронный endpoint `/api/v1/1c/*`:**

```python
# v2/backend/app/api/routes/integration_1c.py
"""
Синхронные endpoints для 1С:Предприятие.

1С НЕ умеет:
- Streaming (SSE)
- Async callbacks
- WebSocket
- Content-Type: text/event-stream

1С УМЕЕТ:
- POST/GET с JSON
- Basic Auth или Bearer token
- Таймаут до 60 сек
- Retry при ошибке

Поэтому: отдельные синхронные endpoints, ответ целиком.
"""
from fastapi import APIRouter, Request, Depends
from ..dependencies import verify_api_key

router = APIRouter(prefix="/api/v1/1c", tags=["1C Integration"])


@router.post("/recognize")
async def recognize_document_1c(
    request: Request,
    body: dict,
    api_key=Depends(verify_api_key),
):
    """Распознать документ — синхронный ответ целиком.

    Request (1С отправляет):
    {
        "image_base64": "...",      // фото документа
        "document_type": "invoice", // накладная/акт/счёт (опционально)
        "account_plan": "BY"        // BY или RU план счетов
    }

    Response (1С получает):
    {
        "document": {
            "type": "invoice",
            "number": "47",
            "date": "2026-03-15",
            "counterparty": "ООО Ромашка",
            "amount": 1500.00,
            "currency": "BYN",
            "vat": 250.00
        },
        "entries": [
            {"debit": "10.01", "credit": "60.01", "amount": 1250.00, "description": "Материалы"},
            {"debit": "18.01", "credit": "60.01", "amount": 250.00, "description": "НДС входящий"}
        ],
        "confidence": 0.94,
        "warnings": []
    }
    """
    # Вызов AI PILOT LLM (provider.chat, НЕ stream)
    from app.llm.router import get_provider
    provider = get_provider(agent_type="iryna")
    # ... OCR + проводки логика
    pass


@router.post("/classify")
async def classify_document_1c(
    body: dict,
    api_key=Depends(verify_api_key),
):
    """Классифицировать документ (тип, статья расхода, НДС).

    Быстрый endpoint — Haiku/Small модель, <2 сек.
    """
    pass


@router.post("/validate")
async def validate_entries_1c(
    body: dict,
    api_key=Depends(verify_api_key),
):
    """Проверить корректность проводок.

    1С отправляет предложенные проводки → AI проверяет по правилам учёта.
    """
    pass


@router.get("/health")
async def health_1c():
    """Health check — 1С может пинговать каждые N минут."""
    return {"status": "ok", "version": "1.0"}
```

**Регистрация в `main.py`:**
```python
from app.api.routes.integration_1c import router as router_1c
app.include_router(router_1c)
```

**Пример кода 1С (BSL) — из предложения Антигравити (доработанный):**

```bsl
// Конфигурация → Общие модули → мод_AIPILOT
Функция РаспознатьДокумент(Base64Фото, ТипДокумента = "") Экспорт

    Соединение = Новый HTTPСоединение("api.ai-pilot.by", 443,,, , 30, Новый ЗащищенноеСоединениеOpenSSL);

    Заголовки = Новый Соответствие;
    Заголовки.Вставить("Content-Type", "application/json");
    Заголовки.Вставить("Authorization", "Bearer " + мод_Настройки.ПолучитьAPIКлюч());

    ТелоJSON = Новый Структура;
    ТелоJSON.Вставить("image_base64", Base64Фото);
    ТелоJSON.Вставить("document_type", ТипДокумента);
    ТелоJSON.Вставить("account_plan", "BY");

    Запрос = Новый HTTPЗапрос("/api/v1/1c/recognize", Заголовки);
    Запрос.УстановитьТелоИзСтроки(
        мод_JSON.ОбъектВJSON(ТелоJSON),
        КодировкаТекста.UTF8,
        ИспользованиеByteOrderMark.НеИспользовать
    );

    Попытка
        Ответ = Соединение.ОтправитьДляОбработки(Запрос);
    Исключение
        ВызватьИсключение "AI PILOT API недоступен: " + ОписаниеОшибки();
    КонецПопытки;

    Если Ответ.КодСостояния = 200 Тогда
        Возврат мод_JSON.JSONВОбъект(Ответ.ПолучитьТелоКакСтроку());
    ИначеЕсли Ответ.КодСостояния = 429 Тогда
        ВызватьИсключение "Превышен лимит запросов AI PILOT. Повторите через минуту.";
    Иначе
        ВызватьИсключение "Ошибка AI PILOT: " + Ответ.КодСостояния;
    КонецЕсли;

КонецФункции
```

---

## ОБНОВЛЁННЫЙ ПОРЯДОК РАБОТЫ (с учётом критики)

1. **Создать** `app/middleware/geoip.py` — GeoIP middleware
2. **Создать** `app/llm/` с 6 файлами (base, router, anthropic, mistral, openai stub, local stub)
3. **Router:** circuit breaker + requires_tools guard + cost tracking
4. **Перенести** логику из `ai/claude.py` → `anthropic_provider.py`
5. **Сделать** `ai/claude.py` thin wrapper (backward compat)
6. **Реализовать** `mistral_provider.py` через httpx (OpenAI-compatible API)
7. **Добавить** `client_country` параметр в base.py + получать из request.state
8. **Добавить** lifespan cleanup в main.py
9. **Создать** `app/api/routes/integration_1c.py` — синхронные endpoints для 1С
10. **Добавить** `cost_eur` и `latency_ms` в return dict всех провайдеров
11. **Создать** `do_copy.ps1` скрипт
12. **Тестировать** — все 9 агентов через Claude, затем Mistral

---

## ОБНОВЛЁННЫЕ КРИТЕРИИ ПРИЁМКИ

- [ ] `app/middleware/geoip.py` — GeoIP middleware (CF-IPCountry + ip-api.com fallback)
- [ ] `app/llm/` — 6 файлов созданы
- [ ] `anthropic_provider.py` — полная реализация (chat, stream, classify, tools) + cost_eur
- [ ] `mistral_provider.py` — рабочая реализация (chat, stream, classify, tools via httpx)
- [ ] `router.py` — маршрутизация по стране + requires_tools guard + circuit breaker + fallback chain
- [ ] `ai/claude.py` — thin wrapper, backward compat, все старые импорты работают
- [ ] `base.py` — client_country параметр из request.state, вызовы через provider
- [ ] `main.py` — lifespan cleanup для providers
- [ ] `integration_1c.py` — /api/v1/1c/* синхронные endpoints (recognize, classify, validate, health)
- [ ] Cost tracking: каждый ответ содержит `cost_eur`, `latency_ms`, `provider`
- [ ] Регрессия: все 9 агентов отвечают через Claude как раньше
- [ ] Boss Bot: `requires_tools=True` — работает через Claude/Mistral Large
- [ ] `do_copy.ps1` готов к запуску

---

## ОЦЕНКА АНТИГРАВИТИ (наш комментарий)

| Его оценка | Наш комментарий |
|-----------|-----------------|
| Архитектура 9/10 | Согласны, фундамент хороший |
| Router 6/10 → **8/10** | С GeoIP + circuit breaker + requires_tools — значительно лучше |
| Tool Calling 5/10 → **8/10** | С requires_tools guard — Boss Bot защищён |
| Observability 4/10 → **7/10** | С cost_eur + latency_ms + provider в каждом ответе |
| 1С SDK 2/10 → **6/10** | С синхронными endpoints + BSL пример. Полный SDK = Этап 7 |
| Model IDs 3/10 → **10/10** | Он ошибся. Модели реальные, 2026 год. |

**Итого после исправлений:** средний балл ~8/10 (было ~5/10)

**Спасибо Антигравити** за конструктивную критику — 5 из 7 замечаний были валидными и улучшили план.

---

*Создано: Claude Code, 2026-03-03*
*Обновлено: 2026-03-03 (ответ на критику Антигравити)*
*Для: Антигравити (Gemini)*
*Проект: AI PILOT — AI PILOT LLM (Этап 1 из 8)*
