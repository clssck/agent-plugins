---
name: openflow-observability-connector-postgresql-sql-managed
description: Authoritative property-value catalog for the SQL-managed OPENFLOW_POSTGRES_CDC connector. Use when proposing connector.config_set_property action edits or interpreting validation errors that mention specific property values.
---

# PostgreSQL CDC -- SQL-Managed Property Catalog

This file is the authoritative reference for valid property values in the SQL-managed `OPENFLOW_POSTGRES_CDC` connector definition (the connector created via `CREATE OPENFLOW CONNECTOR ... FROM DEFINITION OPENFLOW_POSTGRES_CDC`).

**This file is for SQL-managed (gen-2) connector edits only.** The gen-1 PostgreSQL CDC connector, configured through Apache NiFi parameter contexts, uses different property names and a different config shape. For that connector, see [postgresql.md](postgresql.md).

**Source of truth:** the enum classes under `runtime-extensions/runtime-connector-bundles/runtime-postgres-connector-bundle/runtime-postgres-connector/src/main/java/com/snowflake/openflow/runtime/connectors/postgres/properties/`. The connector validator accepts the value returned by each enum's `DescribedValue.getValue()` method. By default this is the Java enum constant name (`name()`), but enum classes that declare a 3-arg constructor override `getValue()` to return a custom string -- typically the display label, including spaces. **Use the table below as the authoritative form for each property; do not infer the form from the enum constant name alone.** When in doubt, the validation error message `Value is not one of the allowable values` typically lists the actual valid values in subsequent log lines.

---

## Critical pitfall: enum value vs display label

Each enum-typed property has exactly one form the validator accepts -- in some cases the Java enum constant name (e.g. `CASE_INSENSITIVE`), in others a display-label string with spaces (e.g. `"Set Null"`). Mixing the two is the most common cause of `Value is not one of the allowable values` validation errors after a SQL-managed config edit. The table below is authoritative; **always look up the property here before writing a value into `config.json`.**

| Property | Accepted value (config.json) | Common wrong value (will fail validation) |
| --- | --- | --- |
| `Object Identifier Resolution` | `CASE_INSENSITIVE` / `CASE_SENSITIVE` | "Case Insensitive" / "Case Sensitive" |
| `Oversized Value Strategy` | **`"Set Null"`** / **`"Fail Table"`** (with the space -- the enum overrides `getValue()` to return the display label) | `SET_NULL` / `FAIL_TABLE` |
| `Snowflake Authentication Strategy` | `SNOWFLAKE_MANAGED` / `KEY_PAIR` | "Snowflake Managed Token" / "Key Pair" |
| `Snowflake Connection Strategy` | `STANDARD` / `PRIVATE_CONNECTIVITY` | "Standard" / "Private Connectivity" |
| `Snapshot Promotion Strategy` | `INSERT_OVERWRITE` / `SWAP` | "Insert Overwrite" / "Swap" |
| `Table Storage Format` | `STANDARD` / `ICEBERG` | "Standard" / "Iceberg" |
| `Ingestion Type` | `full` / `incremental` (lowercase) | "Full" / "Incremental" |

> **Why these forms differ.** Each enum class implements `DescribedValue.getValue()`. The default implementation (used by 2-arg constructors that take only `displayName, description`) returns the Java enum constant name -- so `ObjectIdentifierResolution.CASE_INSENSITIVE` serializes as `CASE_INSENSITIVE`. Some enums declare a 3-arg constructor that overrides `getValue()` to return a custom string -- e.g. `OversizedValueStrategy.SET_NULL("Set Null", "Set Null", "...")` serializes as `"Set Null"`. The catalog table above is the authoritative form for each property. When in doubt, read the enum source under `runtime-postgres-connector-bundle/.../properties/<EnumName>.java` and look at what `getValue()` returns. The validation error message `Value is not one of the allowable values` typically lists the actual valid values in subsequent log lines.

**When the customer's symptom is a `Value is not one of the allowable values` validation error in the event table or canvas bulletin**, the first hypothesis to check is whether their `config.json` value matches the enum form in this table.

---

## Full property catalog

### Source step

| Property | `valueType` | Required | Validator |
| --- | --- | --- | --- |
| `Source Database User` | `STRING_LITERAL` | yes | non-empty |
| `Source Database Password` | `SECRET_REFERENCE` | yes | non-empty fully-qualified secret name |
| `Source Database Connection URL` | `STRING_LITERAL` | yes | non-empty; postgres JDBC URL form `jdbc:postgresql://<host>:<port>/<db>?<params>` |
| `Source Database Driver` | `ASSET_REFERENCE` | yes | non-empty asset id list |
| `Source Database Publication Name` | `STRING_LITERAL` | yes | non-empty |

### Replication table schema step

| Property | `valueType` | Required | Notes |
| --- | --- | --- | --- |
| `Included Comma Separated Source Table Names` | `STRING_LITERAL` | one of these two | format `<schema>.<table>,<schema>.<table>` |
| `Included Source Table Pattern` | `STRING_LITERAL` | one of these two | regex pattern, e.g. `public\..*` |

### Replication columns step

| Property | `valueType` | Required | Notes |
| --- | --- | --- | --- |
| `Column Filter JSON` | `STRING_LITERAL` | yes | JSON array, default `"[]"` |

### Destination authentication step

| Property | `valueType` | Required | Allowed values |
| --- | --- | --- | --- |
| `Snowflake Authentication Strategy` | `STRING_LITERAL` | yes | `SNOWFLAKE_MANAGED`, `KEY_PAIR` |
| `Snowflake Username` | `STRING_LITERAL` | yes when `KEY_PAIR` | non-empty |
| `Snowflake Role` | `STRING_LITERAL` | yes when `KEY_PAIR` | non-empty |
| `Snowflake Account Identifier` | `STRING_LITERAL` | yes when `KEY_PAIR` | non-empty |
| `Snowflake Connection Strategy` | `STRING_LITERAL` | yes when `KEY_PAIR` | `STANDARD`, `PRIVATE_CONNECTIVITY` |
| `Snowflake Private Key` | `SECRET_REFERENCE` | yes when `KEY_PAIR` | non-empty fully-qualified secret name |

When `Snowflake Authentication Strategy` = `SNOWFLAKE_MANAGED`, the auth-side fields are derived from the runtime's identity and may be left null in `config.json`. Do not propose `KEY_PAIR` switches without explicit customer direction.

### Destination details step

| Property | `valueType` | Required | Allowed values |
| --- | --- | --- | --- |
| `Snowflake Destination Database` | `STRING_LITERAL` | yes | non-empty |
| `Snowflake Warehouse` | `STRING_LITERAL` | yes | non-empty |
| `Object Identifier Resolution` | `STRING_LITERAL` | yes | `CASE_INSENSITIVE`, `CASE_SENSITIVE` |
| `Oversized Value Strategy` | `STRING_LITERAL` | yes | `"Set Null"`, `"Fail Table"` (with the space -- see "Critical pitfall: enum value vs display label" above) |
| `Table Storage Format` | `STRING_LITERAL` | yes | `STANDARD`, `ICEBERG` |

### Tuning step

| Property | `valueType` | Required | Notes |
| --- | --- | --- | --- |
| `Concurrent Snapshot Queries` | `STRING_LITERAL` | yes | integer as string, default `"2"` |
| `Merge Task Schedule CRON` | `STRING_LITERAL` | yes | Quartz CRON, default `"* * * * * ?"` |

### Migration step

| Property | `valueType` | Required | Notes |
| --- | --- | --- | --- |
| `Ingestion Type` | `STRING_LITERAL` | yes | `full`, `incremental` |
| `Replication Slot Name` | `STRING_LITERAL` | optional | Auto-generated when null. Set explicitly only for slot-reuse / break-glass cases. |

---

## SECRET_REFERENCE diagnostic checklist

When a `SECRET_REFERENCE` property fails to resolve, the connector typically reports it as a downstream processor validation error like `'Password' is invalid because Password is required` -- the resolution failure itself is silent in the runtime's parameter provider (returns `Optional.empty()` on failure, no event-table error).

If the customer's symptom is "secret-backed property reported as missing" while the secret object exists, walk the chain:

1. **Secret object exists at the FQN** referenced by `config.json` `fullyQualifiedSecretName` -- run `SHOW SECRETS LIKE '<name>' IN SCHEMA <db>.<schema>;`
2. **Secret type matches the connector's expectation** -- postgres CDC expects `GENERIC_STRING`, not `PASSWORD`. The `PASSWORD` type packages USERNAME + PASSWORD pairs; postgres CDC takes the username as a separate property and only consumes the secret value as the password.
3. **Runtime role has BOTH `READ` AND `USAGE` grants on the secret** -- run `SHOW GRANTS ON SECRET <fqn>;`. In SPCS service contexts, `OWNERSHIP` alone does not imply USAGE for `SYSTEM$READ_SECRET_VALUE`. Without `USAGE`, the parameter provider's secret read fails silently. Customer-run grant if missing:
   ```sql
   GRANT USAGE ON SECRET <fqn> TO ROLE <runtime-execute-as-role>;
   ```
   (Find the runtime's execute-as role with `DESCRIBE OPENFLOW RUNTIME <runtime-fqn>;` -- `execute_as_role` field. For SPCS deployments this is typically `OPENFLOW_ADMIN`.)
4. **Secret is in the EAI's `ALLOWED_AUTHENTICATION_SECRETS`** -- run `DESC EXTERNAL ACCESS INTEGRATION <eai>;`
5. **EAI is attached to the runtime** -- run `DESCRIBE OPENFLOW RUNTIME <runtime-fqn>;` and check `external_access_integrations`
6. **Secret value is what the customer expects** -- **customer-run only.** `SELECT SYSTEM$READ_SECRET_VALUE('<fqn>');` returns a JSON envelope containing the plaintext secret. The customer should run this in their own session and inspect locally to verify `properties[*].value` is non-empty, is not a placeholder string (e.g., `"changeme"`, `"REPLACE_ME"`, an empty quoted string), and matches what the source DB expects. **Do NOT instruct the customer to paste the output back to the agent.** If the customer reports a placeholder or empty value, the fix is to update the secret with `ALTER SECRET ... SET ...` -- the customer runs that themselves; the agent does not need to see the actual credential.

If all six pass and the property still reports as missing, the next likely cause is a stale connector validation cache (see lifecycle pitfalls below).

---

## SQL-managed lifecycle pitfalls

### `UPDATE_FAILED` is terminal -- only `STOP` clears it

Once a connector lands in `UPDATE_FAILED` (a COMMIT introduced a config the validator rejects), the lifecycle is:

- `START` is rejected with `"not allowed while connector is in UPDATE_FAILED status"`
- A subsequent `ADD LIVE VERSION FROM LAST -> COMMIT` cycle will re-enter `UPDATE_FAILED` even when the new config is correct
- Only `ALTER OPENFLOW CONNECTOR <fqn> STOP` clears it back to `STOPPED`, after which `START` (or `TERMINATE`) can be issued

Propose `STOP` before any subsequent fix attempt when the customer's connector is in `UPDATE_FAILED`.

### Validation cache can become sticky after multiple version promotes

Observed behavior: when an early connector version was committed with bad property values and subsequent versions promoted with corrected values, the connector validator can continue to report the OLD property values (those from the first bad version) even though the current `default_version` config.json has the corrected values.

Things that have NOT been observed to clear the stale validation:
- Multiple `ADD LIVE VERSION FROM LAST -> COMMIT` cycles
- `ALTER OPENFLOW RUNTIME ... RESTART`
- `ALTER OPENFLOW CONNECTOR ... STOP` followed by `START`

When this is the case, the corrected `config.json` cannot be made to take effect via the SQL-managed config-edit path; the connector must be recreated. **DROP, TERMINATE, and CREATE OPENFLOW CONNECTOR are not in the SQL action allowlist.** Direct the customer to recreate the connector through the Openflow UI wizard, OR to run the lifecycle DDL themselves outside the agent's action surface. Do not author a SQL action sequence that performs `STOP -> TERMINATE -> DROP -> CREATE` end-to-end.

If a customer reports the same validation error persisting across multiple stage-promote attempts despite `config.json` clearly containing the corrected value, this stale-cache pattern is the most likely cause. Surface it as a possible cause and direct the customer to the UI for recreation.

### `CREATE OPENFLOW CONNECTOR ... FROM '@<stage>'` does not fully bind the parameter context

When a connector is created from a stage location (not from `FROM DEFINITION`), the stage's `config.json` and asset files are copied into the connector's first version stage, but the runtime's parameter context for the connector is not fully bound by the `CREATE` alone. A subsequent `START` will fail validation as if every required property were missing -- the canvas bulletin / event-table error reports the full list of `'<property>' is invalid because <property> is required` for every `STRING_LITERAL` and reference field, even though the `config.json` on the version stage clearly contains the values.

The customer's recovery (run by the customer outside the agent's action surface, since `CREATE OPENFLOW CONNECTOR` is not in the allowlist) is to issue:

```sql
ALTER OPENFLOW CONNECTOR <fqn> ADD LIVE VERSION FROM LAST;
ALTER OPENFLOW CONNECTOR <fqn> COMMIT;
```

This is a no-op edit (the live version is identical to the default), but the COMMIT triggers the runtime to re-parse `config.json` and bind the parameter context. After this, `START` proceeds past validation and into actual processor initialization.

The agent should surface this as a known pitfall when a customer reports a freshly created-from-stage connector failing every required-property validation despite a correct `config.json`. Direct them to issue the no-op `ADD LIVE VERSION FROM LAST -> COMMIT` themselves, or to use the Openflow UI wizard which handles this binding step automatically.
