"""Code Assistant endpoints — AI PILOT LLM как Copilot.

Реализовано (Phase 2):
  POST /api/v1/code/review    — ревью кода
  POST /api/v1/code/explain   — объяснение кода
  POST /api/v1/code/convert   — конвертация языков

Реализовано (Phase 3):
  POST /api/v1/code/complete  — автокомплит (claude-haiku, <1000ms)
  POST /api/v1/code/generate  — генерация по описанию
  POST /api/v1/code/refactor  — рефакторинг с объяснением
  POST /api/v1/code/debug     — анализ ошибки + фикс
  POST /api/v1/code/test      — генерация тестов
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aipilot_llm.router import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/code", tags=["Code Assistant"])


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response модели
# ──────────────────────────────────────────────────────────────────────────────

class CodeReviewRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")
    context: Optional[str] = Field(default=None, max_length=2000)
    focus: list[str] = Field(default=["bugs", "security", "style", "performance"])


class CodeExplainRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")
    detail_level: str = Field(default="detailed")  # brief | detailed


class CodeConvertRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    source_language: str = Field(...)
    target_language: str = Field(...)
    preserve_comments: bool = Field(default=True)


class CodeCompleteRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")
    cursor_position: int = Field(...)
    max_tokens: int = Field(default=200, le=500)


class CodeGenerateRequest(BaseModel):
    description: str = Field(..., min_length=5, max_length=5000)
    language: str = Field(default="python")
    framework: Optional[str] = Field(default=None)
    style: str = Field(default="production")


class CodeRefactorRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")
    goals: list[str] = Field(default=["readability", "performance", "maintainability"])
    constraints: Optional[str] = Field(default=None, max_length=2000)


class CodeDebugRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")
    error_message: Optional[str] = Field(default=None, max_length=5000)
    expected_behavior: Optional[str] = Field(default=None, max_length=2000)
    actual_behavior: Optional[str] = Field(default=None, max_length=2000)


class CodeTestRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str = Field(default="python")
    test_framework: str = Field(default="pytest")
    coverage_focus: list[str] = Field(default=["happy_path", "edge_cases", "error_handling"])


# ──────────────────────────────────────────────────────────────────────────────
# Системные промпты
# ──────────────────────────────────────────────────────────────────────────────

_REVIEW_SYSTEM = """Ты Senior Developer в AI PILOT. Специализируешься на:
- Python (FastAPI, async, type hints, dataclasses)
- TypeScript/Next.js (App Router, RSC, hooks)
- 1С:BSL (регистры, документы, обработки, безопасность)
- PHP/WordPress (хуки, фильтры, безопасность)
- SQL/PostgreSQL (индексы, RLS, оптимизация)

Анализируй код СТРОГО. Верни ТОЛЬКО JSON без markdown:
{
    "language": "string",
    "summary": "краткое описание что делает код",
    "issues": [
        {
            "severity": "critical|high|medium|low|info",
            "type": "security|bug|performance|style|maintainability",
            "line": number | null,
            "message": "описание проблемы на русском",
            "suggestion": "как исправить (с примером кода если уместно)"
        }
    ],
    "score": 0-100,
    "good_parts": ["что сделано хорошо"],
    "summary_verdict": "Одно предложение: общая оценка кода"
}"""

_EXPLAIN_SYSTEM = """Ты технический ментор AI PILOT. Объясняешь код разработчикам.
Специализация: Python, TypeScript, 1С:BSL, PHP, SQL.
Язык объяснения: русский.
Верни ТОЛЬКО JSON без markdown:
{
    "language": "string",
    "explanation": "подробное объяснение что делает этот код",
    "how_it_works": "пошаговое объяснение алгоритма",
    "complexity": "O(1)|O(n)|O(n²)|O(log n)|...",
    "key_concepts": ["концепция 1", "концепция 2"],
    "potential_issues": ["возможные проблемы"],
    "use_cases": ["когда использовать этот код"]
}"""

_CONVERT_SYSTEM = """Ты эксперт по конвертации кода AI PILOT.
Специализации:
- 1С:BSL → Python (FastAPI, asyncio)  
- Python → 1С:BSL
- PHP → TypeScript/JavaScript
- TypeScript → PHP
- SQL → Python ORM (SQLAlchemy)
- JavaScript → TypeScript (с типами)

ЗАДАЧА: Конвертируй код МАКСИМАЛЬНО точно.
Сохраняй логику, адаптируй к идиомам целевого языка.
Верни ТОЛЬКО JSON без markdown:
{
    "converted_code": "готовый код на целевом языке",
    "notes": ["важные замечания о конвертации"],
    "warnings": ["что невозможно конвертировать точно и почему"],
    "equivalencies": [{"source": "оригинал", "target": "эквивалент"}]
}"""

_COMPLETE_SYSTEM = """Ты Copilot AI PILOT. Дополни код в позиции курсора.
Верни ТОЛЬКО дополнение (не весь код). Верни ТОЛЬКО JSON без markdown:
{
    "completion": "код-дополнение",
    "confidence": 0.0-1.0,
    "explanation": "почему это дополнение (1 предложение)"
}"""

_GENERATE_SYSTEM = """Ты генератор кода AI PILOT. Специализация: 1С, FastAPI, Next.js, WordPress.
Генерируй production-ready код. Верни ТОЛЬКО JSON без markdown:
{
    "code": "полный код",
    "language": "string",
    "framework": "string | null",
    "files": [{"path": "filename", "code": "..."}],
    "dependencies": ["dep1"],
    "explanation": "что делает код",
    "usage_example": "как использовать"
}"""

_REFACTOR_SYSTEM = """Ты Senior Developer AI PILOT. Рефакторинг кода.
Верни ТОЛЬКО JSON без markdown:
{
    "refactored_code": "улучшенный код",
    "changes": [
        {"type": "extract_function|rename|simplify|split|merge|reorder",
         "description": "что изменено",
         "before": "фрагмент до",
         "after": "фрагмент после"}
    ],
    "metrics": {
        "lines_before": 0,
        "lines_after": 0,
        "complexity_before": "high|medium|low",
        "complexity_after": "high|medium|low"
    }
}"""

_DEBUG_SYSTEM = """Ты опытный отладчик AI PILOT. Найди баг.
Верни ТОЛЬКО JSON без markdown:
{
    "bug_found": true,
    "root_cause": "описание корневой причины",
    "bug_location": {"line": null, "code": "проблемный фрагмент"},
    "fix": {
        "code": "исправленный код",
        "explanation": "что изменено"
    },
    "prevention": "как избежать в будущем",
    "severity": "critical|high|medium|low"
}"""

_TEST_SYSTEM = """Ты QA Engineer AI PILOT. Пишешь тесты.
Верни ТОЛЬКО JSON без markdown:
{
    "test_code": "полный код тестов",
    "test_framework": "string",
    "test_count": 0,
    "coverage_areas": ["happy_path", "edge_cases"],
    "test_descriptions": [{"name": "test_...", "description": "что проверяет"}],
    "setup_required": "pip install ..."
}"""


async def _call_llm(system: str, user: str, model: str = "claude-sonnet") -> dict:
    """Универсальная функция вызова LLM с обработкой ошибок."""
    try:
        provider = get_provider()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM provider unavailable: {e}")

    try:
        result = await provider.chat(
            system_prompt=system,
            user_message=user,
            model=model,
            max_tokens=4096,
        )
    except Exception as e:
        logger.error(f"Code route LLM error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")

    return result


def _parse_json_response(raw: str) -> dict:
    """Парсить JSON ответ Claude, убирая markdown обёртки."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_response": raw, "error": "Failed to parse JSON response"}


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/review
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/review")
async def review_code(req: CodeReviewRequest):
    """Ревью кода: баги, безопасность, стиль, производительность.

    Специализация AI PILOT: 1С:BSL, Python/FastAPI, TypeScript/Next.js, PHP/WordPress.

    Request:
        {
            "code": "...",
            "language": "python",
            "context": "FastAPI endpoint для загрузки файлов (optional)",
            "focus": ["security", "performance"]
        }

    Response:
        {
            "language": "python",
            "summary": "...",
            "issues": [{"severity": "high", "type": "security", "line": 12, "message": "...", "suggestion": "..."}],
            "score": 75,
            "good_parts": ["..."],
            "summary_verdict": "...",
            "provider": "anthropic",
            "latency_ms": 1200
        }
    """
    focus_str = ", ".join(req.focus) if req.focus else "bugs, security, style, performance"
    user_msg = (
        f"Сделай ревью следующего {req.language} кода. "
        f"Фокус на: {focus_str}.\n"
        + (f"Контекст: {req.context}\n" if req.context else "")
        + f"\n```{req.language}\n{req.code}\n```"
    )

    result = await _call_llm(_REVIEW_SYSTEM, user_msg)
    data = _parse_json_response(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/explain
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/explain")
async def explain_code(req: CodeExplainRequest):
    """Объяснение кода на русском языке.

    Request:
        {
            "code": "...",
            "language": "python",
            "detail_level": "brief|detailed"
        }

    Response:
        {
            "language": "python",
            "explanation": "Этот код реализует...",
            "how_it_works": "1. Сначала... 2. Затем...",
            "complexity": "O(n)",
            "key_concepts": ["декораторы", "async/await"],
            "potential_issues": ["не обрабатывается None"],
            "use_cases": ["для парсинга больших файлов"]
        }
    """
    level_instruction = (
        "Дай КРАТКОЕ объяснение (2-3 предложения)." if req.detail_level == "brief"
        else "Дай ПОДРОБНОЕ объяснение с пошаговым разбором."
    )
    user_msg = (
        f"Объясни следующий {req.language} код. {level_instruction}\n"
        f"\n```{req.language}\n{req.code}\n```"
    )

    result = await _call_llm(_EXPLAIN_SYSTEM, user_msg)
    data = _parse_json_response(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/convert
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/convert")
async def convert_code(req: CodeConvertRequest):
    """Конвертация кода между языками программирования.

    Специализация: 1С:BSL ↔ Python, PHP ↔ TypeScript, SQL ↔ ORM.

    Request:
        {
            "code": "...",
            "source_language": "bsl",
            "target_language": "python",
            "preserve_comments": true
        }

    Response:
        {
            "converted_code": "...",
            "notes": ["1С процедура → async функция Python"],
            "warnings": ["Типы данных 1С не имеют прямых аналогов в Python"],
            "equivalencies": [{"source": "Сообщить()", "target": "print() / logger.info()"}]
        }
    """
    comments_note = "Сохраняй все комментарии (адаптируй к синтаксису целевого языка)." \
                    if req.preserve_comments else "Комментарии можно опустить."
    user_msg = (
        f"Конвертируй следующий {req.source_language} код в {req.target_language}.\n"
        f"{comments_note}\n"
        f"\n```{req.source_language}\n{req.code}\n```"
    )

    result = await _call_llm(_CONVERT_SYSTEM, user_msg, model="claude-sonnet")
    data = _parse_json_response(result["text"])
    data["source_language"] = req.source_language
    data["target_language"] = req.target_language
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/complete
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/complete")
async def complete_code(req: CodeCompleteRequest):
    """Автокомплит — IDE integration. claude-haiku, target <1000ms."""
    before = req.code[:req.cursor_position]
    after = req.code[req.cursor_position:]
    user_msg = (
        f"Язык: {req.language}\n"
        f"Код ДО курсора:\n```{req.language}\n{before}\n```\n"
        f"Код ПОСЛЕ курсора:\n```{req.language}\n{after}\n```\n"
        f"Дополни код в позиции курсора."
    )
    result = await _call_llm(_COMPLETE_SYSTEM, user_msg, model="claude-haiku")
    data = _parse_json_response(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/generate
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_code(req: CodeGenerateRequest):
    """Генерация кода по описанию. Специализация: 1С, FastAPI, Next.js, WP."""
    framework_note = f"Framework: {req.framework}." if req.framework else ""
    style_note = {
        "production": "Пиши production-ready код с обработкой ошибок и типами.",
        "prototype": "Пиши быстрый прототип, минимум boilerplate.",
        "minimal": "Пиши минимальный код — только суть.",
    }.get(req.style, "")
    user_msg = (
        f"Язык: {req.language}. {framework_note} {style_note}\n"
        f"Задача: {req.description}"
    )
    result = await _call_llm(_GENERATE_SYSTEM, user_msg, model="claude-sonnet")
    data = _parse_json_response(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/refactor
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/refactor")
async def refactor_code(req: CodeRefactorRequest):
    """Рефакторинг с пошаговым объяснением изменений."""
    goals_str = ", ".join(req.goals)
    constraints_note = f"Ограничения: {req.constraints}" if req.constraints else ""
    user_msg = (
        f"Рефакторинг {req.language} кода. Цели: {goals_str}. {constraints_note}\n"
        f"```{req.language}\n{req.code}\n```"
    )
    result = await _call_llm(_REFACTOR_SYSTEM, user_msg, model="claude-sonnet")
    data = _parse_json_response(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/debug
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/debug")
async def debug_code(req: CodeDebugRequest):
    """Найти баг + предложить исправление."""
    parts = [f"Язык: {req.language}\n```{req.language}\n{req.code}\n```"]
    if req.error_message:
        parts.append(f"Ошибка: {req.error_message}")
    if req.expected_behavior:
        parts.append(f"Ожидаемое поведение: {req.expected_behavior}")
    if req.actual_behavior:
        parts.append(f"Фактическое поведение: {req.actual_behavior}")
    user_msg = "\n".join(parts)
    result = await _call_llm(_DEBUG_SYSTEM, user_msg, model="claude-sonnet")
    data = _parse_json_response(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/v1/code/test
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/test")
async def generate_tests(req: CodeTestRequest):
    """Генерация тестов для существующего кода."""
    focus_str = ", ".join(req.coverage_focus)
    user_msg = (
        f"Напиши тесты для {req.language} кода. "
        f"Фреймворк: {req.test_framework}. Покрытие: {focus_str}.\n"
        f"```{req.language}\n{req.code}\n```"
    )
    result = await _call_llm(_TEST_SYSTEM, user_msg, model="claude-sonnet")
    data = _parse_json_response(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data
