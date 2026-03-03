"""Code Assistant endpoints — AI PILOT LLM как Copilot.

Реализовано (Phase 2):
  POST /api/v1/code/review    — ревью кода (баги, безопасность, стиль)
  POST /api/v1/code/explain   — объяснение кода на русском
  POST /api/v1/code/convert   — конвертация (1С:BSL ↔ Python, PHP ↔ TS и т.д.)

Stubs (Phase 7):
  POST /api/v1/code/complete  — автокомплит (<1000ms)
  POST /api/v1/code/generate  — генерация по описанию
  POST /api/v1/code/refactor  — рефакторинг с объяснением
  POST /api/v1/code/debug     — анализ ошибки + фикс
  POST /api/v1/code/test      — генерация тестов

Этап 7 из 8: Developer Portal + API Platform.
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
# Stubs (Phase 7)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/complete")
async def complete_code(body: dict = None):
    """Автокомплит — IDE integration. Target latency: <1000ms. STUB Phase 7."""
    return {"status": "not_implemented", "message": "Code completion coming in Phase 7"}


@router.post("/generate")
async def generate_code(body: dict = None):
    """Генерация кода по описанию. STUB Phase 7."""
    return {"status": "not_implemented", "message": "Code generation coming in Phase 7"}


@router.post("/refactor")
async def refactor_code(body: dict = None):
    """Рефакторинг с объяснением. STUB Phase 7."""
    return {"status": "not_implemented", "message": "Code refactoring coming in Phase 7"}


@router.post("/debug")
async def debug_code(body: dict = None):
    """Анализ ошибки + предложение фикса. STUB Phase 7."""
    return {"status": "not_implemented", "message": "Code debugging coming in Phase 7"}


@router.post("/test")
async def generate_tests(body: dict = None):
    """Генерация тестов для кода. STUB Phase 7."""
    return {"status": "not_implemented", "message": "Test generation coming in Phase 7"}
