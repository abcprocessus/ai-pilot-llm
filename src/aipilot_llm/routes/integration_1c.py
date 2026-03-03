"""1С Integration endpoints — sync-friendly API для 1С разработчиков.

⚠️  Это STUB — реализация на Этапе 7 (Developer Portal + API Platform).

Почему отдельные endpoints для 1С:
  - 1С не поддерживает async/streaming — нужен синхронный ответ
  - Максимальный timeout: 60 секунд
  - Формат запроса: multipart/form-data (PDF/изображение) или JSON
  - Формат ответа: JSON (без streaming)

Endpoints:
  POST /api/v1/1c/scan-document    — OCR + распознавание документа
  POST /api/v1/1c/accounting-query — Бухгалтерский запрос (проводки, счета)
  POST /api/v1/1c/legal-check      — Юридическая проверка
  GET  /api/v1/1c/health           — Health check (для 1С BSL connectivity test)

Пример BSL кода для вызова:
    Функция СканироватьНакладную(ПутьКФайлу) Экспорт
        Запрос = Новый HTTPЗапрос("/api/v1/1c/scan-document");
        Запрос.Заголовки.Вставить("Authorization", "Bearer " + АПИКлюч);
        МД = Новый МенеджерДанных();
        МД.ДобавитьФайл("file", ПутьКФайлу, "application/pdf");
        Соединение = Новый HTTPСоединение("api.ai-pilot.by", 443, , , , 60,
                         НовыйСоединениеOpenSSL());
        Ответ = Соединение.ОтправитьДляПолучения(Запрос);
        Возврат ПрочитатьJSON(Ответ.ПолучитьТелоКакСтроку());
    КонецФункции

Этап 7 из 8: Developer Portal + API Platform.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/1c", tags=["1C Integration"])


@router.post("/scan-document")
async def scan_document(body: dict = None):
    """OCR + распознавание бухгалтерского документа.

    Request (multipart или JSON):
        file: PDF/JPG/PNG накладной, счёта, акта (или)
        image_base64: base64-encoded изображение
        document_type: "invoice" | "act" | "waybill" | "auto" (default: "auto")
        chart_of_accounts: "by" | "ru" (default: "by")

    Response:
        {
            "document_type": "invoice",
            "supplier": "ООО Ромашка",
            "date": "2026-03-15",
            "amount": 1500.00,
            "vat_amount": 250.00,
            "currency": "BYN",
            "entries": [
                {"debit": "10.01", "credit": "60.01", "amount": 1250.00},
                {"debit": "18.01", "credit": "60.01", "amount": 250.00}
            ],
            "confidence": 0.95,
            "provider": "ai-pilot-llm"
        }
    """
    # TODO(Phase 7): Implement OCR + LLM classification + chart-of-accounts mapping
    return {"status": "not_implemented", "message": "1C Document Scanner coming in Phase 7"}


@router.post("/accounting-query")
async def accounting_query(body: dict = None):
    """Бухгалтерский запрос — проводки, счета, налоги.

    Request:
        {
            "query": "Как провести оплату поставщику из Германии в USD?",
            "context": {"chart_of_accounts": "by", "tax_system": "usn"}
        }

    Response:
        {
            "answer": "...",
            "entries": [...],
            "references": ["НК РБ ст.33", "ПУД №57-З"]
        }
    """
    # TODO(Phase 7): Implement via Iryna agent (accounting specialist)
    return {"status": "not_implemented", "message": "Accounting query coming in Phase 7"}


@router.post("/legal-check")
async def legal_check(body: dict = None):
    """Юридическая проверка документа или вопроса.

    Request:
        {
            "query": "string | contract text",
            "document_type": "contract | agreement | power_of_attorney | auto",
            "jurisdiction": "by | ru | both"
        }

    Response:
        {
            "risks": [{"clause": "5.2", "risk": "штраф без лимита", "severity": "high"}],
            "recommendation": "...",
            "references": ["ГК РБ ст.364"]
        }
    """
    # TODO(Phase 7): Implement via Leon agent (legal specialist)
    return {"status": "not_implemented", "message": "Legal check coming in Phase 7"}


@router.get("/health")
async def health_1c():
    """Health check для 1С BSL connectivity test.

    1С разработчики вызывают этот endpoint при настройке расширения
    чтобы проверить доступность API и корректность ключа.

    Response: {"status": "ok", "version": "1.0", "modules": [...]}
    """
    return {
        "status": "ok",
        "version": "1.0-stub",
        "modules": ["scan-document", "accounting-query", "legal-check"],
        "note": "Full implementation coming in Phase 7",
    }
