---
name: datacontract-writing
description: Write or review ODCS data contracts (v3.1.0 default, v3.2.0 on request) from dbt projects, Snowflake metadata, SQL DDL, or documented schemas. Use when asked to write a data contract, document a dataset schema, generate or lint an ODCS YAML, or diff contract versions. Not for OpenAPI contracts, general documentation, or dbt model authoring (use the dbt skill).
---

# Data Contract Writing

Produce Open Data Contract Standard YAML. Default `apiVersion: v3.1.0`; use v3.2.0 only when the user or the consuming tool asks. Contracts MUST validate against the official JSON schema for their declared `apiVersion`.

## References

| File | Read for |
|------|----------|
| [odcs-template.md](references/odcs-template.md) | Minimal and full YAML, field tables, ODCS vs Sanofi policy, v3.2.0 delta |
| [full-guide.md](references/full-guide.md) | Naming, type mappings, quality patterns, rules, troubleshooting |
| [source-parsing.md](references/source-parsing.md) | dbt, Snowflake (`snow` CLI), SQL DDL extraction |
| [datacontract-cli.md](references/datacontract-cli.md) | `datacontract` CLI: lint, diff, import drafts, tests; import output fixes |

## Workflow

1. Identify source of truth: dbt project, Snowflake schema, DDL, spreadsheet, pasted schema.
2. Extract identity, columns, types, nullability, keys, descriptions. Use `glob`/`grep`/`read` for files, `bash` for `snow`.
3. Map types and constraints per [source-parsing.md](references/source-parsing.md).
4. Add quality rules only with source evidence or user request.
5. Mark uncertain values `# REVIEW:`; NEVER invent meaning.
6. `write` one `datacontracts/{name}.odcs.yaml`, unless review-only.
7. Validate (below). Report the result.

## Rules

- Source metadata beats inferred names or examples.
- NEVER fabricate owners, SLAs, thresholds, or types.
- NEVER emit fields outside the declared `apiVersion` schema; it forbids extras. v3.2.0-only fields (`enum`, `map`, `vector`, `synonyms`, `context`, ...) under v3.1.0 fail.
- NEVER bump `apiVersion` to v3.2.0 unprompted; imported drafts may already say v3.2.0, so check.
- Unknown column type? Omit `logicalType`/`physicalType`; flag it.
- Composite keys → `primaryKeyPosition` + schema-level rules, NEVER per-column.
- Keep Sanofi policy defaults separate from ODCS validity.
- Business definitions stay apart from technical descriptions.
- Preserve source-system names unless asked to normalize.
- Snowflake: metadata queries only; NEVER read data rows. This includes `datacontract test` without `--metadata-only`.
- Prefer `[A-Za-z0-9_-]` for nested `id` values; colons pass the v3.2.0-tag schema but fail the CLI's bundled one.

## Validation

```bash
uv run --no-project --with jsonschema --with pyyaml python3 skill://datacontract-writing/scripts/validate_odcs.py datacontracts/my-schema.odcs.yaml
```

No `uv`? Run it with `python3` from a venv that has `jsonschema` and `pyyaml`; NEVER `pip install` into the system Python (PEP 668). Needs network access. It picks the schema from the contract's `apiVersion` (v3.1.0 or v3.2.0; `--schema <file>` forces one, also for offline use). Exit 0 = valid, 1 = invalid, 2 = validator unavailable.

Exit 2? Say validation did not run; NEVER claim the contract is valid. Optional second opinion: `datacontract lint FILE --all-errors --no-inline-references` ([datacontract-cli.md](references/datacontract-cli.md)). Changing an existing contract? Run `datacontract breaking OLD NEW` and report the result before bumping `version`.

## Checklist

- Validator exit 0, or unavailability reported.
- Root has `apiVersion`, `kind`, `id`, `version`, `status`.
- No `isPrimaryKey`, `isNullable`, `isUnique`, `serviceLevel`, `links`, `slaDefaultElement`, root `classification`/`quality`.
- Fields match the declared `apiVersion`; no v3.2.0 fields under v3.1.0.
- Team uses `team.members[].username`.
- Quality args use `validValues`; composite keys use `arguments.properties`.
- Descriptions present; unknowns flagged `# REVIEW:`.
- Imported drafts reconciled: `id`, `apiVersion`, `physicalType`, server placeholders.
- No placeholder text or invented values.
