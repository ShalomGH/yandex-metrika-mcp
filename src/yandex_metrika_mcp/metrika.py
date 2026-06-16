"""
Клиент API Яндекс Метрики — read-only.

Документация: https://yandex.com/dev/metrika/doc/api2/quickstart/

Базовый URL: https://api-metrika.yandex.net
Аутентификация: OAuth-токен в заголовке Authorization: OAuth <token>

Мы намеренно НЕ используем сторонние обёртки (tapi-yandex-metrika и т.п.) —
только httpx, чтобы не тянуть чужие зависимости и не светить токен за пределами
нашего процесса.

Покрытие API:
  - Management: counters, goals, segments, filters, grants, labels, accounts
  - Reporting:  data, bytime, drilldown, comparison
  - Запись / загрузка данных / logs API намеренно НЕ реализованы.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Iterable

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
                "User-Agent": "yandex-metrika-mcp/0.2.0",
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
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Один HTTP-запрос с простыми retry на 429/5xx."""
        last_exc: Exception | None = None
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
        """GET /management/v1/counters — список всех счётчиков на аккаунте."""
        data = await self._request("GET", "/management/v1/counters")
        return data.get("counters", [])

    async def get_counter(self, counter_id: int | str) -> dict[str, Any]:
        """GET /management/v1/counter/{id} — детали счётчика."""
        return await self._request("GET", f"/management/v1/counter/{counter_id}")

    async def list_goals(self, counter_id: int | str) -> list[dict[str, Any]]:
        """GET /management/v1/counter/{id}/goals — список целей счётчика."""
        data = await self._request(
            "GET", f"/management/v1/counter/{counter_id}/goals"
        )
        return data.get("goals", [])

    async def list_segments(self, counter_id: int | str) -> list[dict[str, Any]]:
        """GET /management/v1/counter/{id}/segments — список сегментов."""
        data = await self._request(
            "GET", f"/management/v1/counter/{counter_id}/segments"
        )
        return data.get("segments", [])

    async def list_filters(self, counter_id: int | str) -> list[dict[str, Any]]:
        """GET /management/v1/counter/{id}/filters — список фильтров."""
        data = await self._request(
            "GET", f"/management/v1/counter/{counter_id}/filters"
        )
        return data.get("filters", [])

    async def list_grants(self, counter_id: int | str) -> list[dict[str, Any]]:
        """GET /management/v1/counter/{id}/grants — права доступа к счётчику."""
        data = await self._request(
            "GET", f"/management/v1/counter/{counter_id}/grants"
        )
        return data.get("grants", [])

    async def list_labels(self) -> list[dict[str, Any]]:
        """GET /management/v1/labels — все метки аккаунта."""
        data = await self._request("GET", "/management/v1/labels")
        return data.get("labels", [])

    async def list_accounts(self) -> list[dict[str, Any]]:
        """GET /management/v1/accounts — список аккаунтов, к которым есть доступ."""
        data = await self._request("GET", "/management/v1/accounts")
        return data.get("accounts", [])

    # ---------- Reporting API ----------

    @staticmethod
    def _csv(value: str | Iterable[str] | None) -> str | None:
        """Принимает строку или список строк — возвращает comma-separated или None."""
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        parts = [str(v).strip() for v in value if str(v).strip()]
        return ",".join(parts) if parts else None

    async def stat_data(
        self,
        counter_id: int | str,
        *,
        metrics: str | list[str],
        dimensions: str | list[str] | None = None,
        date1: str,
        date2: str,
        filters: str | None = None,
        sort: str | None = None,
        limit: int = 100,
        offset: int = 1,
        group: str = "all",
        accuracy: str = "full",
        preset: str | None = None,
    ) -> dict[str, Any]:
        """GET /stat/v1/data — основной эндпоинт отчётов.

        Параметры — как в API Метрики:
          metrics:    ym:s:visits,ym:s:pageviews (через запятую или список)
          dimensions: ym:s:browser,ym:s:date ...
          date1/date2: YYYY-MM-DD или 'today','yesterday','7daysAgo','30daysAgo'
          filters:    ym:s:trafficSource=('organic') AND ...
          group:      day|week|month|hour|all
          accuracy:   low|full (full возвращает точные значения до 10M)
          preset:     имя пресета из шаблонов Метрики
        """
        m = self._csv(metrics)
        if not m:
            raise ValueError("metrics is required (e.g. 'ym:s:visits,ym:s:pageviews')")
        params: dict[str, Any] = {
            "id": counter_id,
            "metrics": m,
            "date1": date1,
            "date2": date2,
            "limit": min(max(limit, 1), 100000),
            "offset": max(offset, 1),  # API требует offset >= 1
            "group": group,
            "accuracy": accuracy,
        }
        d = self._csv(dimensions)
        if d:
            params["dimensions"] = d
        if filters:
            params["filters"] = filters
        if sort:
            params["sort"] = sort
        if preset:
            params["preset"] = preset
        return await self._request("GET", "/stat/v1/data", params=params)

    async def stat_data_bytime(
        self,
        counter_id: int | str,
        *,
        metrics: str | list[str],
        date1: str,
        date2: str,
        group: str = "day",
        dimensions: str | list[str] | None = None,
        filters: str | None = None,
        sort: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """GET /stat/v1/data/bytime — отчёт с группировкой по времени."""
        m = self._csv(metrics)
        if not m:
            raise ValueError("metrics is required")
        params: dict[str, Any] = {
            "id": counter_id,
            "metrics": m,
            "date1": date1,
            "date2": date2,
            "group": group,
            "limit": min(max(limit, 1), 100000),
        }
        d = self._csv(dimensions)
        if d:
            params["dimensions"] = d
        if filters:
            params["filters"] = filters
        if sort:
            params["sort"] = sort
        return await self._request("GET", "/stat/v1/data/bytime", params=params)

    async def stat_data_drilldown(
        self,
        counter_id: int | str,
        *,
        metrics: str | list[str],
        dimensions: str | list[str],
        date1: str,
        date2: str,
        parent_id: str | list[str] | None = None,
        filters: str | None = None,
        sort: str | None = None,
        limit: int = 100,
        offset: int = 1,
    ) -> dict[str, Any]:
        """GET /stat/v1/data/drilldown — раскрытие уровня по parent-значению.

        parent_id: значение измерения, на котором "раскрываем" отчёт
        (например, конкретный браузер из строки отчёта по браузерам).
        ВАЖНО: API ожидает parent_id как массив — даже если передаём одно значение,
        Metrika API ругается 400, если это скаляр. Метод всегда уходит как список
        (через запятую с одним элементом = список из одного).
        """
        m = self._csv(metrics)
        d = self._csv(dimensions)
        if not m or not d:
            raise ValueError("metrics and dimensions are required for drilldown")
        params: dict[str, Any] = {
            "id": counter_id,
            "metrics": m,
            "dimensions": d,
            "date1": date1,
            "date2": date2,
            "limit": min(max(limit, 1), 100000),
            "offset": max(offset, 1),
        }
        p = self._csv(parent_id)
        # Metrika API ожидает parent_id в bracket-notation: parent_id[]=value.
        # Иначе возвращает 400 ("Failed to convert String to List"). httpx не
        # умеет такое из коробки — собираем URL руками.
        if p:
            params["__parent_id__"] = p
        if filters:
            params["filters"] = filters
        if sort:
            params["sort"] = sort
        query_items: list[tuple[str, str]] = []
        for k, v in params.items():
            if k == "__parent_id__":
                parts = [x.strip() for x in v.split(",") if x.strip()]
                for part in parts:
                    query_items.append(("parent_id[]", part))
            else:
                query_items.append((k, str(v)))
        return await self._request("GET", "/stat/v1/data/drilldown", params=query_items)


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
