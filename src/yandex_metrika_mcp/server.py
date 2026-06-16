"""
MCP-сервер Яндекс Метрики — read-only.

Запуск: yandex-metrika-mcp (после `uv tool install .` или `uvx .`)
Протокол: MCP через stdio (по умолчанию в Hermes, Claude Desktop, Cline и т.д.)

Переменные окружения:
    YANDEX_METRIKA_TOKEN  — OAuth-токен Яндекс Метрики с правом metrika:read

ВАЖНО по сигнатурам инструментов FastMCP:
    Параметр `ctx: Context` должен идти ПЕРВЫМ и быть БЕЗ дефолта.
    FastMCP распознаёт его по аннотации Context и прокидывает сам.
    Все остальные параметры инструмента — после.
"""

from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, AsyncIterator

from mcp.server.fastmcp import Context, FastMCP

from .metrika import MetrikaClient, MetrikaError, get_token_from_env

# Логи пишем в stderr — stdout занят JSON-RPC MCP.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("yandex-metrika-mcp.server")


# ---------- Вспомогательные функции ----------


def _to_json(data: Any) -> str:
    """JSON с кириллицей и компактным форматированием."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _resolve_dates(
    date1: str | None,
    date2: str | None,
    days_back: int | None,
) -> tuple[str, str]:
    """Превращаем пользовательский ввод в валидные date1/date2 для API Метрики.

    Поддерживаем:
      - явные даты 'YYYY-MM-DD'
      - relative: today, yesterday, NdaysAgo (отдаём как есть)
      - days_back: date1 = today - N, date2 = today - 1
    """
    if days_back is not None:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days_back - 1)
        return start.isoformat(), end.isoformat()

    if not date1 or not date2:
        raise ValueError(
            "Укажите date1 и date2 (YYYY-MM-DD или today/yesterday/NdaysAgo), "
            "либо используйте days_back=N"
        )
    return date1.strip(), date2.strip()


def _summarize_rows(data: dict[str, Any], max_rows: int = 20) -> dict[str, Any]:
    """Сжимаем полный ответ API Метрики до полезных для LLM полей.

    Полный ответ содержит десятки служебных полей (query, total_rows,
    sample_size, contains_sampled_data, ...) — оставляем только суть.
    """
    rows = data.get("data", [])
    return {
        "query": data.get("query"),
        "total_rows": data.get("total_rows"),
        "sampled": data.get("contains_sampled_data", False),
        "sample_size": data.get("sample_size"),
        "rows": rows[:max_rows],
        "rows_truncated": len(rows) > max_rows,
    }


def _err(e: Exception) -> str:
    """Унифицированный JSON-ответ об ошибке."""
    out: dict[str, Any] = {"error": str(e)}
    if isinstance(e, MetrikaError):
        out["status_code"] = e.status_code
    return _to_json(out)


# ---------- Lifespan: один клиент на MCP-сессию ----------


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Создаём MetrikaClient при старте MCP-сессии, закрываем при завершении.

    Токен читается ОДИН раз из env — потом живёт в этом объекте.
    Никуда наружу не утекает, в логи не пишется.
    """
    token = get_token_from_env()
    client = MetrikaClient(token)
    logger.info("MetrikaClient initialized (token len=%d)", len(token))
    try:
        yield {"client": client}
    finally:
        await client.aclose()
        logger.info("MetrikaClient closed")


mcp = FastMCP(
    "yandex-metrika",
    instructions=(
        "Read-only доступ к Яндекс Метрике. "
        "Перед аналитикой обычно нужно вызвать list_counters, "
        "чтобы узнать counter_id. Даты — YYYY-MM-DD или today/yesterday/NdaysAgo, "
        "либо используйте days_back для последних N дней."
    ),
    lifespan=_lifespan,
)


# ---------- Инструменты ----------
#
# ВАЖНО: в каждом инструменте `ctx: Context` — первый параметр, БЕЗ дефолта.
# Все остальные параметры идут после и попадают в JSON-схему инструмента.


@mcp.tool()
async def list_counters(ctx: Context) -> str:
    """Список всех счётчиков на аккаунте.

    Используйте это в самом начале, чтобы узнать counter_id для дальнейших отчётов.
    Возвращает JSON с полями id, name, site, code_status, permission.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        counters = await client.list_counters()
    except MetrikaError as e:
        return _err(e)

    compact = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "site": c.get("site"),
            "code_status": c.get("code_status"),
            "permission": c.get("permission"),
            "type": c.get("type"),
        }
        for c in counters
    ]
    return _to_json({"count": len(compact), "counters": compact})


@mcp.tool()
async def get_visits_summary(
    ctx: Context,
    counter_id: int,
    days_back: int | None = None,
    date1: str | None = None,
    date2: str | None = None,
) -> str:
    """Сводка по визитам за период: visits, pageviews, users, bounce rate, avg duration.

    Args:
        counter_id: ID счётчика (получите из list_counters).
        days_back:  последние N дней (например, 7 = неделя, 30 = месяц).
        date1:      начало периода (YYYY-MM-DD или 'today'/'yesterday'/'7daysAgo').
        date2:      конец периода.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        data = await client.get_visits(counter_id, d1, d2)
    except (MetrikaError, ValueError) as e:
        return _err(e)

    return _to_json({
        "period": {"date1": d1, "date2": d2},
        **_summarize_rows(data, max_rows=1),  # сводка — это одна строка
    })


@mcp.tool()
async def get_traffic_sources(
    ctx: Context,
    counter_id: int,
    days_back: int | None = None,
    date1: str | None = None,
    date2: str | None = None,
    limit: int = 20,
) -> str:
    """Топ источников трафика (по визитам, убывание).

    Args:
        counter_id: ID счётчика.
        days_back:  последние N дней.
        date1, date2: явный период.
        limit:      сколько строк вернуть (по умолчанию 20, макс 1000).
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        data = await client.get_traffic_sources(counter_id, d1, d2, limit=limit)
    except (MetrikaError, ValueError) as e:
        return _err(e)

    return _to_json({
        "period": {"date1": d1, "date2": d2},
        **_summarize_rows(data, max_rows=limit),
    })


@mcp.tool()
async def get_top_pages(
    ctx: Context,
    counter_id: int,
    days_back: int | None = None,
    date1: str | None = None,
    date2: str | None = None,
    limit: int = 20,
) -> str:
    """Топ страниц по просмотрам (pageviews).

    Args:
        counter_id: ID счётчика.
        days_back:  последние N дней.
        date1, date2: явный период.
        limit:      сколько строк вернуть (по умолчанию 20).
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        data = await client.get_top_pages(counter_id, d1, d2, limit=limit)
    except (MetrikaError, ValueError) as e:
        return _err(e)

    return _to_json({
        "period": {"date1": d1, "date2": d2},
        **_summarize_rows(data, max_rows=limit),
    })


@mcp.tool()
async def get_search_phrases(
    ctx: Context,
    counter_id: int,
    days_back: int | None = None,
    date1: str | None = None,
    date2: str | None = None,
    limit: int = 30,
) -> str:
    """Поисковые фразы из органики (top N по визитам).

    Args:
        counter_id: ID счётчика.
        days_back:  последние N дней.
        date1, date2: явный период.
        limit:      сколько фраз вернуть (по умолчанию 30).
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        data = await client.get_search_phrases(counter_id, d1, d2, limit=limit)
    except (MetrikaError, ValueError) as e:
        return _err(e)

    return _to_json({
        "period": {"date1": d1, "date2": d2},
        **_summarize_rows(data, max_rows=limit),
    })


@mcp.tool()
async def get_visits_by_time(
    ctx: Context,
    counter_id: int,
    days_back: int | None = None,
    date1: str | None = None,
    date2: str | None = None,
    group: str = "day",
) -> str:
    """Визиты с группировкой по времени (hour/day/week/month).

    Подходит для построения графиков и сравнения периодов.

    Args:
        counter_id: ID счётчика.
        days_back:  последние N дней.
        date1, date2: явный период.
        group:      'day' (по умолчанию), 'week', 'month', 'hour'.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    if group not in {"hour", "day", "week", "month"}:
        return _to_json({"error": f"invalid group: {group}"})

    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        data = await client.get_visits_bytime(counter_id, d1, d2, group=group)
    except (MetrikaError, ValueError) as e:
        return _err(e)

    return _to_json({
        "period": {"date1": d1, "date2": d2, "group": group},
        **_summarize_rows(data, max_rows=366),
    })


@mcp.tool()
async def compare_periods(
    ctx: Context,
    counter_id: int,
    period1_days_back: int = 7,
    period2_days_back: int = 14,
) -> str:
    """Сравнение двух одинаковых по длительности периодов: текущего и предыдущего.

    По умолчанию сравнивает последние 7 дней с предыдущими 7
    (дни -14..-8 vs -7..-1). Удобно для отчёта 'неделя к неделе'
    без ручного задания дат.

    Args:
        counter_id:         ID счётчика.
        period1_days_back:  длина текущего периода в днях (по умолчанию 7).
        period2_days_back:  насколько назад начинается ПРЕДЫДУЩИЙ период
                            (по умолчанию 14 = неделя до текущей).
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    yesterday = date.today() - timedelta(days=1)

    p1_end = yesterday
    p1_start = p1_end - timedelta(days=period1_days_back - 1)
    p2_end = p1_start - timedelta(days=1)
    p2_start = p2_end - timedelta(days=period2_days_back - period1_days_back - 1)

    try:
        cur = await client.get_visits(counter_id, p1_start.isoformat(), p1_end.isoformat())
        prev = await client.get_visits(counter_id, p2_start.isoformat(), p2_end.isoformat())
    except MetrikaError as e:
        return _err(e)

    def _totals(resp: dict[str, Any]) -> dict[str, Any]:
        rows = resp.get("data", [])
        if not rows:
            return {}
        dims = resp.get("dimensions", [])
        mets = resp.get("metrics", [])
        return {
            "columns": [d.get("name") for d in dims] + [m.get("name") for m in mets],
            "values": rows[0].get("metrics", []),
        }

    return _to_json({
        "current_period": {
            "date1": p1_start.isoformat(), "date2": p1_end.isoformat(),
            **_totals(cur),
        },
        "previous_period": {
            "date1": p2_start.isoformat(), "date2": p2_end.isoformat(),
            **_totals(prev),
        },
    })


# ---------- Точка входа ----------


def main() -> None:
    """STDIO-транспорт — стандарт для Hermes, Claude Desktop, Cline, Cursor."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
