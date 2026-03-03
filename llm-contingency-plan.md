# СТРАТЕГИЯ LLM: Multi-Provider + Собственная модель AI PILOT LLM

> Создано: 2026-03-03. Обновлено: 2026-03-04. 15 секций: Multi-LLM + Dataset + Fine-tune + Deploy + Router + RLHF + Portal + App + Voice(32 lang) + Translator + Content + Encrypt + Training + Modes + Documents + Freshness + Agent Mesh + Memory + Billing Gate (3 подписки).
> **ПРИОРИТЕТ:** Не просто страховка — стратегическое направление развития AI PILOT.
> BY входит в список 20 запрещённых стран Anthropic → собственная модель = независимость + конкурентное преимущество.
> **Название модели:** AI PILOT LLM (версии: 1.0, 1.5, 2.0...)

---

## ТЕКУЩАЯ СИТУАЦИЯ

### Факты
- **BY и RU** в списке 20 запрещённых стран Anthropic (наряду с CN, IR, KP, CU и др.)
- Terms of Service (сент. 2025): запрет для компаний >50% owned by residents of restricted countries
- Три уровня блокировки: IP (весь сеанс), регистрация (+375 не принимается), оплата (BY карты)
- Сейчас работает: серверы в EU (Railway/GKE), API ключ оплачен — Anthropic пока не проверяет UBO
- **Риск растёт** с каждым ужесточением политики

### Зависимость AI PILOT от Claude
- 9 агентов (8 продуктовых + webmaster) = 100% Claude (Haiku/Sonnet/Opus)
- Генератор сайтов = Claude Opus 32k
- Knowledge crawler = Claude Haiku
- Boss Bot = Claude Opus
- Все конституции заточены под Claude system prompt format

---

## ПЛАН A: Multi-LLM архитектура (ПРИОРИТЕТ)

### Задача
Абстрагировать LLM-провайдер чтобы агенты могли работать с любой моделью.

### Что создать
1. **`v2/backend/app/llm/provider.py`** — абстрактный класс `LLMProvider`:
   ```python
   class LLMProvider(ABC):
       async def chat(self, system: str, messages: list, max_tokens: int, model: str) -> str
       async def stream(self, system: str, messages: list, max_tokens: int, model: str) -> AsyncGenerator
       def supports_tools(self) -> bool
       def max_context_window(self) -> int
   ```

2. **Реализации:**
   - `anthropic_provider.py` — текущий Claude (основной)
   - `mistral_provider.py` — Mistral Large (EU, без санкций, хорошее качество)
   - `openai_provider.py` — GPT-4o/o3 (запасной)
   - `local_provider.py` — Llama 4 через Ollama/vLLM (полная независимость)

3. **Роутинг** — `v2/backend/app/llm/router.py`:
   ```python
   def get_provider(client_country: str = None, agent_type: str = None) -> LLMProvider:
       # 1. Если Claude доступен и клиент не в restricted → Claude
       # 2. Если клиент RU/BY → Mistral Large
       # 3. Если Claude API down → fallback на Mistral → OpenAI → Local
   ```

4. **Изменения в агентах** — `base.py`:
   - Заменить прямые вызовы `anthropic.messages.create()` на `provider.chat()`
   - Конституции: format-agnostic (убрать Claude-specific синтаксис если есть)

### Приоритет моделей-заменителей

| Модель | Качество | Цена | Доступ BY/RU | Санкц. риск | Приоритет |
|--------|----------|------|-------------|-------------|-----------|
| **Mistral Large 2** | 85% Claude | $$  | ✅ Нет ограничений | Нет (Франция) | **#1 fallback** |
| **GPT-4o** (OpenAI) | 90% Claude | $$  | ⚠️ RU блокирован, BY серая зона | Средний (US) | #2 |
| **Gemini 2.5 Pro** (Google) | 80% Claude | $   | ⚠️ Ограничен для РФ | Средний (US) | #3 |
| **Llama 4 Maverick** (Meta) | 75% Claude | Сервер | ✅ Self-hosted | **Нет** | #4 (независимость) |
| **GigaChat** (Сбер) | 50% Claude | $   | ✅ Нативно РФ | Нет для РФ | Только для РФ клиентов |
| **YandexGPT 4** | 50% Claude | $   | ✅ Нативно РФ | Нет для РФ | Только для РФ клиентов |

### Оценка трудозатрат
- Абстрактный класс + 2 провайдера (Mistral + OpenAI): **2-3 дня**
- Рефакторинг base.py + всех агентов: **3-5 дней**
- Тестирование качества ответов на каждой модели: **2-3 дня**
- **Итого: ~2 недели** на полный multi-LLM

---

## ПЛАН B: Перерегистрация юрлица

### Если Anthropic начнёт проверять UBO (Ultimate Beneficial Owner)

| Юрисдикция | Налоги | Setup cost | Время | Примечания |
|-----------|--------|-----------|-------|------------|
| **Грузия (ИП/ООО)** | 1% IT | ~$500 | 1-2 нед | Нужен ВНЖ. Если владелец BY гражданин — серая зона по правилу 50% |
| **Казахстан (МФЦА)** | 0% IT | ~$1000 | 2-4 нед | Английское право, но правило 50% может применяться |
| **Эстония (e-Residency)** | 0% нераспред. | ~$2000 | 2-4 нед | EU юрисдикция, нужен контактный директор EU-резидент |
| **ОАЭ (DMCC)** | 0% | $5-15K | 4-8 нед | Самый чистый вариант, но дорого |
| **Литва/Польша** | 5-15% | ~$2000 | 2-4 нед | EU, без вопросов к Anthropic |

### Важно
- ПВТ Беларусь (0% до 2049) конфликтует с санкционным комплаенсом
- Можно иметь ДВА юрлица: BY (ПВТ) для не-санкционных сервисов + EU для Anthropic API
- Решение зависит от гражданства Валерия и планов по переезду

---

## ПЛАН C: Аварийный (если Claude отключили ПРЯМО СЕЙЧАС)

### Немедленные действия (первые 24 часа):
1. **Переключить все агенты на Mistral Large API** (mistral.ai, API key создаётся за 5 мин)
   - Endpoint: `https://api.mistral.ai/v1/chat/completions`
   - Модель: `mistral-large-latest`
   - Формат: OpenAI-compatible (messages array, system prompt)
   - Ключ: зарегистрироваться на mistral.ai (нет ограничений BY)

2. **env var `LLM_PROVIDER=mistral`** в Railway + GKE — один переключатель

3. **Уведомить клиентов:** "Технические работы, качество ответов временно может отличаться"

4. **Что пострадает:**
   - Качество генерации сайтов (Opus → Mistral Large = заметная деградация)
   - Boss Bot (Opus → деградация аналитики)
   - Knowledge Crawler (Haiku → Mistral Small, минимальное влияние)
   - Обычные диалоги агентов (Sonnet → Mistral Large, приемлемо)

### Временные рамки восстановления:
- **0-24 ч:** Переключение на Mistral (ручная замена URL + API key в env vars)
- **1-7 дней:** Адаптация конституций под Mistral (другой формат system prompt)
- **7-14 дней:** Тюнинг качества, тестирование каждого агента
- **14-30 дней:** Полноценная multi-LLM архитектура (План A)

---

## ПЛАН D: Self-hosted LLM (полная независимость)

### Когда использовать
- Все облачные провайдеры (Claude, GPT, Mistral) недоступны или слишком дорого
- Нужна полная автономия без зависимости от третьих сторон

### Что нужно
- **GPU сервер:** 1x A100 80GB или 2x A10G 24GB
  - Hetzner: ~€200/мес (RTX 4000 SFF Ada)
  - vast.ai / RunPod: ~$1-3/час
- **Модель:** Llama 4 Maverick 17Bx128E (open-source, Meta)
- **Inference:** vLLM или TGI (text-generation-inference)
- **Качество:** ~75% от Claude Sonnet, достаточно для базовых диалогов агентов

### Ограничения
- Генерация сайтов (32k tokens, сложная логика) — качество заметно хуже
- Стоимость GPU сервера ~€200-400/мес vs Claude API ~€100-300/мес при малом трафике
- Имеет смысл только при масштабе >1000 клиентов или при полной блокировке облаков

---

## МОНИТОРИНГ РИСКОВ

### Что отслеживать (Разведчик + ручной мониторинг):
1. **Anthropic Terms updates** — https://www.anthropic.com/legal/consumer-terms (ежемесячно)
2. **Supported countries list** — https://www.anthropic.com/supported-countries (ежемесячно)
3. **Статус API ключа** — Страж проверяет каждые 5 мин (health_checks)
4. **US sanctions updates** (OFAC SDN list) — ежеквартально
5. **EU sanctions BY** — ежеквартально
6. **Hacker News / The Decoder** — новости об ужесточении AI export controls

### Триггеры для активации планов:
- **ЖЁЛТЫЙ:** Anthropic обновил Terms / добавил UBO проверку → начать План A
- **ОРАНЖЕВЫЙ:** API ключ отклонён / warning email от Anthropic → активировать План C + A
- **КРАСНЫЙ:** Полная блокировка + нет возможности создать новый аккаунт → План C + D

---

## КЛЮЧЕВОЕ: НЕ встраивать VPN

**VPN для клиентов бесполезен** — проблема не в IP клиента, а в:
1. Юрлице AI PILOT (BY)
2. API ключе, привязанном к BY-компании
3. Правиле >50% ownership

**VPN для серверов не нужен** — Railway/GKE уже в EU/US.

Решение = **multi-LLM** + **собственная модель** + при необходимости **смена юрисдикции**.

---

## ★ СТРАТЕГИЧЕСКИЙ ПЛАН: Собственная модель "AI PILOT LLM" (ПРИОРИТЕТ)

> Решение Валерия 2026-03-03: это не fallback, а приоритетное направление.
> Цель: собственная AI-модель, обученная на данных AI PILOT, без зависимости от провайдеров.

### Зачем
1. **Независимость** — 0 санкционных рисков, работа в любой стране
2. **Конкурентное преимущество** — модель знает BY/RU бизнес лучше Claude/GPT
3. **Экономия** — при масштабе в 3-5x дешевле облачных API
4. **Маркетинг** — "AI PILOT LLM: русскоязычная бизнес-AI модель" = уникальное позиционирование
5. **Дополнительный бизнес** — возможность продавать API модели другим компаниям

### Что у нас УЖЕ ЕСТЬ (уникальные данные для обучения)
- 8 конституций агентов (500+ KB специализированного текста)
- 3857 записей базы знаний (бухгалтерия BY, юридика BY/RU, продажи, HR, маркетинг, SMM)
- `agent_learning_log` — реальные диалоги с клиентами (растёт ежедневно)
- `agent_example_store` — few-shot примеры с quality score
- 36 ниш × 20 стилей для генерации сайтов
- Знание BY законодательства (ПУД, УСН, КУДИР, Закон №57-З)

### Дорожная карта

#### ЭТАП 1: Multi-LLM абстракция (~2 нед) ← ДЕЛАТЬ ПЕРВЫМ
- Абстрактный `LLMProvider` в `v2/backend/app/llm/`
- Реализации: `anthropic_provider.py`, `mistral_provider.py`, `openai_provider.py`
- Рефакторинг `base.py`: вызовы через провайдер, не напрямую
- Роутер: Claude (основной) → Mistral (BY/RU, fallback) → OpenAI (fallback #2)
- **Результат:** РФ/BY клиенты работают через Mistral → 0 санкционных рисков

#### ЭТАП 2: Подготовка dataset (~1-2 нед)
- Экспорт конституций → формат instruction-tuning (system/user/assistant JSONL)
- Экспорт KB (3857 записей) → пары вопрос-ответ
- Экспорт agent_learning_log → реальные диалоги (фильтр: quality_score > 0.7)
- **НОВОЕ: Кодинг-dataset** (решение 2026-03-04):
  - v2/backend/ (~50K строк Python) → пары "описание задачи → код"
  - control-center/ (~30K строк TS/React) → пары "описание компонента → код"
  - WordPress сниппеты (~15K строк PHP) → пары "функция → реализация"
  - k8s/ + .github/ (~5K строк YAML) → пары "инфраструктура → конфигурация"
  - LESSONS_LEARNED (31 ошибка) → пары "баг → фикс"
  - Claude Code ревью (~500 эпизодов) → пары "плохой код → хороший код"
  - n8n workflows (56 JSON) → пары "задача → workflow"
  - Crawl: Stack Overflow top-1000 по 1С/WP/Next.js/FastAPI
- **Синтетический кодинг-dataset** (генерирует Claude Opus на Этапе 2):

  | Область | Темы | Объём |
  |---|---|---|
  | Python (продвинутый) | async/await, декораторы, метаклассы, typing, dataclasses, FastAPI patterns | 5-10K примеров |
  | TypeScript/React | hooks, generics, server components, streaming, Suspense, Next.js App Router | 5-10K примеров |
  | 1С:BSL | регистры, документы, обработки, отчёты, обмен данными, расширения, управляемые формы | 5-10K примеров |
  | SQL/PostgreSQL | оптимизация, индексы, CTE, window functions, партиционирование, RLS, RPC | 3-5K примеров |
  | DevOps/Infra | Docker, K8s, Terraform, GitHub Actions, NGINX, мониторинг, Railway, Vercel | 3-5K примеров |
  | PHP/WordPress | хуки, фильтры, REST API, WooCommerce, Gutenberg, mu-plugins, Code Snippets | 3-5K примеров |
  | Web Security | OWASP Top 10, XSS, SQL injection, CSRF, CSP, rate limiting, auth patterns | 2-3K примеров |
  | Архитектура | SOLID, DDD, микросервисы, event-driven, CQRS, clean architecture, monorepo | 2-3K примеров |
  | Telegram/Bot | aiogram, pyrogram, webhooks, inline keyboards, FSM, middleware, i18n | 2-3K примеров |
  | Mobile | React Native, Expo, SQLite, push notifications, camera, offline-first | 2-3K примеров |
  | **ИТОГО синтетического кодинга** | | **32-58K примеров** |

  Формат каждого примера (JSONL):
  ```json
  {"system": "Ты AI PILOT LLM — AI-помощник для разработчиков...", "user": "Напиши FastAPI endpoint для загрузки файла с проверкой VirusTotal", "assistant": "```python\nfrom fastapi import ...\n```\n\nОбъяснение: ..."}
  ```

- Синтетические бизнес-данные: Claude генерирует 50-100K примеров по каждому агенту (бухгалтерия, юридика, продажи, HR, маркетинг, реклама, веб)

- **ОГРАНИЧЕНИЯ синтетического dataset (честно):**
  - Модель 17B НЕ сможет "рассуждать" как Claude Opus — она выучит ПАТТЕРНЫ, не логику
  - На типовых задачах (80% запросов) качество будет 85-90% от Claude
  - На сложных задачах (архитектура, отладка race conditions) — 60-70% от Claude
  - Модель НЕ будет знать о технологиях вышедших ПОСЛЕ обучения — нужен регулярный re-crawl + дообучение (ежемесячно)
  - Fine-tune на 150K примерах даёт специализацию, но не расширяет базовые знания модели — для этого нужна более крупная base model (32B+ или 70B)

- **Цель: 200,000+ quality-filtered training examples** (100K бизнес + 50K код проекта + 50K синтетический кодинг)

#### ЭТАП 3: Fine-tune "AI PILOT LLM" v0.1 (~3-5 дней)
- Базовая модель: **Llama 4 Scout 17B** (компактная, быстрая) или **Qwen 3 32B** (умнее)
- Метод: **QLoRA** (4-bit quantization + LoRA adapters)
- Платформа: RunPod / Lambda (1x A100 80GB, ~$2-5/час)
- Фреймворк: `unsloth` (2x ускорение, 60% меньше памяти)
- Стоимость обучения: **$50-200 разово**

#### ЭТАП 4: Деплой и тестирование (~1 нед)
- Inference: **vLLM** на Hetzner GPU (EX44 + RTX 4000 Ada, ~€200/мес)
- OpenAI-compatible API endpoint → подключается к LLM роутеру как `local_provider.py`
- A/B тестирование: AI PILOT LLM vs Claude на 1000 реальных запросов
- Бенчмарк по каждому агенту: accuracy, response quality, hallucination rate

#### ЭТАП 5: Гибридный роутер (~1 нед)
```
Запрос клиента → Классификатор сложности
    ↓
┌─ Простые (80%): FAQ, статус, навигация, приветствия
│  → AI PILOT LLM (своя модель) — ~$0.001/запрос, <1 сек
│
├─ Средние (15%): консультации, анализ, рекомендации
│  → Mistral Large / Claude Sonnet — ~$0.01-0.05/запрос
│
└─ Сложные (5%): генерация сайтов 32k, юрид. анализ, миграция данных
   → Claude Opus — ~$0.50-2.00/запрос
```

#### ЭТАП 6: RLHF / DPO улучшение (~2-4 нед, после 100+ клиентов)
- Сбор пар "хороший/плохой ответ" из реальных взаимодействий
- DPO (Direct Preference Optimization) — проще и дешевле чем RLHF
- Цель: AI PILOT LLM v0.2 → качество 85-90% от Claude Sonnet на наших задачах

#### ЭТАП 7: Продукт "AI PILOT LLM API" — публичная платформа для разработчиков

> **Это НЕ "опционально" — это ГЛАВНАЯ точка монетизации.**
> AI PILOT LLM = специализированная бизнес-модель СНГ, которую встраивают в ЛЮБОЙ софт.

**Формат:**
```
POST https://api.ai-pilot.by/v1/chat/completions     — чат (OpenAI-compatible)
POST https://api.ai-pilot.by/v1/documents/recognize   — OCR + классификация
POST https://api.ai-pilot.by/v1/documents/entries      — автопроводки
POST https://api.ai-pilot.by/v1/legal/analyze          — анализ договора
POST https://api.ai-pilot.by/v1/hr/screen              — скрининг резюме
POST https://api.ai-pilot.by/v1/sales/qualify           — квалификация лида
POST https://api.ai-pilot.by/v1/marketing/content       — генерация контента
Authorization: Bearer apl_xxxxx
```

**Документация:** https://docs.ai-pilot.by (Swagger/Redoc + примеры на Python/JS/1C/PHP)

---

### 7.1 БУХГАЛТЕРИЯ И ФИНАНСЫ (Ирина-модуль)

| Кто встраивает | Что делает API | Пример запроса |
|----------------|---------------|----------------|
| **1С:Бухгалтерия** разработчики | Скан → распознавание → проводки | Накладная.pdf → `{Дт 10.01 Кт 60.01, 1500 BYN}` |
| **МойСклад** интеграторы | Классификация документов, автозаполнение | Счёт-фактура → тип, статья расхода, НДС |
| **iiko** (рестораны) | Аналитика расходов, food cost | Отчёт → "food cost 32%, норма 28%, причина: мясо +15%" |
| **СБИС/Контур** дополнения | Проверка контрагентов, анализ рисков | ИНН → "задолженность, судебные дела, рейтинг" |
| **Банковские приложения** | Категоризация транзакций | "МАГНИТ 1532 МИНСК" → "Продукты, бизнес-расход" |
| **Финтех-стартапы** | AI-бухгалтер как сервис | Полный пайплайн: скан → проводка → КУДИР → декларация |

**Рынок:** ~6 млн компаний в 1С (РФ/BY/KZ). 500K+ разработчиков 1С.
**Уникальность:** Знает План счетов BY/RU, УСН/ОСН, КУДИР, НДС, Закон №57-З.
**Никто не делает** — GigaChat/YandexGPT = общие модели без бухгалтерской специализации.

---

### 7.2 ЮРИДИКА (Леон-модуль)

| Кто встраивает | Что делает API | Пример |
|----------------|---------------|--------|
| **Консультант+/Гарант** плагины | Поиск + объяснение нормы | "Какой срок давности по 159 УК?" → ответ + ссылки |
| **LegalTech стартапы** | Анализ договора, выявление рисков | Договор.pdf → `{risks: [{clause: 5.2, risk: "штраф без лимита"}]}` |
| **Нотариальный софт** | Шаблоны документов, проверка | "Доверенность на авто" → готовый текст по BY праву |
| **Корпоративные юристы** | Due diligence, проверка комплаенс | Устав.pdf → "несоответствие п.3 ст.87 ГК РБ" |
| **Госорганы (ЗАГС, МФЦ)** | Автоматизация обращений граждан | Заявление → классификация → маршрутизация |
| **Арбитражные платформы** | Оценка перспектив иска | Описание спора → "вероятность выигрыша 72%, практика: ..." |

**Рынок:** 200K+ юристов СНГ, 50K+ юрфирм.
**Уникальность:** BY законодательство (ГК, ТК, НК), РФ законодательство, шаблоны договоров.

---

### 7.3 ПРОДАЖИ И CRM (Марина-модуль)

| Кто встраивает | Что делает API | Пример |
|----------------|---------------|--------|
| **Битрикс24** расширения | AI-ответы клиентам в чате | Вопрос клиента → квалификация + ответ + тег |
| **AmoCRM** виджеты | Скоринг лидов, прогноз конверсии | Лид данные → `{score: 78, recommended_action: "звонок сегодня"}` |
| **Retail CRM** | Рекомендации товаров в чате | "Ищу подарок маме" → 3 варианта + upsell |
| **Чат-боты** (Jivo, Carrot) | AI-оператор 1-й линии | Вопрос → ответ + handoff к человеку если сложно |
| **Телеграм-боты** продавцов | Мини-CRM с AI | /lead Иванов 50000 → "лид создан, напомню завтра" |
| **Call-центры** | Пост-обработка звонков | Транскрипт → {summary, sentiment, next_action, lead_score} |

**Рынок:** 2M+ компаний используют CRM в СНГ. 100K+ Telegram-ботов.
**Уникальность:** Знает воронки продаж, BANT, скрипты, возражения, BY/RU рыночные реалии.

---

### 7.4 HR И РЕКРУТИНГ (Анна-модуль)

| Кто встраивает | Что делает API | Пример |
|----------------|---------------|--------|
| **hh.ru / Работа.by** плагины | Скрининг резюме, матчинг | Резюме + вакансия → `{match: 82%, gaps: ["нет опыта React"]}` |
| **Хантфлоу / Potok** | Генерация описания вакансий | Должность + требования → готовый текст |
| **PeopleForce / BambooHR** | Анализ eNPS, рекомендации | Опрос ответы → "eNPS -12, причина: зарплата в IT отделе" |
| **Корпоративные порталы** | AI-HR бот для сотрудников | "Сколько у меня дней отпуска?" → ответ по ТК BY/RU |
| **Кадровые агентства** | Массовый скрининг 100+ кандидатов | Batch: 100 PDF → ранжированный список с обоснованием |
| **Обучающие платформы** | Персональные планы развития | Навыки + цели → план обучения на 3/6/12 мес |

**Рынок:** 50K+ HR-отделов, 5K+ агентств в СНГ.
**Уникальность:** Знает ТК BY/RU, форматы резюме СНГ, hh.ru форматы.

---

### 7.5 МАРКЕТИНГ И КОНТЕНТ (Кира + Влад модули)

| Кто встраивает | Что делает API | Пример |
|----------------|---------------|--------|
| **SMM-платформы** (SMMPlanner, Амплифер) | Генерация постов | Тема + тон → пост + хэштеги + время публикации |
| **SEO-сервисы** (Serpstat, Topvisor) | Генерация SEO-текстов | Ключи + ТЗ → оптимизированный текст |
| **Email-платформы** (Unisender, SendPulse) | Генерация рассылок | Сегмент + цель → тема + тело + CTA |
| **Рекламные кабинеты** | Генерация креативов | Продукт + аудитория → 5 вариантов текста + заголовки |
| **Видео-продакшен** | Скрипты для роликов | Продукт + формат → сценарий + раскадровка |
| **Маркетплейсы** (Ozon, Wildberries) | Описания и карточки товаров | Фото + характеристики → SEO-оптимизированное описание |

**Рынок:** 500K+ маркетологов, 100K+ SMM-агентств в СНГ.
**Уникальность:** Знает BY/RU аудиторию, законы о рекламе, сезонность.

---

### 7.6 РЕКЛАМА (Даниил-модуль)

| Кто встраивает | Что делает API | Пример |
|----------------|---------------|--------|
| **Google Ads / Яндекс.Директ** агентства | Генерация объявлений | Продукт + бюджет → 10 вариантов + стратегия ставок |
| **Платформы автоматизации** (Marilyn, К50) | AI-оптимизация кампаний | Данные кампании → "снизьте CPC на 20%, поднимите группу B" |
| **Facebook/Meta** агентства | Таргетинг + креативы | Аудитория → текст + визуальная концепция |
| **Медиа-баинг** платформы | Анализ эффективности | Отчёт → "ROAS 3.2, лучший канал: VK, убрать Одноклассники" |

---

### 7.7 ВЕБ-РАЗРАБОТКА (Webmaster-модуль)

| Кто встраивает | Что делает API | Пример |
|----------------|---------------|--------|
| **Конструкторы сайтов** (Tilda, Wix, Shopify) | AI-генерация секций | "Секция отзывов для стоматологии" → HTML + CSS |
| **Веб-студии** | Генерация лендингов | Бриф → полная страница (HTML/CSS/JS) |
| **WordPress разработчики** | AI-помощник для контента | Описание бизнеса → полный контент + SEO разметка |
| **No-code платформы** | AI в drag-and-drop | Текстовое описание → готовый layout |

---

### 7.8 КОДИНГ И РАЗРАБОТКА (Code-модуль) — AI PILOT как Copilot

> **Решение Валерия 2026-03-04:** AI PILOT LLM должен уметь работать с кодом.
> Разработчики используют его как помощника — генерация, отладка, рефакторинг, ревью.
> Источник знаний: весь код проекта AI PILOT (1000+ файлов) + мои (Claude Code) реальные решения.

**API Endpoints:**
```
POST /v1/code/complete          — автокомплит (IDE integration, <1000ms target)
POST /v1/code/generate          — генерация кода по описанию
POST /v1/code/review            — ревью кода (баги, безопасность, стиль)
POST /v1/code/refactor          — рефакторинг с объяснением
POST /v1/code/explain           — объяснение кода (для обучения)
POST /v1/code/debug             — анализ ошибки + предложение фикса
POST /v1/code/convert           — конвертация между языками (1С↔Python, PHP↔JS)
POST /v1/code/test              — генерация тестов для функции/класса
```

| Кто встраивает | Что делает API | Пример |
|---|---|---|
| **1С-разработчики** | Генерация/отладка BSL кода | "Обработка загрузки из Excel" → модуль 1С |
| **IDE плагины** (VS Code, JetBrains) | Автокомплит + рефакторинг | Как Copilot, но знает 1С/BY/RU стек |
| **Веб-студии** | Генерация React/Next.js компонентов | "Карточка товара с анимацией" → TSX + CSS |
| **WordPress/Битрикс агентства** | Плагины, сниппеты, темы | "WooCommerce фильтр по цене" → PHP |
| **Telegram-бот разработчики** | Генерация ботов | "Бот записи к врачу" → Python aiogram |
| **No-code → Pro-code** | Экспорт из визуального редактора | Tilda макет → чистый Next.js 16 |
| **DevOps / SRE** | Конфигурации, скрипты, CI/CD | "GitHub Actions для FastAPI" → YAML + Dockerfile |
| **Студенты / bootcamp** | AI-репетитор по программированию | "Объясни async/await в Python" → код + пояснение |

**Специализации (уникальные знания AI PILOT LLM):**

| Область | Что знает ЛУЧШЕ других | Источник данных |
|---|---|---|
| **1С:BSL** | План счетов BY/RU, регистры, обработки, документы, модули | Конституция Ирины + KB + 1С-documentation crawl |
| **WordPress/WooCommerce** | Хуки, фильтры, REST API, Code Snippets, темы, mu-plugins | Наш опыт: 140+ сниппетов, ai-pilot-theme-pro |
| **Next.js 16 + Tailwind** | App Router, RSC, server actions, shadcn, Framer Motion | Наш сайт + Control Center (80+ страниц) |
| **FastAPI + Supabase** | Agents, workers, SSE streaming, RLS, RPC | v2/backend/ (весь наш бэкенд) |
| **Kubernetes / GKE** | Deployments, ingress, HPA, secrets, CI/CD | k8s/ (наша инфраструктура) |
| **Telegram боты** | aiogram, webhook-based, inline keyboards | 10 ботов AI PILOT |
| **n8n workflows** | Nodes, webhooks, expressions, Code node | 56+ workflows |
| **Битрикс24 / AmoCRM** | REST API, webhooks, CRM воронки | Марина-модуль, интеграции |

**Источники для обучения (dataset Этап 2):**

| Источник | Объём | Формат | Что даёт |
|---|---|---|---|
| Код AI PILOT (v2/backend/) | ~50K строк Python | code → description pairs | FastAPI, Supabase, agents |
| Код AI PILOT (control-center/) | ~30K строк TS/React | code → description pairs | Next.js, Tailwind, shadcn |
| Код AI PILOT (k8s/, .github/) | ~5K строк YAML | infra → description pairs | K8s, CI/CD, Terraform |
| WordPress сниппеты | ~15K строк PHP | snippet → description pairs | WP, WC, hooks |
| n8n workflows (JSON) | 56 workflows | workflow → description pairs | Automation patterns |
| Claude Code ревью | ~500 ревью | bad_code → good_code pairs | Качество, безопасность |
| LESSONS_LEARNED.md | 31 ошибка | problem → solution pairs | Антипаттерны |
| Конституции агентов | 500KB текста | domain knowledge | Бизнес-контекст для кода |
| Stack Overflow (crawl) | top-1000 вопросов по 1С/WP/Next.js | Q&A pairs | Общие знания |
| GitHub public repos | Best practices FastAPI/Next.js | code patterns | Идиоматический код |

**Конкурентное преимущество:**
- **GigaChat** (Сбер): не знает 1С, плохо с TypeScript, нет code review
- **YandexGPT**: не знает 1С, нет tool calling, нет streaming
- **GitHub Copilot**: не знает 1С:BSL, не знает BY/RU специфику, $19/мес
- **Cursor**: не знает 1С:BSL, не знает WordPress экосистему, $20/мес
- **AI PILOT LLM**: знает ВСЁ выше + 1С + BY/RU специфику + стоит дешевле

**Продукты на базе Code-модуля:**
1. **VS Code Extension "AI PILOT Code"** — автокомплит + чат + ревью (как Copilot)
2. **JetBrains Plugin** — для IntelliJ / PyCharm / WebStorm
3. **1С:Расширение (.cfe)** — встроенный AI помощник прямо в 1С:Предприятие
4. **CLI инструмент** (`aipilot code review src/` → отчёт) — для CI/CD пайплайнов
5. **Web Playground** (console.ai-pilot.by/playground/code) — попробовать в браузере

---

### 7.9 ЦЕНООБРАЗОВАНИЕ API (обновлено с учётом Code-модуля)

| Тариф | Цена | Лимит | Для кого |
|-------|------|-------|----------|
| **Free** | €0 | 100 запросов/мес | Попробовать, MVP |
| **Startup** | €49/мес | 10K запросов | Стартапы, маленькие боты |
| **Business** | €199/мес | 100K запросов | Средний бизнес, интеграции |
| **Enterprise** | €999/мес | 1M запросов | Крупные платформы, white-label |
| **Custom** | Договор | Безлимит | 1С-франчайзи, банки, госы |

**Специализированные endpoints** (OCR, юр.анализ, HR-скрининг) стоят 2-5x от базового чата.

---

### 7.10 ДОКУМЕНТАЦИЯ И SDK

| Что | Формат | Для кого |
|-----|--------|----------|
| **docs.ai-pilot.by** | Swagger/Redoc + Markdown | Все разработчики |
| **Python SDK** | `pip install aipilot` | Python-разработчики |
| **JavaScript SDK** | `npm install @aipilot/sdk` | JS/Node разработчики |
| **1С:Расширение** | .cfe файл | 1С-разработчики (КЛЮЧЕВОЕ!) |
| **PHP SDK** | `composer require aipilot/sdk` | WordPress/Bitrix |
| **Postman Collection** | .json | Быстрый старт |
| **Примеры интеграций** | GitHub repo | Битрикс24, AmoCRM, МойСклад, hh.ru |

---

### 7.11 ПОТЕНЦИАЛ ДОХОДА

| Сценарий | Клиенты API | Средний чек | MRR |
|----------|-------------|-------------|-----|
| Год 1 (запуск) | 50 | €99 | **€5K/мес** |
| Год 2 (рост) | 500 | €149 | **€75K/мес** |
| Год 3 (масштаб) | 5,000 | €199 | **€1M/мес** |

+ Доход от основной платформы AI PILOT (8 агентов для клиентов) сверху.

**Точка окупаемости GPU:** ~25 клиентов × €199 = €5K/мес (GPU стоит €200-400)

### Экономика

| Масштаб | 100% Claude | Гибрид (AI PILOT LLM + Cloud) | Экономия |
|---------|------------|--------------------------|----------|
| 10K запросов/мес | ~€300-500 | ~€200 GPU + €50 API = €250 | 30-50% |
| 100K запросов/мес | ~€3,000-5,000 | ~€200 GPU + €600 API = €800 | **75-85%** |
| 1M запросов/мес | ~€30,000-50,000 | ~€400 GPU + €5,000 API = €5,400 | **85-90%** |

---

#### ЭТАП 8: Developer Platform + Mobile App (полноценная платформа для разработчиков)

> **Решение Валерия 2026-03-03:** Это не "когда-нибудь" — это часть MVP.
> Мобильное приложение со сканером + Developer Portal + биллинг API = готовый продукт.

---

### 8.1 МОБИЛЬНОЕ ПРИЛОЖЕНИЕ "AI PILOT Scanner"

**Суть:** Бухгалтер/юрист/менеджер открывает приложение → фоткает документ → AI распознаёт и обрабатывает.

```
📱 Экран камеры
  ↓ [фото]
📄 AI распознавание (AI PILOT LLM)
  ↓
┌────────────────────────────────────────────┐
│ Накладная №47 от 15.03.2026               │
│ Поставщик: ООО "Ромашка"                  │
│ Сумма: 1 500.00 BYN (в т.ч. НДС 250.00)  │
│                                            │
│ Рекомендуемая проводка:                    │
│ Дт 10.01  Кт 60.01  — 1 250.00 BYN       │
│ Дт 18.01  Кт 60.01  —   250.00 BYN (НДС) │
│                                            │
│ [✅ Подтвердить]  [✏️ Редактировать]  [📤 В 1С] │
└────────────────────────────────────────────┘
```

**Технический стек:**

| Компонент | Технология | Почему |
|-----------|-----------|--------|
| **Фреймворк** | React Native / Expo | Один код → iOS + Android |
| **Камера/OCR** | встроенная камера + AI PILOT LLM API | Наш OCR лучше общих |
| **Хранение** | SQLite (локальный кеш) + Supabase (синхронизация) | Оффлайн-первый |
| **Авторизация** | OAuth 2.0 (тот же Developer Portal) | Единая учётка |
| **Push** | Firebase Cloud Messaging | Уведомления о результатах |
| **Сборка** | Expo EAS Build | App Store + Google Play |

**Функции приложения:**

| Экран | Что делает |
|-------|-----------|
| **Сканер** | Камера → авто-кроп → отправка на API → результат за 3-5 сек |
| **История** | Все отсканированные документы, поиск, фильтры |
| **Проводки** | Предложенные проводки, edit, export в 1С/Excel |
| **Чат** | AI-консультант (Ирина для бухгалтерии, Леон для юридики) |
| **Настройки** | План счетов (BY/RU), налоговая система, подключение к 1С |
| **API Keys** | Управление ключами прямо из приложения |

**Free tier приложения:**
- 50 сканов/мес бесплатно (привлечение пользователей)
- 100 сообщений чата/мес
- Без экспорта в 1С (только просмотр)
- **Цель:** бухгалтер попробовал → подсел → купил Business (€199/мес)

---

### 8.2 DEVELOPER PORTAL (console.ai-pilot.by)

**Отдельный сайт** — как у Anthropic (console.anthropic.com) или OpenAI (platform.openai.com).

```
console.ai-pilot.by
├── /login                  — OAuth 2.0 (email/Google/GitHub)
├── /dashboard              — Usage charts, spend, rate limits
├── /api-keys               — Создание/удаление/ротация ключей
│   └── apl_live_xxxxx      — production key
│   └── apl_test_xxxxx      — sandbox key (бесплатно, rate limited)
├── /billing                — Текущий план, история платежей, upgrade
│   ├── /billing/plans      — Free/Startup/Business/Enterprise
│   ├── /billing/usage      — Детализация по endpoint и дате
│   └── /billing/invoices   — Скачать акты/счёта (PDF)
├── /docs                   — Интерактивная документация
│   ├── /docs/quickstart    — "Первый запрос за 30 секунд"
│   ├── /docs/api-reference — Swagger/Redoc (все endpoints)
│   ├── /docs/guides        — Гайды по интеграциям (1С, Битрикс, AmoCRM...)
│   ├── /docs/sdks          — Python, JS, PHP, 1С
│   └── /docs/examples      — Код-примеры с playground
├── /playground             — Попробовать API прямо в браузере (как OpenAI Playground)
│   ├── Чат                 — System prompt + message → ответ
│   ├── Документы           — Загрузить PDF → распознавание
│   └── Юридика             — Вставить договор → анализ рисков
├── /team                   — Управление командой (invite, roles)
├── /webhooks               — Настройка callback URL для async операций
├── /logs                   — Журнал всех API вызовов (30 дней)
└── /settings               — Профиль, уведомления, 2FA
```

**Технический стек портала:**

| Компонент | Технология | Почему |
|-----------|-----------|--------|
| **Frontend** | Next.js 16 + Tailwind + shadcn | Единый стек с основным сайтом |
| **Backend** | FastAPI (тот же `v2/backend/`) | Общая кодовая база |
| **Auth** | OAuth 2.0 + JWT | Стандарт для API-платформ |
| **Billing** | Stripe Billing (подписки + usage-based) | Автоматический биллинг |
| **DB** | Supabase (новые таблицы `api_*`) | Общая инфраструктура |
| **Docs** | Mintlify или Docusaurus | Красивая документация |
| **Rate Limiting** | Redis + Token Bucket | Защита от abuse |

---

### 8.3 СИСТЕМА API KEYS И БИЛЛИНГА

**Supabase таблицы (новые):**

```sql
-- Организации разработчиков (отдельно от wp_users!)
api_organizations (
    id UUID PRIMARY KEY,
    name TEXT,
    email TEXT UNIQUE,
    plan TEXT DEFAULT 'free',     -- free/startup/business/enterprise
    stripe_customer_id TEXT,
    created_at TIMESTAMPTZ
);

-- API ключи
api_keys (
    id UUID PRIMARY KEY,
    org_id UUID REFERENCES api_organizations,
    key_hash TEXT UNIQUE,          -- SHA256 хеш ключа (сам ключ не храним!)
    key_prefix TEXT,               -- "apl_live_a3x..." (для идентификации в UI)
    name TEXT,                     -- "Production", "Staging"
    environment TEXT DEFAULT 'live', -- live / test
    permissions TEXT[],            -- ['chat', 'documents', 'legal', 'hr', ...]
    rate_limit_per_min INT DEFAULT 60,
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ
);

-- Usage tracking (per request)
api_usage (
    id BIGSERIAL PRIMARY KEY,
    org_id UUID,
    key_id UUID,
    endpoint TEXT,                 -- '/v1/chat/completions'
    model TEXT,                    -- 'ai-pilot-llm-1.0'
    tokens_input INT,
    tokens_output INT,
    cost_eur NUMERIC(10,6),       -- стоимость запроса в EUR
    latency_ms INT,
    status_code INT,
    created_at TIMESTAMPTZ
);
-- Партиционировать по месяцам!
-- ОБЯЗАТЕЛЬНЫЙ индекс для биллинга (GROUP BY org_id + период):
CREATE INDEX idx_api_usage_org_month ON api_usage(org_id, created_at DESC);

-- Ежемесячные агрегаты для биллинга
api_usage_monthly (
    id SERIAL PRIMARY KEY,
    org_id UUID,
    month DATE,                   -- '2026-04-01'
    total_requests INT,
    total_tokens_input BIGINT,
    total_tokens_output BIGINT,
    total_cost_eur NUMERIC(12,4),
    plan TEXT,
    overage_cost_eur NUMERIC(12,4) DEFAULT 0,
    invoice_id TEXT               -- Stripe invoice ID
);

-- Webhook подписки
api_webhooks (
    id UUID PRIMARY KEY,
    org_id UUID,
    url TEXT,
    events TEXT[],                -- ['document.recognized', 'batch.completed']
    secret TEXT,                  -- для HMAC подписи
    is_active BOOLEAN DEFAULT true
);
```

**Формат API ключа:**
```
apl_live_a3xK7mN2pQ9rT4wZ    — production (оплачивается)
apl_test_b5yL8nO3qR0sU6xA    — sandbox (бесплатно, rate limited, watermark в ответах)
```

**Аутентификация запросов:**
```
Authorization: Bearer apl_live_a3xK7mN2pQ9rT4wZ
```

**Rate Limiting:**

| Тариф | Запросов/мин | Запросов/мес | Tokens/мес |
|-------|-------------|-------------|------------|
| Free | 10 | 100 | 50K |
| Startup | 60 | 10K | 5M |
| Business | 300 | 100K | 50M |
| Enterprise | 1000 | 1M | 500M |

**Ответ при превышении:**
```json
{
    "error": {
        "type": "rate_limit_exceeded",
        "message": "Rate limit exceeded. Upgrade to Business for 300 req/min.",
        "retry_after_seconds": 12,
        "upgrade_url": "https://console.ai-pilot.by/billing/plans"
    }
}
```

---

### 8.4 ONBOARDING РАЗРАБОТЧИКА (два пути)

#### Путь A: Web/API разработчик (~30 секунд до первого запроса)
```
1. console.ai-pilot.by → "Sign Up" (email или GitHub)
2. Автоматически создаётся org + test key (apl_test_...)
3. Экран: "Ваш первый запрос" (curl пример с ключом уже подставленным)
4. Нажми "Run" прямо в браузере → видишь ответ AI PILOT LLM
5. "Получить production ключ" → ввести карту (или Free план без карты)
6. Готово — 50 бесплатных запросов в подарок
```

#### Путь B: 1С-разработчик (~10-15 минут)
```
1. console.ai-pilot.by → "Sign Up" → выбрать "Я разрабатываю на 1С"
2. Автоматически создаётся org + test key
3. Скачать .cfe расширение → установить в конфигуратор 1С
4. Видео-инструкция (2 мин): как подключить, первый запрос из 1С
5. Тестовый пример: "Распознать накладную" прямо из 1С
6. Готово — 50 бесплатных запросов + 10 сканов в подарок
```

> **Почему два пути:** Web-разработчик хочет curl/SDK за 30 сек. 1С-разработчик хочет .cfe расширение и видео.
> Один общий онбординг = потеря одной из аудиторий.

**Бесплатные токены при регистрации:**
- **50 запросов** (chat) + **10 сканов** (OCR) + **5 юр.анализов** = попробовать ВСЁ
- Не сгорают. Используешь когда хочешь.
- После — Free план (100 запросов/мес) или апгрейд.

---

### 8.5 ДОКУМЕНТАЦИЯ API (docs.ai-pilot.by)

**Структура:**

```
Быстрый старт
├── Получение ключа (30 сек)
├── Первый запрос (curl, Python, JS)
└── Выбор endpoint для задачи

API Reference
├── POST /v1/chat/completions        — Универсальный чат
├── POST /v1/documents/recognize      — OCR + распознавание
├── POST /v1/documents/entries        — Автоматические проводки
├── POST /v1/documents/classify       — Классификация документа
├── POST /v1/legal/analyze            — Анализ договора
├── POST /v1/legal/generate           — Генерация документа
├── POST /v1/hr/screen                — Скрининг резюме
├── POST /v1/hr/generate-vacancy      — Генерация вакансии
├── POST /v1/sales/qualify            — Квалификация лида
├── POST /v1/sales/objection          — Обработка возражения
├── POST /v1/marketing/content        — Генерация контента
├── POST /v1/marketing/seo            — SEO-оптимизация текста
├── POST /v1/ads/generate             — Генерация объявлений
├── POST /v1/web/generate-section     — Генерация секции сайта
├── POST /v1/web/generate-landing     — Генерация лендинга
├── POST /v1/code/complete            — Автокомплит кода (IDE integration)
├── POST /v1/code/generate            — Генерация кода по описанию
├── POST /v1/code/review              — Ревью кода (баги, безопасность)
├── POST /v1/code/refactor            — Рефакторинг с объяснением
├── POST /v1/code/explain             — Объяснение кода
├── POST /v1/code/debug               — Анализ ошибки + фикс
├── POST /v1/code/convert             — Конвертация (1С↔Python, PHP↔JS)
├── POST /v1/code/test                — Генерация тестов
├── GET  /v1/usage                    — Статистика использования
└── GET  /v1/models                   — Список доступных моделей

Гайды по интеграции
├── 1С:Бухгалтерия — установка расширения + пример
├── Битрикс24 — webhook + REST API
├── AmoCRM — виджет + Digital Pipeline
├── МойСклад — webhook + интеграция
├── Telegram Bot — Python пример
├── WordPress — PHP плагин
└── React / Next.js — JS SDK

SDK
├── Python: pip install aipilot
├── JavaScript: npm install @aipilot/sdk
├── PHP: composer require aipilot/sdk
├── 1С: скачать .cfe расширение
└── cURL примеры

Changelog
└── История версий API (v1.0, v1.1, ...)
```

---

### 8.6 ГОЛОСОВОЙ AI — Voice Module (полностью своё)

> **Решение Валерия 2026-03-04:** Голосовой чат в мобильном приложении + Voice API.
> На нашем GPU, без сторонних сервисов, €0 сверх инфраструктуры.

#### Пайплайн

```
🎤 Пользователь говорит (микрофон / громкая связь)
    ↓
🗣️ Whisper Large v3 — STT (голос → текст), ~0.3-0.5 сек
    ↓
🧠 AI PILOT LLM — ответ по конституции агента, ~0.5-1 сек
    ↓
🔊 Fish Speech 1.5 / XTTS v2 — TTS (текст → голос), ~0.3-0.5 сек
    ↓
📱 Пользователь слышит ответ (~1.5-2 сек total)
```

#### API Endpoint

```
POST /v1/voice/chat
Content-Type: multipart/form-data

audio: <wav/mp3/ogg file>
agent_type: "iryna"           -- какой агент отвечает
language: "ru"                -- ru/en/de/es/fr/pl
voice_id: "bella"             -- выбор голоса
conversation_id: "uuid"       -- для контекста

Response: audio/mpeg (streaming)
+ Headers: X-Transcript, X-Tokens-Used, X-Latency-Ms
```

#### VRAM бюджет (A100 80GB)

| Модель | VRAM | Назначение |
|--------|------|-----------|
| AI PILOT LLM 17B (4-bit) | ~10 GB | Основной мозг |
| Whisper Large v3 | ~3 GB | STT (речь → текст) |
| Fish Speech 1.5 / XTTS v2 | ~4 GB | TTS (текст → речь) |
| **ИТОГО** | **~17 GB** | Запас: 63 GB свободно |

#### Стоимость

| Компонент | Сторонние сервисы | Всё своё (AI PILOT LLM) |
|-----------|-------------------|------------------------|
| STT | Deepgram $0.004/мин | Whisper — €0 |
| AI мозг | Claude $0.01-0.05/запрос | AI PILOT LLM — €0 |
| TTS | ElevenLabs $0.30/1K символов | Fish Speech — €0 |
| **1K разговоров/мес** | **€65-110** | **€0 (GPU уже есть)** |
| **100K разговоров/мес** | **€6,500-11,000** | **€0** |

#### В мобильном приложении

| Режим | Описание |
|-------|----------|
| **Push-to-talk** | Нажал кнопку → говори → отпустил → ответ |
| **Hands-free** | Постоянное прослушивание, wake word "Пилот" (на устройстве) |
| **Speaker mode** | Громкая связь — как разговор с коллегой |

#### Сценарии использования

| Агент | Голосовой сценарий | Пример |
|-------|-------------------|--------|
| **Ирина** | Бухгалтер за рулём: "Какой у меня остаток на расчётном?" | Ответ голосом + push с цифрами |
| **Леон** | Юрист на встрече: "Какой срок давности по договору поставки?" | Ответ голосом + ссылка на статью |
| **Лиза** | Клиент звонит на сайт: "Расскажи про ваши услуги" | Продающий ответ голосом |
| **Марина** | Менеджер: "Статус лидов за неделю" | Отчёт голосом |
| **Кира** | SMM: "Придумай пост для Instagram про скидки" | Текст поста голосом + отправка в черновик |

#### Языки и голоса (30+ языков — все доступные)

> **Принцип:** включаем ВСЕ языки, которые поддерживают и STT и TTS одновременно.
> Whisper (STT) = 99 языков. Fish Speech (TTS) = 13+. XTTS v2 (TTS) = 17.
> Пересечение с хорошим качеством = **30 языков Tier 1-3**.

##### Tier 1 — Отличное качество (STT + TTS оба ★★★★+)

| Язык | Код | Whisper STT | TTS движок | Качество | Рынок |
|------|-----|-------------|-----------|----------|-------|
| **Русский** | `ru` | ✅ Отличное | Fish + XTTS | ★★★★★ | BY/RU/UA/KZ — основной |
| **English** | `en` | ✅ Отличное | Fish + XTTS | ★★★★★ | Глобальный |
| **中文 (Mandarin)** | `zh` | ✅ Отличное | Fish + XTTS | ★★★★★ | Китай, Сингапур |
| **日本語** | `ja` | ✅ Отличное | Fish + XTTS | ★★★★☆ | Япония |
| **한국어** | `ko` | ✅ Отличное | Fish + XTTS | ★★★★☆ | Южная Корея |
| **Español** | `es` | ✅ Отличное | Fish + XTTS | ★★★★☆ | Испания, Латам |
| **Français** | `fr` | ✅ Отличное | Fish + XTTS | ★★★★☆ | Франция, Африка |
| **Deutsch** | `de` | ✅ Отличное | Fish + XTTS | ★★★★☆ | DACH регион |
| **Português** | `pt` | ✅ Отличное | Fish + XTTS | ★★★★☆ | Бразилия, Португалия |
| **Italiano** | `it` | ✅ Отличное | XTTS | ★★★★☆ | Италия |

##### Tier 2 — Хорошее качество (STT отличное + TTS хорошее)

| Язык | Код | Whisper STT | TTS движок | Качество | Рынок |
|------|-----|-------------|-----------|----------|-------|
| **Polski** | `pl` | ✅ Отличное | XTTS | ★★★★☆ | Польша (соседи BY) |
| **Українська** | `uk` | ✅ Хорошее | XTTS | ★★★☆☆ | Украина |
| **Nederlands** | `nl` | ✅ Отличное | XTTS | ★★★★☆ | Нидерланды, Бельгия |
| **Türkçe** | `tr` | ✅ Отличное | XTTS | ★★★★☆ | Турция |
| **العربية** | `ar` | ✅ Хорошее | XTTS | ★★★☆☆ | Ближний Восток |
| **हिन्दी** | `hi` | ✅ Хорошее | XTTS | ★★★☆☆ | Индия |
| **Čeština** | `cs` | ✅ Хорошее | XTTS | ★★★☆☆ | Чехия |
| **Magyar** | `hu` | ✅ Хорошее | XTTS | ★★★☆☆ | Венгрия |
| **Română** | `ro` | ✅ Хорошее | XTTS | ★★★☆☆ | Румыния |
| **Svenska** | `sv` | ✅ Отличное | XTTS | ★★★★☆ | Швеция |

##### Tier 3 — Базовое качество (STT хорошее, TTS через voice cloning)

| Язык | Код | Whisper STT | TTS | Качество | Рынок |
|------|-----|-------------|-----|----------|-------|
| **Беларуская** | `be` | ✅ Среднее | XTTS clone | ★★☆☆☆ | Беларусь (гос.язык) |
| **Қазақ** | `kk` | ✅ Среднее | XTTS clone | ★★☆☆☆ | Казахстан |
| **Lietuvių** | `lt` | ✅ Хорошее | XTTS clone | ★★★☆☆ | Литва |
| **Latviešu** | `lv` | ✅ Хорошее | XTTS clone | ★★★☆☆ | Латвия |
| **Eesti** | `et` | ✅ Хорошее | XTTS clone | ★★★☆☆ | Эстония |
| **Suomi** | `fi` | ✅ Хорошее | XTTS clone | ★★★☆☆ | Финляндия |
| **Dansk** | `da` | ✅ Хорошее | XTTS clone | ★★★☆☆ | Дания |
| **Norsk** | `no` | ✅ Хорошее | XTTS clone | ★★★☆☆ | Норвегия |
| **Ελληνικά** | `el` | ✅ Хорошее | XTTS clone | ★★★☆☆ | Греция |
| **Српски** | `sr` | ✅ Среднее | XTTS clone | ★★☆☆☆ | Сербия |
| **Български** | `bg` | ✅ Среднее | XTTS clone | ★★☆☆☆ | Болгария |
| **ქართული** | `ka` | ✅ Среднее | XTTS clone | ★★☆☆☆ | Грузия |

> **ИТОГО: 32 языка** при запуске. Whisper распознаёт ещё ~67 языков — для них TTS добавляется
> через voice cloning: 6 секунд аудио на любом языке → готовый голос. Масштабирование = бесплатно.
> Добавить новый язык = загрузить 6 сек audio sample + протестировать. Без переобучения модели.

#### Голоса (по умолчанию, расширяемые)

| Язык | Голос (женский) | Голос (мужской) |
|------|----------------|----------------|
| Русский | Bella (основной) | Alex |
| English | Sarah | James |
| Deutsch | Anna | Max |
| Español | Sofia | Carlos |
| Français | Claire | Pierre |
| Português | Ana | Rafael |
| Italiano | Giulia | Marco |
| 中文 | Mei | Wei |
| 日本語 | Yuki | Kenji |
| 한국어 | Soo-jin | Min-ho |
| Polski | Kasia | Marek |
| العربية | Layla | Omar |
| Türkçe | Elif | Emre |
| हिन्दी | Priya | Arjun |
| *Остальные 18 языков* | *Через voice cloning* | *Через voice cloning* |

Голоса можно клонировать (XTTS v2 поддерживает voice cloning из 6 секунд аудио).
**Идея:** клиент загружает свой голос → AI агент говорит ЕГО голосом. Premium фича.

---

### 8.6.1 ГОЛОСОВОЙ ПЕРЕВОДЧИК — Voice Translator (двусторонний, real-time)

> **Решение Валерия 2026-03-04:** Голосовой переводчик прямо в приложении / API.
> На том же GPU, теми же компонентами (Whisper + LLM + Fish Speech), €0 сверх инфраструктуры.
> **Ключевое преимущество перед Google Translate:** AI PILOT LLM знает бизнес-терминологию
> (бухгалтерские, юридические, коммерческие термины точнее любого общего переводчика).

#### Пайплайн перевода

```
👤 Пользователь A говорит на русском
    ↓
🗣️ Whisper — STT (ru → текст), авто-определение языка
    ↓
🧠 AI PILOT LLM — перевод ru → de (с учётом контекста + терминологии)
    ↓
🔊 Fish Speech — TTS (немецкий текст → немецкая речь)
    ↓
👤 Собеседник B слышит на немецком (~2 сек)

    ... и наоборот:

👤 Собеседник B отвечает на немецком
    ↓
🗣️ Whisper — STT (de → текст)
    ↓
🧠 AI PILOT LLM — перевод de → ru (с бизнес-контекстом)
    ↓
🔊 Fish Speech — TTS (русский текст → русская речь)
    ↓
👤 Пользователь A слышит на русском (~2 сек)
```

#### API Endpoint

```
POST /v1/voice/translate
Content-Type: multipart/form-data

audio: <wav/mp3/ogg file>       -- аудио на исходном языке
source_lang: "auto"              -- "auto" = Whisper определит сам
target_lang: "de"                -- в какой язык перевести
voice_id: "default"              -- голос на целевом языке (или "clone")
mode: "negotiations"             -- тип контекста (влияет на терминологию)
conversation_id: "uuid"          -- для сохранения контекста диалога

Response: audio/mpeg (streaming)
+ Headers:
    X-Source-Text: "Какая ставка НДС по договору поставки?"
    X-Target-Text: "Wie hoch ist der MwSt-Satz im Liefervertrag?"
    X-Source-Lang: "ru"
    X-Detected-Lang: "ru"
    X-Latency-Ms: "1850"
```

#### 4 режима перевода

| Режим | Контекст LLM | Пример |
|-------|-------------|--------|
| **negotiations** | Коммерческие переговоры, контракты, цены | RU бухгалтер ↔ DE поставщик: "Ставка НДС" → "MwSt-Satz" (не "VAT rate") |
| **calls** | Телефонные переговоры, деловая переписка | RU менеджер ↔ EN клиент: "Отгрузка партии" → "Batch shipment" |
| **dictation** | Голосовой ввод текста с переводом | Надиктовать договор на RU → получить текст на EN |
| **document** | Юридические документы, акты, счета | RU юрист → PL контрагент: "Акт сверки" → "Protokół uzgodnienia" |

#### Преимущество перед Google Translate

| Критерий | Google Translate | AI PILOT Voice Translator |
|----------|-----------------|---------------------------|
| Общий перевод | ★★★★★ | ★★★★☆ |
| **Бухгалтерская терминология** | ★★☆☆☆ | ★★★★★ |
| **Юридическая терминология** | ★★☆☆☆ | ★★★★★ |
| **Коммерческая терминология** | ★★★☆☆ | ★★★★★ |
| Контекст диалога (помнит о чём разговор) | ❌ | ✅ |
| Голосовой ввод/вывод | ✅ | ✅ |
| Работает offline (GPU) | ❌ | ✅ |
| Стоимость | Бесплатно (лимиты) / $20/M символов | €0 (свой GPU) |

#### Примеры бизнес-перевода

```
❌ Google Translate:
  "Акт выполненных работ" → "Act of completed works"  (буквально, неправильно)

✅ AI PILOT (mode: document):
  "Акт выполненных работ" → "Certificate of Completion" (правильный юридический термин)

❌ Google Translate:
  "УСН 6%" → "STS 6%" (аббревиатура, непонятно)

✅ AI PILOT (mode: negotiations):
  "УСН 6%" → "Simplified Tax System (6% of revenue)" (понятно собеседнику)

❌ Google Translate:
  "Кассовая книга" → "Cash book" (ок, но без контекста)

✅ AI PILOT (mode: negotiations, context: BY accounting):
  "Кассовая книга" → "Kassenbuch" (DE) / "Livre de caisse" (FR) — точный термин
```

#### В мобильном приложении — режим "Переводчик"

```
┌──────────────────────────────────────┐
│         🌐 Переводчик                │
│                                      │
│  [🇷🇺 Русский ▼]  ⇄  [🇩🇪 Deutsch ▼] │
│                                      │
│  ┌────────────────────────────────┐  │
│  │ 💬 "Какая ставка НДС по       │  │
│  │     договору поставки?"        │  │
│  │                                │  │
│  │ → "Wie hoch ist der MwSt-Satz │  │
│  │    im Liefervertrag?"          │  │
│  └────────────────────────────────┘  │
│                                      │
│  Режим: [📋 Переговоры ▼]           │
│                                      │
│         [ 🎤 Говорите... ]           │
│                                      │
│  История:                            │
│  • Вы: "Оплата в течение 30 дней"   │
│    → "Zahlung innerhalb von 30 Tagen"│
│  • Собеседник: "Einverstanden, ..."  │
│    → "Согласен, отправляю счёт..."   │
└──────────────────────────────────────┘
```

#### Сценарии использования

| Сценарий | Языки | Режим | Кто использует |
|----------|-------|-------|----------------|
| RU бухгалтер звонит DE поставщику | ru ↔ de | negotiations | Клиенты Ирины |
| BY юрист работает с PL контрагентом | ru ↔ pl | document | Клиенты Леона |
| RU менеджер ведёт EN переговоры | ru ↔ en | negotiations | Клиенты Марины |
| Арабский клиент звонит в BY компанию | ar ↔ ru | calls | Все агенты |
| Диктовка контракта на 2 языках | ru → en | dictation | Клиенты Леона |
| JP партнёр, встреча по Zoom | ja ↔ ru | negotiations | Все агенты |

#### Стоимость: €0

Всё на том же GPU (A100 80GB), теми же моделями:
- Whisper (STT) — уже загружен для voice/chat
- AI PILOT LLM — уже загружен, перевод = обычный prompt
- Fish Speech (TTS) — уже загружен, просто другой голос/язык

**Никаких дополнительных затрат. Переводчик — бонус к голосовому модулю.**

---

### 8.7 КОНТЕНТ-МАШИНА — Соцсети, Рилсы, Видео (Кира + Влад + AI PILOT LLM)

> **Решение Валерия 2026-03-04:** AI PILOT должен сам вести соцсети, генерировать рилсы и видео.
> У нас уже есть Кира (SMM) + Кира Video Pipeline (933 строки). Нужно замкнуть цикл.

#### Полный пайплайн контента

```
📋 Контент-план (Влад генерирует стратегию на месяц)
    ↓
📝 Тексты постов (Кира пишет под каждую площадку)
    ↓
🖼️ Визуалы (Flux.1 генерирует изображения / Кира подбирает)
    ↓
🎬 Видео/Рилсы (Кира Video Pipeline):
    │   Claude → сценарий
    │   ElevenLabs/Fish Speech → озвучка
    │   Flux.1 → картинки/слайды
    │   Luma → видеоклипы (AI video)
    │   FFmpeg → финальная сборка
    ↓
📱 Автопубликация (по расписанию):
    │   Instagram (через Meta Graph API)
    │   Telegram-канал (через Bot API)
    │   YouTube Shorts (через YouTube Data API)
    │   VK (через VK API)
    │   TikTok (через TikTok API)
    ↓
📊 Аналитика (Кира собирает метрики):
    │   Просмотры, лайки, комменты, подписки
    │   → Комендант анализирует → корректирует стратегию
    ↓
🔄 Цикл: лучшие посты → больше таких, худшие → меньше
```

#### API Endpoints (Content Module — 9-й модуль)

```
POST /v1/content/plan           — контент-план на неделю/месяц
POST /v1/content/post           — генерация поста (текст + хэштеги + время)
POST /v1/content/image          — генерация изображения (Flux.1)
POST /v1/content/video          — генерация видео/рилса (полный пайплайн)
POST /v1/content/publish        — автопубликация в соцсети
GET  /v1/content/analytics      — статистика контента
POST /v1/content/reels          — быстрая генерация Reels/Shorts (30-60 сек)
POST /v1/voice/synthesize       — TTS: текст → аудио (для озвучки видео)
```

#### Что уже есть (Кира Video Pipeline — kira_video.py, 933 строки)

| Компонент | Статус | Технология |
|-----------|--------|-----------|
| Скрипт видео | ✅ Работает | Claude → сценарий |
| Озвучка | ✅ Работает | ElevenLabs (→ Fish Speech после LLM) |
| Картинки | ✅ Работает | Flux.1 (Replicate API) |
| Видеоклипы | ✅ Работает | Luma Dream Machine |
| Сборка | ✅ Работает | FFmpeg (на сервере) |
| Хранение | ✅ Работает | Supabase Storage |
| M6 модуль | ✅ Продаётся | €99/мес — 5 видео |
| M7 модуль | ✅ Продаётся | €149/мес — YouTube + Mureka Song |

#### Что нужно добавить

| Фича | Для кого | Как |
|------|----------|-----|
| **Автопубликация** | Клиенты Киры | API соцсетей: Meta Graph, TG Bot, YouTube Data, VK |
| **Расписание** | Клиенты Киры | Celery Beat: публикация по контент-плану |
| **Рилсы 30 сек** | API клиенты | Шаблоны: hook(5с) + контент(20с) + CTA(5с) |
| **AI озвучка (своя)** | После LLM | Fish Speech вместо ElevenLabs → €0 |
| **AI картинки (своя)** | Опционально | SDXL на нашем GPU вместо Flux.1 API → €0 |
| **Аналитика контента** | Клиенты | Сбор метрик → Комендант → рекомендации |

#### Стоимость генерации контента

| Что генерируем | Сторонние | Своё (после LLM) |
|----------------|-----------|-------------------|
| **Пост (текст + хэштеги)** | €0.05 (Claude) | €0 |
| **Изображение** | €0.03 (Flux.1 API) | €0 (SDXL на GPU) |
| **Рилс 30 сек** | €1-2 (Claude + ElevenLabs + Luma) | €0.10 (только Luma API) |
| **Полное видео 3 мин** | €5-10 | €0.50 (только Luma) |
| **30 постов/мес** | €1.50 | €0 |
| **8 рилсов/мес** | €8-16 | €0.80 |
| **Весь контент-план на месяц** | **~€15-25** | **~€1-2** |

> **Luma API** — единственная платная зависимость для видео (AI video generation).
> Альтернатива: Stable Video Diffusion на GPU, но качество пока хуже Luma.
> В будущем: open-source video models дорастут → €0 полностью.

#### Форматы контента по площадкам

| Площадка | Формат | Размер | Частота |
|----------|--------|--------|---------|
| **Instagram** | Рилс 30-60с + карусели + сторис | 1080×1920 / 1080×1080 | 3-5/нед |
| **Telegram** | Посты + видеокружочки + polls | Текст + медиа | 5-7/нед |
| **YouTube Shorts** | Вертикальное видео 30-60с | 1080×1920 | 2-3/нед |
| **VK** | Клипы + посты + видео | 1080×1920 / 1200×630 | 3-5/нед |
| **TikTok** | Вертикальное видео 15-60с | 1080×1920 | 3-5/нед |
| **LinkedIn** | Экспертные посты + карусели | 1200×630 | 1-2/нед |

#### Для клиентов AI PILOT (что продаём)

Кира уже умеет генерировать видео (M6/M7). Дополнение:

| Модуль | Что включает | Цена |
|--------|-------------|------|
| **Кира M6** | 5 видео/мес + контент-план + посты | €99/мес |
| **Кира M7** | YouTube канал + Mureka Song + 10 видео | €149/мес |
| **Кира M8 (NEW)** | Автопубликация 5 площадок + аналитика + A/B тесты | €199/мес |
| **Влад M6 (NEW)** | Контент-стратегия + SEO-посты + рассылки | €149/мес |

#### Для нашего сайта ai-pilot.by

AI PILOT сам ведёт свои соцсети:
- Кира-Пилот генерирует контент для наших аккаунтов
- Автоматически: рилсы с демо агентов, кейсы клиентов, новости обновлений
- Человек (Валерий) только одобряет или корректирует

---

### 8.8 ИТОГОВАЯ СТРУКТУРА ПРОДУКТОВ

```
AI PILOT
│
├── 1. ПЛАТФОРМА (ai-pilot.by)              — 8 AI-сотрудников для бизнеса
│   ├── Текстовый чат (Telegram + Cabinet + Widget)
│   ├── Голосовой чат (Mobile App + Web)
│   ├── Видео/Рилсы (Кира Video Pipeline)
│   ├── Автопубликация (5 соцсетей)
│   └── Клиенты: бизнесы (€39-249/мес per agent)
│
├── 2. API (api.ai-pilot.by)                — AI PILOT LLM для разработчиков
│   ├── 10 модулей: Бухгалтерия/Юридика/Продажи/HR/Маркетинг/Реклама/Веб/Код/Контент/Перевод
│   ├── Voice API (/v1/voice/chat, /v1/voice/translate, /v1/voice/synthesize)
│   ├── Content API (/v1/content/*)
│   └── Клиенты: разработчики (€49-999/мес)
│
├── 3. ПРИЛОЖЕНИЕ (App Store / Google Play)  — AI PILOT
│   ├── Сканер документов (OCR → проводки)
│   ├── Голосовой ассистент (hands-free)
│   ├── Голосовой переводчик (двусторонний, 30+ языков)
│   ├── Чат со всеми 8 агентами
│   └── Клиенты: бухгалтеры, юристы, менеджеры (Free → €9.99/мес)
│
└── 4. КОНТЕНТ-МАШИНА (внутренняя)           — AI PILOT ведёт свои соцсети
    ├── Instagram + TikTok + YouTube Shorts + VK + Telegram + LinkedIn
    ├── Рилсы / видео / посты / сторис — автоматически
    └── Стоимость: ~€2/мес (только Luma API)
```

**Все продукты работают на одном движке: AI PILOT LLM + Whisper + Fish Speech.**
**Один GPU €200/мес. Ноль зависимостей от сторонних AI-сервисов.**

### Сроки общие
| Этап | Что | Срок | Стоимость |
|------|-----|------|-----------|
| 1 | Multi-LLM абстракция | 2 нед | $0 |
| 2 | Dataset подготовка | 1 нед | $0 |
| 3 | Fine-tune v0.1 | 3-5 дней | $50-200 |
| 4 | Деплой + тестирование | 1 нед | €200/мес |
| 5 | Гибридный роутер | 1 нед | $0 |
| 6 | RLHF/DPO (v0.2) | 2-4 нед | $100-500 |
| 7 | Developer Portal + API docs | 3-4 нед | $0 (свой стек) |
| 8 | Mobile App (Scanner + Voice + Chat) | 4-6 нед | €99/год (Apple+Google) |
| 9 | Voice Module + Translator (Whisper + TTS, 32 языка) | 2-3 нед | €0 (на GPU) |
| 10 | Content Pipeline (автопубликация) | 2-3 нед | €0 (API соцсетей бесплатные) |
| **ИТОГО до полного продукта** | | **~18-24 недели** | **~€800 разово + €200/мес** |

### Технические требования
- **Обучение:** RunPod/Lambda 1x A100 80GB ($2-5/час × 4-8 часов)
- **Inference:** Hetzner EX44 + GPU (~€200/мес) — LLM + Whisper + TTS + опционально SDXL
- **Фреймворк обучения:** unsloth / axolotl (Python, open-source)
- **Inference server:** vLLM или TGI (HuggingFace)
- **STT:** Whisper Large v3 (open-source, ~3GB VRAM, 99 языков)
- **TTS:** Fish Speech 1.5 / XTTS v2 (open-source, ~4GB VRAM, voice cloning из 6 сек аудио)
- **Translator:** Тот же пайплайн (Whisper→LLM→TTS), 32 языка, 4 бизнес-режима, €0
- **Image gen:** SDXL (open-source, ~6GB VRAM) или Flux.1 API ($0.03/img)
- **Video gen:** Luma Dream Machine API ($0.10/clip) — пока нет open-source альтернативы
- **Mobile:** React Native + Expo EAS Build
- **Developer Portal:** Next.js 16 (console.ai-pilot.by)
- **Docs:** Mintlify или Docusaurus (docs.ai-pilot.by)
- **Social APIs:** Meta Graph API, YouTube Data API v3, VK API, Telegram Bot API, TikTok API
- **Нужен ML-опыт:** средний (QLoRA fine-tune хорошо документирован, есть готовые скрипты)

---

### 8.9 ШИФРОВАНИЕ И ХРАНЕНИЕ ДИАЛОГОВ

> **Принцип:** Все диалоги, голосовые расшифровки и переводы — шифруются.
> Никаких данных в открытом виде. Ключи отдельно от данных. GDPR + Закон РБ о персональных данных.

#### Что храним

| Тип данных | Таблица Supabase | Шифрование | Срок хранения |
|------------|-----------------|------------|---------------|
| **Текстовые диалоги** | `conversations` | AES-256-GCM | 6 мес (data retention) |
| **Голосовые расшифровки** | `voice_transcripts` | AES-256-GCM | 6 мес |
| **Переводы** | `translation_logs` | AES-256-GCM | 6 мес |
| **Аудио-файлы** | НЕ ХРАНИМ | — | Удаляем сразу после обработки |
| **Метаданные** (кто, когда, токены) | `conversation_meta` | Без шифрования (нет PII) | 5 лет (бух.учёт РБ) |
| **Анонимизированные логи** | `agent_learning_log` | SHA256 client_id | 5 лет (для ML) |

#### Архитектура шифрования

```
📱 Клиент (текст / голос / перевод)
    │
    ↓ TLS 1.3 (шифрование в транзите)
    │
🔒 FastAPI endpoint (HTTPS only, HSTS)
    │
    ├── 1. Обработка (LLM / Whisper / TTS)
    │       ↓
    │   📝 Результат (текст ответа / расшифровка / перевод)
    │       ↓
    ├── 2. Шифрование перед записью в БД
    │       ↓
    │   🔑 AES-256-GCM (ключ = ENCRYPTION_KEY из Railway env)
    │   🔑 Уникальный IV (initialization vector) на каждую запись
    │   🔑 AAD (associated data) = conversation_id + timestamp (защита от подмены)
    │       ↓
    ├── 3. Запись в Supabase
    │       ↓
    │   🗄️ encrypted_content (bytea) + iv (bytea) + tag (bytea)
    │       ↓
    └── 4. Аудио-файлы → УДАЛЕНИЕ
            (только текст расшифровки сохраняется, сам голос — нет)
```

#### Схема таблицы `conversations`

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL,          -- группировка сообщений одного диалога
    client_id_hash TEXT NOT NULL,            -- SHA256(wp_user_id + salt), НЕ реальный ID
    agent_type TEXT NOT NULL,                -- 'iryna', 'leon', etc.
    channel TEXT NOT NULL,                   -- 'telegram', 'cabinet', 'widget', 'voice', 'api'
    direction TEXT NOT NULL,                 -- 'user' | 'agent'

    -- Зашифрованное содержимое
    encrypted_content BYTEA NOT NULL,        -- AES-256-GCM(message_text)
    encryption_iv BYTEA NOT NULL,            -- Уникальный IV (12 bytes)
    encryption_tag BYTEA NOT NULL,           -- GCM auth tag (16 bytes)
    encryption_version SMALLINT DEFAULT 1,   -- Для key rotation

    -- Метаданные (НЕ зашифрованы — нет PII)
    tokens_used INTEGER,
    model_used TEXT,                          -- 'ai-pilot-llm-v1', 'claude-haiku', etc.
    language TEXT DEFAULT 'ru',
    latency_ms INTEGER,

    -- Для голосовых
    is_voice BOOLEAN DEFAULT FALSE,
    voice_duration_sec NUMERIC(6,1),

    -- Для переводов
    is_translation BOOLEAN DEFAULT FALSE,
    source_lang TEXT,
    target_lang TEXT,
    translation_mode TEXT,                   -- 'negotiations', 'calls', 'dictation', 'document'

    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '6 months'
);

-- Индексы
CREATE INDEX idx_conv_client ON conversations(client_id_hash, created_at DESC);
CREATE INDEX idx_conv_agent ON conversations(agent_type, created_at DESC);
CREATE INDEX idx_conv_conversation ON conversations(conversation_id);
CREATE INDEX idx_conv_expires ON conversations(expires_at) WHERE expires_at < NOW();

-- RLS: только service_role
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_only" ON conversations FOR ALL TO service_role USING (true);
```

#### Ключи шифрования

```
┌─────────────────────────────────────────────────────────────────┐
│  KEY MANAGEMENT                                                  │
│                                                                  │
│  ENCRYPTION_KEY          = Railway env var (32 bytes, hex)       │
│  ENCRYPTION_KEY_PREVIOUS = Railway env var (для rotation)        │
│  ENCRYPTION_SALT         = Railway env var (для client_id_hash)  │
│                                                                  │
│  ⛔ Ключи НИКОГДА не хранятся в:                                │
│     - Supabase (ни в таблицах, ни в vault)                      │
│     - Git (ни в коде, ни в .env файлах в репо)                  │
│     - Логах (маскируются при любом выводе)                       │
│                                                                  │
│  ✅ Ключи ТОЛЬКО в:                                             │
│     - Railway environment variables (encrypted at rest)          │
│     - GKE Secrets (Kubernetes)                                   │
│     - При необходимости: HashiCorp Vault (будущее)              │
│                                                                  │
│  🔄 Key Rotation: каждые 90 дней                                │
│     1. Новый ключ → ENCRYPTION_KEY                              │
│     2. Старый ключ → ENCRYPTION_KEY_PREVIOUS                    │
│     3. Background job: перешифровать записи с version=N → N+1   │
│     4. После 100% миграции: удалить PREVIOUS                    │
└─────────────────────────────────────────────────────────────────┘
```

#### FastAPI: модуль шифрования

```python
# v2/backend/app/security/encryption.py

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, hashlib

class ConversationEncryptor:
    """AES-256-GCM шифрование диалогов."""

    def __init__(self, key_hex: str):
        self.key = bytes.fromhex(key_hex)
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str, conversation_id: str) -> tuple[bytes, bytes, bytes]:
        """Шифрует текст. Возвращает (ciphertext, iv, tag)."""
        iv = os.urandom(12)  # 96-bit IV, уникальный каждый раз
        aad = conversation_id.encode()  # associated data = защита от подмены
        ct = self.aesgcm.encrypt(iv, plaintext.encode('utf-8'), aad)
        # GCM: последние 16 байт = tag
        return ct[:-16], iv, ct[-16:]

    def decrypt(self, ciphertext: bytes, iv: bytes, tag: bytes, conversation_id: str) -> str:
        """Расшифровывает текст."""
        aad = conversation_id.encode()
        plaintext = self.aesgcm.decrypt(iv, ciphertext + tag, aad)
        return plaintext.decode('utf-8')

    @staticmethod
    def hash_client_id(wp_user_id: int, salt: str) -> str:
        """SHA256 хеш для анонимизации."""
        return hashlib.sha256(f"{wp_user_id}:{salt}".encode()).hexdigest()
```

#### Data Retention (автоочистка)

```
⏰ Celery Beat: каждый понедельник 04:00 UTC

    1. SELECT id FROM conversations WHERE expires_at < NOW()
       → Soft delete (помечаем deleted_at, НЕ удаляем физически)

    2. SELECT id FROM conversations WHERE deleted_at < NOW() - INTERVAL '30 days'
       → Hard delete (физическое удаление через 30 дней после soft delete)

    3. Страж проверяет: есть ли активность клиента за последние 6 мес?
       → Да: продлить expires_at ещё на 6 мес
       → Нет: оставить для удаления

    4. Бухгалтерские метаданные (conversation_meta) → хранятся 5 лет
       (по Закону РБ о бухгалтерском учёте)
```

#### Для ML-обучения (RLHF/DPO)

```
Диалоги → анонимизация → обучение:

1. client_id_hash (SHA256, необратимый)
2. Убираем PII из текста:
   - Имена → [ИМЯ]
   - Телефоны → [ТЕЛЕФОН]
   - Email → [EMAIL]
   - УНП/ИНН → [УНП]
   - Адреса → [АДРЕС]
   - Банковские реквизиты → [РЕКВИЗИТЫ]
3. Только качественные диалоги (response_quality ≥ 0.7)
4. Экспорт в JSONL: {"system": ..., "user": ..., "assistant": ...}
5. PII-скрубер: regex + spaCy NER (Named Entity Recognition)
```

#### GDPR + Закон РБ

| Требование | Как выполняем |
|------------|--------------|
| **Право на удаление (GDPR Art.17)** | `DELETE FROM conversations WHERE client_id_hash = hash(user_id)` — мгновенно |
| **Право на экспорт (GDPR Art.20)** | `SELECT decrypt(encrypted_content) WHERE client_id_hash = ...` → JSON/CSV |
| **Минимизация данных** | Аудио НЕ храним, только расшифровка. Метаданные без PII |
| **Encryption at rest** | AES-256-GCM, ключи вне БД |
| **Encryption in transit** | TLS 1.3 на всех endpoints |
| **Data breach notification** | Даже при утечке БД — данные зашифрованы, бесполезны без ключа |
| **Закон РБ о перс.данных** | Согласие при регистрации + хранение 6 мес + бух.метаданные 5 лет |
| **Логирование доступа** | Каждое чтение диалога логируется (кто, когда, зачем) |

#### Стоимость

| Компонент | Стоимость |
|-----------|-----------|
| `pgcrypto` (PostgreSQL) | €0 (встроен в Supabase) |
| `cryptography` (Python) | €0 (open-source) |
| Хранение (шифротекст ~1.1× от оригинала) | ~€0 (Supabase 8GB free) |
| Key management | €0 (Railway/GKE env vars) |
| **ИТОГО** | **€0** |

> **Вывод:** Полное шифрование всех диалогов (текст, голос, переводы) с нулевыми дополнительными затратами.
> Даже при компрометации базы данных — злоумышленник получит только зашифрованные байты.
> Ключи хранятся отдельно (Railway/GKE), не в Supabase.

---

### 8.10 РОСТ И ОБУЧЕНИЕ МОДЕЛИ — Training Data Pipeline

> **Вопрос:** где хранить данные для обучения, когда их станет много?
> **Ответ:** текст — компактный. Даже через 3 года = ~200 GB максимум. Это один SSD диск.
> Аудио НЕ хранится (только расшифровки). Видео НЕ хранится (генерируется на лету).

#### Рост данных по этапам

| Этап | Когда | Клиентов | Диалогов | Размер датасета | Размер модели |
|------|-------|----------|----------|-----------------|---------------|
| **v0.1** Fine-tune | Месяц 3 | 0 (синтетика) | ~50K | **~250 MB** | 10 GB (4-bit) |
| **v0.2** RLHF/DPO | Месяц 6 | 100+ | ~200K filtered | **~2 GB** | 10 GB |
| **v1.0** Зрелая | Год 1 | 1,000+ | ~2M filtered | **~17 GB** | 10 GB |
| **v2.0** Масштаб | Год 2-3 | 10,000+ | ~10M filtered | **~50 GB** | 10-20 GB |
| **v3.0** Полная | Год 3+ | 50,000+ | ~50M | **~200 GB** | 20-30 GB |

> **Почему так мало?** Текст = компактно. 1 диалог (user + assistant) ≈ 2 KB.
> 1 миллион диалогов = 2 GB. Аудио не храним (только расшифровку = текст).

#### Откуда берутся данные

```
📊 ИСТОЧНИКИ ДАННЫХ ДЛЯ ОБУЧЕНИЯ

┌── A. СИНТЕТИЧЕСКИЕ (v0.1, есть сейчас) ──────────────────────┐
│                                                                │
│  1. Конституции 9 агентов              ~500 KB                │
│  2. KB seed (3857 записей)             ~2 MB                  │
│  3. Примеры диалогов (example_store)   ~1 MB                  │
│  4. Knowledge sources (217 URL)        ~50 MB (краулинг)      │
│  5. Генерация Claude:                                          │
│     - 50K синтетических диалогов       ~200 MB                │
│     - По каждому агенту: 5K+ примеров                         │
│     - Разные сценарии, языки, тональности                     │
│                                                                │
│  ИТОГО: ~250 MB                                                │
└────────────────────────────────────────────────────────────────┘

┌── B. РЕАЛЬНЫЕ (v0.2+, после запуска) ─────────────────────────┐
│                                                                │
│  1. Реальные диалоги (conversations)                          │
│     - Фильтр: quality ≥ 0.7                                   │
│     - Анонимизация: SHA256 + PII scrubber                     │
│     - ~40% диалогов проходят фильтр                           │
│                                                                │
│  2. Голосовые расшифровки (voice_transcripts)                  │
│     - Тот же формат: user/assistant text                       │
│     - Дополнительно: language, accent metadata                 │
│                                                                │
│  3. Переводы (translation_logs)                                │
│     - Тройка: source_text + target_text + correction           │
│     - Бесценно для обучения переводчика                       │
│                                                                │
│  4. Feedback (user_feedback)                                   │
│     - Thumbs up/down → DPO preference pairs                   │
│     - "Этот ответ лучше того" → прямое обучение              │
│                                                                │
│  5. Краулинг (knowledge_crawler, ежедневно)                   │
│     - 217 источников → новые статьи → KB                      │
│     - Юридические обновления, новости, тренды                 │
│                                                                │
│  ИТОГО через год: ~17 GB                                       │
└────────────────────────────────────────────────────────────────┘

┌── C. СПЕЦИАЛИЗИРОВАННЫЕ (v1.0+) ──────────────────────────────┐
│                                                                │
│  1. Бухгалтерские документы (шаблоны, не клиентские)          │
│     - Акты, счета, КУДИР форматы, проводки                    │
│     - Законодательство BY/RU (NALOG, ilex.by)                 │
│                                                                │
│  2. Юридические шаблоны                                        │
│     - Договоры, NDA, претензии, ответы на запросы              │
│     - Судебная практика (open data)                            │
│                                                                │
│  3. 1С-специфичные данные                                      │
│     - Форматы обмена, проводки, справочники                   │
│     - Open-source: 1С:EDT примеры (GitHub)                    │
│                                                                │
│  ИТОГО: ~5-10 GB                                               │
└────────────────────────────────────────────────────────────────┘
```

#### Где хранить — 3 уровня

```
┌─────────────────────────────────────────────────────────────────┐
│  УРОВЕНЬ 1: ГОРЯЧИЕ ДАННЫЕ (нужны прямо сейчас)                │
│                                                                  │
│  📍 Supabase PostgreSQL (уже есть)                              │
│  📦 Лимит: 8 GB free → Pro $25/мес 100 GB                      │
│  🔒 Шифрование: AES-256-GCM (секция 8.9)                       │
│                                                                  │
│  Что здесь:                                                     │
│  • conversations (текущие диалоги, 6 мес)          ~5-10 GB     │
│  • agent_knowledge_base (RAG)                      ~100 MB      │
│  • agent_learning_log (логи взаимодействий)        ~500 MB      │
│  • knowledge_sources + crawl_log                   ~200 MB      │
│                                                                  │
│  Стоимость: $25/мес (Supabase Pro, уже платим)                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  УРОВЕНЬ 2: ТЁПЛЫЕ ДАННЫЕ (датасеты для обучения)               │
│                                                                  │
│  📍 Hetzner Storage Box (тот же дата-центр что GPU)             │
│  📦 BX11: 1 TB = €3.81/мес | BX21: 5 TB = €9.17/мес           │
│  🔒 Шифрование: SFTP/FTPS + encryption at rest                  │
│  🌍 Локация: EU (Falkenstein/Helsinki) — GDPR compliant         │
│                                                                  │
│  Что здесь:                                                     │
│  • training_datasets/ (JSONL файлы для fine-tune)               │
│  •   ├── v0.1_synthetic_50k.jsonl          ~200 MB              │
│  •   ├── v0.2_real_200k.jsonl              ~400 MB              │
│  •   ├── v0.2_dpo_pairs_50k.jsonl          ~200 MB              │
│  •   ├── v1.0_full_2m.jsonl               ~4 GB                 │
│  •   └── translations_500k.jsonl           ~1 GB                │
│  • model_checkpoints/ (веса модели после обучения)              │
│  •   ├── ai-pilot-llm-v0.1/ (QLoRA adapter)  ~500 MB           │
│  •   ├── ai-pilot-llm-v0.2/ (merged)         ~10 GB            │
│  •   └── ai-pilot-llm-v1.0/ (merged)         ~20 GB            │
│  • raw_crawl/ (сырые данные краулинга)         ~2 GB            │
│  • evaluations/ (результаты бенчмарков)        ~100 MB          │
│                                                                  │
│  Стоимость: €3.81/мес (1 TB хватит на 2+ года)                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  УРОВЕНЬ 3: ХОЛОДНЫЕ ДАННЫЕ (архив, бэкапы)                     │
│                                                                  │
│  📍 Hetzner Storage Box BX21 (5 TB) или Backblaze B2            │
│  📦 Backblaze B2: $6/TB/мес (первые 10 GB бесплатно)           │
│  🔒 Шифрование: client-side AES-256 перед загрузкой             │
│                                                                  │
│  Что здесь:                                                     │
│  • Старые датасеты (>1 года)                                    │
│  • Архивные model checkpoints                                    │
│  • Бэкапы conversations (после data retention)                   │
│  • Полные снэпшоты Supabase (pg_dump, weekly)                   │
│                                                                  │
│  Стоимость: ~€5-10/мес (только когда данных >1 TB)              │
└─────────────────────────────────────────────────────────────────┘
```

#### Суммарная стоимость хранения

| Этап | Объём данных | Где | Стоимость/мес |
|------|-------------|-----|---------------|
| **v0.1** (старт) | ~250 MB | Supabase free | **€0** |
| **v0.2** (100 клиентов) | ~2 GB | Supabase free + Hetzner BX11 | **€3.81** |
| **v1.0** (1K клиентов) | ~30 GB | Supabase Pro + Hetzner BX11 | **€28.81** |
| **v2.0** (10K клиентов) | ~200 GB | Supabase Pro + Hetzner BX21 | **€34.17** |
| **v3.0** (50K клиентов) | ~1 TB | Supabase Pro + Hetzner BX21 + Backblaze | **€40-50** |

> **Вывод:** Хранение данных для обучения = **€0-50/мес** даже при 50K клиентах.
> Это копейки по сравнению с GPU (€200/мес) и доходом от API.

#### Пайплайн обучения (как модель растёт)

```
🔄 ЦИКЛ ОБУЧЕНИЯ AI PILOT LLM

Ежедневно (автоматически):
┌─────────────────────────────────────────────┐
│  1. Краулер собирает новые статьи (217 URL) │
│  2. Новые диалоги → conversations           │
│  3. Комендант анализирует learning_log      │
│  4. Knowledge gaps → agent_knowledge_base   │
└─────────────────────────────────────────────┘

Еженедельно (автоматически):
┌─────────────────────────────────────────────┐
│  1. Export: conversations → JSONL            │
│     (filtered: quality ≥ 0.7, anonymized)   │
│  2. Export: feedback → DPO pairs             │
│  3. Upload → Hetzner Storage Box             │
│  4. Метрики: accuracy, hallucination rate    │
└─────────────────────────────────────────────┘

Ежемесячно (полуавтоматически):
┌─────────────────────────────────────────────┐
│  1. Накопилось 10K+ новых примеров?         │
│     → Да: запуск дообучения (LoRA)          │
│     → Нет: ждём следующий месяц             │
│                                              │
│  2. Fine-tune на RunPod ($10-30 за сессию)  │
│     - Базовая модель + новый LoRA adapter   │
│     - 2-4 часа на A100                      │
│                                              │
│  3. A/B тест: новая vs текущая              │
│     - 100 тестовых запросов                  │
│     - Сравнение: точность, скорость, тон    │
│                                              │
│  4. Если лучше → деплой (vLLM hot-swap)     │
│     Если хуже → откат, анализ               │
│                                              │
│  5. Валерий получает отчёт в Boss Bot:      │
│     "LLM v0.3 → v0.4: +3% accuracy,        │
│      -12% hallucinations, 15K new examples" │
└─────────────────────────────────────────────┘

Ежеквартально (ручное решение):
┌─────────────────────────────────────────────┐
│  1. Полный merge LoRA → base model          │
│  2. Публикация новой major версии           │
│  3. Бенчмарк vs Claude / Mistral            │
│  4. Решение: нужна ли бОльшая модель?       │
│     17B хватает? Или пора на 32B/70B?       │
└─────────────────────────────────────────────┘
```

#### Формат данных для обучения

```jsonl
// training_datasets/v0.2_real_200k.jsonl
// Одна строка = один пример обучения

{"system": "Ты — Ирина, AI бухгалтер компании AI PILOT...", "messages": [{"role": "user", "content": "Какой у меня остаток по УСН за Q1?"}, {"role": "assistant", "content": "По данным КУДИР за Q1 2026: доход 12,450 BYN, налог УСН 6% = 747 BYN. Срок уплаты: до 22 апреля 2026 (п.2 ст.342 НК РБ)."}], "metadata": {"agent": "iryna", "lang": "ru", "quality": 0.92, "tags": ["tax", "usn", "quarterly"]}}

// DPO pairs (v0.2+): хороший vs плохой ответ
{"system": "...", "prompt": "Сколько стоит тариф Pro?", "chosen": "Тариф Pro для Ирины — €79/мес. Включает: 200K токенов, миграцию данных, 12 мес хранение. Попробовать бесплатно: ai-pilot.by/agents/iryna", "rejected": "Про стоит 79 евро. Купить можно на сайте.", "metadata": {"agent": "iryna", "quality_chosen": 0.95, "quality_rejected": 0.4}}
```

#### Безопасность данных для обучения

| Угроза | Защита |
|--------|--------|
| **PII в датасете** | PII scrubber (regex + spaCy NER) перед экспортом. Имена→[ИМЯ], УНП→[УНП] |
| **Утечка датасета** | Шифрование AES-256 на Storage Box. Доступ только по SSH key |
| **Отравление данных** (data poisoning) | quality filter ≥ 0.7 + outlier detection + ручная проверка 1% |
| **Bias в модели** | Балансировка по агентам/языкам/сценариям. Бенчмарк fairness метрик |
| **Model extraction** (кража модели) | Модель на нашем GPU, не в облаке. API rate limits. Watermarking |
| **Клиент просит удалить данные** | GDPR delete → убираем из conversations + из следующего датасета. Текущая модель не "забывает" (это ок по GDPR — модель ≠ данные) |

#### Когда нужна бОльшая модель?

| Сигнал | Действие |
|--------|----------|
| Quality score ≤ 0.75 (plateau) | Пора: 17B → 32B |
| Клиенты жалуются на "глупые ответы" | Анализ: данные или размер модели? |
| Новый домен (медицина, строительство) | Может хватить LoRA adapter, не full model |
| 100K+ клиентов | Скорее всего нужен 32B+ для diversity |
| Конкуренты выпустили лучше | Бенчмарк → решение |

**Переход 17B → 32B:**
- VRAM: ~20 GB (4-bit) вместо ~10 GB — влезает на тот же A100
- Обучение: $100-400 вместо $50-200
- Качество: +5-10% на сложных задачах
- Решение принимает Валерий на основе метрик

---

### 8.11 РЕЖИМЫ РАБОТЫ АГЕНТА — Agent Modes (план / разговор / автомат)

> Как Claude Code имеет режимы Plan / Chat / Auto — наш AI PILOT LLM будет иметь аналог.
> Каждый агент может работать в 3 режимах. Клиент выбирает, или режим выбирается автоматически.

#### Три режима

| Режим | Иконка | Когда | Что делает |
|-------|--------|-------|-----------|
| **Plan** (План) | 📋 | Клиент: "Составь план миграции" / "Что нужно для регистрации ООО?" | Агент анализирует задачу, составляет пошаговый план, показывает клиенту на утверждение. НЕ выполняет действий до одобрения. Вопросы уточняющие задаёт ДО плана. |
| **Chat** (Разговор) | 💬 | По умолчанию. Вопрос-ответ. "Какой у меня баланс?" / "Когда платить УСН?" | Обычный диалог. Агент отвечает на вопросы, консультирует, объясняет. Не выполняет сложных многошаговых действий без запроса. |
| **Auto** (Автомат) | ⚡ | Клиент: "Сделай всё сам" / "Проведи полный аудит и исправь" | Агент выполняет полный цикл автономно: анализ → план → действия → проверка → отчёт. Промежуточного одобрения не требует. Обращается к клиенту только при критических решениях (деньги, удаление данных). |

#### Как переключается режим

```
1. ЯВНОЕ переключение (клиент пишет):
   "Составь план" → автоматически переключает в Plan
   "Сделай сам" / "на автомате" → переключает в Auto
   "Просто ответь" / "расскажи" → переключает в Chat

2. КНОПКИ в UI (кабинет + виджет):
   [📋 План] [💬 Чат] [⚡ Авто]
   Текущий режим подсвечен

3. API параметр:
   POST /v1/chat
   { "mode": "plan" | "chat" | "auto", "message": "..." }
   Если mode не указан → агент определяет автоматически по intent

4. АВТОДЕТЕКЦИЯ (intent-based):
   Classifier (Haiku/small модель) анализирует сообщение:
   - "составь" / "спланируй" / "что нужно для" → Plan
   - "сделай" / "проведи" / "исправь всё" / "автоматом" → Auto
   - всё остальное → Chat (default)
```

#### Поведение в каждом режиме

**Plan mode:**
```
Клиент: "Подготовь документы для открытия ООО в Беларуси"

Леон (Plan mode):
┌──────────────────────────────────────────────────┐
│ 📋 ПЛАН: Регистрация ООО в Беларуси              │
│                                                  │
│ 1. Устав (шаблон + кастомизация под вашу сферу)  │
│ 2. Решение единственного учредителя              │
│ 3. Заявление формы 1 (Минюст)                    │
│ 4. Гарантийное письмо на юр. адрес               │
│ 5. Квитанция госпошлины (1 БВ = ~41 BYN)         │
│                                                  │
│ Срок: 2-3 рабочих дня после утверждения          │
│ Стоимость: тариф Pro (включено в подписку)       │
│                                                  │
│ [✅ Одобрить и начать]  [✏️ Изменить]  [❌ Отмена] │
└──────────────────────────────────────────────────┘

После одобрения → переходит в Auto для исполнения.
```

**Auto mode:**
```
Клиент: "Проведи полный аудит моей бухгалтерии за Q1"

Ирина (Auto mode):
⚡ Начинаю полный аудит Q1 2026...
├── ✅ 1/5 Загрузка данных КУДИР (237 записей)
├── ✅ 2/5 Проверка полноты: 3 пропущенных акта
├── ⏳ 3/5 Сверка с банком...
├── ⏳ 4/5 Расчёт УСН
└── ⏳ 5/5 Генерация отчёта

[Промежуточный статус обновляется в реальном времени через SSE]

По завершении:
📊 Отчёт аудита Q1 2026
- Записей проверено: 237
- Найдено ошибок: 3 (недостающие акты)
- УСН к уплате: 1,247 BYN (срок: 22.04.2026)
- Рекомендации: [список]
- [📄 Скачать PDF отчёт]
```

#### Технические детали

```python
# API endpoint
POST /v1/chat
{
    "agent": "iryna",
    "mode": "auto",         # plan | chat | auto | null (auto-detect)
    "message": "Проведи аудит за Q1",
    "config_id": "uuid-...",
    "stream": true
}

# SSE events для Auto mode:
data: {"type": "mode", "mode": "auto"}
data: {"type": "plan", "steps": [...], "total": 5}
data: {"type": "progress", "step": 1, "status": "done", "detail": "Загрузка данных КУДИР"}
data: {"type": "progress", "step": 2, "status": "done", "detail": "Проверка полноты"}
data: {"type": "progress", "step": 3, "status": "running", "detail": "Сверка с банком..."}
data: {"type": "delta", "text": "Найдено 3 расхождения..."}
data: {"type": "progress", "step": 3, "status": "done"}
data: {"type": "result", "summary": "...", "attachments": ["report.pdf"]}
data: {"type": "done", "tokens_used": 4200, "cost_eur": 0.012}
```

#### Матрица режимов по агентам

| Агент | Plan (частые сценарии) | Auto (частые сценарии) |
|-------|----------------------|----------------------|
| **Лиза** | "Что нужно чтобы подключить агента?" | "Настрой мне Марину с AmoCRM" |
| **Ирина** | "Составь план миграции от бухгалтера" | "Проведи аудит Q1" / "Закрой период" |
| **Марина** | "План маркетинга на месяц" | "Обработай все новые лиды" |
| **Леон** | "Что нужно для регистрации ООО?" | "Подготовь все документы для ООО" |
| **Даниил** | "Стратегия рекламной кампании" | "Запусти кампанию с бюджетом $500" |
| **Кира** | "Контент-план на неделю" | "Создай 5 рилсов для Instagram" |
| **Влад** | "SWOT-анализ моего бизнеса" | "Проведи полное исследование рынка" |
| **Анна** | "Оценить кандидатов на вакансию" | "Отфильтруй 50 резюме и составь шортлист" |

#### Защита Auto mode

- **Финансовые действия** (оплата, списание, перевод): ВСЕГДА подтверждение клиента
- **Удаление данных**: ВСЕГДА подтверждение клиента
- **Лимит стоимости**: если автоматические действия превысят €5 токенов → пауза + запрос
- **Таймаут**: Auto mode прерывается через 10 минут с промежуточным отчётом
- **Тарифная проверка**: если действие требует тариф выше текущего → показать upgrade, не блокировать

#### Стоимость реализации

| Что | Затраты |
|-----|---------|
| Intent classifier (fine-tune Haiku) | $0 (уже есть в pipeline) |
| SSE progress events | €0 (уже есть инфраструктура) |
| UI кнопки режимов | €0 (фронтенд) |
| Auto mode orchestrator | 2-3 дня разработки |
| **Итого** | €0 прямых, 1 неделя разработки |

---

### 8.12 ЗАГРУЗКА И ОБРАБОТКА ДОКУМЕНТОВ — Document Processing Pipeline

> Агенты должны уметь принимать файлы: PDF, Word, Excel, изображения, архивы.
> OCR + извлечение текста + анализ контента — нативно, без сторонних SaaS.

#### Поддерживаемые форматы

| Категория | Форматы | Библиотека | Что извлекаем |
|-----------|---------|-----------|--------------|
| **PDF** | `.pdf` | PyMuPDF (fitz) | Текст, таблицы, метаданные, страницы-картинки |
| **Word** | `.doc`, `.docx` | python-docx, antiword (для .doc) | Текст, таблицы, стили, embedded images |
| **Excel** | `.xls`, `.xlsx`, `.csv` | openpyxl, xlrd, pandas | Данные ячеек, формулы, несколько листов |
| **Презентации** | `.ppt`, `.pptx` | python-pptx | Текст слайдов, заметки, embedded images |
| **Изображения** | `.jpg`, `.png`, `.gif`, `.bmp`, `.webp`, `.tiff`, `.heic` | Pillow + Tesseract OCR | OCR текст, EXIF метаданные, размеры |
| **Сканы/фото документов** | `.jpg`, `.png`, `.pdf` (scanned) | Tesseract OCR + Claude Vision | Распознанный текст, структура документа |
| **Архивы** | `.zip`, `.rar`, `.7z`, `.tar.gz` | zipfile, py7zr, rarfile | Список файлов → рекурсивная обработка каждого |
| **Текст** | `.txt`, `.md`, `.json`, `.xml`, `.html`, `.rtf` | Встроенные | Текст напрямую |
| **Электронные таблицы** | `.ods` (OpenDocument) | odfpy | Ячейки, формулы |
| **Email** | `.eml`, `.msg` | email (stdlib), extract-msg | Тема, отправитель, тело, вложения → рекурсивно |
| **CAD/Чертежи** | `.dwg`, `.dxf` | ezdxf (только DXF) | Слои, размеры, текст (ограниченно) |

#### Размеры и ограничения

| Параметр | Лимит | Почему |
|----------|-------|--------|
| **Макс. размер файла** | 50 MB | RAM на Railway ~512MB |
| **Макс. страниц PDF** | 200 | >200 → разбивка по частям |
| **Макс. файлов в архиве** | 100 | Защита от zip-бомб |
| **Макс. разрешение изображения** | 4096×4096 | OCR быстрее, RAM экономия |
| **Макс. листов Excel** | 20 | Разумный лимит |
| **OCR языки** | ru, en, be, de, pl, fr, es, uk | Tesseract lang packs |
| **Одновременных загрузок** | 5 (Free), 20 (Pro), 50 (Enterprise) | Тарифная защита |

#### Pipeline обработки

```
ФАЙЛ → [1. Валидация] → [2. Антивирус] → [3. Извлечение] → [4. OCR] → [5. LLM анализ] → РЕЗУЛЬТАТ

1. ВАЛИДАЦИЯ:
   - Проверка MIME type (magic bytes, не расширение)
   - Размер ≤ 50MB
   - Расширение в whitelist
   - Имя файла: sanitize (убрать ../. shell injection)
   - Zip: проверка на zip-bomb (compression ratio > 100:1 → reject)

2. АНТИВИРУС (опционально, для Pro+ тарифов):
   - VirusTotal API (уже интегрирован, VypCyyMyC6JyDVLV workflow)
   - Quarantine если ≥2 AV engines flagged
   - Hash check: SHA256 против known malware DB

3. ИЗВЛЕЧЕНИЕ ТЕКСТА:
   - PDF: PyMuPDF → text + tables. Если text пустой → OCR fallback
   - Word: python-docx → paragraphs + tables
   - Excel: openpyxl → DataFrame → markdown table
   - Изображения: → пункт 4 (OCR)
   - Архивы: распаковка во temp → рекурсивная обработка каждого файла

4. OCR (для изображений и сканов):
   Приоритет:
   a) Claude Vision API (лучшее качество, дороже) — для Pro+ тарифов
   b) Tesseract (бесплатный, хорошее качество для чётких сканов)
   c) Комбо: Tesseract → если confidence < 0.8 → Claude Vision

5. LLM АНАЛИЗ (по запросу агента):
   - Суммаризация ("О чём этот документ?")
   - Извлечение структурированных данных (накладные → JSON)
   - Классификация типа документа
   - Проверка на дубликаты (SHA256 + document_fingerprints)
   - Перевод
```

#### UI загрузки файлов (drag & drop + кнопка)

```
ДЕСКТОП (браузер, кабинет, виджет):
┌─────────────────────────────────────────────────────┐
│  💬 Чат с Ириной                          [📋][⚡]  │
│─────────────────────────────────────────────────────│
│                                                     │
│  Ирина: Загрузите накладную, я распознаю            │
│         реквизиты и внесу в КУДИР.                  │
│                                                     │
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐         │
│  │                                       │         │
│  │    📄 Перетащите файл сюда            │  ← drag │
│  │       или нажмите чтобы выбрать       │    zone │
│  │                                       │         │
│  │  PDF · Word · Excel · JPG · PNG       │         │
│  │  до 50 MB                             │         │
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘         │
│                                                     │
│  [📎 Прикрепить файл]  [📷 Сфотографировать]        │
│                                                     │
│─────────────────────────────────────────────────────│
│  Вы: [вот накладная за февраль              ] [➤]   │
│       📄 nakladnaya_feb.pdf  ██████████ 100%        │
└─────────────────────────────────────────────────────┘

Способы загрузки:
1. Drag & Drop — перетащить файл(ы) в зону чата
2. Кнопка 📎 — открыть файловый диалог (multi-select)
3. 📷 Камера (мобайл) — сфотографировать документ
4. Буфер обмена — Ctrl+V вставить скриншот/изображение
5. Множественная загрузка — до 10 файлов за раз

МОБИЛЬНОЕ ПРИЛОЖЕНИЕ (AI PILOT Scanner):
- Камера → автофокус → кадрирование → отправка в чат
- Из галереи → выбрать фото → отправить
- Из "Файлы" / iCloud / Google Drive → выбрать
- Share Sheet → "Отправить в AI PILOT" (из любого приложения)

ПРОГРЕСС ЗАГРУЗКИ:
- ██████████ 100% → "Файл загружен"
- ⏳ "Распознаю текст..." (OCR)
- ✅ "Готово: накладная №247 от 15.02.2026, сумма 2,450 BYN"
  → "Внести в КУДИР? [Да] [Изменить] [Отмена]"
```

#### API endpoints

```python
# Загрузка файла
POST /v1/documents/upload
Content-Type: multipart/form-data
- file: (binary)
- agent: "iryna"         # какой агент обрабатывает
- mode: "extract"        # extract | analyze | ocr | full
- language: "ru"         # язык OCR
- config_id: "uuid"      # контекст клиента
→ 202 Accepted { "document_id": "uuid", "status": "processing" }

# Статус обработки
GET /v1/documents/{document_id}/status
→ { "status": "ready", "pages": 12, "text_length": 45000, "ocr_confidence": 0.94 }

# Получить результат
GET /v1/documents/{document_id}
→ {
    "text": "Извлечённый текст...",
    "tables": [...],
    "metadata": { "pages": 12, "author": "...", "created": "..." },
    "ocr_languages": ["ru", "en"],
    "ocr_confidence": 0.94,
    "file_hash": "sha256:...",
    "duplicate_check": { "is_duplicate": false }
  }

# Анализ документа через LLM
POST /v1/documents/{document_id}/analyze
{ "question": "Какая сумма в этом счёте?", "agent": "iryna" }
→ { "answer": "Сумма: 2,450.00 BYN, НДС 20%: 408.33 BYN, итого: 2,858.33 BYN", "confidence": 0.97 }

# Batch upload (несколько файлов)
POST /v1/documents/batch
Content-Type: multipart/form-data
- files[]: (binary × N)
- agent: "iryna"
→ { "batch_id": "uuid", "files": [{"name": "...", "document_id": "..."}, ...] }
```

#### Сценарии по агентам

| Агент | Что загружают | Что делает |
|-------|--------------|-----------|
| **Ирина** | Накладные, счета-фактуры, выписки банка (PDF/Excel) | OCR → распознавание реквизитов → проводка в КУДИР → проверка дубликатов |
| **Леон** | Договоры, исковые, учредительные (Word/PDF) | Анализ юр. рисков, извлечение сроков/сумм/сторон, проверка на соответствие шаблону |
| **Марина** | Прайс-листы конкурентов, КП клиентов (PDF/Excel) | Извлечение цен, сравнительный анализ, генерация контр-КП |
| **Анна** | Резюме (PDF/Word), дипломы (скан JPG/PNG) | Парсинг резюме → структурированная карточка, скоринг кандидата |
| **Даниил** | Отчёты рекламных площадок (CSV/Excel) | Импорт метрик → анализ ROI → рекомендации по оптимизации |
| **Кира** | Фото/видео для контента (JPG/PNG/MP4), брендбуки (PDF) | Извлечение фирменных цветов/шрифтов, подготовка ассетов |
| **Влад** | Маркетинговые отчёты, исследования рынка (PDF/Excel) | Извлечение данных → SWOT, конкурентный анализ |
| **Лиза** | Документы клиента для передачи специалисту | Классификация → маршрутизация к нужному агенту |

#### Хранение загруженных файлов

```
НЕ в нашей БД. Принцип client_systems_only:

1. Supabase Storage (temporary, 24h TTL):
   - bucket: "document_uploads"
   - path: /{config_id}/{document_id}/{filename}
   - Auto-delete через 24h (cron)
   - Используется ТОЛЬКО для обработки

2. Google Drive клиента (permanent):
   - После обработки файл загружается в Drive клиента
   - В нашей БД остаётся только метаданные:
     document_id, file_hash, pages, text_length, ocr_confidence
   - Текст хранится ЗАШИФРОВАННЫЙ (AES-256-GCM, см. 8.9)

3. Для API разработчиков:
   - файл не хранится вообще — обработка on-the-fly
   - результат возвращается в response
   - TTL кеш извлечённого текста: 1 час (по hash файла)
```

#### Зависимости (pip)

```
# Новые зависимости для document processing:
PyMuPDF>=1.24.0          # PDF parsing (fitz), MIT license, 0 dependencies
python-docx>=1.1.0       # Word .docx
openpyxl>=3.1.0          # Excel .xlsx
python-pptx>=1.0.0       # PowerPoint .pptx
pytesseract>=0.3.10      # Tesseract OCR wrapper
Pillow>=10.0.0           # Image processing (уже есть)
python-magic>=0.4.27     # MIME type detection by magic bytes
extract-msg>=0.48.0      # Outlook .msg files
odfpy>=1.4.1             # OpenDocument .ods
xlrd>=2.0.0              # Legacy .xls
pandas>=2.0.0            # DataFrame для табличных данных
# System: tesseract-ocr (apt install / brew install)
```

#### Стоимость

| Что | Затраты |
|-----|---------|
| PyMuPDF + python-docx + openpyxl | €0 (open source) |
| Tesseract OCR | €0 (open source, Apache 2.0) |
| Claude Vision (для Pro+ OCR) | ~$0.003 / страница |
| Supabase Storage (temp, 24h) | €0 (в рамках плана) |
| VirusTotal API | €0 (бесплатный план, 500 req/day) |
| **Итого** | €0 + $0.003/стр для Vision OCR |

#### Сроки реализации

| Этап | Что | Срок |
|------|-----|------|
| 1 | PDF + Word + Excel + images (базовые) | 1 неделя |
| 2 | OCR (Tesseract + Claude Vision fallback) | 3 дня |
| 3 | Архивы + email + batch upload | 3 дня |
| 4 | LLM analysis + agent integration | 1 неделя |
| **Итого** | | ~3 недели |

---

### 8.13 СВЕЖЕСТЬ ЗНАНИЙ — Knowledge Freshness System (анти-устаревание)

> **Проблема:** Большие LLM (GPT, Gemini, даже Claude) обучены на данных 1-2 летней давности.
> Антигравити (Gemini) регулярно даёт устаревшие model ID, API форматы, ценники.
> AI PILOT LLM должна работать с АКТУАЛЬНЫМИ данными — это конкурентное преимущество.
>
> **Но!** Не забывать историю. Модель должна:
> - Отвечать актуальными данными по умолчанию
> - Помнить исторические данные для сравнения ("было → стало")
> - При запросе уметь сказать: "В 2024 ставка была 5%, сейчас (2026) — 6%"

#### Почему LLM дают устаревшие ответы

```
Проблема фундаментальная:
- GPT-4o: обучена на данных до апреля 2024 (2 года назад!)
- Gemini 2.5: обучена на данных до ~марта 2025 (1 год назад)
- Claude Opus 4.6: данные до мая 2025 (10 мес назад)
- Наша Llama 4 QLoRA: данные = наш training set (свежие, но замороженные)

Примеры косяков Антигравити из-за устаревших знаний:
- Model ID "claude-3-5-sonnet-20241022" → на самом деле claude-sonnet-4-6 (с мая 2025)
- Anthropic SDK формат messages → изменился в v0.43+ (ноябрь 2025)
- Цены Mistral: использовал прайс 2024 года вместо 2026
- Railway API: рекомендовал deprecated endpoints

→ Наша модель НЕ ДОЛЖНА полагаться на замороженные веса.
   Ответ = RAG (свежие данные) + замороженная база (здравый смысл).
```

#### Архитектура: RAG-first, Weights-second

```
                    ┌─────────────────────────┐
                    │     ЗАПРОС КЛИЕНТА       │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   1. CLASSIFIER          │
                    │   "Нужна ли свежая       │
                    │    информация?"           │
                    └──────────┬──────────────┘
                          ┌────┴────┐
                          │         │
                    Да    ▼         ▼   Нет
              ┌──────────────┐  ┌──────────────┐
              │ 2. RAG SEARCH │  │ LLM напрямую │
              │ (свежие данные)│  │ (веса модели) │
              └──────┬───────┘  └──────┬───────┘
                     │                 │
              ┌──────▼───────┐         │
              │ 3. LLM + RAG │         │
              │ context       │←────────┘
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │ 4. FRESHNESS  │
              │ VALIDATOR     │
              │ (проверка     │
              │  даты данных) │
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │   ОТВЕТ       │
              │ + дата данных  │
              │ + источник     │
              └───────────────┘
```

#### 5 уровней обеспечения свежести

**Уровень 1: Knowledge Base (agent_knowledge_base) — обновляется ЕЖЕДНЕВНО**

```
Уже работает (knowledge_crawler.py):
- 217 URL-источников для 9 агентов
- Каждый день 02:00 UTC → crawler обходит источники
- Claude Haiku извлекает 3-5 фактов → upserts в agent_knowledge_base
- confidence_score = 0.85 (crawled) vs 0.95 (verified)

Для AI PILOT LLM добавить:
- Метка freshness_date на КАЖДУЮ запись KB
- При ответе → приоритет записей с freshness_date < 7 дней
- Если запись > 90 дней → автоматически снижать confidence до 0.3
- Если > 180 дней и нет re-crawl → пометить stale, не использовать
```

**Уровень 2: Real-time Data Sources — запрос в момент ответа**

```
Когда crawler не хватает — агент СЕЙЧАС проверяет:

| Данные | Источник | Когда проверять |
|--------|----------|----------------|
| Курсы валют | НБРБ API (nbrb.by/api) | Каждый ответ Ирины про деньги |
| Статус сервисов | Railway/Supabase/n8n health | Каждый ответ Стража |
| Ставки налогов | minfin.gov.by | Раз в неделю + при запросе |
| Тарифы AI PILOT | Supabase agent_tier_config | Каждый ответ про цены |
| Цены Anthropic/Mistral | Pricing pages | Раз в день |
| Законы BY | pravo.by, ilex.by | Раз в неделю (Леон) |
| Курс крипто (TON) | ton-price-monitor workflow | Real-time |

Реализация:
- Каждый агент имеет список "critical data sources"
- Перед ответом → quick check: "последний crawl > 24h назад?" → re-fetch
- Результат включается в RAG context с тегом source=realtime, date=now
```

**Уровень 3: Versioned System Prompt — обновляется при каждом deploy**

```python
# При каждом deploy FastAPI backend:
# Автоматически генерируется system_prompt_context.json

{
    "generated_at": "2026-03-04T15:30:00Z",
    "ai_pilot_version": "1.0.0-webmaster-full",
    "knowledge_cutoff": "2026-03-04",     # ← ЭТО КЛЮЧЕВОЕ
    "model_versions": {
        "claude": "claude-sonnet-4-6",
        "mistral": "mistral-large-latest",
        "ai_pilot_llm": "0.1.0"
    },
    "pricing": {
        "lisa_free": 0, "lisa_lite": 39, "iryna_pro": 79,
        "mistral_input_1k": 0.00184, "claude_sonnet_input_1k": 0.003
    },
    "legal": {
        "by_usn_rate": 0.06,
        "by_nds_rate": 0.20,
        "by_min_wage_byn": 626.0,
        "last_verified": "2026-03-01"
    }
}

# Включается в КАЖДЫЙ system prompt агента:
system_prompt = f"""
{constitution}

АКТУАЛЬНЫЕ ДАННЫЕ (обновлены {context['generated_at']}):
- Курсы валют: 1 USD = {rates['USD']} BYN, 1 EUR = {rates['EUR']} BYN
- Тарифы: {json.dumps(context['pricing'])}
- Юридические данные: {json.dumps(context['legal'])}

ВАЖНО: Если клиент спрашивает о данных, которые могут быть устаревшими,
ВСЕГДА указывай дату последней проверки. Пример: "По данным на {date}, ставка УСН = 6%."
"""
```

**Уровень 4: Fine-tune Data Freshness — при каждом обучении модели**

```
При fine-tune AI PILOT LLM:

1. TRAINING DATA = только последние 6 месяцев диалогов
   - Старые диалоги (>6 мес) → удаляются из training set
   - Если в старом диалоге цена/закон/API → проверить актуальность
   - Если изменилось → перегенерировать пример с новыми данными

2. АНТИТРЕНИРОВОЧНЫЙ НАБОР (negative examples):
   {"prompt": "Какая модель Claude самая новая?",
    "rejected": "Claude 3.5 Sonnet (claude-3-5-sonnet-20241022)",    ← УСТАРЕВШЕЕ
    "chosen": "Claude Opus 4.6 (claude-opus-4-6, актуально на март 2026)",  ← ВЕРНО
    "metadata": {"type": "anti_stale", "domain": "models"}}

   → Модель УЧИТСЯ не повторять устаревшие факты

3. ДАТА В КАЖДОМ ПРИМЕРЕ:
   Каждый пример в training set содержит метку текущей даты:
   {"system": "Сегодня 2026-03-04. Ты — Ирина...", ...}
   → Модель понимает временной контекст

4. ВЕРСИОНИРОВАНИЕ:
   - v0.1 (март 2026) → данные до марта 2026
   - v0.2 (июнь 2026) → +данные апрель-июнь, удалены устаревшие примеры
   - Каждая версия знает свой knowledge cutoff
```

**Уровень 5: Freshness Validator — проверка ответа ПЕРЕД отправкой**

```python
class FreshnessValidator:
    """Проверяет ответ на устаревшие данные ПЕРЕД отправкой клиенту."""

    # Паттерны, требующие проверки свежести
    CHECKS = [
        # Цены и тарифы
        {"pattern": r"(\d+)\s*(EUR|BYN|USD|€|\$)", "check": "verify_price"},
        # Модели AI
        {"pattern": r"claude-\d|gpt-\d|mistral-\w+", "check": "verify_model_id"},
        # Законы и ставки
        {"pattern": r"(\d+)%\s*(НДС|УСН|налог)", "check": "verify_tax_rate"},
        # Даты и сроки
        {"pattern": r"до (\d{1,2}\.\d{1,2}\.\d{4})", "check": "verify_deadline"},
        # Курсы валют
        {"pattern": r"курс\s+(\w+)\s*[=:]\s*(\d+[\.,]\d+)", "check": "verify_rate"},
    ]

    async def validate(self, response: str, agent_type: str) -> str:
        """Если найдены потенциально устаревшие данные → пометить."""
        warnings = []
        for check in self.CHECKS:
            matches = re.findall(check["pattern"], response)
            if matches:
                is_fresh = await self._check_freshness(check["check"], matches)
                if not is_fresh:
                    warnings.append(f"⚠️ Данные могут быть устаревшими: {matches}")

        if warnings:
            response += "\n\n_Примечание: " + "; ".join(warnings) + "_"
        return response
```

#### Сравнение с конкурентами

| | ChatGPT | Gemini | Claude | **AI PILOT LLM** |
|---|---------|--------|--------|-----------------|
| Knowledge cutoff | Apr 2024 | ~Mar 2025 | May 2025 | **Real-time** |
| Обновление знаний | Web search (опц.) | Grounding (опц.) | - | **5 уровней (встроено)** |
| Цены/ставки | Устаревшие | Устаревшие | Устаревшие | **Актуальные (НБРБ API)** |
| BY законодательство | Приблизительно | Часто неверно | Неплохо | **pravo.by + ilex.by daily** |
| Model IDs | Устаревшие | **Устаревшие!** | Свои верные | **Verified при каждом deploy** |
| Дата в ответе | Редко | Редко | Иногда | **Всегда (обязательно)** |

#### Историческая память (НЕ удалять старые данные, а версионировать)

```
ПРИНЦИП: Актуальное по умолчанию, история по запросу.

Пример:
  Клиент: "Какая ставка УСН?"
  Ирина: "Ставка УСН в РБ = 6% (п.1 ст.329 НК РБ, актуально на 04.03.2026)"

  Клиент: "А раньше какая была?"
  Ирина: "История ставки УСН:
    - 2024: 5% (до 01.01.2025)
    - 2025-2026: 6% (с 01.01.2025, Закон №141-З от 30.12.2024)
    Рост на 1 п.п. — учтите при планировании."

Реализация в Knowledge Base:

| id | agent | content | valid_from | valid_to | is_current | freshness_date |
|----|-------|---------|-----------|----------|-----------|---------------|
| 1  | iryna | УСН = 5% (п.1 ст.329 НК РБ) | 2022-01-01 | 2024-12-31 | false | 2024-12-30 |
| 2  | iryna | УСН = 6% (Закон №141-З) | 2025-01-01 | null | true | 2026-03-04 |

Колонки:
- valid_from / valid_to — период действия записи
- is_current — текущая актуальная запись (индекс для быстрого поиска)
- freshness_date — дата последней проверки актуальности

При обновлении данных:
  1. Старая запись: valid_to = вчера, is_current = false
  2. Новая запись: valid_from = сегодня, valid_to = null, is_current = true
  3. Обе записи ОСТАЮТСЯ в БД (никогда не удаляем)

Запрос "текущая ставка" → WHERE is_current = true
Запрос "история ставок" → WHERE agent = 'iryna' AND tags @> '{tax,usn}' ORDER BY valid_from

Бонус для обучения модели:
  Training examples включают и текущие, и исторические данные.
  Модель учится: "Я знаю что сейчас X, а раньше было Y, потому что Z."
  Это ЛУЧШЕ чем конкуренты — ChatGPT/Gemini не помнят что менялось.
```

#### Правило для агентов (добавить в конституции)

```
§ СВЕЖЕСТЬ ДАННЫХ (обязательно для всех агентов):

1. При упоминании цен, курсов, ставок, сроков — ВСЕГДА указать дату:
   "По данным на 04.03.2026, курс USD/BYN = 3.25 (НБРБ)"

2. Если данные из KB старше 30 дней — предупредить:
   "⚠️ Эти данные от 15.01.2026. Рекомендую уточнить актуальность."

3. Если не уверен в актуальности — НЕ утверждать:
   ❌ "Ставка НДС = 20%"
   ✅ "На момент моей последней проверки (01.03.2026), ставка НДС в РБ = 20%"

4. При любом изменении (обнаружил что данные устарели):
   → Обновить KB запись (confidence -= 0.3)
   → Пометить для re-crawl
   → Если критичное (закон/цена/срок) → алерт Комендант-Пилот

5. НИКОГДА не давать дату из замороженных весов модели без проверки.
   Веса модели = общие знания (что такое НДС).
   Конкретные цифры = ТОЛЬКО из RAG / real-time API.
```

#### Стоимость

| Что | Затраты |
|-----|---------|
| Knowledge crawler (уже работает) | €0 |
| НБРБ API | €0 (бесплатный) |
| Real-time data checks | ~$0.001/запрос (Haiku classify) |
| FreshnessValidator | €0 (regex, встроенный) |
| Versioned system prompt | €0 (генерируется при deploy) |
| Anti-stale training examples | €0 (часть dataset pipeline) |
| **Итого** | ~$0.001/запрос (пренебрежимо) |

---

### 8.14 ИНТЕГРАЦИЯ С АГЕНТАМИ AI PILOT — Agent Mesh Network

> **Принцип:** AI PILOT LLM — не изолированная модель. Она ЗНАЕТ всех 9 агентов,
> умеет их вызывать, получать от них данные и передавать задачи.
> Если клиент API одновременно пользуется нашими агентами — модель устанавливает
> прямую связь с ними по всем каналам.

#### Почему это важно

```
Сценарий БЕЗ интеграции (как у конкурентов):
  Разработчик: POST /v1/chat "Сколько я должен по налогам?"
  LLM: "Я не имею доступа к вашей бухгалтерии. Обратитесь к бухгалтеру."
  → Бесполезно.

Сценарий С интеграцией (AI PILOT LLM):
  Разработчик: POST /v1/chat "Сколько я должен по налогам?"
  LLM: [обнаруживает что у клиента активна Ирина]
       → вызывает Ирина API: GET /agents/iryna/tax-summary?firm_id=...
       → получает: {usn: 747 BYN, deadline: "2026-04-22", period: "Q1 2026"}
  LLM: "По данным вашей Ирины, задолженность по УСН за Q1 2026 = 747 BYN.
        Срок уплаты: 22 апреля 2026. Хотите сформировать платёжку?"
  → Ценность. Ни один конкурент так не умеет.
```

#### Реестр агентов (hardcoded в модель + обновляется при deploy)

```python
# aipilot_llm/agent_registry.py

AGENT_REGISTRY = {
    # ── Продуктовые агенты (продаём клиентам) ──────────────────
    "lisa": {
        "name_ru": "Лиза",
        "role": "AI Секретарь",
        "capabilities": [
            "scheduling", "email_management", "call_screening",
            "document_routing", "client_greeting", "faq_answering",
            "agent_orchestration",   # ← Лиза = главный оркестратор
        ],
        "api_prefix": "/agents/lisa",
        "channels": ["telegram", "widget", "cabinet", "email", "voice"],
        "can_delegate_to": ["iryna", "leon", "marina", "anna", "daniil", "kira", "vlad"],
        "tiers": {"free": 0, "lite": 39, "pro": 99, "enterprise": 249},
        "currency": "EUR",
    },
    "iryna": {
        "name_ru": "Ирина",
        "role": "AI Бухгалтер",
        "capabilities": [
            "bookkeeping", "tax_calculation", "invoice_recognition",
            "bank_statement_import", "kudir_management", "document_scan",
            "expense_tracking", "tax_calendar", "audit",
        ],
        "api_prefix": "/agents/iryna",
        "channels": ["telegram", "cabinet", "email"],
        "data_access": ["firm.ledger", "firm.cash_book", "firm.tax_periods",
                        "firm.service_expenses", "irina_scan_sessions"],
        "can_delegate_to": ["leon"],  # юр. вопросы → Леон
        "tiers": {"free": 0, "lite": 39, "pro": 79, "enterprise": 199},
        "currency": "EUR",
    },
    "marina": {
        "name_ru": "Марина",
        "role": "AI Менеджер по продажам",
        "capabilities": [
            "lead_management", "crm_integration", "amocrm_sync",
            "sales_funnel", "commercial_proposals", "follow_up",
            "competitor_pricing", "deal_closing",
        ],
        "api_prefix": "/agents/marina",
        "channels": ["telegram", "cabinet", "widget", "amocrm"],
        "data_access": ["marina_leads", "marina_configs"],
        "can_delegate_to": ["leon", "iryna"],
        "tiers": {"free": 0, "lite": 49, "pro": 99, "enterprise": 249},
        "currency": "EUR",
    },
    "leon": {
        "name_ru": "Леон",
        "role": "AI Юрист",
        "capabilities": [
            "contract_analysis", "legal_risk_assessment", "document_generation",
            "law_database", "nda_creation", "dispute_resolution",
            "compliance_check", "regulation_monitoring",
        ],
        "api_prefix": "/agents/leon",
        "channels": ["telegram", "cabinet"],
        "data_access": ["leon_documents", "document_registry"],
        "can_delegate_to": ["iryna"],  # финансовые аспекты → Ирина
        "tiers": {"free": 0, "lite": 49, "pro": 129, "enterprise": 299},
        "currency": "USD",
    },
    "daniil": {
        "name_ru": "Даниил",
        "role": "AI Специалист по рекламе",
        "capabilities": [
            "google_ads", "facebook_ads", "campaign_management",
            "budget_optimization", "ab_testing", "roi_analysis",
            "audience_targeting", "creative_generation",
        ],
        "api_prefix": "/agents/daniil",
        "channels": ["telegram", "cabinet"],
        "data_access": ["daniil_campaigns", "daniil_configs"],
        "can_delegate_to": ["kira", "vlad"],
        "tiers": {"free": 0, "lite": 49, "pro": 99, "enterprise": 249},
        "currency": "USD",
    },
    "kira": {
        "name_ru": "Кира",
        "role": "AI Мастер соцсетей",
        "capabilities": [
            "content_planning", "post_generation", "video_creation",
            "reel_production", "social_analytics", "hashtag_strategy",
            "brand_voice", "community_management",
        ],
        "api_prefix": "/agents/kira",
        "channels": ["telegram", "cabinet"],
        "data_access": ["kira_content_plan", "kira_videos"],
        "can_delegate_to": ["vlad", "daniil"],
        "tiers": {"free": 0, "lite": 39, "pro": 79, "enterprise": 199},
        "currency": "USD",
    },
    "vlad": {
        "name_ru": "Влад",
        "role": "AI Маркетолог",
        "capabilities": [
            "market_research", "swot_analysis", "cjm_mapping",
            "competitor_analysis", "positioning", "brand_strategy",
            "pricing_strategy", "go_to_market",
        ],
        "api_prefix": "/agents/vlad",
        "channels": ["telegram", "cabinet"],
        "data_access": ["vlad_strategies", "vlad_configs"],
        "can_delegate_to": ["marina", "daniil", "kira"],
        "tiers": {"free": 0, "lite": 49, "pro": 99, "enterprise": 249},
        "currency": "USD",
    },
    "anna": {
        "name_ru": "Анна",
        "role": "AI HR-менеджер",
        "capabilities": [
            "resume_parsing", "candidate_scoring", "interview_scheduling",
            "vacancy_creation", "ats_management", "onboarding",
            "employee_surveys", "hr_analytics",
        ],
        "api_prefix": "/agents/anna",
        "channels": ["telegram", "cabinet"],
        "data_access": ["anna_candidates", "anna_configs"],
        "can_delegate_to": ["leon"],  # трудовое право → Леон
        "tiers": {"free": 0, "lite": 29, "pro": 69, "enterprise": 179},
        "currency": "EUR",
    },

    # ── Внутренние агенты -Пилот (работают для AI PILOT) ──────
    "webmaster": {
        "name_ru": "Вебмастер",
        "role": "AI Создатель сайтов",
        "capabilities": [
            "site_generation", "design_system", "seo_optimization",
            "responsive_layout", "content_writing", "deployment",
            "visual_qa", "performance_audit",
        ],
        "api_prefix": "/api/v1/webmaster",
        "channels": ["cabinet", "api"],
        "internal": False,  # Это тоже продукт
    },
}
```

#### Каналы связи LLM ↔ Агенты

```
                    ┌──────────────────────────────┐
                    │        AI PILOT LLM API      │
                    │   /v1/chat  /v1/code  /v1/*  │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │     AGENT MESH ROUTER         │
                    │  (определяет: какие агенты    │
                    │   активны у этого клиента)    │
                    └──────────┬───────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
    │ КАНАЛ 1:       │ │ КАНАЛ 2:     │ │ КАНАЛ 3:     │
    │ Internal API   │ │ Supabase     │ │ Webhooks     │
    │ (FastAPI→Fast) │ │ (данные)     │ │ (async)      │
    └────────────────┘ └──────────────┘ └──────────────┘

КАНАЛ 1 — Internal API (синхронный, <100ms):
  LLM вызывает агента через внутренний FastAPI endpoint.
  Пример: GET /agents/iryna/tax-summary?firm_id=123
  Используется когда LLM нужен ОТВЕТ прямо сейчас.

КАНАЛ 2 — Supabase Direct (данные, <50ms):
  LLM читает данные агента напрямую из Supabase.
  Пример: SELECT * FROM firm.ledger WHERE wp_user_id = 123
  Используется для получения структурированных данных.

КАНАЛ 3 — Webhooks / Agent Delegation (асинхронный):
  LLM ставит ЗАДАЧУ агенту через webhook.
  Пример: POST /webhook/agent-delegation
    { from: "llm_api", to: "marina", task: "process_new_leads", client_id: 123 }
  Агент обрабатывает в фоне, результат → callback или cabinet_messages.

КАНАЛ 4 — Telegram (уведомления клиенту):
  LLM просит агента отправить сообщение клиенту в Telegram.
  Пример: через agent_bot_configs → telegram_token → sendMessage
  Используется для уведомлений и follow-up.

КАНАЛ 5 — Email (через Комиссар):
  LLM инициирует отправку email от имени агента.
  Пример: POST /internal/send-agent-email
    { from: "iryna@ai-pilot.by", to: client_email, subject: "Отчёт Q1" }
```

#### Как LLM определяет активных агентов клиента

```python
# При каждом API-запросе от клиента:

async def get_client_agents(api_key: str) -> list[dict]:
    """Определить какие агенты AI PILOT активны у клиента API."""

    # 1. Найти wp_user_id по API key
    org = await supabase.table("api_organizations") \
        .select("wp_user_id").eq("api_key_hash", hash(api_key)).single()

    if not org:
        return []  # внешний клиент, без агентов

    wp_user_id = org["wp_user_id"]

    # 2. Получить активные подписки агентов
    subs = await supabase.table("agent_subscriptions") \
        .select("agent_type, tier, status") \
        .eq("wp_user_id", wp_user_id) \
        .eq("status", "active") \
        .execute()

    # 3. Получить конфигурации агентов (Telegram, коннекторы)
    configs = await supabase.table("agent_bot_configs") \
        .select("agent_type, config_id, telegram_token, status, settings") \
        .eq("wp_user_id", wp_user_id) \
        .eq("status", "active") \
        .execute()

    # 4. Получить фирмы клиента
    firms = await supabase.table("client_firms") \
        .select("id, name, company_type, tax_system, currency") \
        .eq("wp_user_id", wp_user_id) \
        .eq("is_active", True) \
        .execute()

    # 5. Собрать карту доступных агентов + их возможностей
    active_agents = []
    for sub in subs.data:
        agent_type = sub["agent_type"]
        registry = AGENT_REGISTRY.get(agent_type, {})
        config = next((c for c in configs.data if c["agent_type"] == agent_type), None)

        active_agents.append({
            "agent_type": agent_type,
            "name_ru": registry.get("name_ru", agent_type),
            "role": registry.get("role", ""),
            "tier": sub["tier"],
            "capabilities": registry.get("capabilities", []),
            "config_id": config["config_id"] if config else None,
            "channels": registry.get("channels", []),
            "firms": firms.data,
        })

    return active_agents
```

#### System prompt injection (контекст агентов)

```python
# При каждом запросе к LLM API — добавляем в system prompt:

def build_agent_context(active_agents: list[dict]) -> str:
    """Сгенерировать контекст агентов для system prompt."""
    if not active_agents:
        return ""

    lines = [
        "\n## АКТИВНЫЕ АГЕНТЫ AI PILOT У ЭТОГО КЛИЕНТА:",
        "Ты можешь обращаться к ним за данными и делегировать задачи.\n",
    ]

    for a in active_agents:
        lines.append(f"### {a['name_ru']} ({a['agent_type']}) — {a['role']}")
        lines.append(f"  Тариф: {a['tier']}")
        lines.append(f"  Возможности: {', '.join(a['capabilities'])}")
        lines.append(f"  Каналы: {', '.join(a['channels'])}")
        if a.get('firms'):
            firm_names = [f['name'] for f in a['firms']]
            lines.append(f"  Фирмы клиента: {', '.join(firm_names)}")
        lines.append("")

    lines.append("ПРАВИЛА ВЗАИМОДЕЙСТВИЯ С АГЕНТАМИ:")
    lines.append("1. Если вопрос входит в capabilities агента → вызови его (tool call)")
    lines.append("2. Если нужны данные → используй Supabase read (канал 2)")
    lines.append("3. Если задача длительная → делегируй через webhook (канал 3)")
    lines.append("4. НИКОГДА не говори 'обратитесь к Ирине' — вызови её сам и верни результат")
    lines.append("5. При ошибке агента → сообщи клиенту, предложи альтернативу")
    lines.append("")

    return "\n".join(lines)
```

#### Tool definitions для вызова агентов

```python
# LLM получает tools для каждого активного агента:

AGENT_TOOLS = [
    {
        "name": "call_agent",
        "description": "Вызвать агента AI PILOT для получения данных или выполнения задачи",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "enum": ["lisa", "iryna", "marina", "leon", "daniil",
                             "kira", "vlad", "anna", "webmaster"],
                    "description": "Тип агента"
                },
                "action": {
                    "type": "string",
                    "description": "Действие: query (вопрос), task (задача), data (данные)"
                },
                "message": {
                    "type": "string",
                    "description": "Запрос к агенту на русском языке"
                },
                "firm_id": {
                    "type": "string",
                    "description": "ID фирмы клиента (если применимо)"
                },
            },
            "required": ["agent_type", "action", "message"]
        }
    },
    {
        "name": "read_agent_data",
        "description": "Прочитать данные агента из базы (быстрый доступ без вызова агента)",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_type": {"type": "string"},
                "data_type": {
                    "type": "string",
                    "enum": ["tax_summary", "leads", "documents", "campaigns",
                             "content_plan", "strategies", "candidates",
                             "ledger", "cash_book", "subscriptions"],
                    "description": "Тип данных"
                },
                "filters": {
                    "type": "object",
                    "description": "Фильтры: period, firm_id, status, limit"
                },
            },
            "required": ["agent_type", "data_type"]
        }
    },
    {
        "name": "delegate_task",
        "description": "Поставить задачу агенту (асинхронно, результат позже)",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_type": {"type": "string"},
                "task_description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "notify_channel": {
                    "type": "string",
                    "enum": ["telegram", "email", "cabinet", "callback"],
                    "description": "Куда отправить результат"
                },
            },
            "required": ["agent_type", "task_description"]
        }
    },
]
```

#### Сценарии кросс-агентного взаимодействия

```
СЦЕНАРИЙ 1: Разработчик спрашивает про финансы
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  API запрос: "Сколько мы потратили на рекламу в феврале?"

  LLM думает:
    → У клиента активны: Ирина (бухгалтерия) + Даниил (реклама)
    → Нужны данные из двух источников

  LLM вызывает параллельно:
    1. call_agent(iryna, "query", "расходы на рекламу за февраль 2026")
    2. read_agent_data(daniil, "campaigns", {period: "2026-02", status: "completed"})

  Результат:
    "По данным Ирины, расходы на рекламу в феврале: $340 (Google Ads $220, Facebook $120).
     По данным Даниила, проведено 3 кампании, общий ROI = 340%.
     Самая эффективная: 'Весенняя распродажа' (Google Ads, ROI 520%)."


СЦЕНАРИЙ 2: Клиент API хочет автоматизировать процесс
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  API запрос: "Когда приходит новый лид, автоматически проверь его юридически
               и создай коммерческое предложение"

  LLM (Auto mode):
    → Активны: Марина + Леон
    → Создаёт pipeline:

    1. Марина: новый лид (webhook marina → trigger)
       ↓
    2. Леон: проверка компании (ИНН/УНП → реестр → риски)
       ↓ результат: {risk: "low", company_verified: true}
       ↓
    3. Марина: генерация КП с учётом данных Леона
       ↓
    4. Лиза: отправка КП клиенту (email + Telegram)

  Ответ LLM:
    "Настроил автоматический pipeline:
     1. Новый лид → Марина принимает
     2. Леон проверяет юр. чистоту (2-3 сек)
     3. Марина создаёт КП
     4. Лиза отправляет клиенту
     Всё работает автоматически. Тестовый лид отправить?"


СЦЕНАРИЙ 3: 1С-интеграция с полным циклом
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1С отправляет: POST /v1/1c/recognize
    { "document_image": "base64...", "document_type": "invoice" }

  LLM pipeline:
    1. OCR → извлечение реквизитов (8.12 Document Processing)
    2. Ирина → проверка дубликатов (document_fingerprints)
    3. Ирина → проводка в КУДИР (firm.ledger)
    4. Леон → проверка контрагента (если новый)
    5. Возврат в 1С: { "recognized": {...}, "posted": true, "ledger_id": "..." }

  Весь цикл: 3-5 секунд, полностью автоматический.
  Ни один конкурент не предлагает OCR → бухгалтерия → юрпроверка в одном API.


СЦЕНАРИЙ 4: Мобильное приложение — сфотографировал чек
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  App → POST /v1/documents/upload { file: photo.jpg, agent: "iryna" }

  Pipeline:
    1. OCR чека → { shop: "Евроопт", amount: 45.30, date: "04.03.2026", items: [...] }
    2. Ирина → классификация расхода (продукты → "хозяйственные расходы")
    3. Ирина → запись в firm.cash_book
    4. Push уведомление: "Чек Евроопт 45.30 BYN записан в кассовую книгу ✅"
```

#### Безопасность Agent Mesh

| Угроза | Защита |
|--------|--------|
| **LLM вызывает чужого агента** | Проверка: agent_subscriptions.wp_user_id = api_key.wp_user_id |
| **Доступ к данным чужой фирмы** | RLS Supabase: firm_id проверяется на уровне БД |
| **Injection через agent response** | Ответ агента = data, не instruction. LLM НЕ выполняет код из ответа агента |
| **Cascade failure** | Таймаут 10с на вызов агента. Если агент не ответил → LLM сообщает клиенту |
| **Лимиты тарифа** | Каждый вызов агента = use_agent_resource(). Лимит исчерпан → upgrade flow |
| **Circular delegation** | Max depth = 3 (LLM → Agent A → Agent B → стоп). Логирование цепочки |

#### Метрики Agent Mesh

```sql
-- Новая таблица: отслеживание кросс-агентных вызовов
CREATE TABLE agent_mesh_calls (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    api_key_id UUID REFERENCES api_keys(id),
    source VARCHAR(20) NOT NULL,        -- 'llm_api' или agent_type
    target VARCHAR(20) NOT NULL,        -- agent_type
    channel VARCHAR(20) NOT NULL,       -- 'internal_api', 'supabase', 'webhook', 'telegram'
    action VARCHAR(50),                 -- 'query', 'task', 'data_read', 'delegate'
    latency_ms INTEGER,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для аналитики
CREATE INDEX idx_mesh_calls_source_target ON agent_mesh_calls(source, target, created_at);
```

#### Конкурентное преимущество

```
У КОНКУРЕНТОВ (OpenAI API, Mistral API, Google Vertex AI):
  - Чистый LLM API — вопрос → ответ
  - Никаких встроенных агентов
  - Никакого доступа к бизнес-данным клиента
  - Разработчик сам пишет всю интеграцию

У AI PILOT LLM API:
  - LLM + 9 готовых агентов в одном API
  - Агенты ЗНАЮТ бизнес клиента (если подключены)
  - Кросс-агентные сценарии из коробки
  - 1С + CRM + бухгалтерия + юрист + маркетинг = один API call
  - Разработчику не нужно писать бизнес-логику — она уже есть

АНАЛОГИЯ:
  OpenAI API = голый движок автомобиля
  AI PILOT LLM API = полностью собранный автомобиль с навигацией, кондиционером и автопилотом
```

#### Стоимость

| Что | Затраты |
|-----|---------|
| agent_registry.py | €0 (код) |
| Agent Mesh Router | 1 неделя разработки |
| Tool definitions | €0 (часть prompt) |
| agent_mesh_calls таблица | €0 (Supabase) |
| Internal API endpoints | Частично уже есть (cabinet channel) |
| **Итого** | €0 прямых, 1-2 недели разработки |

---

### 8.15 ПАМЯТЬ АГЕНТОВ + БИЛЛИНГ-ГЕЙТ — Полная осведомлённость о клиенте

> **Принцип:** Если клиент подключён к AI PILOT — модель ЗНАЕТ ВСЁ о его бизнесе:
> историю диалогов, подписки, балансы, фирмы, документы, лиды, задолженности.
> Если на счету пусто — модель ограничивает ответы до момента оплаты.
> Никаких бесплатных консультаций за счёт чужих агентов.

#### Что именно модель знает о клиенте

```
При каждом API-запросе LLM загружает ПОЛНЫЙ КОНТЕКСТ клиента:

┌──────────────────────────────────────────────────────────────┐
│                   CLIENT CONTEXT LOADER                       │
│                                                              │
│  1. IDENTITY                                                 │
│     wp_user_id, email, name, registration_date               │
│     language_preference, timezone                            │
│                                                              │
│  2. FIRMS (client_firms)                                     │
│     [{name, company_type, tax_system, unp, currency,         │
│       is_default, country_code}]                             │
│                                                              │
│  3. SUBSCRIPTIONS (agent_subscriptions)                      │
│     [{agent_type, tier, status, tokens_used, tokens_limit,   │
│       expires_at, auto_renew}]                               │
│                                                              │
│  4. BALANCE (billing_events + agent_tier_config)             │
│     [{agent_type, tokens_remaining, next_reset_date,         │
│       overage_allowed, payment_status}]                      │
│                                                              │
│  5. AGENT MEMORY (agent_client_memory)                       │
│     [{agent_type, memory_key, memory_value,                  │
│       last_updated, importance}]                             │
│     Примеры: "предпочитает краткие ответы",                 │
│              "УНП сменился в январе 2026",                   │
│              "ведёт 3 фирмы, основная = ИП Иванов"          │
│                                                              │
│  6. RECENT INTERACTIONS (agent_learning_log, last 20)        │
│     [{agent_type, interaction_type, summary,                 │
│       response_quality, created_at}]                         │
│                                                              │
│  7. DOCUMENTS (document_registry, last 50)                   │
│     [{doc_type, doc_number, date, amount, status,            │
│       counterparty}]                                         │
│                                                              │
│  8. CONNECTIONS (agent_bot_configs.settings)                 │
│     [{agent_type, connected_services: [telegram, sheets,     │
│       amocrm, 1c, moysklad, google_drive]}]                 │
│                                                              │
│  9. PAYMENT HISTORY (billing_events, last 10)                │
│     [{event_type, amount, currency, agent_type,              │
│       created_at, wc_order_id}]                              │
│                                                              │
│  10. ACTIVE ISSUES / ALERTS                                  │
│      [{type: "low_balance", agent: "iryna",                  │
│        message: "Осталось 12% токенов"},                     │
│       {type: "subscription_expiring", agent: "marina",       │
│        expires_in_days: 3}]                                  │
└──────────────────────────────────────────────────────────────┘
```

#### Реализация загрузки контекста

```python
# aipilot_llm/client_context.py

from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentBalance:
    agent_type: str
    tier: str                    # free / lite / pro / business / enterprise
    status: str                  # active / expired / suspended
    tokens_used: int
    tokens_limit: int
    tokens_remaining: int
    next_reset_date: str         # ISO date
    payment_status: str          # paid / overdue / trial / free
    overage_allowed: bool        # можно ли уходить в минус
    expires_at: Optional[str]    # ISO date или None (бессрочно)
    auto_renew: bool


@dataclass
class ClientContext:
    """Полный контекст клиента для injection в system prompt."""
    wp_user_id: int
    email: str
    name: str
    language: str = "ru"

    # Фирмы
    firms: list[dict] = field(default_factory=list)
    active_firm: Optional[dict] = None

    # Подписки и балансы
    balances: list[AgentBalance] = field(default_factory=list)
    total_tokens_remaining: int = 0
    has_active_subscription: bool = False
    any_agent_overdue: bool = False

    # Память агентов
    agent_memories: dict[str, list[dict]] = field(default_factory=dict)
    # {"iryna": [{"key": "tax_system", "value": "УСН 6%"}, ...]}

    # Последние взаимодействия
    recent_interactions: list[dict] = field(default_factory=list)

    # Документы
    recent_documents: list[dict] = field(default_factory=list)

    # Подключения
    connections: dict[str, list[str]] = field(default_factory=dict)
    # {"iryna": ["telegram", "google_drive"], "marina": ["telegram", "amocrm"]}

    # Алерты
    alerts: list[dict] = field(default_factory=list)

    def billing_gate_verdict(self) -> dict:
        """Определить уровень доступа на основе баланса."""
        if not self.has_active_subscription and self.total_tokens_remaining <= 0:
            return {
                "level": "blocked",
                "reason": "no_subscription_no_tokens",
                "message": "Подписка не активна, токены исчерпаны.",
                "allowed_actions": ["view_balance", "subscribe", "top_up", "general_faq"],
            }

        overdue_agents = [b for b in self.balances if b.payment_status == "overdue"]
        if overdue_agents:
            return {
                "level": "restricted",
                "reason": "payment_overdue",
                "overdue_agents": [a.agent_type for a in overdue_agents],
                "message": f"Задолженность по {len(overdue_agents)} агентам.",
                "allowed_actions": ["view_balance", "subscribe", "top_up",
                                    "general_faq", "basic_chat"],
            }

        low_balance = [b for b in self.balances
                       if b.tokens_remaining < b.tokens_limit * 0.1 and b.tier != "free"]
        if low_balance:
            return {
                "level": "warning",
                "reason": "low_balance",
                "low_agents": [a.agent_type for a in low_balance],
                "message": f"Баланс < 10% у {len(low_balance)} агентов.",
                "allowed_actions": ["all"],  # всё разрешено, но предупредить
            }

        return {"level": "full", "allowed_actions": ["all"]}


async def load_client_context(wp_user_id: int, supabase) -> ClientContext:
    """Загрузить полный контекст клиента. ~5 параллельных запросов, <100ms."""

    import asyncio

    # Параллельные запросы к Supabase
    async def _load_firms():
        r = supabase.table("client_firms") \
            .select("*").eq("wp_user_id", wp_user_id) \
            .eq("is_active", True).execute()
        return r.data or []

    async def _load_subscriptions():
        r = supabase.table("agent_subscriptions") \
            .select("agent_type,tier,status,tokens_used,tokens_limit,expires_at,auto_renew") \
            .eq("wp_user_id", wp_user_id).execute()
        return r.data or []

    async def _load_memories():
        r = supabase.table("agent_client_memory") \
            .select("agent_type,memory_key,memory_value,importance,updated_at") \
            .eq("wp_user_id", wp_user_id) \
            .order("importance", desc=True).limit(100).execute()
        return r.data or []

    async def _load_recent():
        r = supabase.table("agent_learning_log") \
            .select("agent_type,interaction_type,response_quality,created_at") \
            .eq("client_id_hash", _hash_client_id(wp_user_id)) \
            .order("created_at", desc=True).limit(20).execute()
        return r.data or []

    async def _load_billing():
        r = supabase.table("billing_events") \
            .select("event_type,amount,currency,agent_type,created_at") \
            .eq("wp_user_id", wp_user_id) \
            .order("created_at", desc=True).limit(10).execute()
        return r.data or []

    # Все запросы параллельно
    firms, subs, memories, recent, billing = await asyncio.gather(
        _load_firms(), _load_subscriptions(), _load_memories(),
        _load_recent(), _load_billing(),
    )

    # Сборка контекста
    ctx = ClientContext(
        wp_user_id=wp_user_id,
        email="",  # заполняется из api_keys/wp_users
        name="",
        firms=firms,
        active_firm=next((f for f in firms if f.get("is_default")), firms[0] if firms else None),
    )

    # Балансы
    for sub in subs:
        used = sub.get("tokens_used", 0)
        limit = sub.get("tokens_limit", 0)
        ctx.balances.append(AgentBalance(
            agent_type=sub["agent_type"],
            tier=sub.get("tier", "free"),
            status=sub.get("status", "active"),
            tokens_used=used,
            tokens_limit=limit,
            tokens_remaining=max(0, limit - used),
            next_reset_date="",
            payment_status="paid" if sub.get("status") == "active" else "overdue",
            overage_allowed=False,
            expires_at=sub.get("expires_at"),
            auto_renew=sub.get("auto_renew", False),
        ))

    ctx.total_tokens_remaining = sum(b.tokens_remaining for b in ctx.balances)
    ctx.has_active_subscription = any(b.status == "active" and b.tier != "free" for b in ctx.balances)
    ctx.any_agent_overdue = any(b.payment_status == "overdue" for b in ctx.balances)

    # Память агентов → сгруппировать по agent_type
    for m in memories:
        at = m["agent_type"]
        if at not in ctx.agent_memories:
            ctx.agent_memories[at] = []
        ctx.agent_memories[at].append({
            "key": m["memory_key"],
            "value": m["memory_value"],
            "importance": m.get("importance", 0),
        })

    ctx.recent_interactions = recent

    return ctx
```

#### Биллинг-гейт: 4 уровня доступа

```
УРОВЕНЬ 1: FULL ACCESS (всё оплачено)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Клиент: "Проведи аудит за Q1"
  LLM: [проверяет баланс] → OK, 45K токенов, тариф Pro
       → вызывает Ирину, полный аудит
       → возвращает детальный отчёт


УРОВЕНЬ 2: WARNING (баланс < 10%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Клиент: "Проведи аудит за Q1"
  LLM: [проверяет баланс] → 4,200 токенов из 50,000 осталось (8%)
       → выполняет запрос, НО добавляет:
       "⚠️ Ирина: осталось 8% токенов (4,200 из 50,000).
        При текущем расходе хватит на ~3 дня.
        [💳 Пополнить] [📊 Тарифы]"


УРОВЕНЬ 3: RESTRICTED (задолженность / истекшая подписка)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Клиент: "Проведи аудит за Q1"
  LLM: [проверяет баланс] → подписка Ирины expired 3 дня назад

  LLM отвечает (НЕ вызывая Ирину):
  "Подписка на Ирину (тариф Pro, €79/мес) истекла 01.03.2026.

   Я могу дать общую консультацию по бухгалтерии,
   но для работы с вашими данными (КУДИР, банк, документы)
   нужна активная подписка.

   Что включает Pro:
   • 200K токенов/мес • Миграция данных
   • Приоритетная поддержка • Аудит за 12 мес

   [🔄 Продлить Pro за €79]  [📊 Другие тарифы]  [💬 Общий вопрос]"

  Если клиент выбирает "Общий вопрос":
    LLM отвечает из ОБЩИХ знаний (веса модели + KB),
    но НЕ обращается к данным фирмы клиента.
    Пример:
      Клиент: "Когда платить УСН за Q1?"
      LLM: "Срок уплаты УСН за Q1 2026 — до 22 апреля 2026 (п.2 ст.342 НК РБ).
            Для расчёта точной суммы по вашим данным нужна активная подписка Ирины."


УРОВЕНЬ 4: BLOCKED (нет подписок + 0 токенов)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Клиент: "Посчитай мне налоги"
  LLM: [проверяет] → 0 подписок, 0 токенов (free trial исчерпан)

  LLM отвечает (МИНИМАЛЬНО, экономим свои токены):
  "Для работы с Ириной (AI бухгалтер) нужна подписка.

   🎁 Попробуйте бесплатно:
   • Free: 5,000 токенов, базовые консультации — €0

   Или полноценно:
   • Lite: €39/мес — 50K токенов, базовые отчёты
   • Pro: €79/мес — 200K токенов, полный аудит

   [🎁 Начать бесплатно]  [📊 Все тарифы]

   Могу ответить на общие вопросы (не связанные с вашими данными)."
```

#### Память агентов — что модель использует

```python
def build_memory_context(ctx: ClientContext) -> str:
    """Превратить память агентов в часть system prompt."""
    if not ctx.agent_memories:
        return ""

    lines = ["\n## ПАМЯТЬ АГЕНТОВ О КЛИЕНТЕ (персонализация):\n"]

    for agent_type, memories in ctx.agent_memories.items():
        name = AGENT_REGISTRY.get(agent_type, {}).get("name_ru", agent_type)
        lines.append(f"### {name} помнит:")
        for m in memories[:10]:  # макс 10 записей на агента
            lines.append(f"  • {m['key']}: {m['value']}")
        lines.append("")

    lines.append("ИСПОЛЬЗУЙ эту память для персонализации ответов.")
    lines.append("Не спрашивай то, что уже знаешь. Не путай фирмы клиента.")
    lines.append("Если память противоречит запросу — уточни, не угадывай.\n")

    return "\n".join(lines)


# Пример результата в system prompt:
"""
## ПАМЯТЬ АГЕНТОВ О КЛИЕНТЕ (персонализация):

### Ирина помнит:
  • tax_system: УСН 6% (с 01.01.2025)
  • prev_tax_system: общая система (до 31.12.2024)
  • primary_bank: Альфа-Банк BY, счёт BY12ALFA000...
  • monthly_revenue_avg: ~4,500 BYN
  • prefers_brief_reports: да
  • last_audit: Q4 2025 (чистый, 0 замечаний)

### Марина помнит:
  • crm: AmoCRM (pipeline_id: 12345)
  • avg_deal_size: €1,200
  • sales_cycle_days: 14
  • hot_leads_count: 7
  • preferred_channel: Telegram

### Леон помнит:
  • company_type: ООО
  • unp: 291916447
  • registered: 2024-06-15
  • pending_contracts: 2 (NDA с PartnerX, Договор с ClientY)

ИСПОЛЬЗУЙ эту память для персонализации ответов.
"""
```

#### Обновление памяти (двунаправленное)

```
LLM API вызов → ответ → ОБНОВИТЬ ПАМЯТЬ если узнал что-то новое

Пример:
  Клиент: "Мы перешли на общую систему налогообложения с января"
  LLM: [отвечает на вопрос]
       [одновременно обновляет память]:
         UPDATE agent_client_memory
         SET memory_value = 'ОСН (с 01.01.2026)',
             updated_at = NOW()
         WHERE wp_user_id = 123
           AND agent_type = 'iryna'
           AND memory_key = 'tax_system';

         INSERT INTO agent_client_memory (wp_user_id, agent_type, memory_key, memory_value)
         VALUES (123, 'iryna', 'prev_tax_system', 'УСН 6% (до 31.12.2025)');

Что триггерит обновление памяти:
  • Клиент явно сообщает факт ("мы переехали", "сменили банк", "уволили бухгалтера")
  • Агент обнаружил изменение в данных (новый counterparty, другая валюта)
  • Периодический пересмотр: если запись >90 дней и клиент активен → пометить "verify"

Что НЕ записывается в память:
  • Эмоции / личные мнения клиента
  • Промежуточные вычисления
  • Конфиденциальные данные (пароли, полные IBAN) — только последние 4 символа
```

#### Биллинг-гейт в коде

```python
# aipilot_llm/billing_gate.py

class BillingGate:
    """Проверка баланса ПЕРЕД обработкой запроса.

    Вызывается на каждый API запрос. Быстрый (<10ms).
    Не блокирует общие вопросы — блокирует только доступ к данным клиента.
    """

    # Общие вопросы разрешены ВСЕГДА (даже без подписки)
    ALWAYS_ALLOWED = [
        "general_faq",          # "Что такое УСН?" — из общих знаний
        "pricing_info",         # "Сколько стоит Ирина?" — продажа
        "subscription_manage",  # "Как подписаться?" / "Где оплатить?"
        "view_balance",         # "Сколько у меня токенов?"
        "feature_info",         # "Что умеет Марина?"
    ]

    # Действия требующие подписку
    REQUIRES_SUBSCRIPTION = [
        "query_firm_data",      # любой запрос к данным фирмы
        "agent_call",           # вызов агента для обработки
        "document_process",     # загрузка и обработка документов
        "report_generate",      # генерация отчётов
        "delegation",           # делегирование задач агенту
    ]

    async def check(self, ctx: ClientContext, intent: str, agent_type: str) -> dict:
        """
        Returns:
            {"allowed": True} — выполнять
            {"allowed": False, "reason": "...", "upgrade_offer": {...}} — блокировать
        """
        # Общие вопросы — всегда OK
        if intent in self.ALWAYS_ALLOWED:
            return {"allowed": True}

        verdict = ctx.billing_gate_verdict()

        # FULL или WARNING → разрешить (warning добавится к ответу)
        if verdict["level"] in ("full", "warning"):
            # Проверить конкретного агента
            agent_balance = next(
                (b for b in ctx.balances if b.agent_type == agent_type), None
            )
            if agent_balance and agent_balance.tokens_remaining <= 0:
                return {
                    "allowed": False,
                    "reason": "agent_tokens_exhausted",
                    "agent": agent_type,
                    "message": f"Токены {agent_type} исчерпаны.",
                    "upgrade_offer": self._make_offer(agent_type, agent_balance.tier),
                }
            return {"allowed": True, "warning": verdict if verdict["level"] == "warning" else None}

        # RESTRICTED → только общие вопросы
        if verdict["level"] == "restricted":
            return {
                "allowed": False,
                "reason": verdict["reason"],
                "message": verdict["message"],
                "fallback": "general_knowledge_only",
                "upgrade_offer": self._make_offer(agent_type, "expired"),
            }

        # BLOCKED → минимальный ответ + продажа
        return {
            "allowed": False,
            "reason": "no_active_plan",
            "message": "Нет активных подписок.",
            "fallback": "upsell_only",
            "upgrade_offer": self._make_offer(agent_type, "none"),
        }

    def _make_offer(self, agent_type: str, current_tier: str) -> dict:
        """Сформировать предложение апгрейда."""
        registry = AGENT_REGISTRY.get(agent_type, {})
        tiers = registry.get("tiers", {})
        currency = registry.get("currency", "EUR")

        offers = []
        for tier_name, price in sorted(tiers.items(), key=lambda x: x[1]):
            if price == 0:
                offers.append({"tier": tier_name, "price": 0, "label": "Бесплатно"})
            else:
                offers.append({
                    "tier": tier_name,
                    "price": price,
                    "currency": currency,
                    "label": f"{tier_name.title()} — {currency} {price}/мес"
                })

        return {
            "agent": agent_type,
            "agent_name": registry.get("name_ru", agent_type),
            "current_tier": current_tier,
            "available_tiers": offers,
            "subscribe_url": f"https://ai-pilot.by/agents/{agent_type}#pricing",
        }
```

#### Как это выглядит в потоке запроса

```
ЗАПРОС КЛИЕНТА → API
         │
    ┌────▼─────────────────┐
    │ 1. Auth (API key)     │
    │    → wp_user_id       │
    └────┬─────────────────┘
         │
    ┌────▼─────────────────┐
    │ 2. Load Context       │  ← 5 параллельных запросов Supabase (~80ms)
    │    → ClientContext     │     firms + subs + memory + recent + billing
    └────┬─────────────────┘
         │
    ┌────▼─────────────────┐
    │ 3. Classify Intent    │  ← Haiku: 1-2 tokens, <50ms
    │    → "query_firm_data"│
    └────┬─────────────────┘
         │
    ┌────▼─────────────────┐
    │ 4. BILLING GATE       │  ← <10ms (всё в памяти из шага 2)
    │    → allowed / blocked│
    └────┬────────┬────────┘
         │        │
    allowed     blocked
         │        │
    ┌────▼────┐  ┌▼───────────────────────┐
    │ 5. LLM  │  │ 5b. Ограниченный ответ  │
    │ + agents│  │   + upgrade offer       │
    │ + memory│  │   + общие знания (если  │
    │ FULL    │  │     fallback разрешён)   │
    └────┬────┘  └────┬───────────────────┘
         │            │
    ┌────▼────────────▼────┐
    │ 6. Update Memory      │  ← записать новые факты если были
    │    + Log interaction   │
    │    + Deduct tokens     │
    └──────────────────────┘
```

#### Экономия наших токенов

```
КЛЮЧЕВОЕ: когда клиент blocked/restricted — мы НЕ тратим Claude/Mistral токены.

Стоимость ответа по уровням:
  FULL:       Полный запрос → ~$0.005-0.05 (зависит от сложности)
  WARNING:    Полный запрос + 1 строка предупреждения → тот же $0.005-0.05
  RESTRICTED: Шаблонный ответ (no LLM call!) → $0.000 (нулевая стоимость!)
  BLOCKED:    Шаблонный ответ (no LLM call!) → $0.000

  Restricted/Blocked = ШАБЛОНЫ, не LLM-генерация.
  Мы не платим за ответ неплатящему клиенту.
  Единственное исключение: если fallback = "general_knowledge_only"
  → маленький Haiku запрос (50 токенов, $0.0001).
```

#### Сценарий полного цикла

```
КЛИЕНТ: API ключ apl_live_abc123 → wp_user_id = 47

КОНТЕКСТ ЗАГРУЖЕН:
  Фирмы: ИП Сидоров (УСН 6%, BYN), ООО "ТехноСофт" (ОСН, EUR)
  Подписки: Ирина Pro (35K/200K токенов), Марина Lite (20K/50K, expires in 3 дн)
  Леон: НЕТ подписки (trial 0 токенов)

  Память Ирины: prev_audit=Q4_clean, bank=Альфа-Банк, prefers_brief
  Память Марины: crm=AmoCRM, hot_leads=7, deal_cycle=14d

ЗАПРОС 1: "Сколько я должен по налогам?"
  Intent: query_firm_data → agent: iryna
  Billing: FULL (35K токенов Pro)
  → LLM вызывает Ирину → firm.ledger → расчёт УСН
  → "По ИП Сидоров за Q1 2026: доход 18,200 BYN, УСН 6% = 1,092 BYN.
     Срок: до 22.04.2026. По ООО 'ТехноСофт' — НДС и налог на прибыль
     рассчитаю после получения банковской выписки за март."
  Токены: -1,200 (осталось 33,800)

ЗАПРОС 2: "Составь мне договор NDA с компанией XYZ"
  Intent: agent_call → agent: leon
  Billing: BLOCKED (нет подписки Леона)
  → ШАБЛОННЫЙ ответ (0 токенов LLM):
  "Для создания договоров нужна подписка на Леона (AI Юрист).
   Lite: $49/мес — базовые шаблоны, NDA, проверка контрагента.
   [Подключить Леона] [Подробнее]

   Могу дать общую информацию о структуре NDA (без персонализации)."

ЗАПРОС 3: "Какие новые лиды?"
  Intent: query_firm_data → agent: marina
  Billing: WARNING (20K/50K = 40%, НО expires in 3 дн)
  → LLM вызывает Марину → marina_leads
  → "7 горячих лидов (AmoCRM):
     1. ООО 'Прогресс' — €3,200 (стадия: КП отправлено)
     2. ИП Козлов — €800 (стадия: переговоры)
     ...
     ⚠️ Подписка Марины Lite истекает через 3 дня (07.03.2026).
     Продлить автоматически? [Да, продлить] [Напомнить позже]"
```

#### Стоимость

| Что | Затраты |
|-----|---------|
| client_context.py | €0 (код) |
| billing_gate.py | €0 (код) |
| 5 параллельных Supabase запросов | €0 (+80ms latency) |
| Шаблонные ответы для blocked | €0 (нет LLM вызова!) |
| Memory update (по необходимости) | €0 (Supabase upsert) |
| **Итого секция 8.15** | €0 прямых, 1 неделя разработки |

#### ТРИ РАЗНЫЕ ПОДПИСКИ — НЕ ПУТАТЬ! (критическое правило)

```
⚠️  В AI PILOT существуют ТРИ НЕЗАВИСИМЫХ типа подписок.
    Модель ОБЯЗАНА различать их и НИКОГДА не путать.

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   ПОДПИСКА 1: AI PILOT LLM API (для разработчиков)                  │
│   ─────────────────────────────────────────────────                  │
│   Кто покупает: РАЗРАБОТЧИК (программист, интегратор, студия)       │
│   Что получает: API ключ (apl_live_xxx) для вызова AI PILOT LLM    │
│   Таблица: api_organizations + api_usage_monthly                    │
│   Тарифы: Free(€0) / Startup(€49) / Business(€199) / Enterprise    │
│   Лимиты: запросы/мес, токены LLM/мес, доступные модели             │
│   Биллинг: api_usage_monthly.tokens_used vs plan_limit              │
│   Пример: "Мой API ключ превысил лимит" → это про LLM API          │
│                                                                     │
│   НЕ ДАЁТ доступа к агентам! API ключ ≠ подписка на Ирину.         │
│   НЕ ДАЁТ доступа к данным фирмы клиента!                          │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ПОДПИСКА 2: АГЕНТЫ AI PILOT (платформа ai-pilot.by)               │
│   ─────────────────────────────────────────────────                  │
│   Кто покупает: БИЗНЕС (предприниматель, директор, бухгалтер)       │
│   Что получает: доступ к конкретному агенту (Ирина, Марина, ...)    │
│   Таблица: agent_subscriptions + agent_tier_config                  │
│   Тарифы: Free / Lite / Pro / Business / Enterprise (per agent!)    │
│   Лимиты: токены/мес per agent, функции per tier                    │
│   Биллинг: use_agent_resource() → tokens_used per agent             │
│   Пример: "У Ирины кончились токены" → это про подписку агента      │
│                                                                     │
│   НЕ ДАЁТ доступа к LLM API! Подписка Ирины ≠ API ключ.            │
│   ДАЁТ работу агента через Telegram, кабинет, виджет.               │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ПОДПИСКА 3: AI PILOT LLM MODEL API (для своей модели)             │
│   ─────────────────────────────────────────────────────              │
│   Кто покупает: РАЗРАБОТЧИК, который хочет ПРЯМОЙ доступ к модели   │
│   Что получает: endpoint /v1/completions, /v1/chat/completions      │
│   Таблица: api_organizations (model_access: true)                   │
│   Тарифы: входит в LLM API тариф (Startup+), доп. модули отдельно  │
│   Лимиты: токены модели/мес, concurrent requests                    │
│   Отличие от подписки 1: подписка 1 = полный AI PILOT API           │
│     (агенты + бухгалтерия + юрист + маркетинг + OCR + ...).         │
│     Подписка 3 = ТОЛЬКО raw модель (как OpenAI API).                │
│                                                                     │
│   Кому нужна: тем кто строит СВОЁ приложение на нашей модели        │
│   и не нуждается в готовых агентах, а хочет сырой LLM.              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

КОГДА КЛИЕНТ ИМЕЕТ ВСЕ ТРИ:
  1С-интегратор купил:
    - LLM API Business (€199) — полный API с агентами
    - Ирина Pro (€79) — бухгалтерия для его клиентов
    - Model API (входит в Business) — прямой /v1/completions для своего софта

  → ТРИ ОТДЕЛЬНЫХ баланса:
    API Business: 2M LLM-токенов/мес (for /v1/1c/*, /v1/code/*, /v1/chat)
    Ирина Pro: 200K agent-токенов/мес (for бухгалтерские запросы)
    Model: общий с API (те же 2M, другие endpoints)

  Если API лимит исчерпан:
    → /v1/chat, /v1/code, /v1/1c/* = ❌ 429 Too Many Requests
    → Ирина в Telegram = ✅ работает (отдельный баланс)
    → Ирина через API = ❌ (API заблокирован, но агент-баланс не тронут)

  Если у Ирины кончились токены:
    → LLM API = ✅ работает (можно вызывать /v1/chat, /v1/code)
    → Ирина через API = ❌ (агент заблокирован)
    → Ирина в Telegram = ❌ (агент заблокирован)
    → Общие бухгалтерские вопросы через LLM = ✅ (из KB, без данных клиента)


ПРАВИЛО ДЛЯ МОДЕЛИ (обязательно в system prompt):

  "У клиента ТРИ возможных типа подписок:
   1. LLM API ({api_tier}, {api_tokens_remaining} токенов) — для программного доступа
   2. Агенты: {agents_summary} — для работы с конкретными AI-сотрудниками
   3. Model API: {model_access} — для прямого доступа к модели

   Это РАЗНЫЕ балансы! Исчерпание одного НЕ влияет на другие.
   Когда клиент спрашивает 'сколько осталось?' — определи контекст:
   - Если через API endpoint → показать API баланс
   - Если про агента → показать баланс агента
   - Если неясно → показать ВСЕ ТРИ и объяснить разницу.
   - НИКОГДА не путать 'API токены' и 'токены Ирины' — это разные вещи!"
```

#### Матрица: что работает при каком статусе

```
                           │ API оплачен    │ API не оплачен  │
                           │ (есть токены)  │ (0 токенов)     │
━━━━━━━━━━━━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━━┤
Агент оплачен               │ ✅ ПОЛНЫЙ       │ ❌ API blocked   │
(Ирина Pro, 35K ост.)       │ Всё работает   │ API → 429       │
                           │                │ Ирина TG/каб ✅  │
━━━━━━━━━━━━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━━┤
Агент НЕ оплачен            │ ⚠️ LLM API ✅   │ ❌ Ничего через  │
(Ирина 0 токенов)           │ Общие вопросы  │ API не работает │
                           │ Данные Ирины ❌ │ Ирина TG ❌      │
━━━━━━━━━━━━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━━┤
Нет подписки на агента      │ ⚠️ LLM API ✅   │ ❌ Ничего        │
(Леон не подключён)         │ Общие юр. ✅    │                 │
                           │ Данные Леона ❌ │                 │
━━━━━━━━━━━━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━━┤
Только Model API            │ ✅ raw модель   │ ❌ 429           │
(без AI PILOT агентов)      │ /v1/completions│                 │
                           │ Агенты ❌       │                 │
━━━━━━━━━━━━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━━━━┤

ВАЖНО: Telegram бот агента = ОТДЕЛЬНЫЙ канал.
  Работает на балансе АГЕНТА, не API.
  Клиент без API ключа может пользоваться Ириной в TG — если подписка активна.
```

#### Как модель отвечает "сколько осталось?"

```
СЦЕНАРИЙ A: Разработчик через LLM API (имеет всё)
  Запрос: "Сколько у меня осталось?"

  LLM: "📊 Все ваши балансы:

   🔑 LLM API (Business, €199/мес):
      312K / 2M токенов (15%) — хватит на ~12 дней
      Endpoints: /v1/chat, /v1/code, /v1/1c, /v1/completions

   🤖 Агенты AI PILOT:
      Ирина Pro (€79/мес): 165K / 200K (82%) ✅
      Марина Lite (€49/мес): 8K / 50K (16%) ⚠️ мало!
      Леон: не подключён

   Это разные балансы — исчерпание API не влияет на Ирину в Telegram."


СЦЕНАРИЙ B: Бизнес-клиент (только агенты, без API)
  Запрос через кабинет: "Сколько у меня осталось?"

  LLM: "📊 Ваши агенты:
      Ирина Pro: 165K / 200K (82%) ✅
      Марина Lite: 8K / 50K (16%) ⚠️
      ⚠️ У Марины осталось на ~3 дня.
      [💳 Пополнить] [📊 Тарифы]"

  (НЕ показывать API баланс — у клиента нет API подписки)


СЦЕНАРИЙ C: Разработчик (только Model API, без агентов)
  Запрос: "Сколько осталось?"

  LLM: "📊 Ваш LLM API (Startup, €49/мес):
      Использовано: 280K / 500K токенов (56%)
      Модели: AI PILOT LLM + Mistral Large

      Агенты AI PILOT не подключены.
      Хотите подключить Ирину (бухгалтерия) или Марину (продажи)?
      [📋 Каталог агентов]"
```
