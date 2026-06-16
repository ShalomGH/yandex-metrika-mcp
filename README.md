# yandex-metrika-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![MCP server](https://img.shields.io/badge/MCP-server-0ea5e9)](https://modelcontextprotocol.io)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)
[![Tools: 12](https://img.shields.io/badge/tools-12-success)](./src/yandex_metrika_mcp/server.py)
[![Runtime deps: 4](https://img.shields.io/badge/runtime_deps-4-success)](./pyproject.toml)
[![Companion skill](https://img.shields.io/badge/Hermes-skill-7c3aed)](./skills/yandex-metrika-analytics/SKILL.md)

> **Languages**: [English](./README.md) · [Русский](./README.ru.md)
>
> **What this repository provides**: a read-only MCP server for Yandex Metrika (data layer) and a companion Hermes skill (analysis layer). Installing both enables an LLM agent to perform structured Yandex Metrika analysis: account discovery, period comparison, segment decomposition, and confidence-rated reporting.

## What's in the box

This repository ships two components intended to be used together. The MCP server provides the API surface; the skill provides the methodology that drives the API surface. Each component is of limited value on its own.

| Layer | Description | Location |
|---|---|---|
| **MCP server** (`yandex-metrika`) | Speaks MCP over stdio and calls the official Yandex Metrika API using the `Authorization: OAuth <token>` header. Exposes 12 read-only tools. 4 runtime dependencies. No write endpoints. | [`src/yandex_metrika_mcp/`](./src/yandex_metrika_mcp/) |
| **Companion skill** (`yandex-metrika-analytics`) | A `SKILL.md` for [Hermes Agent](https://hermes-agent.nousresearch.com) that defines the analysis pattern: which tool to call, in what order, how to compare periods, how to decompose a change by source, page, or device, and how to present the result. | [`skills/yandex-metrika-analytics/`](./skills/yandex-metrika-analytics/SKILL.md) |

The MCP without the skill provides a flat tool surface with no analytical context, which can lead to incorrect conclusions (for example, comparing a full month against a partial one, or attributing a change to a single source without decomposition). The skill without the MCP has no access to live data. Together, they provide a complete analysis workflow.

## Example queries

The following are representative question patterns the skill is designed to handle:

- Period-over-period traffic comparison with decomposition.
- Goal conversion diagnostics by source, page, or device.
- Weekly or monthly executive reports in a structured format.
- Landing page analysis with bounce rate and depth breakdown.
- Organic traffic comparison across search engines.
- Content-level SEO diagnosis of ranking and traffic changes.
- Traffic quality assessment, including bot and referral-spam filtering.

The skill enforces a single rule across all question types: conclusions must not be drawn from a single metric. Every analysis pulls a comparable baseline, decomposes the change, checks quality, and returns a confidence label (high, medium, or low).

## Why this exists

A marketing analysis agent typically needs the following capabilities:

- Discover what counters, goals, segments, filters, grants, and labels are available.
- Run reports with arbitrary metrics, dimensions, filters, and sorts.
- Slice results over time (day, hour, week, or month).
- Drill down into a single dimension value.
- Compare two periods of equal length.

Existing Yandex Metrika MCP servers fall into one of two categories. The first wraps every API endpoint, which produces dozens of low-level tools and inflates the model's prompt. The second ships with the wrong authentication header (`Bearer` instead of `OAuth`), which Yandex rejects with HTTP 401. This server follows a different design: 12 tools, 4 runtime dependencies, 1 authentication scheme, read-only.

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

## Optional: Hermes Agent integration

If you use [Hermes Agent](https://hermes-agent.nousresearch.com), two extras ship with this repo.

### MCP wrapper (recommended for Hermes)

Hermes redacts `--env` values in `config.yaml` but passes them as the literal
`***` to the subprocess, which would break the auth header. Use a wrapper
script so the token stays outside the MCP config:

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
YANDEX_METRIKA_TOKEN="your-y...oken"
```

### Companion skill (the analysis layer)

The companion analysis skill ships in [`skills/yandex-metrika-analytics/`](./skills/yandex-metrika-analytics/) — same repo, no second install step. It is a `SKILL.md` for [Hermes Agent](https://hermes-agent.nousresearch.com) that the agent loads on demand.

**What the skill does for the LLM:**

- Forces `list_counters` first — never guesses `counter_id`.
- Picks comparable periods (same duration, same weekday pattern, explicit dates over `days_back` when the user named a period).
- Decomposes changes by source / page / device / region / phrase.
- Checks quality: bounce rate, time on site, depth, and conversion rate. A traffic increase with a falling conversion rate indicates a quality problem, not a positive trend.
- Handles time-zone differences between the counter and the user (for example, Omsk UTC+6 vs. a Moscow-timezoned counter).
- Outputs in a consistent structure: a single-sentence finding, the supporting numbers, and concrete next steps.
- Adds a confidence label (high, medium, or low) and states the underlying assumptions.

**What the skill does NOT cover** (and what to use instead):

- Counter installation, GTM, event setup → use a generic `analytics` skill
- Pure technical SEO crawl without traffic metrics → use `seo-audit` / `technical-seo-checker`
- Paid ads account optimization with no site analytics involved → use a `ppc` skill
- GA4 / Mixpanel / Segment — this is Yandex Metrika only

**Install after the MCP:**

```bash
# If you installed from PyPI / uv, the skill is not bundled — copy it manually:
git clone https://github.com/ShalomGH/yandex-metrika-mcp.git
cp yandex-metrika-mcp/skills/yandex-metrika-analytics/SKILL.md \
   ~/.hermes/skills/marketing/yandex-metrika-analytics/SKILL.md
# restart the agent session — the skill auto-loads
```

If you installed from a local clone (`pip install -e .` from this repo), the skill file is already in the right place to symlink or copy.

The skill declares `metadata.hermes.requires_mcp: yandex-metrika` in its frontmatter — Hermes will warn if the MCP is missing and the skill is loaded.

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

## How the two layers fit together

```
┌─────────────────────────────────────────────────────────────┐
│  User: "What happened with traffic this week?"              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Companion skill (skills/yandex-metrika-analytics/SKILL.md) │
│  • list_counters → pick counter                             │
│  • compare_periods → week-over-week delta                   │
│  • get_report (sources) → find the contributor              │
│  • get_report (quality) → bounce, duration, conversion      │
│  • synthesize → Суть / Цифры / Что делать + confidence      │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MCP server (src/yandex_metrika_mcp/server.py)              │
│  • 12 read-only tools                                       │
│  • Authorization: OAuth <token>  (not Bearer — Yandex quirk)│
│  • 4 runtime deps, ~800 LOC, stdio JSON-RPC                 │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Yandex Metrika API → JSON → back up the stack              │
└─────────────────────────────────────────────────────────────┘
```

**Design rationale.** The MCP server contains no business logic. It is a thin and predictable API wrapper. The skill contains the analytical methodology and is loaded on demand by the agent. Keeping both in the same repository ensures version coupling: when a tool signature changes, the corresponding skill updates ship in the same commit.

## Security notes

- The server is read-only and does not expose write/edit Metrika endpoints.
- The OAuth token is read once from `YANDEX_METRIKA_TOKEN` during server startup.
- The token is not printed in logs or returned in tool responses.
- Do not commit `.env` or wrapper scripts containing real tokens.

## License

MIT
