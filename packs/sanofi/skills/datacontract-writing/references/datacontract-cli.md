# datacontract-cli

Optional cross-check with the open-source [Data Contract CLI](https://docs.datacontract.com) (`datacontract`). It validates ODCS and can import, diff, and test contracts. The bundled `validate_odcs.py` stays the primary validator; the CLI is a second opinion or a source of drafts.

Verified against datacontract-cli 1.2.4 (2026-10-06). Run `datacontract --version` and `datacontract <command> --help` first; flags change between releases.

## Install and Run

| Need | Command (bash, zsh, PowerShell) |
|------|---------------------------------|
| Run once (lint, diff, DDL/dbt import) | `uvx --from datacontract-cli datacontract lint FILE` |
| Run once with Snowflake import/test | `uvx --from "datacontract-cli[snowflake]" datacontract import snowflake ...` |
| Install for repeated use | `uv tool install "datacontract-cli[snowflake]"`, then plain `datacontract ...` |

The command tables below show plain `datacontract`; prefix `uvx --from "datacontract-cli[snowflake]"` unless the tool is installed. NEVER `pip install` it. No `uv`? Report the CLI check as not run; NEVER claim it passed.

## Commands for This Skill

| Goal | Command | Notes |
|------|---------|-------|
| Validate structure | `datacontract lint FILE --all-errors --no-inline-references` | Validates against the schema for the contract's declared `apiVersion` (CLI 1.2.1+). Exit 1 = invalid. `--all-errors` reports every error instead of the first. `--no-inline-references` stops it fetching `authoritativeDefinitions` URLs |
| Pin schema | `datacontract lint FILE --json-schema PATH_OR_URL` | Same flag as `validate_odcs.py --schema` |
| Compare versions | `datacontract changelog OLD NEW` | Lists changed fields |
| Gate a release | `datacontract breaking OLD NEW` | Fails on backward-incompatible change (incl. `quality` rules); run before bumping a `version` major |
| Schema-only test | `datacontract test FILE --server NAME --metadata-only` | Reads the catalog only: field presence and types, no row values |
| Plan without connecting | `datacontract test FILE --dry-run` | Lists checks; no connection, no data |
| Draft from live schema | `datacontract import snowflake --source ORG-ACCOUNT --database DB --schema SCHEMA --output draft.odcs.yaml` | Reads `INFORMATION_SCHEMA.COLUMNS`; also writes a `servers` block |
| Draft from dbt | `datacontract import dbt --source target/manifest.json --model orders --output draft.odcs.yaml` | Keeps column `meta`: `classification` maps to `classification`, other keys to a `meta` custom property |
| Draft from DDL | `datacontract import sql --source ddl.sql --dialect snowflake --output draft.odcs.yaml` | Warns about statements it skips |

## Rules

- Plain `datacontract test` (no `--metadata-only`) reads row values for quality, null, and duplicate checks. The Snowflake metadata-only rule in [SKILL.md](../SKILL.md) applies: NEVER run it unless the user explicitly asks for a data test and supplies credentials.
- NEVER invent or print credentials. Snowflake auth comes from the user's environment: `DATACONTRACT_SNOWFLAKE_USERNAME`, `_PASSWORD`, `_WAREHOUSE`, `_ROLE`; key-pair via `_PRIVATE_KEY_FILE` and `_PRIVATE_KEY_FILE_PWD`; `_AUTHENTICATOR` for SSO/MFA. Without a password, `import snowflake` opens a browser SSO login.
- Set variables per shell: POSIX `export DATACONTRACT_SNOWFLAKE_ROLE=ROLE`; PowerShell `$env:DATACONTRACT_SNOWFLAKE_ROLE = "ROLE"`.
- Snowflake `--source` is `<orgname>-<accountname>`, without `.snowflakecomputing.com`. `250001: Could not connect` usually means a wrong identifier.
- Treat every `import` output as a draft. Never write it straight into `datacontracts/`. Reconcile it with this skill's rules:

| CLI import behavior | Skill rule |
|---------------------|------------|
| Draft declares `apiVersion: v3.2.0` (observed on `import sql`, 1.2.4) | Change to `v3.1.0` unless the user wants v3.2.0 |
| Snowflake import: `NUMBER` (incl. `INT`, `BIGINT`) → `number`; precision and scale go to custom properties | Zero-scale `NUMBER` → `integer` ([full-guide.md](full-guide.md#snowflake)) |
| Snowflake import: `VARIANT`, `OBJECT`, `GEOGRAPHY`, `GEOMETRY` leave `logicalType` unset | Map to `object` per the same table |
| Snowflake import: `unique` derived from `IS_IDENTITY` | `unique: true` only from a real UNIQUE/PK constraint |
| SQL import rewrites `NUMBER(38,0)` to `physicalType: DECIMAL(38, 0)` | Keep `physicalType` exactly as in the source DDL |
| Placeholder `id: my-data-contract`, `name: My Data Contract`, `my_host`/`my_database`/`my_schema` server values (observed on `import sql`) | Generate a UUID v4 `id`; take server values from the user; apply [Sanofi policy](odcs-template.md#standard-vs-sanofi-policy) (`tenant`, `domain`, `dataProduct`) |

- The CLI's bundled v3.1.0 schema is older than the v3.2.0-tag schema: nested `id` values with `:` (for example `urn:uuid:...`) fail CLI lint but pass `validate_odcs.py`. Use `[A-Za-z0-9_-]` ids.
- Put an `id` on quality rules if the user will filter with `datacontract test --quality-id`.
- dbt exports (`export dbt-models`, `dbt sync`) nest generic-test parameters under `arguments:` and require dbt 1.10+. Check the project's dbt version before suggesting them; see the `dbt` skill for model authoring.

## Sources

- [datacontract-cli README](https://github.com/datacontract/datacontract-cli/blob/main/README.md)
- [datacontract-cli release notes](https://github.com/datacontract/datacontract-cli/releases) (1.2.0 adds ODCS v3.2.0; 1.2.1 lints by declared `apiVersion`; 1.2.3 requires dbt 1.10+ for dbt exports)
- [Commands](https://docs.datacontract.com/commands), [lint](https://docs.datacontract.com/commands/lint.md), [test](https://docs.datacontract.com/commands/test.md), [breaking](https://docs.datacontract.com/commands/breaking.md)
- [Test Snowflake](https://docs.datacontract.com/testing/snowflake.md) and [Snowflake reference](https://docs.datacontract.com/reference/snowflake) (env vars, import type mapping)
- [Import: dbt](https://docs.datacontract.com/imports/dbt.md)
- [ODCS in the CLI](https://docs.datacontract.com/open-data-contract-standard.md)
