# yandex-metrika-mcp

Read-only MCP server for Yandex Metrika.

A small, dependency-minimal stdio MCP wrapper around the official Yandex Metrika API. It exposes a compact set of analytics tools suitable for Hermes Agent, Claude Desktop, Cursor, Cline, and other MCP clients.

## Features

- Lists available Metrika counters.
- Returns visits/pageviews/users/bounce-rate/duration summaries.
- Shows traffic sources, top pages, organic search phrases, and visits over time.
- Compares the latest period with the previous period.
- Uses raw `httpx` calls to Yandex API — no third-party Metrika wrappers.
- Read-only by design.

## Tools

- `list_counters` — list all counters available to the token.
- `get_visits_summary` — visits, pageviews, users, bounce rate, average visit duration.
- `get_traffic_sources` — top traffic sources by visits.
- `get_top_pages` — top pages by pageviews.
- `get_search_phrases` — organic search phrases by visits.
- `get_visits_by_time` — visits grouped by `hour`, `day`, `week`, or `month`.
- `compare_periods` — compare the latest period with the previous period.

## Requirements

- Python 3.10+
- Yandex OAuth token with Metrika read access (`metrika:read`)

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

Yandex Metrika expects the HTTP header format `Authorization: OAuth <token>`. The server constructs that header internally; pass only the raw token in the environment variable.

## Run

```bash
yandex-metrika-mcp
```

The server speaks MCP over stdio. Logs go to stderr; stdout is reserved for JSON-RPC.

## Hermes Agent setup

Recommended: use a wrapper script so the token stays outside the MCP config.

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

## Smoke test

The smoke test starts the MCP server over stdio, performs `initialize`, `tools/list`, and calls `list_counters` with a fake token. A structured Yandex `invalid_token` response is expected; a Python crash is not.

```bash
PYTHONPATH=src python tests/smoke_mcp.py
```

Expected output includes:

```text
✅ initialize
✅ tools/list: 7 tools
✅ tools/call list_counters (fake token): { "error": "[403] ... invalid_token ..." }
```

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
python -m compileall src tests
PYTHONPATH=src python tests/smoke_mcp.py
```

## Security notes

- The server is read-only and does not expose write/edit Metrika endpoints.
- The OAuth token is read once from `YANDEX_METRIKA_TOKEN` during server startup.
- The token is not printed in logs or returned in tool responses.
- Do not commit `.env` or wrapper scripts containing real tokens.

## License

MIT
