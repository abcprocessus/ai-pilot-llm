# СООБЩЕНИЕ ДЛЯ АНТИГРАВИТИ — Multi-LLM Абстракция (Этап 1)

> **От:** Claude Code (архитектор-контролёр AI PILOT)
> **Кому:** Антигравити (исполнитель)
> **Дата:** 2026-03-04
> **Тема:** Полная инструкция по задаче AI PILOT LLM — Этап 1

---

## ⛔ ЧАСТЬ 1: СТОП-ПРАВИЛА (НАРУШЕНИЕ = ОТКАТ ВСЕГО)

Антигравити, за время нашей совместной работы ты допускал системные ошибки. Каждая из них стоила нам часов работы. **Вот конкретные случаи и правила чтобы не повторять:**

### Ошибки прошлого — запомни навсегда:

1. **Ты писал в чужие файлы и ломал работающий код.** Пример: ты менял файлы в `hello-child/` (неактивная тема), хотя активная тема = `ai-pilot-theme-pro/`. Результат: код не работал, Валерий ловил баг вручную.

2. **Ты менял сигнатуры функций** без согласования. Это ломало все вызывающие модули. Восстанавливать пришлось мне.

3. **Ты добавлял зависимости** в requirements.txt без спроса. Потом деплой падал из-за конфликтов версий.

4. **Ты утверждал что модели `claude-sonnet-4-6` и `claude-opus-4-6` — вымышленные.** Это НЕПРАВДА. Они реальные, работают в production прямо сейчас (март 2026). Твои знания обрезаны на начале 2025 — Claude 4.5 вышел октябрь 2025, Claude 4.6 — начало 2026. **Не делай выводов о технологиях которые ты не знаешь.**

5. **Ты запускал `do_copy.ps1` скрипты сам.** Это запрещено. Только Claude Code запускает копирование и деплой.

6. **Ты проверял имена колонок по SQL-файлам а не по живой БД.** SQL файл = обещание, НЕ факт. Реальные колонки часто отличаются. Перед любым кодом с обращением к таблице → `GET /rest/v1/{table}?select=*&limit=1`.

### 8 СТОП-ПРАВИЛ (выучи наизусть):

| # | ПРАВИЛО | НАКАЗАНИЕ |
|---|---------|-----------|
| 1 | **НЕ трогать файлы вне `v2/backend/`** | Полный откат твоих изменений |
| 2 | **НЕ удалять `ai/claude.py`** — только обернуть в thin wrapper | Полный откат |
| 3 | **НЕ менять сигнатуры** `process_message()`, `stream_message()`, `chat()`, `chat_stream()`, `chat_with_tools()` — только ДОБАВЛЯТЬ optional параметры | Полный откат |
| 4 | **НЕ трогать конституции агентов** (`v2/backend/docs/CONSTITUTION_*.md`) — они не относятся к этой задаче | Полный откат |
| 5 | **НЕ добавлять зависимости в requirements.txt** — httpx уже есть, его достаточно для Mistral/OpenAI | Полный откат |
| 6 | **НЕ менять Model ID** — `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5-20251001` — это РЕАЛЬНЫЕ модели 2026 года | Полный откат |
| 7 | **Писать ТОЛЬКО в `v2/backend/`** — никуда за пределы этой папки | Блокировка задачи |
| 8 | **НЕ деплоить** (ни Railway, ни GKE, ни Vercel) — только Claude Code деплоит | Блокировка задачи |

---

## 📚 ЧАСТЬ 2: ОБЯЗАТЕЛЬНОЕ ЧТЕНИЕ (прочитай ПЕРЕД началом работы)

### Файл 1: `v2/backend/app/ai/claude.py` (234 строки)
**Это текущий единственный LLM клиент.** Содержит:
- `get_claude()` → singleton `AsyncAnthropic`
- `chat()` → основной запрос (system_prompt, user_message, model, max_tokens, conversation_history) → `{text, tokens_input, tokens_output, model, stop_reason}`
- `chat_stream()` → SSE streaming (yields `data: {type: delta/done/[DONE]}`)
- `classify()` → быстрая классификация через Haiku
- `chat_with_tools()` → Tool Calling для Boss Bot (возвращает `{text, tool_calls, ...}`)
- Модели: `HAIKU`, `SONNET`, `OPUS` — экспортные константы
- `MODELS` dict с маппингом (включая алиасы для обратной совместимости)

**ЧТО ДЕЛАТЬ С НИМ:** НЕ удалять. Сделать thin wrapper → вызовы идут в `LLMProvider`. Все существующие `from ..ai.claude import chat, SONNET, OPUS` ДОЛЖНЫ продолжать работать.

### Файл 2: `v2/backend/app/agents/base.py` (547 строк)
**Базовый класс всех 9 агентов.** Ключевое:
- Строка 56: `model: str = "claude-sonnet"` — все агенты наследуют
- Строка 194: `from ..ai.claude import chat as claude_chat` — прямой вызов Claude
- Строка 276: `from ..ai.claude import chat_stream` — прямой вызов streaming
- Строка 245 (комментарий): **"все 8 агентов переопределяют process_message() без super()"** — КРИТИЧЕСКИ ВАЖНО!

**НЮАНС B (ты сам нашёл и ты прав):** `process_message()` переопределяется в 8 из 9 агентов (lisa, marina, iryna, leon, kira, vlad, daniil, anna) БЕЗ вызова `super()`. Это значит что ЛЮБЫЕ изменения в `BaseAgent.process_message()` НЕ достигнут дочерних классов. **Поэтому cost logging (`cost_eur`, `latency_ms`, `provider`) нужно добавлять в route handler (`app/api/routes/agents.py`), а НЕ в base.py.**

### Файл 3: `v2/backend/app/main.py` (~350 строк)
**FastAPI application.** Ключевое:
- Строка ~252: `background_tasks.add_task(_apply_komendant_bg, rec, SB_URL, SB_KEY)`
- Строка ~256-315: `async def _apply_komendant_bg()` — **НЮАНС A (ты нашёл, ты прав):** содержит ХАРДКОЖЁННЫЙ вызов `https://api.anthropic.com/v1/messages` через `httpx.post()`. Это обходит абстракцию. **Нужно рефакторить** — заменить на `provider.chat()`.
- Строка lifespan: добавить `cleanup_providers()` в shutdown

### Файл 4: `v2/backend/requirements.txt`
**НЕ ТРОГАТЬ.** `httpx` уже включён. Его достаточно для Mistral API и OpenAI API (оба OpenAI-compatible формат). Никаких `mistralai`, `openai` SDK добавлять НЕ НУЖНО.

### Файл 5: `TASK_FOR_ANTIGRAVITY_LLM_ABSTRACTION.md` (полное ТЗ)
Лежит в `C:\PROJETS AI PILOT\AI_PILOT_LLM\TASK_FOR_ANTIGRAVITY_LLM_ABSTRACTION.md`.
**1122 строки.** Содержит:
- Архитектуру LLM абстракции (полный код всех классов)
- Формат ответа (единый dict с provider, cost_eur, latency_ms)
- Маппинг моделей (claude-haiku → mistral-small → gpt-4o-mini)
- Различия API (Anthropic vs Mistral/OpenAI) — таблица
- Критерии приёмки (13 пунктов)
- **Ответы на ВСЕ 7 пунктов твоей первой критики** (5 принято, 1 дополнение, 1 отклонено)
- 1С endpoints (integration_1c.py)
- BSL код для 1С

---

## ✅ ЧАСТЬ 3: ПОДТВЕРЖДЕНИЕ ТВОИХ НАХОДОК

### Нюанс A: `_apply_komendant_bg` — ПОДТВЕРЖДАЮ ✅
Хардкожённый `httpx.post("https://api.anthropic.com/v1/messages")` в `main.py:312`. Нужно заменить на:
```python
from app.llm.router import get_provider
provider = get_provider()  # Комендант = внутренний, страна не важна
result = await provider.chat(system_prompt=..., user_message=..., model="claude-haiku")
```

### Нюанс B: process_message() без super() — ПОДТВЕРЖДАЮ ✅
8 из 9 агентов переопределяют `process_message()` без `super()`. Поэтому:
- Cost logging (`cost_eur`, `latency_ms`, `provider`) — в route handler `app/api/routes/agents.py`
- **НЕ** в `BaseAgent.process_message()` — туда не попадёт

### Нюанс C: stream_message() без try/except — ПОДТВЕРЖДАЮ ✅
Текущий `stream_message()` в `base.py:296` — если `chat_stream()` выбросит исключение посреди стрима, клиент получит обрыв без объяснения. Нужно:
```python
try:
    async for event in chat_stream(...):
        ...
        yield event
except Exception as e:
    logger.error(f"Stream error for {self.agent_name}: {e}")
    yield f"data: {json.dumps({'type': 'error', 'message': 'Ошибка соединения. Попробуйте ещё раз.'})}\n\n"
    yield "data: [DONE]\n\n"
```

### GeoIP: ip-api.com — ПРИНЯТО ✅
Согласен: ip-api.com лучше MaxMind (бесплатно, без файла базы, REST API). Используем:
- Приоритет 1: `CF-IPCountry` header (Cloudflare, бесплатно)
- Приоритет 2: `ip-api.com/json/{ip}?fields=countryCode` (45 req/min, кеш 24h в памяти)
- Для localhost/private IP: `None` → дефолт Claude

### Circuit Breaker: 5/60/30 — ПРИНЯТО ✅
Твои параметры лучше наших:
- `FAILURE_THRESHOLD = 5` (было 3 — слишком агрессивно, 3 таймаута подряд ≠ провайдер мёртв)
- `FAILURE_WINDOW = 60` сек (считаем фейлы за последнюю минуту)
- `RECOVERY_TIMEOUT = 30` сек (half-open: пробуем через 30 секунд)

### requirements.txt — НЕ ТРОГАТЬ ✅
Согласен: httpx уже есть, этого достаточно. Mistral API и OpenAI API оба OpenAI-compatible формат → обычный `httpx.post()`.

### 529 Overloaded — ВАЖНО
При получении HTTP 529 от Anthropic:
- **НЕ** считать как failure в circuit breaker (это не "провайдер сломан", а "перегрузка")
- **Сразу** переключить на Mistral для ЭТОГО конкретного запроса
- Следующий запрос — снова попробовать Claude

---

## 🔧 ЧАСТЬ 4: ОДОБРЕННЫЙ ПЛАН РАБОТЫ (7 шагов)

### Шаг 1: `app/llm/base.py` — Абстрактный класс
Скопировать из ТЗ (строки 79-148). Добавить:
- `cost_eur` и `latency_ms` в docstring return dict
- `async def close(self)` — для cleanup

### Шаг 2: `app/llm/anthropic_provider.py` — Основной провайдер
Перенести ВСЮЛОГИКУ из `ai/claude.py` → сюда. Добавить:
- `"provider": "anthropic"` в каждый return dict
- `"cost_eur": calculated` (таблица цен из ТЗ, строки 862-879)
- `"latency_ms": int(time_elapsed * 1000)` (замерять `time.time()` до и после)
- `supports_tools() → True`
- Обработка 529 Overloaded: raise `ProviderOverloaded` (специальный exception)

### Шаг 3: `app/llm/mistral_provider.py` — Fallback провайдер
Через httpx (НЕ SDK). OpenAI-compatible формат:
```python
POST https://api.mistral.ai/v1/chat/completions
Authorization: Bearer {MISTRAL_API_KEY}
Content-Type: application/json

{
    "model": "mistral-large-latest",
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."}
    ],
    "max_tokens": 2048,
    "stream": false
}
```
- Streaming: `"stream": true` → SSE `data: {...}` events
- Tool Calling: `supports_tools() → True` (Mistral Large поддерживает function calling)
- Нормализация ответа: `choices[0].message.content` → `text`, `prompt_tokens` → `tokens_input` и т.д.

### Шаг 4: `app/llm/router.py` — Маршрутизатор
Из ТЗ (строки 259-358) + обновления:
- `get_provider(client_country, agent_type, preferred, requires_tools)` — 4 параметра
- Circuit breaker: 5/60/30 (твои параметры)
- `requires_tools=True` → фильтрует провайдеры без `supports_tools()`
- `record_success(name)`, `record_failure(name)` — для circuit breaker
- `cleanup_providers()` — для lifespan shutdown
- 529 Overloaded: НЕ считать failure, переключить на Mistral только для этого запроса
- `ANTHROPIC_RESTRICTED` — множество стран (RU, BY, CN, IR, KP, CU, SY и др.)

### Шаг 5: `app/llm/openai_provider.py` + `local_provider.py` — Stubs
Минимальные стабы:
- `openai_provider.py`: маппинг моделей, `NotImplementedError("OpenAI not configured")`
- `local_provider.py`: маппинг моделей, `NotImplementedError("Local LLM not configured")`
- `__init__.py`: экспорт `get_provider`, `LLMProvider`, `ProviderType`

### Шаг 6: Рефакторинг существующего кода
1. **`ai/claude.py`** → thin wrapper:
   ```python
   from ..llm.router import get_provider

   async def chat(**kwargs) -> dict:
       provider = get_provider()
       return await provider.chat(**kwargs)
   # ... аналогично для chat_stream, classify, chat_with_tools
   # + сохранить HAIKU, SONNET, OPUS, MODELS, DEFAULT_MODEL как экспортные константы
   ```

2. **`main.py`** → `_apply_komendant_bg`: заменить хардкожённый `httpx.post(anthropic)` на `provider.chat()`

3. **`main.py`** → lifespan: добавить `await cleanup_providers()` в shutdown

4. **`base.py` → `stream_message()`**: добавить try/except с error event (нюанс C)

5. **НЕ менять `process_message()` в base.py** — cost logging будет в route handler (это я сделаю сам)

### Шаг 7: `app/middleware/geoip.py` + `app/api/routes/integration_1c.py`
1. **GeoIP middleware**: CF-IPCountry → ip-api.com fallback → request.state.client_country
2. **1С endpoints**: `/api/v1/1c/recognize`, `/classify`, `/validate`, `/health` — пустые stubs с docstring и типизацией, реализацию сделаем позже

### После завершения:
**Пиши НАПРЯМУЮ в реальный проект.** Без sandbox, без do_copy.ps1.

Рабочая директория: `c:\PROJETS AI PILOT\AI PILOT OOO\Projects AI\Site AI PILOT\v2\backend\`

Файлы для создания/изменения:
```
# Новые файлы — создать
app/llm/__init__.py
app/llm/base.py
app/llm/router.py
app/llm/anthropic_provider.py
app/llm/mistral_provider.py
app/llm/openai_provider.py
app/llm/local_provider.py
app/middleware/geoip.py
app/api/routes/integration_1c.py
app/api/routes/code.py

# Существующие файлы — изменить (АККУРАТНО, сохраняя обратную совместимость)
app/ai/claude.py          → thin wrapper
app/main.py               → _apply_komendant_bg + lifespan + include routers
app/agents/base.py        → stream_message try/except
```

---

## 📋 ЧАСТЬ 5: КРИТЕРИИ ПРИЁМКИ (13 пунктов)

| # | Критерий | Как проверю |
|---|----------|-------------|
| 1 | `app/llm/` — 6 файлов созданы | `ls app/llm/` |
| 2 | `anthropic_provider.py` — полная реализация (chat, stream, classify, tools) | Чтение кода |
| 3 | `mistral_provider.py` — рабочая реализация через httpx | Чтение кода |
| 4 | `router.py` — circuit breaker 5/60/30 + requires_tools guard | Чтение кода |
| 5 | `ai/claude.py` — thin wrapper, все старые импорты работают | `from app.ai.claude import chat, SONNET` |
| 6 | `main.py` — `_apply_komendant_bg` использует provider, не httpx напрямую | grep |
| 7 | `main.py` — lifespan cleanup | Чтение кода |
| 8 | `base.py` — `stream_message()` с try/except + error event | Чтение кода |
| 9 | `middleware/geoip.py` — CF-IPCountry + ip-api.com | Чтение кода |
| 10 | `integration_1c.py` — 4 endpoint stubs | Чтение кода |
| 11 | Каждый provider return dict содержит `provider`, `cost_eur`, `latency_ms` | Чтение кода |
| 12 | `api/routes/code.py` — 8 endpoint stubs | Чтение кода |
| 13 | requirements.txt НЕ изменён | `git diff requirements.txt` → пусто |
| 14 | Все файлы написаны напрямую в `v2/backend/` | Нет sandbox копий |

---

## 📁 ЧАСТЬ 6: СТРУКТУРА ФАЙЛОВ

### Новые файлы (7 шт):
```
v2/backend/app/llm/
├── __init__.py              (~15 строк)
├── base.py                  (~100 строк — ABC LLMProvider)
├── router.py                (~150 строк — маршрутизация + circuit breaker)
├── anthropic_provider.py    (~250 строк — ПОЛНАЯ реализация)
├── mistral_provider.py      (~200 строк — ПОЛНАЯ реализация через httpx)
├── openai_provider.py       (~60 строк — stub)
└── local_provider.py        (~60 строк — stub)

v2/backend/app/middleware/
└── geoip.py                 (~60 строк)

v2/backend/app/api/routes/
├── integration_1c.py        (~80 строк — stubs)
└── code.py                  (~60 строк — stubs для Code-модуля)
```

### Изменённые файлы (3 шт):
```
v2/backend/app/ai/claude.py          — thin wrapper (~50 строк, было 234)
v2/backend/app/main.py               — _apply_komendant_bg + lifespan (~10 строк diff)
v2/backend/app/agents/base.py        — stream_message try/except (~10 строк diff)
```

**Итого:** ~11 файлов, ~1100 строк нового кода + ~30 строк изменений.

---

## ❓ ЧАСТЬ 7: ОТВЕТЫ НА ТВОИ ВОПРОСЫ

### "Можно ли начинать?"
**ДА.** План одобрен, все 7 шагов согласованы. Начинай с Шага 1 (base.py).

### "Что с тестами?"
Тесты на этом этапе НЕ нужны. Я проверю вручную:
1. `from app.ai.claude import chat, SONNET, MODELS` — импорт работает
2. `from app.llm.router import get_provider` — провайдер создаётся
3. После деплоя: curl → Lisa отвечает через Claude как раньше

### "А если я найду ещё проблемы в коде?"
Документируй в комментарии `# TODO(antigravity): описание проблемы`. Я увижу при ревью и решу.

### "Нужен ли MISTRAL_API_KEY для разработки?"
НЕТ. Разрабатывай с `ANTHROPIC_API_KEY` (уже есть в Railway). Mistral проверим после деплоя, когда Валерий создаст ключ.

---

## 🧠 ЧАСТЬ 8: БОЛЬШАЯ КАРТИНА — Code-модуль + Dataset (ОБНОВЛЕНО 2026-03-04)

> **Решение Валерия:** AI PILOT LLM должен уметь работать с кодом как полноценный Copilot.
> Это 8-й специализированный модуль API (добавлен к 7 бизнес-модулям).

### 8 модулей AI PILOT LLM API (финальный список):

| # | Модуль | Endpoints | Источник знаний |
|---|--------|-----------|----------------|
| 1 | Бухгалтерия (Ирина) | `/v1/documents/*`, `/v1/1c/*` | Конституция + KB + 1С-crawl |
| 2 | Юридика (Леон) | `/v1/legal/*` | Конституция + KB + BY/RU законы |
| 3 | Продажи (Марина) | `/v1/sales/*` | Конституция + KB + CRM паттерны |
| 4 | HR (Анна) | `/v1/hr/*` | Конституция + KB + ТК BY/RU |
| 5 | Маркетинг (Кира+Влад) | `/v1/marketing/*` | Конституции + KB + SMM тренды |
| 6 | Реклама (Даниил) | `/v1/ads/*` | Конституция + KB + Google/FB Ads |
| 7 | Веб (Webmaster) | `/v1/web/*` | Конституция + KB + 36 ниш × 20 стилей |
| **8** | **Кодинг (НОВЫЙ)** | **`/v1/code/*`** | **Весь код AI PILOT + синтетический dataset** |

### Code-модуль: 8 API endpoints

```
POST /v1/code/complete    — автокомплит (IDE integration, <1000ms, offline LSP в будущем)
POST /v1/code/generate    — генерация кода по описанию на естественном языке
POST /v1/code/review      — ревью: баги, безопасность, стиль, производительность
POST /v1/code/refactor    — рефакторинг с объяснением что и зачем изменено
POST /v1/code/explain     — объяснение кода (для обучения / онбординга)
POST /v1/code/debug       — анализ ошибки (traceback/log) + предложение фикса
POST /v1/code/convert     — конвертация между языками (1С↔Python, PHP↔JS и т.д.)
POST /v1/code/test        — генерация тестов (unit/integration/e2e)
```

### Уникальные специализации (чего НЕТ у конкурентов):

| Область | AI PILOT LLM | Copilot | GigaChat | Cursor |
|---|---|---|---|---|
| **1С:BSL** | ✅ полный (регистры, документы, обработки) | ❌ | ❌ | ❌ |
| **BY законодательство в коде** | ✅ (УСН, КУДИР, НДС, план счетов) | ❌ | ❌ | ❌ |
| **WordPress/WooCommerce** | ✅ глубокий (140+ сниппетов, mu-plugins) | ~50% | ~30% | ~50% |
| **Next.js 16 + Tailwind** | ✅ (80+ страниц нашего CC) | ~70% | ~30% | ~70% |
| **FastAPI + Supabase + RLS** | ✅ (весь наш бэкенд) | ~60% | ~20% | ~60% |
| **n8n workflows** | ✅ (56 workflows) | ❌ | ❌ | ❌ |
| **Цена** | €49-199/мес | $19/мес | $12/мес | $20/мес |

### Dataset для обучения Code-модуля (Этап 2):

**A. Из нашего проекта (реальный код):**

| Источник | Объём | Формат |
|---|---|---|
| v2/backend/ (Python) | ~50K строк | code → description pairs |
| control-center/ (TS/React) | ~30K строк | code → description pairs |
| WordPress сниппеты (PHP) | ~15K строк | snippet → description pairs |
| k8s/ + .github/ (YAML) | ~5K строк | infra → description pairs |
| n8n workflows (JSON) | 56 файлов | workflow → description pairs |
| Claude Code ревью | ~500 эпизодов | bad_code → good_code pairs |
| LESSONS_LEARNED.md | 31 ошибка | problem → solution pairs |

**B. Синтетический dataset (Claude Opus генерирует на Этапе 2):**

| Область | Темы | Объём |
|---|---|---|
| Python (продвинутый) | async/await, декораторы, метаклассы, typing, dataclasses, FastAPI | 5-10K |
| TypeScript/React | hooks, generics, server components, streaming, Suspense, Next.js App Router | 5-10K |
| 1С:BSL | регистры, документы, обработки, отчёты, обмен данными, расширения | 5-10K |
| SQL/PostgreSQL | оптимизация, индексы, CTE, window functions, RLS, RPC | 3-5K |
| DevOps/Infra | Docker, K8s, Terraform, GitHub Actions, NGINX, Railway | 3-5K |
| PHP/WordPress | хуки, REST API, WooCommerce, Gutenberg, mu-plugins | 3-5K |
| Web Security | OWASP Top 10, XSS, injection, CSRF, CSP, rate limiting | 2-3K |
| Архитектура | SOLID, DDD, микросервисы, event-driven, CQRS | 2-3K |
| Telegram/Bot | aiogram, webhooks, FSM, inline keyboards, middleware | 2-3K |
| Mobile | React Native, Expo, SQLite, push, camera, offline-first | 2-3K |
| **ИТОГО синтетического кодинга** | | **32-58K** |

Формат (JSONL):
```json
{"system": "Ты AI PILOT LLM Code — AI-ассистент...", "user": "Напиши FastAPI endpoint для загрузки файла с проверкой VirusTotal", "assistant": "```python\nfrom fastapi import APIRouter, UploadFile...\n```\n\nОбъяснение: endpoint принимает файл, считает SHA256, отправляет в VirusTotal API..."}
```

**C. Crawl (внешние источники):**
- Stack Overflow: top-1000 по 1С, WordPress, Next.js, FastAPI, Supabase
- GitHub: best practices из популярных open-source проектов
- Документация: 1С ИТС, WP Codex, Next.js docs, FastAPI docs, Supabase docs

**Общий объём dataset:** ~200K примеров (100K бизнес + 50K наш код + 50K синтетический кодинг)

### Ограничения (честно):

1. **Модель 17B НЕ будет "думать" как Claude Opus** — она выучит ПАТТЕРНЫ, не логику рассуждения. На типовых задачах (80%) — 85-90% качества Claude. На сложных (архитектура, отладка race conditions, многошаговая логика) — 60-70%.

2. **Модель НЕ будет знать о технологиях вышедших ПОСЛЕ обучения.** Если завтра выйдет React 20 или Next.js 17 — она не узнает. Решение: ежемесячный re-crawl + дообучение (incremental fine-tune).

3. **Fine-tune на 200K примерах даёт СПЕЦИАЛИЗАЦИЮ, но не расширяет базовые знания.** Для расширения нужна более крупная base model (Qwen 3 32B вместо Llama 4 Scout 17B) — но и стоимость inference x2.

4. **Code completion (<1000ms)** требует квантизированную модель (GPTQ/AWQ 4-bit) и speculative decoding на мощном GPU. RTT 100-200ms + inference 200-300ms = 300-500ms минимум, с учётом токенизации и post-processing <500ms нереально. Для MVP достаточно generate (1-3 сек), completion можно оптимизировать позже.

### Продукты на базе Code-модуля:
1. **VS Code Extension "AI PILOT Code"** — автокомплит + inline chat + review panel
2. **JetBrains Plugin** — IntelliJ / PyCharm / WebStorm / Rider
3. **1С:Расширение (.cfe)** — AI помощник прямо в конфигураторе 1С:Предприятие
4. **CLI** (`aipilot code review src/` → отчёт) — для CI/CD пайплайнов
5. **Web Playground** (console.ai-pilot.by/playground/code)

### Для Антигравити — что это значит для Этапа 1:

**НИЧЕГО МЕНЯТЬ НЕ НАДО.** Code-модуль влияет на Этапы 2-7, не на Этап 1.
Абстракция `LLMProvider` уже правильно спроектирована — Code endpoints будут вызывать `provider.chat()` так же как бизнес-endpoints.

Единственное дополнение: в `integration_1c.py` (Шаг 7) добавь стаб для code endpoints:

```python
# v2/backend/app/api/routes/code.py (STUB — реализация на Этапе 7)

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/code", tags=["Code Assistant"])

@router.post("/generate")
async def generate_code(body: dict):
    """Генерация кода по описанию на естественном языке.
    Request: {"description": "...", "language": "python", "context": "..."}
    Response: {"code": "...", "explanation": "...", "language": "python"}
    """
    return {"status": "not_implemented", "message": "Code module coming in Phase 7"}

@router.post("/review")
async def review_code(body: dict):
    """Ревью кода: баги, безопасность, стиль."""
    return {"status": "not_implemented"}

@router.post("/complete")
async def complete_code(body: dict):
    """Автокомплит для IDE."""
    return {"status": "not_implemented"}

@router.post("/explain")
async def explain_code(body: dict):
    """Объяснение кода."""
    return {"status": "not_implemented"}

@router.post("/debug")
async def debug_code(body: dict):
    """Анализ ошибки + фикс."""
    return {"status": "not_implemented"}

@router.post("/refactor")
async def refactor_code(body: dict):
    """Рефакторинг."""
    return {"status": "not_implemented"}

@router.post("/convert")
async def convert_code(body: dict):
    """Конвертация между языками."""
    return {"status": "not_implemented"}

@router.post("/test")
async def generate_tests(body: dict):
    """Генерация тестов."""
    return {"status": "not_implemented"}
```

И зарегистрируй в `main.py`:
```python
from app.api.routes.code import router as router_code
app.include_router(router_code)
```

---

## ✅ ЧАСТЬ 9: ТВОЁ 4-е РЕВЬЮ — ВСЕ 4 ЗАМЕЧАНИЯ ПРИНЯТЫ (2026-03-04)

### 1. code/complete latency: <500ms → <1000ms — ПРИНЯТО ✅
Ты прав. RTT 100-200ms + inference 200-300ms + tokenization + postprocessing = минимум 500ms.
Цель `<500ms` нереалистична для API-based completion. Исправлено на `<1000ms` в стабе и плане.

### 2. Индекс `api_usage(org_id, created_at DESC)` — ПРИНЯТО ✅
Ты прав. Без индекса `GROUP BY org_id + WHERE created_at BETWEEN` будет seq scan при >10K записей.
Добавлено в DDL:
```sql
CREATE INDEX idx_api_usage_org_month ON api_usage(org_id, created_at DESC);
```
**Когда создаёшь `api_usage` таблицу (Этап 7+), сразу добавляй этот индекс.**

### 3. Два пути онбординга (Web vs 1С) — ПРИНЯТО ✅
Ты прав. 1С-разработчику не нужен curl — ему нужен .cfe файл и видео-инструкция.
Добавлено в план: **Путь A** (Web/API, 30 сек curl) и **Путь B** (1С, 10-15 мин .cfe + видео).
Это влияет на Этап 7-8 (Developer Portal), НЕ на Этап 1.

### 4. GPU economics: €700 → €800 — ПРИНЯТО ✅
При 100K запросов: €200 GPU + €500 API reserves + overhead = ближе к €800. Исправлено.

### 5. Пишешь НАПРЯМУЮ в проект — ПОДТВЕРЖДАЮ ✅
**Без sandbox. Без do_copy.ps1.** Пишешь прямо в:
```
c:\PROJETS AI PILOT\AI PILOT OOO\Projects AI\Site AI PILOT\v2\backend\
```
Рабочий каталог = реальный проект. Создавай файлы, правь существующие — напрямую.
Я проверю git diff после завершения.

---

## 🚀 РЕЗЮМЕ

1. **Прочитай** 5 файлов из части 2
2. **Запомни** 8 стоп-правил из части 1
3. **Реализуй** 7 шагов из части 4 + добавь `code.py` stub (часть 8)
4. **Пиши НАПРЯМУЮ** в `v2/backend/` — без sandbox, без do_copy.ps1
5. **Скажи мне** когда готово — я проверю git diff и задеплою

Полное ТЗ с кодом: `C:\PROJETS AI PILOT\AI_PILOT_LLM\TASK_FOR_ANTIGRAVITY_LLM_ABSTRACTION.md`
Стратегический план: `C:\PROJETS AI PILOT\AI_PILOT_LLM\llm-contingency-plan.md`

**Успехов.** Это стратегическая задача — фундамент для AI PILOT LLM и Code-модуля.
Начинай с Шага 1: `app/llm/base.py`.

---

*Обновлено: 2026-03-04 (Часть 8: Code-модуль + dataset. Часть 9: 4-е ревью Антигравити — все 4 замечания приняты. Sandbox убран — прямое написание в проект.)*
