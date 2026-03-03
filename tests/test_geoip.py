"""Tests для aipilot_llm.geoip — определение страны клиента."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from aipilot_llm import geoip as geoip_module
from aipilot_llm.geoip import detect_country, _lookup_ip_api, _extract_client_ip
import httpx


def make_request(
    headers: dict = None,
    client_host: str = "1.2.3.4",
) -> Request:
    """Создать мок FastAPI Request с заданными заголовками."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": b"",
    }
    return Request(scope, receive=AsyncMock())


@pytest.fixture(autouse=True)
def clear_ip_cache():
    """Очищать кеш IP между тестами."""
    geoip_module._ip_cache.clear()
    yield
    geoip_module._ip_cache.clear()


# ──────────────────────────────────────────────────────────────────────────────

async def test_cloudflare_header_takes_priority():
    """CF-IPCountry имеет наивысший приоритет — всегда возвращается первым."""
    req = make_request(headers={"CF-IPCountry": "BY"})

    result = await detect_country(req)
    assert result == "BY"


async def test_cloudflare_xx_is_ignored():
    """CF-IPCountry=XX (unknown) → не использовать, fallback на ip-api."""
    req = make_request(
        headers={
            "CF-IPCountry": "XX",
            "X-Forwarded-For": "8.8.8.8",
        }
    )

    with patch("aipilot_llm.geoip._lookup_ip_api", new=AsyncMock(return_value="US")):
        result = await detect_country(req)

    assert result == "US"


async def test_x_forwarded_for_fallback():
    """X-Forwarded-For используется когда нет CF-IPCountry."""
    req = make_request(headers={"X-Forwarded-For": "85.21.100.100, 10.0.0.1"})

    with patch("aipilot_llm.geoip._lookup_ip_api", new=AsyncMock(return_value="RU")):
        result = await detect_country(req)

    assert result == "RU"


def test_x_forwarded_for_first_ip_extracted():
    """Из X-Forwarded-For берётся первый IP (клиент), а не прокси."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 10.0.0.1, 192.168.1.1")],
        "query_string": b"",
    }
    req = Request(scope, receive=AsyncMock())
    ip = _extract_client_ip(req)
    assert ip == "1.2.3.4"


async def test_private_ip_returns_none():
    """Приватные IP (10.x, 127.x, 192.168.x) → None (без запроса к api)."""
    req = make_request(headers={"X-Forwarded-For": "192.168.1.1"})

    with patch("aipilot_llm.geoip._lookup_ip_api", new=AsyncMock()) as mock_lookup:
        result = await detect_country(req)

    assert result is None
    mock_lookup.assert_not_called()


async def test_cache_hit_avoids_api_call():
    """Второй запрос для того же IP → из кеша, без api."""
    geoip_module._ip_cache["5.5.5.5"] = "DE"

    req = make_request(headers={"X-Forwarded-For": "5.5.5.5"})

    with patch("aipilot_llm.geoip._lookup_ip_api", new=AsyncMock()) as mock_lookup:
        result = await detect_country(req)

    assert result == "DE"
    mock_lookup.assert_not_called()


async def test_ip_api_result_stored_in_cache():
    """Результат ip-api.com сохраняется в кеш для следующего запроса."""
    req = make_request(headers={"X-Forwarded-For": "77.88.55.55"})

    with patch("aipilot_llm.geoip._lookup_ip_api", new=AsyncMock(return_value="RU")):
        result = await detect_country(req)

    assert result == "RU"
    assert geoip_module._ip_cache.get("77.88.55.55") == "RU"


async def test_api_timeout_returns_none():
    """Timeout у ip-api.com → None (fail open, запрос не блокируется)."""
    req = make_request(headers={"X-Forwarded-For": "130.0.0.1"})

    with patch("aipilot_llm.geoip._lookup_ip_api", new=AsyncMock(return_value=None)):
        result = await detect_country(req)

    assert result is None


async def test_tor_t1_treated_as_unknown():
    """CF-IPCountry=T1 (Tor network) → не возвращать т1, fallback."""
    req = make_request(headers={
        "CF-IPCountry": "T1",
        "X-Forwarded-For": "185.220.101.1",
    })

    with patch("aipilot_llm.geoip._lookup_ip_api", new=AsyncMock(return_value=None)):
        result = await detect_country(req)

    # T1 игнорируется, lookup также None → result None
    assert result is None


async def test_lookup_ip_api_parses_response():
    """_lookup_ip_api() правильно парсит ответ ip-api.com."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success", "countryCode": "PL"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("aipilot_llm.geoip.httpx.AsyncClient", return_value=mock_client):
        result = await _lookup_ip_api("5.183.0.1")

    assert result == "PL"
