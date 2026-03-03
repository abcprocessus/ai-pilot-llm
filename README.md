# AI PILOT LLM — Multi-LLM Abstraction Project

> Отдельная директория для всего что связано с Multi-LLM абстракцией и будущим AI PILOT LLM.
> Основной проект: `C:\PROJETS AI PILOT\AI PILOT OOO\Projects AI\Site AI PILOT\`

## Структура

```
AI_PILOT_LLM/
├── README.md                              ← этот файл
├── TASK_FOR_ANTIGRAVITY_LLM_ABSTRACTION.md ← ТЗ для Антигравити (полное, с ответами на критику)
├── llm-contingency-plan.md                 ← стратегический план AI PILOT LLM (8 этапов, ~€700)
├── docs/                                   ← документация, спецификации
├── antigravity-output/                     ← сюда Антигравити кладёт do_copy.ps1 и готовый код
└── reviews/                                ← ревью кода (мои проверки перед копированием)
```

## Целевые файлы в основном проекте (v2/backend/)

| Файл | Действие | Описание |
|------|----------|----------|
| `app/llm/__init__.py` | СОЗДАТЬ | Пакет провайдеров |
| `app/llm/base.py` | СОЗДАТЬ | ABC LLMProvider |
| `app/llm/anthropic_provider.py` | СОЗДАТЬ | Claude (основной) |
| `app/llm/mistral_provider.py` | СОЗДАТЬ | Mistral (fallback EU) |
| `app/llm/openai_provider.py` | СОЗДАТЬ | OpenAI (fallback) |
| `app/llm/local_provider.py` | СОЗДАТЬ | Ollama (dev/test) |
| `app/llm/router.py` | СОЗДАТЬ | Маршрутизация + circuit breaker |
| `app/llm/cost_tracker.py` | СОЗДАТЬ | Учёт расходов |
| `app/middleware/geoip.py` | СОЗДАТЬ | GeoIP через CF-IPCountry + ip-api.com |
| `app/api/routes/integration_1c.py` | СОЗДАТЬ | 4 эндпоинта для 1С |
| `app/ai/claude.py` | ИЗМЕНИТЬ | Тонкая обёртка → LLMProvider |
| `app/agents/base.py` | ИЗМЕНИТЬ | cost_eur + latency_ms в route handler |
| `app/main.py` | ИЗМЕНИТЬ | _apply_komendant_bg → provider |

## Процесс

1. Антигравити пишет код в своём sandbox
2. Создаёт `do_copy.ps1` → кладёт в `antigravity-output/`
3. Claude Code проверяет → `reviews/`
4. Если OK → Claude Code запускает `do_copy.ps1`
5. Deploy на Railway

## СТОП-ПРАВИЛА для Антигравити

1. НЕ трогать файлы вне `v2/backend/`
2. НЕ удалять `claude.py` — только обернуть
3. НЕ менять сигнатуры `process_message()` / `stream_message()`
4. НЕ трогать конституции агентов
5. НЕ добавлять зависимости (httpx уже есть)
6. НЕ менять model ID (claude-sonnet-4-6, claude-opus-4-6 — реальные 2026)
7. НЕ запускать `do_copy.ps1` сам
8. НЕ деплоить — только Claude Code деплоит

## Статус

- [x] ТЗ написано и одобрено
- [x] Ревью Антигравити #1: 5/7 принято
- [x] Ревью Антигравити #2: 3/3 нюанса принято
- [x] Инструкция для Антигравити написана (8 стоп-правил + план)
- [ ] Антигравити реализует 7 шагов
- [ ] Claude Code проверяет
- [ ] Deploy на Railway
