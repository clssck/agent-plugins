---
name: datacontract-writing
description: "Write, review, lint, diff, and import ODCS (Open Data Contract Standard) data contracts. Use when producing `.odcs.yaml` from dbt projects, Snowflake schemas, SQL DDL, spreadsheets, or pasted column lists; validating apiVersion v3.1.0/v3.2.0; running `datacontract` CLI lint, breaking, or import. Not for OpenAPI specs, ADRs, or architecture docs; dbt model authoring → `dbt` skill."
---

# Data Contract Writing

Write, review, lint, or diff Open Data Contract Standard YAML from dbt projects, Snowflake metadata, SQL DDL, or pasted schemas. Default `apiVersion: v3.1.0`; v3.2.0 only when the user or the consuming tool asks. Contracts MUST validate against the official JSON schema for their declared `apiVersion`, and that schema forbids extra fields, so version discipline decides validity.

Governing principle: source metadata is the only authority. A contract that guesses owners, types, or thresholds is worse than one with `# REVIEW:` gaps, because consumers trust it. Out of scope: OpenAPI specs, ADRs, and architecture docs. dbt model authoring belongs to the `dbt` skill.

## References

| File | Read for |
|------|----------|
| [odcs-template.md](references/odcs-template.md) | Minimal and full YAML, field tables, ODCS vs Sanofi policy, v3.2.0 delta |
| [full-guide.md](references/full-guide.md) | Naming, type mappings, quality patterns, rules, troubleshooting |
| [source-parsing.md](references/source-parsing.md) | dbt, Snowflake (`snow` CLI), SQL DDL extraction |
| [datacontract-cli.md](references/datacontract-cli.md) | `datacontract` CLI: lint, diff, import drafts, tests; import output fixes |

## Workflow

1. **Identify the source of truth:** a dbt project, Snowflake schema, DDL, spreadsheet, or pasted schema.
2. **Extract** identity, columns, types, nullability, keys, and descriptions. Use `glob`/`grep`/`read` for files and `bash` for `snow`.
3. **Map types and constraints** per [source-parsing.md](references/source-parsing.md).
4. **Add quality rules** only with source evidence or a user request.
5. **Mark uncertain values** `# REVIEW:`. NEVER invent meaning.
6. **Write** one `datacontracts/{name}.odcs.yaml` with `write`, unless the task is review-only.
7. **Validate** (below) and report the result.

## Authoring rules

- **Precedence:** source metadata beats inferred names or examples.
- **No fabrication:** NEVER fabricate owners, SLAs, thresholds, or types.
- **Schema-exact:** NEVER emit fields outside the declared `apiVersion` schema. v3.2.0-only fields (`enum`, `map`, `vector`, `synonyms`, `context`, ...) fail under v3.1.0.
- **Version:** NEVER bump `apiVersion` to v3.2.0 unprompted. Imported drafts may already declare v3.2.0, so check them.
- **Unknown column type:** omit `logicalType`/`physicalType` and flag it.
- **Composite keys:** use `primaryKeyPosition` plus schema-level rules, NEVER per-column rules.
- **Policy vs standard:** keep Sanofi policy defaults separate from ODCS validity.
- **Definitions:** keep business definitions apart from technical descriptions.
- **Naming:** preserve source-system names unless asked to normalize.
- **Snowflake:** metadata queries only. NEVER read data rows; this includes `datacontract test` without `--metadata-only`.
- **Nested `id` values:** use `[A-Za-z0-9_-]` only. Colons fail the CLI's v3.1.0 lint ([odcs-template.md](references/odcs-template.md#v320-delta)).

## Validation

```bash
uv run "$(realpath skill://datacontract-writing/scripts/validate_odcs.py)" datacontracts/my-schema.odcs.yaml
```

`uv run` reads the script's inline dependencies (`jsonschema`, `pyyaml`) into an isolated environment. NEVER `pip install` them. The script fetches the schema for the contract's `apiVersion` (v3.1.0 or v3.2.0) over the network; `--schema <file>` forces a specific schema and also works offline.

| Exit | Meaning |
|------|---------|
| 0 | valid |
| 1 | invalid |
| 2 | validator unavailable (no network, unreadable input) |

- **No `uv`, or exit 2:** say validation did not run. NEVER claim the contract is valid.
- **Second opinion (optional):** `uvx --from datacontract-cli datacontract lint FILE --all-errors --no-inline-references` ([datacontract-cli.md](references/datacontract-cli.md)).
- **Changing an existing contract:** run `datacontract breaking OLD NEW` the same way, and report the result before bumping `version`.

## Before reporting

Check the artifact against each of these before handing it back:

| Check | Requirement |
|-------|-------------|
| Validator | exit 0, or unavailability reported |
| Root | has `apiVersion`, `kind`, `id`, `version`, `status` |
| Forbidden fields | no `isPrimaryKey`, `isNullable`, `isUnique`, `serviceLevel`, `links`, `slaDefaultElement`, root `classification`/`quality` |
| Version fit | fields match the declared `apiVersion`; no v3.2.0 fields under v3.1.0 |
| Team | uses `team.members[].username` |
| Quality | args use `validValues`; composite keys use `arguments.properties` |
| Descriptions | present; unknowns flagged `# REVIEW:` |
| Imported drafts | reconciled: `id`, `apiVersion`, `physicalType`, server placeholders |
| Placeholders | no placeholder text or invented values |
