"""Tests для 1C Integration endpoints — accounting-query и legal-check."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient
from fastapi import FastAPI

from aipilot_llm.routes.integration_1c import router


# ── Test App ──────────────────────────────────────────────────────────────────

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


def _mock_llm_result(text: str = None) -> dict:
    """Создать мок результат LLM."""
    payload = text or json.dumps({
        "answer": "Дебет 60.01 Кредит 51 — оплата поставщику",
        "accounting_entries": [
            {"debit": "60.01", "credit": "51", "amount": None, "description": "Оплата"}
        ],
        "legal_references": ["Закон №57-З"],
        "tax_implications": "НДС 20%",
        "warnings": [],
        "confidence": 0.9,
    })
    return {
        "text": payload,
        "tokens_input": 100,
        "tokens_output": 200,
        "provider": "anthropic",
        "cost_eur": 0.005,
        "latency_ms": 800,
    }


def _mock_legal_result() -> dict:
    payload = json.dumps({
        "document_type": "contract",
        "jurisdiction": "by",
        "risk_level": "medium",
        "issues": [{"severity": "high", "type": "missing_clause",
                    "clause": "п.5", "issue": "Нет форс-мажора",
                    "recommendation": "Добавить", "legal_reference": "ГК РБ ст.372"}],
        "missing_clauses": ["форс-мажор"],
        "compliance": {"gdpr": True, "local_law": True, "tax_compliance": True},
        "summary": "Договор требует доработки",
        "confidence": 0.85,
    })
    return {
        "text": payload,
        "tokens_input": 150,
        "tokens_output": 300,
        "provider": "anthropic",
        "cost_eur": 0.008,
        "latency_ms": 1100,
    }


# ── accounting-query тесты ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accounting_query_valid():
    """Корректный запрос → 200 + нужные поля."""
    with patch("aipilot_llm.routes.integration_1c._llm_call",
               new=AsyncMock(return_value=_mock_llm_result())):
        resp = client.post("/api/v1/1c/accounting-query", json={
            "query": "Как провести оплату поставщику?",
            "chart_of_accounts": "by",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["provider"] == "anthropic"
    assert "latency_ms" in data
    assert "cost_eur" in data


@pytest.mark.asyncio
async def test_accounting_query_by_chart_in_prompt():
    """chart_of_accounts=by → промпт содержит 'BY'."""
    captured = {}

    async def capture_call(system, user, **kwargs):
        captured["user"] = user
        return _mock_llm_result()

    with patch("aipilot_llm.routes.integration_1c._llm_call", new=capture_call):
        client.post("/api/v1/1c/accounting-query", json={
            "query": "Проводки по НДС",
            "chart_of_accounts": "by",
        })

    assert "BY" in captured["user"]
    assert "Беларусь" in captured["user"]


@pytest.mark.asyncio
async def test_accounting_query_ru_chart_in_prompt():
    """chart_of_accounts=ru → промпт содержит 'RU'."""
    captured = {}

    async def capture_call(system, user, **kwargs):
        captured["user"] = user
        return _mock_llm_result()

    with patch("aipilot_llm.routes.integration_1c._llm_call", new=capture_call):
        client.post("/api/v1/1c/accounting-query", json={
            "query": "НДС в России",
            "chart_of_accounts": "ru",
        })

    assert "RU" in captured["user"]
    assert "Россия" in captured["user"]


@pytest.mark.asyncio
async def test_accounting_query_with_context():
    """context передаётся в промпт."""
    captured = {}

    async def capture_call(system, user, **kwargs):
        captured["user"] = user
        return _mock_llm_result()

    with patch("aipilot_llm.routes.integration_1c._llm_call", new=capture_call):
        client.post("/api/v1/1c/accounting-query", json={
            "query": "Что делать с остатком?",
            "chart_of_accounts": "by",
            "context": "Оборотно-сальдовая ведомость за март",
        })

    assert "Оборотно-сальдовая ведомость за март" in captured["user"]


def test_accounting_query_empty_query_rejected():
    """Пустой query (< 5 символов) → 422."""
    resp = client.post("/api/v1/1c/accounting-query", json={
        "query": "НДС",  # 3 символа — меньше min_length=5
    })
    assert resp.status_code == 422


# ── legal-check тесты ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_legal_check_valid():
    """Корректный запрос → 200 + нужные поля."""
    with patch("aipilot_llm.routes.integration_1c._llm_call",
               new=AsyncMock(return_value=_mock_legal_result())):
        resp = client.post("/api/v1/1c/legal-check", json={
            "document_text": "ДОГОВОР ПОСТАВКИ\n\nПродавец обязуется передать товар покупателю.",
            "document_type": "contract",
            "jurisdiction": "by",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_level" in data
    assert "issues" in data
    assert data["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_legal_check_jurisdiction_in_prompt():
    """jurisdiction=by → промпт содержит 'BY'."""
    captured = {}

    async def capture_call(system, user, **kwargs):
        captured["user"] = user
        return _mock_legal_result()

    with patch("aipilot_llm.routes.integration_1c._llm_call", new=capture_call):
        client.post("/api/v1/1c/legal-check", json={
            "document_text": "Договор оказания услуг между сторонами.",
            "jurisdiction": "by",
        })

    assert "BY" in captured["user"]


@pytest.mark.asyncio
async def test_legal_check_document_type_in_prompt():
    """document_type=nda → тип передаётся в промпт."""
    captured = {}

    async def capture_call(system, user, **kwargs):
        captured["user"] = user
        return _mock_legal_result()

    with patch("aipilot_llm.routes.integration_1c._llm_call", new=capture_call):
        client.post("/api/v1/1c/legal-check", json={
            "document_text": "Соглашение о неразглашении между сторонами договора.",
            "document_type": "nda",
        })

    assert "nda" in captured["user"]


def test_legal_check_empty_text_rejected():
    """Пустой document_text → 422."""
    resp = client.post("/api/v1/1c/legal-check", json={
        "document_text": "Кратко",  # < 10 символов
    })
    assert resp.status_code == 422
