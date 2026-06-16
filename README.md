# yandex-metrika-mcp

Read-only MCP server for Yandex Metrika. Small, dependency-minimal stdio wrapper around the official Yandex Metrika API. Designed for marketing analytics: a marketing agent can inspect account structure, run reports, slice by any dimension, and compare periods — all without learning the raw API.

## Why this exists

A marketing agent usually needs:

- **Discover** what counters, goals, segments, filters, grants, and labels are available.
- **Run reports** with arbitrary metrics, dimensions, filters, and sorts.
- **Slice over time** (day / hour / week / month).
- **Drill down** into a single dimension value (e.g. what pages do Chrome users land on).
- **Compare two periods** (week vs week, month vs month, this quarter vs last).

Other Yandex Metrika MCP servers either wrap every API endpoint at the cost of dozens of low-level tools and large models, or ship with the wrong auth header (`Bearer` instead of `OAuth`, which Yandex rejects). This server keeps the surface flat: **12 tools, 4 runtime dependencies, 1 auth scheme, no write access**.

## Tools

### Discovery (account structure)

- `list_counters` — list all counters available to the token.
- `get_counter` — full details for a single counter.
- `list_goals` — list goals (conversions) of a counter.
- `list_segments` — list saved segments.
- `list_filters` — list filters (e.g. exclude internal traffic).
- `list_grants` — list access grants on a counter.
- `list_labels` — list all labels in the account.
- `list_accounts` — list accounts available to the token.

### Analytics (reports)

- `get_report` — arbitrary table report. `metrics`, `dimensions`, `filters`, `sort`, `date1/date2` or `days_back`, `limit`, optional `preset`.
- `get_bytime` — same as `get_report` but grouped by `hour | day | week | month`. For time series and charts.
- `get_drilldown` — expand a row from a parent report (e.g. drill into `ym:s:startURL` for the `chrome` browser).
- `compare_periods` — compare two arbitrary periods, returns side-by-side totals and deltas (absolute + percent) per row.

## Requirements

- Python 3.10+
- Yandex OAuth token with `metrika:read` scope

## Install

From a local checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Or with `uv`:

```bash
uv tool install .
```

## Environment

```bash
export YANDEX_METRIKA_TOKEN="your-yandex-oauth-token"
```

Yandex Metrika expects the HTTP header `Authorization: OAuth <token>`. The server constructs that header internally — pass only the raw token in the environment variable.

## Run

```bash
yandex-metrika-mcp
```

The server speaks MCP over stdio. Logs go to stderr; stdout is reserved for JSON-RPC.

## Hermes Agent setup

Recommended: use a wrapper script so the token stays outside the MCP config (Hermes redacts `--env` values in `config.yaml` but passes them as the literal `***` to the subprocess, which would break the auth).

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

Put the token in `~/.hermes/.env`:

```bash
YANDEX_METRIKA_TOKEN=your-yandex-oauth-token
```

## Hermes Skill

A companion skill ships in [`skills/yandex-metrika-analytics/`](skills/yandex-metrika-analytics/).
It wraps the 12 MCP tools with an analysis pattern: resolve `counter_id` via `list_counters` first,
pick comparable periods, decompose by source/page/device, check quality (bounce, duration, conversion),
and present the answer in three blocks (Суть / Цифры / Что делать).

Install after the MCP:

```bash
hermes skills install https://raw.githubusercontent.com/ShalomGH/yandex-metrika-mcp/main/skills/yandex-metrika-analytics/SKILL.md
```

The skill declares `metadata.hermes.requires_mcp: yandex-metrika` — Hermes will warn if the MCP
is missing and the skill is loaded.

## Common metric and dimension names

The MCP tools accept raw Yandex Metrika metric/dimension IDs. Most-used values:

**Metrics** (`ym:s:*` for session-level, `ym:pv:*` for pageview-level):

- `ym:s:visits`, `ym:s:pageviews`, `ym:s:users`, `ym:s:newUsers`
- `ym:s:bounceRate`, `ym:s:avgVisitDurationSeconds`, `ym:s:pageDepth`
- `ym:s:goal<id>visits`, `ym:s:goal<id>conversions`, `ym:s:goal<id>conversionRate`
- `ym:s:sumParams`, `ym:s:manGoal<id>conversionRate` (manual goals)

**Dimensions:**

- `ym:s:date`, `ym:s:week`, `ym:s:month`
- `ym:s:lastTrafficSource`, `ym:s:lastSearchEngine`, `ym:s:lastSearchPhraseRoot`
- `ym:s:searchEngine`, `ym:s:searchPhrase`
- `ym:s:startURL`, `ym:s:endURL`, `ym:s:pageTitle`
- `ym:s:browser`, `ym:s:browserVersion`
- `ym:s:deviceCategory`, `ym:s:operatingSystemRoot`, `ym:s:mobilePhone`
- `ym:s:country`, `ym:s:city`, `ym:s:region`
- `ym:s:referer`, `ym:s:refererSource`

## Smoke test

The smoke test starts the MCP server over stdio, performs `initialize`, `tools/list`, and calls `list_counters` with a fake token. A structured Yandex `invalid_token` response is expected; a Python crash is not.

```bash
PYTHONPATH=src python tests/smoke_mcp.py
```

Expected output includes:

```text
✅ initialize
✅ tools/list: 12 tools
✅ tools/call list_counters (fake token): { "error": "[403] ... invalid_token ..." }
```

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
python -m compileall src tests
python -m pytest -q
PYTHONPATH=src python tests/smoke_mcp.py
```

## Security notes

- The server is read-only and does not expose write/edit Metrika endpoints.
- The OAuth token is read once from `YANDEX_METRIKA_TOKEN` during server startup.
- The token is not printed in logs or returned in tool responses.
- Do not commit `.env` or wrapper scripts containing real tokens.

## License

MIT
