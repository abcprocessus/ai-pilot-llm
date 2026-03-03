"""GeoIP middleware — определение страны клиента по IP.

Используется LLM router для санкционной защиты:
  RU/BY клиенты → Mistral (Anthropic запрещён в этих странах)

Приоритет источников:
  1. CF-IPCountry (Cloudflare заголовок) — 0ms, точный
  2. X-Real-IP / X-Forwarded-For + ip-api.com — ~100ms, TTL-кеш 24h
  3. None — fail open (не блокируем запрос при ошибке GeoIP)

Кеш: dict в памяти (IP → country_code).
При масштабе >100K уникальных IP/мес — заменить на Redis.

Использование в route handler:
    from aipilot_llm.geoip import detect_country
    country = await detect_country(request)
    provider = get_provider(client_country=country)
"""
import logging
from typing import Optional

import httpx
from fastapi import Request

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# In-memory кеш: IP → ISO country code
# Lifetime = время жизни процесса (Railway редеплоит ~раз в день)
# ──────────────────────────────────────────────
_ip_cache: dict[str, str] = {}

# Таймаут на запрос к ip-api.com (fail open при превышении)
_GEO_TIMEOUT = httpx.Timeout(connect=2.0, read=3.0, write=1.0, pool=2.0)

# Приватные/локальные IP диапазоны — не запрашиваем GeoIP
_PRIVATE_PREFIXES = (
    "127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "::1", "fc", "fd",
)


async def detect_country(request: Request) -> Optional[str]:
    """Определить страну клиента по IP адресу.

    Args:
        request: FastAPI Request объект

    Returns:
        ISO 3166-1 alpha-2 код страны ("RU", "BY", "DE", ...) или None
    """
    # 1. Cloudflare заголовок — самый быстрый и надёжный (0ms)
    cf_country = request.headers.get("CF-IPCountry", "").upper().strip()
    if cf_country and cf_country not in ("", "XX", "T1"):
        # "XX" = неизвестная, "T1" = Tor network
        logger.debug(f"GeoIP: CF-IPCountry={cf_country}")
        return cf_country

    # 2. Определить реальный IP клиента
    ip = _extract_client_ip(request)
    if not ip:
        return None

    # Локальные IP — не запрашивать GeoIP
    if any(ip.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        logger.debug(f"GeoIP: private IP {ip} → skip")
        return None

    # 3. Кеш
    if ip in _ip_cache:
        cached = _ip_cache[ip]
        logger.debug(f"GeoIP: cache hit {ip} → {cached}")
        return cached

    # 4. ip-api.com (бесплатно, 1000 req/min)
    country = await _lookup_ip_api(ip)
    if country:
        _ip_cache[ip] = country
        logger.info(f"GeoIP: {ip} → {country} (ip-api.com)")

    return country


def _extract_client_ip(request: Request) -> Optional[str]:
    """Извлечь реальный IP клиента из заголовков.

    Railway и reverse proxies передают IP через X-Forwarded-For.
    """
    # X-Forwarded-For: client, proxy1, proxy2 — берём первый
    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        ip = xff.split(",")[0].strip()
        if ip:
            return ip

    # X-Real-IP (nginx)
    x_real = request.headers.get("X-Real-IP", "").strip()
    if x_real:
        return x_real

    # Прямое подключение (локальная разработка)
    if request.client:
        return request.client.host

    return None


async def _lookup_ip_api(ip: str) -> Optional[str]:
    """Запросить страну у ip-api.com.

    Бесплатный план: 1000 req/min — достаточно для нашего масштаба.
    При rate limit возвращаем None (fail open).
    """
    try:
        async with httpx.AsyncClient(timeout=_GEO_TIMEOUT) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "countryCode,status"},
            )
            if resp.status_code != 200:
                logger.warning(f"GeoIP ip-api.com: HTTP {resp.status_code} for {ip}")
                return None

            data = resp.json()
            if data.get("status") != "success":
                logger.debug(f"GeoIP ip-api.com: status={data.get('status')} for {ip}")
                return None

            return data.get("countryCode")

    except httpx.TimeoutException:
        logger.debug(f"GeoIP ip-api.com: timeout for {ip} (fail open)")
        return None
    except Exception as e:
        logger.debug(f"GeoIP ip-api.com: error for {ip}: {e} (fail open)")
        return None
