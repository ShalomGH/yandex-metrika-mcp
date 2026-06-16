# yandex-metrika-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![MCP server](https://img.shields.io/badge/MCP-server-0ea5e9)](https://modelcontextprotocol.io)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)
[![Tools: 12](https://img.shields.io/badge/tools-12-success)](./src/yandex_metrika_mcp/server.py)
[![Runtime deps: 4](https://img.shields.io/badge/runtime_deps-4-success)](./pyproject.toml)
[![Companion skill](https://img.shields.io/badge/Hermes-skill-7c3aed)](./skills/yandex-metrika-analytics/SKILL.md)

> **Языки**: [English](./README.md) · [Русский (этот файл)](./README.ru.md)
>
> **Что даёт этот репозиторий**: MCP-сервер Яндекс.Метрики (слой данных) **плюс** компаньон-скилл для Hermes (слой аналитики). Ставишь оба — и LLM-агент становится аналитиком Метрики, а не трубой для цифр.

## Что в коробке

В репозитории два компонента, которые работают в связке. По отдельности толку мало.

| Слой | Что это | Где |
|---|---|---|
| **MCP-сервер** (`yandex-metrika`) | Говорит по MCP через stdio, дёргает официальный API Яндекс.Метрики с правильным заголовком `Authorization: OAuth <token>`, отдаёт сырой JSON. 12 read-only инструментов, 4 runtime-зависимости, никаких write-эндпоинтов. | [`src/yandex_metrika_mcp/`](./src/yandex_metrika_mcp/) |
| **Скилл-компаньон** (`yandex-metrika-analytics`) | `SKILL.md` для [Hermes Agent](https://hermes-agent.nousresearch.com). Объясняет LLM: какой инструмент вызвать, в каком порядке, как сравнить периоды, как разложить изменение по источнику / странице / устройству, как подать ответ человеческим языком (Суть / Цифры / Что делать). | [`skills/yandex-metrika-analytics/`](./skills/yandex-metrika-analytics/SKILL.md) |

**MCP без скилла** = 12 сырых инструментов, в которых LLM плавает и часто выдаёт ерунду (сравнивает полный месяц с неполным, объявляет «SEO сдох» по одной метрике).
**Скилл без MCP** = методичка без данных.
**Оба вместе** = маркетинговый аналитик, который умеет читать Метрику.

## Что можно спросить у агента с обоими установленными

Это реальные паттерны вопросов, под которые скилл заточен:

- *«Что случилось с трафиком на weltall.energy за эту неделю по сравнению с прошлой?»*
- *«Конверсии по основной цели упали на 30% — найди виновника: источник, страница или устройство»*
- *«Еженедельный отчёт для руководства, формат: Суть / Цифры / Что делать»*
- *«Топ-10 посадочных по органике с разбивкой bounce rate и глубины просмотра»*
- *«Сравни органический трафик за май и июнь, разложи по поисковым системам»*
- *«SEO-аудит блога: какие страницы теряют позиции и почему»*
- *«Проверка качества: трафик вырос — это рост или боты/реферальный спам?»*

Через все эти запросы скилл гонит одно правило: **никогда не выводы по одной метрике**. Всегда тянет сопоставимую базу, раскладывает изменение по сегментам, проверяет качество и ставит ярлык уверенности (высокая / средняя / низкая).

## Зачем это вообще

Существующие Yandex Metrika MCP-серверы идут по одному из двух неудачных путей: либо оборачивают вообще все эндпоинты API (десятки низкоуровневых инструментов, раздутые промпты), либо шлют неправильный auth-заголовок (`Bearer` вместо `OAuth` — Яндекс такие запросы режет с 401). Этот сервер идёт по третьему пути: **12 инструментов, 4 зависимости, 1 схема авторизации, read-only**.

## Инструменты

### Discovery (структура аккаунта)

- `list_counters` — все счётчики, доступные токену
- `get_counter` — полная инфа по одному счётчику
- `list_goals` — цели (конверсии) счётчика
- `list_segments` — сохранённые сегменты
- `list_filters` — фильтры (например, исключить внутренний трафик)
- `list_grants` — права доступа к счётчику
- `list_labels` — все метки в аккаунте
- `list_accounts` — аккаунты, доступные токену

### Analytics (отчёты)

- `get_report` — произвольный табличный отчёт: `metrics`, `dimensions`, `filters`, `sort`, `date1/date2` или `days_back`, `limit`, опциональный `preset`
- `get_bytime` — то же, что `get_report`, но с группировкой `hour | day | week | month` (для графиков и динамики)
- `get_drilldown` — раскрыть строку родительского отчёта (например, какие страницы у Chrome)
- `compare_periods` — два произвольных периода рядом, с дельтами (абсолютные и проценты) по каждой строке

## Требования

- Python 3.10+
- Yandex OAuth-токен со скоупом `metrika:read`

## Установка

Из локального чекаута:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Или через `uv`:

```bash
uv tool install .
```

## Переменные окружения

```bash
export YANDEX_METRIKA_TOKEN="y0_ваш-oauth-токен"
```

Яндекс.Метрика ждёт HTTP-заголовок `Authorization: OAuth <token>`. Сервер формирует его сам — в env-переменную кладите только сырой токен.

## Запуск

```bash
yandex-metrika-mcp
```

Сервер говорит по MCP через stdio. Логи в stderr; stdout зарезервирован под JSON-RPC.

## Интеграция с Hermes Agent

Если вы используете [Hermes Agent](https://hermes-agent.nousresearch.com), в репозитории есть всё, чтобы поднять связку за пять минут.

### MCP-обёртка (рекомендуется для Hermes)

Hermes редактирует значения `--env` в `config.yaml` и передаёт их в subprocess буквально как `***`, что ломает auth-заголовок. Обёрточный скрипт прячет токен от `config.yaml`:

```bash
cat > ~/.hermes/mcp-yandex-metrika-wrapper.sh <<'EOF'
#!/bin/bash
set -a
source ~/.hermes/.env
set +a
exec /path/to/yandex-metrika-mcp/.venv/bin/yandex-metrika-mcp
EOF
chmod 700 ~/.hermes/mcp-yandex-metrika-wrapper.sh

hermes mcp add yandex-metrika --command ~/.hermes/mcp-yandex-metrika-wrapper.sh
```

Токен — в `~/.hermes/.env`:

```bash
YANDEX_METRIKA_TOKEN="y0_ваш-oauth-токен"
```

### Скилл-компаньон (слой аналитики)

Скилл лежит в [`skills/yandex-metrika-analytics/`](./skills/yandex-metrika-analytics/) — в этом же репо, никаких вторых установок.

**Что скилл делает для LLM:**

- Заставляет сначала вызвать `list_counters` — никакого угадывания `counter_id`.
- Подбирает сопоставимые периоды (одинаковая длительность, одинаковая структура будни/выходные, явные даты вместо `days_back`, когда пользователь назвал период).
- Раскладывает изменение по источнику / странице / устройству / региону / фразе.
- Проверяет качество: bounce rate, время на сайте, глубина, **conversion rate** — всплеск трафика с падающей CR это проблема, а не победа.
- Помнит про таймзоны (таймзона счётчика vs. таймзона пользователя, например Омск UTC+6 vs. Москва).
- Выдаёт ответ в стабильной структуре: **Суть** (одно предложение) / **Цифры** (3-7 буллетов) / **Что делать** (конкретные следующие шаги).
- Ставит ярлык уверенности (высокая / средняя / низкая) и проговаривает допущения.

**Что скилл НЕ покрывает** (и чем заменить):

- Установка счётчиков, GTM, событий → используйте обычный `analytics`-скилл
- Чисто технический SEO-краулинг без метрик → `seo-audit` / `technical-seo-checker`
- Оптимизация рекламного кабинета без site analytics → `ppc`-скилл
- GA4 / Mixpanel / Segment — это только про Яндекс.Метрику

**Установка скилла:**

```bash
# Если ставили MCP из PyPI / uv — скилл в wheel не попадает, копируем вручную:
git clone https://github.com/ShalomGH/yandex-metrika-mcp.git
cp yandex-metrika-mcp/skills/yandex-metrika-analytics/SKILL.md \
   ~/.hermes/skills/marketing/yandex-metrika-analytics/SKILL.md
# перезапустите сессию агента — скилл подхватится сам
```

Если ставили из локального клона (`pip install -e .` из этого репо), файл скилла уже на месте — копируйте или делайте симлинк.

В frontmatter скилла стоит `metadata.hermes.requires_mcp: yandex-metrika` — Hermes предупредит, если MCP не подключён, а скилл загружен.

## Основные метрики и измерения

MCP-инструменты принимают сырые ID Яндекс.Метрики. Самые ходовые:

**Метрики** (`ym:s:*` — на уровне сессии, `ym:pv:*` — на уровне просмотров):

- `ym:s:visits`, `ym:s:pageviews`, `ym:s:users`, `ym:s:newUsers`
- `ym:s:bounceRate`, `ym:s:avgVisitDurationSeconds`, `ym:s:pageDepth`
- `ym:s:goal<id>visits`, `ym:s:goal<id>conversions`, `ym:s:goal<id>conversionRate`
- `ym:s:sumParams`, `ym:s:manGoal<id>conversionRate` (ручные цели)

**Измерения:**

- `ym:s:date`, `ym:s:week`, `ym:s:month`
- `ym:s:lastTrafficSource`, `ym:s:lastSearchEngine`, `ym:s:lastSearchPhraseRoot`
- `ym:s:searchEngine`, `ym:s:searchPhrase`
- `ym:s:startURL`, `ym:s:endURL`, `ym:s:pageTitle`
- `ym:s:browser`, `ym:s:browserVersion`
- `ym:s:deviceCategory`, `ym:s:operatingSystemRoot`, `ym:s:mobilePhone`
- `ym:s:country`, `ym:s:city`, `ym:s:region`
- `ym:s:referer`, `ym:s:refererSource`

## Smoke-тест

Smoke-тест стартует MCP-сервер через stdio, прогоняет `initialize`, `tools/list` и вызывает `list_counters` с фейковым токеном. В ответ ждём структурированный `invalid_token` от Яндекса — но никакого Python-краша.

```bash
PYTHONPATH=src python tests/smoke_mcp.py
```

Ожидаемый вывод:

```text
✅ initialize
✅ tools/list: 12 tools
✅ tools/call list_counters (fake token): { "error": "[403] ... invalid_token ..." }
```

## Как два слоя работают вместе

```
┌─────────────────────────────────────────────────────────────┐
│  Пользователь: «Что с трафиком на этой неделе?»             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Скилл (skills/yandex-metrika-analytics/SKILL.md)           │
│  • list_counters → выбрать счётчик                           │
│  • compare_periods → дельта неделя к неделе                  │
│  • get_report (sources) → найти виновника                   │
│  • get_report (quality) → bounce, duration, conversion      │
│  • синтез → Суть / Цифры / Что делать + уверенность         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MCP-сервер (src/yandex_metrika_mcp/server.py)              │
│  • 12 read-only инструментов                                │
│  • Authorization: OAuth <token>  (не Bearer — квирк Яндекса)│
│  • 4 runtime-зависимости, ~800 LOC, stdio JSON-RPC          │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  API Яндекс.Метрики → JSON → обратно вверх                  │
└─────────────────────────────────────────────────────────────┘
```

**Почему скилл отдельно, а не «умный сервер».** Сервер — это тонкая, предсказуемая обёртка над API, без бизнес-логики. Скилл несёт методологию и живёт рядом с агентом (Hermes грузит его по запросу). Одна репа держит версионную связку честной: когда меняется сигнатура инструмента, скилл обновляется в том же коммите.

## Разработка

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
python -m compileall src tests
python -m pytest -q
PYTHONPATH=src python tests/smoke_mcp.py
```

## Безопасность

- Сервер read-only: ни write-, ни edit-эндпоинтов Метрики наружу не торчит.
- OAuth-токен читается один раз из `YANDEX_METRIKA_TOKEN` на старте сервера.
- Токен не печатается в логи и не возвращается в ответах инструментов.
- Не коммитьте `.env` и обёрточные скрипты с реальными токенами.

## Лицензия

MIT
