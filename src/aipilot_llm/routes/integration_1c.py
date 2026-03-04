"""1С Integration endpoints — sync-friendly API.

Реализовано (Phase 2):
  POST /api/v1/1c/scan-document    — OCR + распознавание документа через Claude Vision
  GET  /api/v1/1c/health           — Статус модулей

Stubs (Phase 7):
  POST /api/v1/1c/accounting-query — Бухгалтерский запрос
  POST /api/v1/1c/legal-check      — Юридическая проверка

Почему отдельные endpoints:
  - 1С не поддерживает async/streaming — синхронный ответ
  - Timeout: 60 секунд (Claude Vision может долго обрабатывать PDF)
  - Формат: multipart/form-data (PDF/PNG/JPG) → JSON ответ

Пример BSL (1С:Предприятие 8.3):
  Запрос = Новый HTTPЗапрос("/api/v1/1c/scan-document");
  Запрос.Заголовки.Вставить("Authorization", "Bearer " + АПИКлюч);
  МД = Новый МенеджерДанных();
  МД.ДобавитьФайл("file", ПутьКФайлу, "application/pdf");
  Соединение = Новый HTTPСоединение("api.ai-pilot.by", 443, , , , 60, OpenSSL());
  Ответ = Соединение.ОтправитьДляПолучения(Запрос);
"""
import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel, Field

from aipilot_llm.router import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/1c", tags=["1C Integration"])

# Допустимые MIME типы для загрузки
_ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp", "application/pdf"}
_MAX_SIZE_MB = 20
_MAX_SIZE_BYTES = _MAX_SIZE_MB * 1024 * 1024

# Системный промпт для распознавания документов BY/RU
_SCAN_SYSTEM_PROMPT = """Ты AI PILOT — специализированный ассистент для распознавания бухгалтерских документов Беларуси и России.

Задача: проанализируй изображение документа и верни структурированный JSON.

Поддерживаемые типы документов:
- invoice (счёт-фактура, СФ)
- act (акт выполненных работ/услуг)
- waybill (товарно-транспортная накладная, ТТН, ТН)
- contract (договор)
- payment_order (платёжное поручение)
- receipt (кассовый чек)

Обязательно верни ТОЛЬКО валидный JSON без markdown, комментариев и пояснений.
Используй кодировку UTF-8 для кириллицы.
Если не можешь распознать поле — используй null.
Для сумм используй числа (не строки).
"""

_SCAN_USER_TEMPLATE = """Распознай этот документ. Тип документа: {doc_type}.
План счетов: {chart} ({chart_name}).

Верни JSON следующей структуры:
{{
    "document_type": "invoice|act|waybill|contract|payment_order|receipt|unknown",
    "document_number": "string | null",
    "document_date": "YYYY-MM-DD | null",
    "supplier": {{"name": "string | null", "inn_unp": "string | null"}},
    "buyer": {{"name": "string | null", "inn_unp": "string | null"}},
    "currency": "BYN|RUB|USD|EUR",
    "amount_without_vat": number | null,
    "vat_rate": number | null,
    "vat_amount": number | null,
    "total_amount": number | null,
    "items": [{{"description": "string", "quantity": number, "unit_price": number, "amount": number}}],
    "accounting_entries": [
        {{"debit": "XX.XX", "credit": "XX.XX", "amount": number, "description": "string"}}
    ],
    "confidence": 0.0-1.0,
    "notes": "string | null"
}}"""


def _build_anthropic_vision_message(image_bytes: bytes, media_type: str) -> list[dict]:
    """Создать messages с image для Claude Vision API."""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    # Для PDF Claude не поддерживает прямую передачу — конвертируем как document
    if media_type == "application/pdf":
        # Claude поддерживает PDF через document source type (API 2024+)
        return [{
            "role": "user",
            "content": [{
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            }],
        }]
    else:
        return [{
            "role": "user",
            "content": [{
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            }],
        }]


@router.post("/scan-document")
async def scan_document(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form(default="auto"),
    chart_of_accounts: str = Form(default="by"),
):
    """OCR + распознавание бухгалтерского документа (Claude Vision).

    Request (multipart/form-data):
        file: PDF/JPG/PNG/WEBP — обязательно
        document_type: auto|invoice|act|waybill|contract|payment_order|receipt
        chart_of_accounts: by|ru

    Response:
        {
            "document_type": "invoice",
            "document_number": "47",
            "document_date": "2026-03-15",
            "supplier": {"name": "ООО Ромашка", "inn_unp": "123456789"},
            "buyer": {"name": "ИП Иванов", "inn_unp": "987654321"},
            "currency": "BYN",
            "amount_without_vat": 1250.00,
            "vat_rate": 20,
            "vat_amount": 250.00,
            "total_amount": 1500.00,
            "items": [...],
            "accounting_entries": [
                {"debit": "10.01", "credit": "60.01", "amount": 1250.00, "description": "Товары"}
            ],
            "confidence": 0.92,
            "provider": "anthropic",
            "latency_ms": 1240
        }
    """
    # 1. Валидация файла
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Allowed: {', '.join(_ALLOWED_MIME)}"
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(file_bytes) // (1024*1024)}MB. "
                   f"Maximum: {_MAX_SIZE_MB}MB"
        )

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # 2. Определить параметры
    chart_name = "Беларуси (BY)" if chart_of_accounts == "by" else "России (RU)"
    doc_type_hint = document_type if document_type != "auto" else "определи автоматически"

    # 3. Получить провайдера (Anthropic — для Vision обязательно)
    # Anthropic Claude Vision нативно поддерживает PDF и изображения
    try:
        provider = get_provider(preferred="anthropic")
    except Exception as e:
        logger.error(f"scan-document: failed to get provider: {e}")
        raise HTTPException(status_code=503, detail="LLM provider unavailable")

    # 4. Формируем Claude Vision запрос
    user_text = _SCAN_USER_TEMPLATE.format(
        doc_type=doc_type_hint,
        chart=chart_of_accounts.upper(),
        chart_name=chart_name,
    )
    media_type = file.content_type or "image/jpeg"
    vision_messages = _build_anthropic_vision_message(file_bytes, media_type)
    # Добавляем текст к последнему content блоку
    vision_messages[0]["content"].append({"type": "text", "text": user_text})

    # 5. Вызов Claude Vision
    try:
        result = await provider.chat(
            system_prompt=_SCAN_SYSTEM_PROMPT,
            user_message="",  # сообщение уже в conversation_history
            model="claude-sonnet",
            max_tokens=2048,
            conversation_history=vision_messages,
        )
    except Exception as e:
        logger.error(f"scan-document: LLM error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM processing error: {str(e)[:200]}")

    # 6. Парсим JSON из ответа
    raw_text = result["text"].strip()
    # Убираем markdown обёртку если Claude добавил
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1])

    try:
        doc_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.warning(f"scan-document: JSON parse error: {e}, raw: {raw_text[:200]}")
        # Возвращаем raw text если JSON сломан
        doc_data = {"raw_response": raw_text, "parse_error": str(e)}

    # 7. Добавляем метаданные
    doc_data["provider"] = result["provider"]
    doc_data["latency_ms"] = result["latency_ms"]
    doc_data["cost_eur"] = result["cost_eur"]

    return doc_data


class AccountingQueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=3000)
    chart_of_accounts: str = Field(default="by")  # by | ru
    context: Optional[str] = Field(default=None, max_length=5000)
    operation_type: Optional[str] = Field(default=None)


class LegalCheckRequest(BaseModel):
    document_text: str = Field(..., min_length=10, max_length=30_000)
    document_type: str = Field(default="contract")
    jurisdiction: str = Field(default="by")  # by | ru | eu
    check_focus: list[str] = Field(default=["risks", "compliance", "missing_clauses"])


_ACCOUNTING_SYSTEM = """Ты Ирина — AI бухгалтер AI PILOT.
Специализация: бухгалтерский учёт Беларусь (план счетов 2012, Закон №57-З) и Россия (ПБУ, план счетов 2000).
Отвечаешь точно, со ссылками на НПА. Верни ТОЛЬКО JSON без markdown:
{
    "answer": "ответ на вопрос",
    "accounting_entries": [
        {"debit": "60.01", "credit": "51", "amount": null, "description": "Оплата поставщику"}
    ],
    "legal_references": ["Постановление Минфина №13 от 29.06.2011"],
    "tax_implications": "НДС 20%, вычет по входному НДС",
    "warnings": ["Проверьте лимит расчётов наличными (100 БВ)"],
    "confidence": 0.85
}"""

_LEGAL_SYSTEM = """Ты Леон — AI юрист AI PILOT.
Специализация: договорное право Беларусь (ГК РБ), Россия (ГК РФ), ЕС (GDPR/CCPA).
Анализируешь риски, нарушения, отсутствующие условия. Верни ТОЛЬКО JSON без markdown:
{
    "document_type": "string",
    "jurisdiction": "by|ru|eu",
    "risk_level": "high|medium|low",
    "issues": [
        {
            "severity": "critical|high|medium|low",
            "type": "missing_clause|ambiguous|non_compliant|unfavorable|risky",
            "clause": "п. 5.2",
            "issue": "описание проблемы",
            "recommendation": "как исправить",
            "legal_reference": "ГК РБ ст. 393"
        }
    ],
    "missing_clauses": ["форс-мажор", "ответственность сторон"],
    "compliance": {"gdpr": true, "local_law": true, "tax_compliance": true},
    "summary": "общая оценка документа",
    "confidence": 0.88
}"""


async def _llm_call(system: str, user: str, model: str = "claude-sonnet",
                    preferred: str = "anthropic") -> dict:
    """Вызов LLM с обработкой ошибок."""
    try:
        provider = get_provider(preferred=preferred)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
    try:
        return await provider.chat(
            system_prompt=system,
            user_message=user,
            model=model,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error(f"1C LLM error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)[:200]}")


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_response": raw, "error": "JSON parse failed"}


@router.post("/accounting-query")
async def accounting_query(req: AccountingQueryRequest):
    """Бухгалтерский запрос — проводки, счета, налоги BY/RU (Ирина)."""
    chart_name = "Беларусь (план счетов 2012)" if req.chart_of_accounts == "by" else "Россия (план счетов 2000)"
    parts = [
        f"План счетов: {req.chart_of_accounts.upper()} — {chart_name}",
        f"Вопрос: {req.query}",
    ]
    if req.operation_type:
        parts.append(f"Тип операции: {req.operation_type}")
    if req.context:
        parts.append(f"Контекст:\n{req.context}")

    result = await _llm_call(_ACCOUNTING_SYSTEM, "\n".join(parts))
    data = _parse_json(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data


@router.post("/legal-check")
async def legal_check(req: LegalCheckRequest):
    """Юридическая проверка документа BY/RU/EU (Леон)."""
    focus_str = ", ".join(req.check_focus)
    user_msg = (
        f"Тип документа: {req.document_type}\n"
        f"Юрисдикция: {req.jurisdiction.upper()}\n"
        f"Фокус проверки: {focus_str}\n\n"
        f"Текст документа:\n{req.document_text}"
    )
    result = await _llm_call(_LEGAL_SYSTEM, user_msg)
    data = _parse_json(result["text"])
    data["provider"] = result["provider"]
    data["latency_ms"] = result["latency_ms"]
    data["cost_eur"] = result["cost_eur"]
    return data



@router.get("/health")
async def health_1c():
    """Health check для 1С BSL connectivity test."""
    return {
        "status": "ok",
        "version": "0.2.0",
        "modules": ["scan-document", "accounting-query", "legal-check"],
        "file_types": list(_ALLOWED_MIME),
        "max_file_size_mb": _MAX_SIZE_MB,
    }
