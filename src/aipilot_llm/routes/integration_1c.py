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


@router.post("/accounting-query")
async def accounting_query(body: dict = None):
    """Бухгалтерский запрос — проводки, счета, налоги.

    STUB — реализация в Phase 7 через Iryna agent.
    """
    return {"status": "not_implemented", "message": "Accounting query coming in Phase 7"}


@router.post("/legal-check")
async def legal_check(body: dict = None):
    """Юридическая проверка документа.

    STUB — реализация в Phase 7 через Leon agent.
    """
    return {"status": "not_implemented", "message": "Legal check coming in Phase 7"}


@router.get("/health")
async def health_1c():
    """Health check для 1С BSL connectivity test.

    1С разработчики вызывают при настройке .cfe расширения.
    """
    return {
        "status": "ok",
        "version": "0.1.0",
        "modules": ["scan-document"],
        "pending": ["accounting-query", "legal-check"],
        "file_types": list(_ALLOWED_MIME),
        "max_file_size_mb": _MAX_SIZE_MB,
    }
