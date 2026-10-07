---
name: snowpipe-streaming
description: "**[REQUIRED]** Use for ALL Snowpipe Streaming tasks: setup, configure, troubleshoot, monitor, optimize, or migrate streaming pipelines. Covers the High-Performance Architecture exclusively. Triggers: snowpipe streaming, streaming ingestion, low-latency ingestion, real-time ingestion, Snowpipe Streaming SDK, channel, insertRows, appendRows, streaming channel, PIPE object, streaming pipe, snowpipe v2, high-performance streaming, migrate classic streaming, troubleshoot streaming."
---

# Snowpipe Streaming (High-Performance Architecture)

Guides users through setting up, troubleshooting, monitoring, optimizing, and migrating Snowpipe Streaming pipelines using the High-Performance Architecture.

## Important Context

- **Only the High-Performance Architecture** — classic is planned for deprecation mid-2026
- **Python SDK** (`snowpipe-streaming` PyPI package) is the primary SDK; Java SDK is an alternative
- The High-Performance Architecture uses **PIPE objects** — channels open against pipes, not directly against tables
- Default pipe naming: `<TABLE_NAME>-STREAMING` (auto-created on first use)
- **Schema evolution**: Default pipes automatically adapt to source schema changes (new columns added automatically). Schematization via Kafka Connect is optional, not required.
- Key-pair authentication is required for SDK access

## Intent Detection

| Intent | Triggers | Route |
|--------|----------|-------|
| **SETUP** | "set up", "create", "configure", "new pipeline", "get started", "quickstart" | `setup/SKILL.md` |
| **TROUBLESHOOT** | "debug", "fix", "error", "failing", "not working", "troubleshoot", "channel error", "offset gap" | `troubleshoot/SKILL.md` |
| **MONITOR** | "monitor", "status", "check", "health", "dashboard", "channel status", "costs", "billing" | `monitor/SKILL.md` |
| **OPTIMIZE** | "optimize", "improve", "throughput", "latency", "performance", "cost reduction", "tune" | `optimize/SKILL.md` |
| **MIGRATE** | "migrate", "upgrade", "classic to v2", "move from classic", "switch SDK", "deprecation", "high-performance" | `migrate/SKILL.md` |

## Workflow

```
User Request
  ↓
Detect Intent (see table above)
  ↓
  ├─→ SETUP    → Load setup/SKILL.md
  ├─→ TROUBLESHOOT → Load troubleshoot/SKILL.md
  ├─→ MONITOR  → Load monitor/SKILL.md
  ├─→ OPTIMIZE → Load optimize/SKILL.md
  └─→ MIGRATE  → Load migrate/SKILL.md
```

If intent is ambiguous, ask the user:

```
What would you like to do with Snowpipe Streaming?

1. Set up a new pipeline
2. Troubleshoot an existing pipeline
3. Monitor pipeline health & costs
4. Optimize performance or costs
5. Migrate from classic to High-Performance Architecture
```

## Tools

### Script: health_check.py

**Description**: Checks pipeline health — channel status, offset progress, row errors, ingestion gaps. Auto-detects timestamp column or accepts `--timestamp-column` override.

**Usage:**
```bash
# Via uv run
uv run --project <SKILL_DIR>/scripts python <SKILL_DIR>/scripts/health_check.py \
  --database <DB> --schema <SCHEMA> --table <TABLE> \
  --connection <CONNECTION_NAME>

# Or install and use CLI entry point
cd <SKILL_DIR>/scripts && uv pip install -e .
ss-health-check --database <DB> --schema <SCHEMA> --table <TABLE>
```

### Script: stream_demo.py

**Description**: End-to-end demo — creates table, opens channel, streams sample rows, verifies ingestion.

**Usage:**
```bash
# Via uv run
uv run --project <SKILL_DIR>/scripts python <SKILL_DIR>/scripts/stream_demo.py \
  --database <DB> --schema <SCHEMA> --table <TABLE> \
  --private-key-path <KEY_PATH> --account <ACCOUNT> --user <USER>

# Or install and use CLI entry point
ss-demo --database <DB> --schema <SCHEMA> --table <TABLE> \
  --private-key-path <KEY_PATH> --account <ACCOUNT> --user <USER>
```

## References

### SDK Code Samples

**Load** the relevant file based on the user's integration method:
- `references/python-sdk.md` — Python SDK (minimal, production service, FastAPI, offset tracking)
- `references/java-sdk.md` — Java SDK (minimal, batch, self-healing)
- `references/rest-api.md` — REST API (JWT auth, append rows, compression)
- `references/kafka-connect.md` — Kafka Connect (basic, schematized, Iceberg, Docker Compose)
- `references/common-patterns.md` — Profile JSON, key-pair generation, VARIANT best practices

### Monitoring Queries

**Load** `references/monitoring-queries.md` for SQL queries covering channel health, throughput, offset gaps, and cost analysis.

## Key Documentation Links

- [Snowpipe Streaming Overview](https://docs.snowflake.com/en/user-guide/snowpipe-streaming/data-load-snowpipe-streaming-overview)
- [High-Performance Architecture](https://docs.snowflake.com/en/user-guide/snowpipe-streaming/snowpipe-streaming-high-performance-overview)
- [Python SDK Reference](https://docs.snowflake.com/en/user-guide/snowpipe-streaming-sdk-python/reference/latest/index)
- [Best Practices](https://docs.snowflake.com/en/user-guide/snowpipe-streaming/snowpipe-streaming-high-performance-best-practices)
- [Getting Started Tutorial](https://docs.snowflake.com/en/user-guide/snowpipe-streaming/snowpipe-streaming-high-performance-getting-started)
