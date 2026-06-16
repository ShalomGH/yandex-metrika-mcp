---
name: yandex-metrika-analytics
description: Use when analyzing Yandex Metrika website analytics via the yandex-metrika MCP server (list_counters, get_report, get_bytime, get_drilldown, compare_periods, list_goals, list_segments, list_filters, list_labels, list_accounts, get_counter, list_grants) and the user asks why traffic, conversions, SEO, sources, pages, campaigns, or business metrics changed, or asks for a weekly/monthly report, week-over-week comparison, or page-level diagnosis.
version: 0.1.0
author: ShalomGH
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [yandex-metrika, analytics, marketing, seo, traffic, conversions, mcp]
    related_skills: [analytics, seo-audit, performance-reporter]
    requires_mcp: yandex-metrika
---

# Yandex Metrika Analytics (ShalomGH/yandex-metrika-mcp)

## Overview

Skill for the `yandex-metrika` MCP server from
[ShalomGH/yandex-metrika-mcp](https://github.com/ShalomGH/yandex-metrika-mcp).
The MCP fetches data; this skill decides what to ask for, how to compare
it, how to avoid false conclusions, and how to present results in business
terms.

**Core rule: never declare success, failure, or root cause from one metric
alone.** Compare periods, decompose the change, check quality and
conversions, then give a confidence-rated conclusion.

## When to use

Use for any analytics answer backed by Yandex Metrika data fetched through
the MCP:

- "Что случилось с трафиком / конверсиями?"
- Traffic drop / growth diagnosis
- Weekly / monthly site health reports
- Source / channel quality analysis
- SEO organic: phrases, landing pages, branded vs non-branded
- Page prioritization: which URLs to improve first
- Conversion diagnosis by source / page / device
- Executive summaries
- "Compare this week vs last week", "Compare May vs April"

Do not use for:

- Installing counters, tags, events, GTM (use `analytics`)
- Full technical SEO crawl without metrics (use `seo-audit` /
  `technical-seo-checker`)
- Paid ads account optimization with no site analytics involved
- GA4 / Mixpanel / Segment — this skill is Yandex Metrika only

## Tool map

All tools are namespaced `mcp__yandex_metrika__*`. Prefer these over
generic HTTP calls. Tool groups:

**Discovery (always start here if `counter_id` is unknown):**

- `mcp_yandex_metrika_list_counters` — list counters visible to the token
- `mcp_yandex_metrika_get_counter` — full info for one counter
- `mcp_yandex_metrika_list_accounts` — top-level accounts
- `mcp_yandex_metrika_list_goals` — goals (conversions) of a counter
- `mcp_yandex_metrika_list_segments` — saved segments
- `mcp_yandex_metrika_list_filters` — saved filters
- `mcp_yandex_metrika_list_labels` — labels across account
- `mcp_yandex_metrika_list_grants` — access grants on a counter

**Analytics (reports):**

- `mcp_yandex_metrika_get_report` — arbitrary table: `metrics`,
  `dimensions`, `filters`, `sort`, `date1/date2` or `days_back`, `limit`,
  optional `preset`
- `mcp_yandex_metrika_get_bytime` — same as `get_report` but grouped
  `hour | day | week | month`. Use for time series and charts.
- `mcp_yandex_metrika_get_drilldown` — expand a row of a parent report
  (e.g. drill into `ym:s:startURL` for `ym:s:browser == "chrome"`)
- `mcp_yandex_metrika_compare_periods` — compare two periods, returns
  side-by-side totals + absolute and percent deltas per row

## Mandatory analysis pattern

For any non-trivial question:

1. **Define the question** — drop, growth, quality, SEO, pages,
   conversions, campaign, report.
2. **Resolve `counter_id`** with `list_counters` first. Do not guess.
3. **Pick comparable periods** — same duration; never compare a full
   week to a 3-day window. Avoid weekday-vs-weekend unless the user
   asked for it. For "this week vs last week" use `compare_periods` with
   `days_back` derived from current Omsk (UTC+6) date if no explicit
   dates are given.
4. **Choose metrics and dimensions** from the Yandex Metrika IDs (see
   reference list below). Use `ym:s:*` for session-level, `ym:pv:*` for
   pageview-level.
5. **Pull baseline** — total visits/users/pageviews for the period.
6. **Decompose** — by source, page, device, country, etc. Pick the cut
   that matches the question.
7. **Check quality** — bounce rate, avg visit duration, page depth, goal
   conversion rate. A traffic spike with collapsing conversion rate is
   a problem, not a win.
8. **Synthesize** — give a single confidence-rated answer (high /
   medium / low) with the supporting numbers. State assumptions.

## Common metric and dimension IDs

**Metrics (session-level, `ym:s:*`):**

- `ym:s:visits`, `ym:s:pageviews`, `ym:s:users`, `ym:s:newUsers`
- `ym:s:bounceRate`, `ym:s:avgVisitDurationSeconds`, `ym:s:pageDepth`
- `ym:s:goal<id>visits`, `ym:s:goal<id>conversions`,
  `ym:s:goal<id>conversionRate`
- `ym:s:sumParams`, `ym:s:manGoal<id>conversionRate`

**Dimensions:**

- `ym:s:date`, `ym:s:week`, `ym:s:month`
- `ym:s:lastTrafficSource`, `ym:s:lastSearchEngine`,
  `ym:s:lastSearchPhraseRoot`
- `ym:s:searchEngine`, `ym:s:searchPhrase`
- `ym:s:startURL`, `ym:s:endURL`, `ym:s:pageTitle`
- `ym:s:browser`, `ym:s:browserVersion`
- `ym:s:deviceCategory`, `ym:s:operatingSystemRoot`, `ym:s:mobilePhone`
- `ym:s:country`, `ym:s:city`, `ym:s:region`
- `ym:s:referer`, `ym:s:refererSource`

The full list is documented in the Yandex Metrika API reference; the MCP
accepts raw IDs, no alias mapping is done server-side.

## Common analysis recipes

### "Traffic dropped this week"

1. `compare_periods(counter_id, metrics="ym:s:visits,ym:s:users,ym:s:pageviews,ym:s:bounceRate", period1_date1, period1_date2, period2_date1, period2_date2)` — week vs week
2. If drop confirmed: `get_report(counter_id, metrics="ym:s:visits", dimensions="ym:s:lastTrafficSource", ...)` — find which source fell
3. Drill: `get_report` with `dimensions="ym:s:searchEngine"` or
   `ym:s:lastSearchPhraseRoot` for organic, `ym:s:refererSource` for
   external
4. Check page-level: `get_report` with `dimensions="ym:s:startURL"`
5. Check device: `dimensions="ym:s:deviceCategory"`
6. Optional drilldown: `get_drilldown` to see what a specific source /
   browser segment looks like at page level

### "Weekly executive report"

1. `list_counters` (confirm counter)
2. `get_bytime(counter_id, metrics="ym:s:visits,ym:s:users,ym:s:pageviews,ym:s:bounceRate,ym:s:avgVisitDurationSeconds", group="day", days_back=7)` — daily time series
3. `get_report` with `dimensions="ym:s:lastTrafficSource"` for share of
   traffic
4. `get_report` with `dimensions="ym:s:startURL"` top-10 by views
5. `get_report` with `dimensions="ym:s:searchPhrase"` (organic) top-10
6. For each goal in `list_goals`: pull `ym:s:goal<id>conversions` and
   `ym:s:goal<id>conversionRate` over the same period
7. Compose 3-block report: Суть / Цифры / Что делать

### "Compare two periods"

Always use `compare_periods` — it returns deltas in a single call and
saves a round trip. Pass both periods explicitly when the user gave
exact dates; use `days_back` only as a fallback.

### "Page-level SEO diagnosis"

1. `get_report` with `dimensions="ym:s:startURL",ym:s:searchEngine"`
   filtered to organic (`filters="ym:s:lastTrafficSource=='organic'"`)
2. Sort by `ym:s:visits` desc, `limit=50`
3. For each top landing page: `get_report` with
   `dimensions="ym:s:searchPhrase"`, filter by `ym:s:startURL=='<url>'`
4. Cross-check `ym:s:bounceRate` and `ym:s:pageDepth` per URL

## Pitfalls

- **Do not compare a full previous month to a partial current month**
  without flagging it. State the partial period explicitly in the
  answer.
- **Bounce rate near 0 is suspicious** — usually means the counter has
  no non-bounce events, not "great engagement".
- **Time-zone**: the server returns dates in the counter's configured
  timezone. Convert mentally to the user's context. For a user in
  Omsk (UTC+6) and a Moscow-timezoned counter, day boundaries differ
  by 3 hours — say so when it matters.
- **Yandex Metrika requires `Authorization: OAuth <token>`, not
  `Bearer`.** The MCP handles this internally; do not add a header
  override.
- **Tokens with no `metrika:read` scope return 403** even on
  `list_counters`. If `list_counters` is empty or 403, ask the user
  to verify the token, not to re-run the query.
- **`days_back` counts back from today (counter time), not from the
  user's "now"** — for "last 7 days" the endpoint covers the last 7
  full days plus a partial current day, not 7×24 hours.
- **Large `limit` values are slow.** For exploratory queries, use
  `limit=20-50` first; only raise it once you know the shape.
- **Never invent a metric or dimension name.** If unsure, run
  `get_report` with no `dimensions` and the default schema exposes
  what the counter supports, or use a known ID from the list above.

## Output format

For a substantive answer (drop, report, comparison) use three blocks:

- **Суть** — one sentence, the headline finding with confidence
- **Цифры** — 3-7 bullet points of the supporting numbers, with the
  period and source they came from
- **Что делать / Гипотезы** — concrete next checks or actions

For a quick lookup (one number, one page) just give the number with
the period and counter.

## Required environment

- MCP server `yandex-metrika` installed and enabled
  (`hermes mcp list` should show it as `✓ enabled`)
- `YANDEX_METRIKA_TOKEN` set in `~/.hermes/.env` with `metrika:read`
  scope
- At least one counter visible to the token (verify with
  `mcp_yandex_metrika_list_counters`)
