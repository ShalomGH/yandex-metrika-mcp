"""
Клиент API Яндекс Метрики — read-only.

Документация: https://yandex.com/dev/metrika/doc/api2/quickstart/

Базовый URL: https://api-metrika.yandex.net
Аутентификация: OAuth-токен в заголовке Authorization: OAuth ***

Мы намеренно НЕ используем сторонние обёртки (tapi-yandex-metrika и т.п.) —
только httpx, чтобы не тянуть чужие зависимости и не светить токен за пределами
нашего процесса.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger("yandex-metrika-mcp")

API_BASE = "https://api-metrika.yandex.net"

# ВАЖНО: Яндекс Метрика принимает токен в формате "OAuth <token>", не "Bearer <token>".
# Подтверждено официальной документацией: https://yandex.com/dev/metrika/en/intro/authorization


class MetrikaError(RuntimeError):
    """Ошибка при обращении к API Метрики."""

    def __init__(self, status_code: int, message: str, body: Any = None) -> None:
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.body = body


class MetrikaClient:
    """Тонкий async-клиент API Яндекс Метрики.

    Создаётся один раз на сервер (через lifespan), живёт до завершения MCP-сессии.
    Не пишет токен в логи, не передаёт никуда кроме api-metrika.yandex.net.
    """

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not token:
            raise ValueError("YANDEX_METRIKA_TOKEN is empty")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": f"OAuth {token}",  # Яндекс использует OAuth, не Bearer
                "Accept": "application/json",
                "User-Agent": "yandex-metrika-mcp/0.1.0",
            },
            timeout=timeout,
        )
        self._max_retries = max_retries

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Один HTTP-запрос с простыми retry на 429/5xx."""
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                )
            except httpx.TransportError as e:
                last_exc = e
                logger.warning("transport error attempt %s: %s", attempt + 1, e)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = MetrikaError(
                    resp.status_code, resp.text[:200], resp.text
                )
                logger.warning(
                    "retryable status %s attempt %s", resp.status_code, attempt + 1
                )
                continue

            if resp.status_code >= 400:
                # Не повторяем на 4xx — это ошибка запроса
                raise MetrikaError(resp.status_code, resp.text[:500], resp.text)

            return resp.json()

        # исчерпали попытки
        if last_exc is not None:
            raise last_exc
        raise MetrikaError(0, "retries exhausted without response")

    # ---------- Management API ----------

    async def list_counters(self) -> list[dict[str, Any]]:
        """GET /management/v1/counters — список всех счётчиков на аккаунте.

        Поля ответа: counters[].id, .name, .site, .code_status, .permission
        """
        data = await self._request("GET", "/management/v1/counters")
        return data.get("counters", [])

    # ---------- Reporting API ----------

    async def stat_data(
        self,
        counter_id: int | str,
        *,
        metrics: str,
        dimensions: str | None = None,
        date1: str,
        date2: str,
        filters: str | None = None,
        sort: str | None = None,
        limit: int = 100,
        offset: int = 1,  # API Метрики требует offset >= 1, не 0
        group: str = "all",
        accuracy: str = "full",
        quantile: float | None = None,
    ) -> dict[str, Any]:
        """GET /stat/v1/data — основной эндпоинт отчётов.

        Параметры — как в API Метрики:
          metrics:    ym:s:visits,ym:s:pageviews (через запятую)
          dimensions: ym:s:browser,ym:s:date ...
          date1/date2: YYYY-MM-DD или 'today','yesterday','7daysAgo','30daysAgo'
          filters:    ym:s:trafficSource=('organic') AND ...
          group:      day|week|month|hour|all
          accuracy:   low|full (full возвращает точные значения до 10M)
        """
        params: dict[str, Any] = {
            "id": counter_id,
            "metrics": metrics,
            "date1": date1,
            "date2": date2,
            "limit": min(max(limit, 1), 1000),
            "offset": max(offset, 1),  # API требует offset >= 1
            "group": group,
            "accuracy": accuracy,
        }
        if dimensions:
            params["dimensions"] = dimensions
        if filters:
            params["filters"] = filters
        if sort:
            params["sort"] = sort
        if quantile is not None:
            params["quantile"] = quantile

        return await self._request("GET", "/stat/v1/data", params=params)

    # ---------- Удобные обёртки (читаемый API для LLM) ----------

    async def get_visits(
        self,
        counter_id: int | str,
        date1: str,
        date2: str,
    ) -> dict[str, Any]:
        """Сводка по визитам: визиты, просмотры, посетители, отказы, время на сайте."""
        return await self.stat_data(
            counter_id,
            metrics=(
                "ym:s:visits,ym:s:pageviews,ym:s:users,"
                "ym:s:bounceRate,ym:s:avgVisitDurationSeconds"
            ),
            date1=date1,
            date2=date2,
        )

    async def get_traffic_sources(
        self,
        counter_id: int | str,
        date1: str,
        date2: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Топ источников трафика (по визитам, desc)."""
        return await self.stat_data(
            counter_id,
            metrics="ym:s:visits,ym:s:users,ym:s:bounceRate",
            dimensions="ym:s:lastTrafficSource",
            sort="-ym:s:visits",
            date1=date1,
            date2=date2,
            limit=limit,
        )

    async def get_top_pages(
        self,
        counter_id: int | str,
        date1: str,
        date2: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Топ страниц по просмотрам."""
        return await self.stat_data(
            counter_id,
            metrics="ym:s:pageviews,ym:s:visits,ym:s:users",
            dimensions="ym:s:startURL",
            sort="-ym:s:pageviews",
            date1=date1,
            date2=date2,
            limit=limit,
        )

    async def get_search_phrases(
        self,
        counter_id: int | str,
        date1: str,
        date2: str,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Поисковые фразы (из органического поиска)."""
        return await self.stat_data(
            counter_id,
            metrics="ym:s:visits,ym:s:users",
            dimensions="ym:s:searchPhrase",
            filters="ym:s:trafficSource=='organic'",
            sort="-ym:s:visits",
            date1=date1,
            date2=date2,
            limit=limit,
        )

    async def get_conversions(
        self,
        counter_id: int | str,
        date1: str,
        date2: str,
    ) -> dict[str, Any]:
        """Конверсии по всем целям счётчика.

        Возвращает rows: [ym:goal<id>, visits, conversions, conversion_rate]
        """
        return await self.stat_data(
            counter_id,
            metrics=(
                "ym:s:visits,"
                "ym:s:goal<goal_id>visits,"
                "ym:s:goal<goal_id>conversions,"
                "ym:s:goal<goal_id>conversionRate"
            ),
            dimensions="ym:s:date",
            date1=date1,
            date2=date2,
            group="day",
        )

    async def get_visits_bytime(
        self,
        counter_id: int | str,
        date1: str,
        date2: str,
        group: str = "day",
    ) -> dict[str, Any]:
        """Визиты с группировкой по времени (hour/day/week/month) — для сравнения периодов."""
        return await self.stat_data(
            counter_id,
            metrics="ym:s:visits,ym:s:users,ym:s:pageviews",
            dimensions="ym:s:date",
            date1=date1,
            date2=date2,
            group=group,
            sort="ym:s:date",
        )


def get_token_from_env() -> str:
    """Читает токен из переменной окружения.

    ВАЖНО: не пишем токен в логи, не печатаем в ошибках.
    """
    token = os.environ.get("YANDEX_METRIKA_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "YANDEX_METRIKA_TOKEN is not set. "
            "Получите токен на https://oauth.yandex.com/client/new "
            "с правами metrika:read и передайте его через env."
        )
    return token
