"""LLM health endpoint — состояние провайдеров и circuit breaker.

GET /api/v1/llm/health
Возвращает: статус каждого провайдера, circuit state, failures count.

Регистрировать в FastAPI:
    from aipilot_llm.health import router as llm_health_router
    app.include_router(llm_health_router)

Этап 1 из 8: Multi-LLM абстракция.
"""
import os
import time
from fastapi import APIRouter

from .router import _providers, _circuits, _get_circuit, _is_available, FAILURE_THRESHOLD

router = APIRouter(prefix="/api/v1/llm", tags=["LLM Health"])


@router.get("/health")
async def llm_health():
    """Состояние LLM подсистемы: провайдеры, circuit breaker, доступность.

    Response:
        {
            "status": "ok" | "degraded",
            "default_provider": "anthropic",
            "providers": {
                "anthropic": {
                    "available": true,
                    "initialized": true,
                    "supports_tools": true,
                    "circuit_state": "closed",
                    "failures": 0
                },
                ...
            }
        }
    """
    now = time.monotonic()
    providers_status: dict = {}
    all_ok = True

    for name in ["anthropic", "mistral", "openai", "local"]:
        available = _is_available(name)
        initialized = name in _providers

        state = _get_circuit(name)
        open_until: float = state.get("open_until", 0.0)
        failures_deque = state.get("failures", [])
        failure_count = len(failures_deque)

        if open_until > 0 and now < open_until:
            circuit_state = "open"
            all_ok = False
        elif failure_count > 0:
            circuit_state = "half_open"
        else:
            circuit_state = "closed"

        provider_obj = _providers.get(name)
        supports_tools = provider_obj.supports_tools() if provider_obj else False

        providers_status[name] = {
            "available":     available,
            "initialized":   initialized,
            "supports_tools": supports_tools,
            "circuit_state": circuit_state,
            "failures":      failure_count,
            "failure_threshold": FAILURE_THRESHOLD,
        }

    return {
        "status":           "ok" if all_ok else "degraded",
        "default_provider": os.getenv("LLM_PROVIDER", "anthropic"),
        "providers":        providers_status,
    }
