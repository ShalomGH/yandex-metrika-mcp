# yandex-metrika-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![MCP server](https://img.shields.io/badge/MCP-server-0ea5e9)](https://modelcontextprotocol.io)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)
[![Tools: 12](https://img.shields.io/badge/tools-12-success)](./src/yandex_metrika_mcp/server.py)
[![Runtime deps: 4](https://img.shields.io/badge/runtime_deps-4-success)](./pyproject.toml)
[![Companion skill](https://img.shields.io/badge/Hermes-skill-7c3aed)](./skills/yandex-metrika-analytics/SKILL.md)

> **Languages**: [English](./README.md) · [Русский](./README.ru.md)
>
> **What this repo gives you**: a Yandex Metrika MCP server (data layer) **plus** a companion Hermes skill (analysis layer) — install both and an LLM agent becomes a Metrika analyst, not a Metrika data pipe.

## What's in the box

This repository ships two pieces that work together. Neither is useful on its own.

| Layer | What it is | Where |
|---|---|---|
| **MCP server** (`yandex-metrika`) | Speaks MCP over stdio, calls Yandex Metrika's official API with the correct `Authorization: OAuth <token>` header, returns raw JSON. 12 read-only tools, 4 runtime dependencies, no write access. | [`src/yandex_metrika_mcp/`](./src/yandex_metrika_mcp/) |
| **Companion skill** (`yandex-metrika-analytics`) | A `SKILL.md` for [Hermes Agent](https://hermes-agent.nousresearch.com) that tells the LLM which tool to call in which order, how to compare periods, how to decompose a change into source / page / device, and how to present the answer in business terms (Суть / Цифры / Что делать). | [`skills/yandex-metrika-analytics/`](./skills/yandex-metrika-analytics/SKILL.md) |

**MCP without the skill** = 12 raw tools that an LLM has to learn on the fly, often producing bad outputs (e.g. comparing a full month to a partial one, declaring "SEO is bad" from a single number).
**Skill without the MCP** = a methodology doc with no data behind it.
**Both together** = a marketing analyst that reads Metrika.

## What you can ask an agent with both installed

These are real question patterns the skill is designed to answer confidently:

- *"What happened with traffic on weltall.energy this week vs last week?"*
- *"Conversions on the main goal fell 30% — find the culprit: source, page, or device?"*
- *"Weekly executive report, format: Summary / Numbers / Next steps."*
- *"Top 10 organic landing pages, with bounce rate and depth breakdown."*
- *"Compare May vs June organic traffic, split by search engine."*
- *"Blog SEO audit: which pages are losing positions and why?"*
- *"Quality check: my traffic is up — is it real growth or bot/referral-spam?"*

The skill enforces a single rule across all of them: **never conclude from one metric**. It always pulls a comparable baseline, decomposes the change, checks quality, and gives a confidence label (high / medium / low).

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
- Checks quality: bounce rate, time on site, depth, **conversion rate** — a traffic spike with collapsing CR is a problem, not a win.
- Calls out time-zone quirks (counter timezone vs. user timezone, e.g. Omsk UTC+6 vs. Moscow).
- Outputs in a consistent structure: **Суть** (one-sentence finding) / **Цифры** (supporting numbers) / **Что делать** (concrete next checks).
- Adds a confidence label (high / medium / low) and states assumptions.

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

**Why a separate skill, not a smarter server.** The server has no business logic — it's a thin, predictable API wrapper. The skill carries the methodology and lives with the agent (Hermes loads it on demand). Same repo keeps the version coupling honest: when a tool signature changes, the skill can be updated in the same commit.

## Security notes

- The server is read-only and does not expose write/edit Metrika endpoints.
- The OAuth token is read once from `YANDEX_METRIKA_TOKEN` during server startup.
- The token is not printed in logs or returned in tool responses.
- Do not commit `.env` or wrapper scripts containing real tokens.

## License

MIT
