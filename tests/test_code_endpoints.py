"""Tests для code endpoints — complete, generate, refactor, debug, test."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from aipilot_llm.routes.code import router

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)

SAMPLE_CODE = "def calculate_tax(amount, rate):\n    return amount * rate / 100"


def _llm_result(payload: dict = None, model_used: str = "claude-sonnet") -> dict:
    """Мок LLM result — имитирует provider.chat() return value."""
    text = json.dumps(payload or {
        "completion": ":\n    return amount * rate / 100",
        "confidence": 0.95,
        "explanation": "Завершает определение функции",
    })
    return {
        "text": text,
        "provider": "anthropic",
        "latency_ms": 350,
        "cost_eur": 0.001,
        "tokens_input": 50,
        "tokens_output": 30,
        "model": model_used,
    }


# ── /complete ─────────────────────────────────────────────────────────────────

async def test_complete_valid_request():
    """cursor_position=10 → 200 + completion в ответе."""
    with patch("aipilot_llm.routes.code._call_llm",
               new=AsyncMock(return_value=_llm_result())):
        resp = client.post("/api/v1/code/complete", json={
            "code": SAMPLE_CODE,
            "language": "python",
            "cursor_position": 10,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "completion" in data
    assert data["provider"] == "anthropic"
    assert data["latency_ms"] == 350


async def test_complete_uses_haiku_model():
    """complete endpoint передаёт model='claude-haiku' в _call_llm."""
    captured = {}

    async def capture(system, user, model="claude-sonnet"):
        captured["model"] = model
        return _llm_result()

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/complete", json={
            "code": SAMPLE_CODE,
            "cursor_position": 5,
        })

    assert captured.get("model") == "claude-haiku"


async def test_complete_cursor_out_of_bounds():
    """cursor_position > len(code) → не крашится, возвращает 200."""
    with patch("aipilot_llm.routes.code._call_llm",
               new=AsyncMock(return_value=_llm_result())):
        resp = client.post("/api/v1/code/complete", json={
            "code": "x = 1",
            "cursor_position": 9999,
        })
    assert resp.status_code == 200


# ── /generate ─────────────────────────────────────────────────────────────────

async def test_generate_with_framework():
    """framework='fastapi' → попадает в промпт пользователя."""
    captured = {}

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return _llm_result({"code": "app = FastAPI()", "language": "python",
                             "framework": "fastapi", "files": [],
                             "dependencies": [], "explanation": "...", "usage_example": "..."})

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/generate", json={
            "description": "Создай FastAPI endpoint для загрузки файлов",
            "language": "python",
            "framework": "fastapi",
        })

    assert "fastapi" in captured.get("user", "").lower()


async def test_generate_minimal_style():
    """style='minimal' → в промпте есть слово 'минимальный'."""
    captured = {}

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return _llm_result({"code": "x=1", "language": "python",
                             "framework": None, "files": [],
                             "dependencies": [], "explanation": "", "usage_example": ""})

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/generate", json={
            "description": "Функция сложения двух чисел",
            "style": "minimal",
        })

    assert "минимальный" in captured.get("user", "").lower() or \
           "minimal" in captured.get("user", "").lower()


def test_generate_description_required():
    """Пустой description (< 5 символов) → 422."""
    resp = client.post("/api/v1/code/generate", json={
        "description": "API",  # 3 символа < min_length=5
    })
    assert resp.status_code == 422


# ── /refactor ─────────────────────────────────────────────────────────────────

async def test_refactor_with_constraints():
    """constraints передаётся в промпт."""
    captured = {}

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return _llm_result({"refactored_code": "def f(): pass",
                             "changes": [], "metrics": {"lines_before": 2, "lines_after": 1,
                                                        "complexity_before": "low", "complexity_after": "low"}})

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/refactor", json={
            "code": SAMPLE_CODE,
            "constraints": "не менять публичный API функции",
        })

    assert "не менять публичный API" in captured.get("user", "")


async def test_refactor_default_goals():
    """Без goals → дефолтные [readability, performance, maintainability] в промпте."""
    captured = {}

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return _llm_result({"refactored_code": SAMPLE_CODE,
                             "changes": [], "metrics": {"lines_before": 2, "lines_after": 2,
                                                        "complexity_before": "low", "complexity_after": "low"}})

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/refactor", json={"code": SAMPLE_CODE})

    user_text = captured.get("user", "")
    assert "readability" in user_text
    assert "performance" in user_text
    assert "maintainability" in user_text


# ── /debug ────────────────────────────────────────────────────────────────────

async def test_debug_with_error_message():
    """error_message передаётся в промпт."""
    captured = {}
    fix_result = _llm_result({"bug_found": True, "root_cause": "IndentationError",
                               "bug_location": {"line": 2, "code": "    return"},
                               "fix": {"code": "def f(): return 1", "explanation": "fix"},
                               "prevention": "use linter", "severity": "medium"})

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return fix_result

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/debug", json={
            "code": SAMPLE_CODE,
            "error_message": "IndentationError: unexpected indent",
        })

    assert "IndentationError" in captured.get("user", "")


async def test_debug_without_error():
    """Без error_message → endpoint работает, 200."""
    fix_result = _llm_result({"bug_found": False, "root_cause": "no bug",
                               "bug_location": {"line": None, "code": ""},
                               "fix": {"code": SAMPLE_CODE, "explanation": "ok"},
                               "prevention": "all good", "severity": "low"})

    with patch("aipilot_llm.routes.code._call_llm",
               new=AsyncMock(return_value=fix_result)):
        resp = client.post("/api/v1/code/debug", json={"code": SAMPLE_CODE})

    assert resp.status_code == 200


async def test_debug_with_all_fields():
    """error_message + expected_behavior + actual_behavior → все в промпте."""
    captured = {}

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return _llm_result({"bug_found": True, "root_cause": "ZeroDivision",
                             "bug_location": {"line": 2, "code": "/ rate"},
                             "fix": {"code": "if rate: return ...", "explanation": "guard"},
                             "prevention": "validate inputs", "severity": "high"})

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/debug", json={
            "code": SAMPLE_CODE,
            "error_message": "ZeroDivisionError",
            "expected_behavior": "вернуть 0 при rate=0",
            "actual_behavior": "бросает исключение",
        })

    user = captured.get("user", "")
    assert "ZeroDivisionError" in user
    assert "вернуть 0 при rate=0" in user
    assert "бросает исключение" in user


# ── /test ─────────────────────────────────────────────────────────────────────

async def test_test_generation_pytest():
    """test_framework='pytest' → в промпте."""
    captured = {}
    test_result = _llm_result({"test_code": "def test_f(): assert f()==1",
                                "test_framework": "pytest", "test_count": 1,
                                "coverage_areas": ["happy_path"],
                                "test_descriptions": [{"name": "test_f", "description": "ok"}],
                                "setup_required": "pip install pytest"})

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return test_result

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/test", json={
            "code": SAMPLE_CODE,
            "test_framework": "pytest",
        })

    assert "pytest" in captured.get("user", "")


async def test_test_generation_jest():
    """test_framework='jest' → в промпте."""
    captured = {}
    test_result = _llm_result({"test_code": "test('f', () => {})",
                                "test_framework": "jest", "test_count": 1,
                                "coverage_areas": ["happy_path"],
                                "test_descriptions": [{"name": "test_f", "description": "ok"}],
                                "setup_required": None})

    async def capture(system, user, model="claude-sonnet"):
        captured["user"] = user
        return test_result

    with patch("aipilot_llm.routes.code._call_llm", new=capture):
        client.post("/api/v1/code/test", json={
            "code": "function add(a,b){return a+b}",
            "language": "javascript",
            "test_framework": "jest",
        })

    assert "jest" in captured.get("user", "")


# ── Общие проверки ────────────────────────────────────────────────────────────

async def test_all_return_provider_latency():
    """Каждый endpoint → provider + latency_ms + cost_eur в ответе."""
    endpoints_payloads = [
        ("/api/v1/code/complete",
         {"code": SAMPLE_CODE, "cursor_position": 5},
         _llm_result()),
        ("/api/v1/code/generate",
         {"description": "Функция сложения двух чисел"},
         _llm_result({"code": "def add(a,b): return a+b", "language": "python",
                       "framework": None, "files": [], "dependencies": [],
                       "explanation": "", "usage_example": ""})),
        ("/api/v1/code/refactor",
         {"code": SAMPLE_CODE},
         _llm_result({"refactored_code": SAMPLE_CODE, "changes": [],
                       "metrics": {"lines_before": 2, "lines_after": 2,
                                   "complexity_before": "low", "complexity_after": "low"}})),
        ("/api/v1/code/debug",
         {"code": SAMPLE_CODE},
         _llm_result({"bug_found": False, "root_cause": "", "bug_location": {"line": None, "code": ""},
                       "fix": {"code": "", "explanation": ""}, "prevention": "", "severity": "low"})),
        ("/api/v1/code/test",
         {"code": SAMPLE_CODE},
         _llm_result({"test_code": "", "test_framework": "pytest", "test_count": 0,
                       "coverage_areas": [], "test_descriptions": [], "setup_required": None})),
    ]

    for url, body, mock_result in endpoints_payloads:
        with patch("aipilot_llm.routes.code._call_llm",
                   new=AsyncMock(return_value=mock_result)):
            resp = client.post(url, json=body)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"
        data = resp.json()
        assert "provider" in data, f"{url}: missing 'provider'"
        assert "latency_ms" in data, f"{url}: missing 'latency_ms'"
        assert "cost_eur" in data, f"{url}: missing 'cost_eur'"


def test_empty_code_rejected():
    """Пустой code (min_length=1 — нужен хоть 1 символ) → 422."""
    resp = client.post("/api/v1/code/refactor", json={"code": ""})
    assert resp.status_code == 422
