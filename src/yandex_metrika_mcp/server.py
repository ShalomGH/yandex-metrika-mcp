"""
MCP-сервер Яндекс Метрики — read-only для маркетинговой аналитики.

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
from typing import Any, AsyncIterator, Iterable

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


def _err(e: Exception) -> str:
    """Унифицированный JSON-ответ об ошибке."""
    out: dict[str, Any] = {"error": str(e)}
    if isinstance(e, MetrikaError):
        out["status_code"] = e.status_code
    return _to_json(out)


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


def _summarize_rows(data: dict[str, Any], max_rows: int | None = None) -> dict[str, Any]:
    """Сжимаем полный ответ API Метрики до полезных для LLM полей.

    Полный ответ содержит десятки служебных полей (query, total_rows,
    sample_size, contains_sampled_data, ...) — оставляем только суть.
    """
    rows = data.get("data", [])
    out: dict[str, Any] = {
        "query": data.get("query"),
        "total_rows": data.get("total_rows"),
        "sampled": data.get("contains_sampled_data", False),
        "sample_size": data.get("sample_size"),
        "rows": rows,
    }
    if max_rows is not None and len(rows) > max_rows:
        out["rows"] = rows[:max_rows]
        out["rows_truncated"] = True
    return out


def _normalize_metrics(metrics: str | list[str]) -> list[str]:
    """Список метрик — принимает строку через запятую или список, чистит пробелы."""
    if isinstance(metrics, str):
        return [m.strip() for m in metrics.split(",") if m.strip()]
    return [str(m).strip() for m in metrics if str(m).strip()]


def _normalize_dimensions(dimensions: str | list[str] | None) -> list[str]:
    if dimensions is None:
        return []
    if isinstance(dimensions, str):
        return [d.strip() for d in dimensions.split(",") if d.strip()]
    return [str(d).strip() for d in dimensions if str(d).strip()]


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
        "Read-only доступ к Яндекс Метрике для маркетинговой аналитики. "
        "Начни с list_counters, чтобы узнать counter_id. "
        "Discovery-инструменты (list_goals, list_segments, list_filters, "
        "list_grants, list_labels, list_accounts) показывают структуру аккаунта. "
        "Аналитические инструменты: get_report (произвольные metrics+dimensions+"
        "filters+sort), get_bytime (с группировкой по времени), "
        "get_drilldown (раскрытие уровня), compare_periods (сравнение двух "
        "произвольных периодов по любым метрикам). "
        "Даты — YYYY-MM-DD, today/yesterday/NdaysAgo, либо days_back=N."
    ),
    lifespan=_lifespan,
)


# ---------- Discovery: структура аккаунта ----------


def _compact_counter(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "site": c.get("site"),
        "code_status": c.get("code_status"),
        "permission": c.get("permission"),
        "type": c.get("type"),
    }


def _compact_list(items: Iterable[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        compact = {k: it.get(k) for k in keys}
        out.append(compact)
    return out


@mcp.tool()
async def list_counters(ctx: Context) -> str:
    """Список всех счётчиков на аккаунте.

    Используйте это в самом начале, чтобы узнать counter_id для дальнейших отчётов.
    Возвращает JSON с полями id, name, site, code_status, permission, type.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        counters = await client.list_counters()
    except MetrikaError as e:
        return _err(e)
    return _to_json({"count": len(counters), "counters": [_compact_counter(c) for c in counters]})


@mcp.tool()
async def get_counter(ctx: Context, counter_id: int) -> str:
    """Детальная информация о счётчике.

    Args:
        counter_id: ID счётчика (из list_counters).
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        data = await client.get_counter(counter_id)
    except MetrikaError as e:
        return _err(e)
    return _to_json(data)


@mcp.tool()
async def list_goals(ctx: Context, counter_id: int) -> str:
    """Список целей счётчика.

    Цели нужны, чтобы понять, какие конверсии отслеживаются.
    Args:
        counter_id: ID счётчика.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        goals = await client.list_goals(counter_id)
    except MetrikaError as e:
        return _err(e)
    compact = _compact_list(goals, ["id", "name", "type", "is_retargeting", "default_price"])
    return _to_json({"count": len(compact), "goals": compact})


@mcp.tool()
async def list_segments(ctx: Context, counter_id: int) -> str:
    """Список сегментов счётчика.

    Сегменты — это сохранённые аудитории, на которые удобно ссылаться из отчётов.
    Args:
        counter_id: ID счётчика.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        segments = await client.list_segments(counter_id)
    except MetrikaError as e:
        return _err(e)
    compact = _compact_list(segments, ["segment_id", "name", "expression", "is_active"])
    return _to_json({"count": len(compact), "segments": compact})


@mcp.tool()
async def list_filters(ctx: Context, counter_id: int) -> str:
    """Список фильтров счётчика.

    Фильтры исключают из отчётов внутренний трафик, ботов и т.п.
    Args:
        counter_id: ID счётчика.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        filters = await client.list_filters(counter_id)
    except MetrikaError as e:
        return _err(e)
    compact = _compact_list(filters, ["id", "name", "type", "action", "status", "expression"])
    return _to_json({"count": len(compact), "filters": compact})


@mcp.tool()
async def list_grants(ctx: Context, counter_id: int) -> str:
    """Список разрешений на счётчик (кто имеет доступ).

    Args:
        counter_id: ID счётчика.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        grants = await client.list_grants(counter_id)
    except MetrikaError as e:
        return _err(e)
    compact = _compact_list(grants, ["user_login", "uid", "perm", "created_at"])
    return _to_json({"count": len(compact), "grants": compact})


@mcp.tool()
async def list_labels(ctx: Context) -> str:
    """Список всех меток аккаунта.

    Метки используются для группировки счётчиков.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        labels = await client.list_labels()
    except MetrikaError as e:
        return _err(e)
    compact = _compact_list(labels, ["id", "name"])
    return _to_json({"count": len(compact), "labels": compact})


@mcp.tool()
async def list_accounts(ctx: Context) -> str:
    """Список аккаунтов, к которым у токена есть доступ.

    Полезно, чтобы понять, какие счётчики в принципе доступны.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        accounts = await client.list_accounts()
    except MetrikaError as e:
        return _err(e)
    compact = _compact_list(accounts, ["user_login", "created_at"])
    return _to_json({"count": len(compact), "accounts": compact})


# ---------- Аналитика: универсальные отчёты ----------


@mcp.tool()
async def get_report(
    ctx: Context,
    counter_id: int,
    metrics: str,
    dimensions: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    date1: str | None = None,
    date2: str | None = None,
    days_back: int | None = None,
    limit: int = 100,
    preset: str | None = None,
) -> str:
    """Произвольный табличный отчёт по метрикам и измерениям Метрики.

    Покрывает большинство задач: трафик, источники, страницы, география,
    устройства, браузеры, конверсии, поисковые фразы и т.д.

    Args:
        counter_id:  ID счётчика.
        metrics:     метрики через запятую, например
                     'ym:s:visits,ym:s:pageviews,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds'.
                     Типичные:
                       ym:s:visits, ym:s:pageviews, ym:s:users, ym:s:newUsers,
                       ym:s:bounceRate, ym:s:avgVisitDurationSeconds,
                       ym:s:goal<id>visits, ym:s:goal<id>conversions, ym:s:goal<id>conversionRate
        dimensions:  измерения через запятую, например
                     'ym:s:lastTrafficSource', 'ym:s:startURL',
                     'ym:s:searchPhrase', 'ym:s:browser', 'ym:s:deviceCategory',
                     'ym:s:country', 'ym:s:city', 'ym:s:date', 'ym:s:week',
                     'ym:s:searchEngine', 'ym:s:operatingSystemRoot'.
        filters:     выражение фильтра, например
                     "ym:s:trafficSource=='organic'" или
                     "ym:s:searchEngine=='yandex' AND ym:s:deviceCategory=='mobile'".
        sort:        сортировка, например '-ym:s:visits' (по убыванию).
        date1, date2: явный период YYYY-MM-DD, либо 'today','yesterday','7daysAgo','30daysAgo'.
        days_back:   альтернатива — последние N дней до сегодня.
        limit:       сколько строк вернуть (по умолчанию 100, макс 100000).
        preset:      имя пресета Метрики (если хотите использовать шаблон).
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        # Валидируем — плохие метрики/измерения сразу дадут понятную ошибку
        _normalize_metrics(metrics)
        data = await client.stat_data(
            counter_id,
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            sort=sort,
            date1=d1,
            date2=d2,
            limit=limit,
            preset=preset,
        )
    except (MetrikaError, ValueError) as e:
        return _err(e)
    return _to_json({
        "period": {"date1": d1, "date2": d2},
        **_summarize_rows(data, max_rows=limit),
    })


@mcp.tool()
async def get_bytime(
    ctx: Context,
    counter_id: int,
    metrics: str,
    group: str = "day",
    date1: str | None = None,
    date2: str | None = None,
    days_back: int | None = None,
    dimensions: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    limit: int = 366,
) -> str:
    """Отчёт с группировкой по времени — для графиков и динамики.

    Args:
        counter_id: ID счётчика.
        metrics:    метрики через запятую.
        group:      'day' (по умолчанию), 'hour', 'week', 'month'.
        date1, date2 / days_back: период.
        dimensions, filters, sort, limit: то же, что в get_report.
    """
    if group not in {"hour", "day", "week", "month"}:
        return _to_json({"error": f"invalid group: {group}. Use hour/day/week/month."})

    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        _normalize_metrics(metrics)
        data = await client.stat_data_bytime(
            counter_id,
            metrics=metrics,
            date1=d1,
            date2=d2,
            group=group,
            dimensions=dimensions,
            filters=filters,
            sort=sort,
            limit=limit,
        )
    except (MetrikaError, ValueError) as e:
        return _err(e)
    return _to_json({
        "period": {"date1": d1, "date2": d2, "group": group},
        **_summarize_rows(data, max_rows=limit),
    })


@mcp.tool()
async def get_drilldown(
    ctx: Context,
    counter_id: int,
    metrics: str,
    dimensions: str,
    parent_id: str,
    date1: str | None = None,
    date2: str | None = None,
    days_back: int | None = None,
    filters: str | None = None,
    sort: str | None = None,
    limit: int = 100,
) -> str:
    """Раскрытие уровня отчёта: что внутри выбранной группы.

    Пример: получили отчёт по браузерам, видим Chrome — передаём
    parent_id='chrome' и получаем, какие страницы/источники/фразы у Chrome.

    Args:
        counter_id: ID счётчика.
        metrics:    метрики через запятую.
        dimensions: измерения для раскрытия (например, 'ym:s:startURL').
        parent_id:  значение родительского измерения (например, 'chrome').
        date1, date2 / days_back: период.
        filters, sort, limit: то же, что в get_report.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        d1, d2 = _resolve_dates(date1, date2, days_back)
        _normalize_metrics(metrics)
        _normalize_dimensions(dimensions)
        data = await client.stat_data_drilldown(
            counter_id,
            metrics=metrics,
            dimensions=dimensions,
            parent_id=parent_id,
            date1=d1,
            date2=d2,
            filters=filters,
            sort=sort,
            limit=limit,
        )
    except (MetrikaError, ValueError) as e:
        return _err(e)
    return _to_json({
        "period": {"date1": d1, "date2": d2},
        "parent_id": parent_id,
        **_summarize_rows(data, max_rows=limit),
    })


@mcp.tool()
async def compare_periods(
    ctx: Context,
    counter_id: int,
    metrics: str,
    period1_date1: str,
    period1_date2: str,
    period2_date1: str,
    period2_date2: str,
    dimensions: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    limit: int = 100,
) -> str:
    """Сравнение двух произвольных периодов по любым метрикам.

    Удобно для отчёта 'неделя к неделе', 'месяц к месяцу',
    'этот квартал vs прошлый квартал'.

    Args:
        counter_id:       ID счётчика.
        metrics:          метрики через запятую.
        period1_date1/2:  первый период (обычно текущий).
        period2_date1/2:  второй период (обычно предыдущий).
        dimensions, filters, sort, limit: то же, что в get_report.

    Возвращает два блока period_1 и period_2 с одинаковой структурой rows,
    плюс deltas (абсолютные и процентные) по каждой строке/метрике.
    """
    client: MetrikaClient = ctx.request_context.lifespan_context["client"]
    try:
        _normalize_metrics(metrics)
        p1 = await client.stat_data(
            counter_id,
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            sort=sort,
            date1=period1_date1,
            date2=period1_date2,
            limit=limit,
        )
        p2 = await client.stat_data(
            counter_id,
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            sort=sort,
            date1=period2_date1,
            date2=period2_date2,
            limit=limit,
        )
    except (MetrikaError, ValueError) as e:
        return _err(e)

    def _shape(resp: dict[str, Any]) -> dict[str, Any]:
        return {
            "date1": period1_date1 if resp is p1 else period2_date1,
            "date2": period1_date2 if resp is p1 else period2_date2,
            "total_rows": resp.get("total_rows"),
            "rows": resp.get("data", [])[:limit],
        }

    def _deltas(p1_rows: list[dict[str, Any]], p2_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Считаем дельту по метрикам для каждой строки.

        Ключ сопоставления строк — JSON-сериализованный dimensions, чтобы
        дельта считалась по тем же группам (например, "Direct vs Direct").
        """
        def key(r: dict[str, Any]) -> str:
            return json.dumps(r.get("dimensions", []), ensure_ascii=False, sort_keys=True)

        p2_map = {key(r): r.get("metrics", []) for r in p2_rows}
        out: list[dict[str, Any]] = []
        for r in p1_rows:
            k = key(r)
            p1_metrics = r.get("metrics", [])
            p2_metrics = p2_map.get(k)
            metrics_delta: list[dict[str, Any]] = []
            if p2_metrics is not None:
                for i, v1 in enumerate(p1_metrics):
                    v2 = p2_metrics[i] if i < len(p2_metrics) else 0
                    abs_delta = (v1 or 0) - (v2 or 0)
                    pct = None
                    if v2 not in (None, 0):
                        try:
                            pct = round(((v1 or 0) - v2) / v2 * 100, 2)
                        except ZeroDivisionError:
                            pct = None
                    metrics_delta.append({"p1": v1, "p2": v2, "abs": abs_delta, "pct": pct})
            out.append({
                "dimensions": r.get("dimensions", []),
                "metrics_delta": metrics_delta,
            })
        return out

    return _to_json({
        "period_1": _shape(p1),
        "period_2": _shape(p2),
        "deltas": _deltas(p1.get("data", []), p2.get("data", [])),
    })


# ---------- Точка входа ----------


def main() -> None:
    """STDIO-транспорт — стандарт для Hermes, Claude Desktop, Cline, Cursor."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
