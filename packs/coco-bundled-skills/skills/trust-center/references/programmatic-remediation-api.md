# Trust Center Programmatic Remediation — API Reference

Programmatic remediation turns a Trust Center finding into validated, ready-to-run SQL (plus rollback where reversible). The platform **renders and validates** the SQL and declares its risk, reversibility, and required permissions; **the caller executes it** in their own account, then records the structured outcome. The platform does NOT auto-apply changes.

## Execution model

```
finding ─► preview_remediation (read-only)  ─► caller executes rendered_sql ─► record_remediation_result
          returns execution_id + rendered_sql + risk         (in array order)        (structured status)
```

## Availability detection (2-level)

The feature is gated by account param `ENABLE_TRUST_CENTER_PROGRAMMATIC_REMEDIATION`. When off, the view and procedures do not exist.

**1. Is the feature enabled?** The secure view exists only when the param is on:

```sql
SHOW VIEWS LIKE 'REMEDIATION_SCOPES' IN SCHEMA snowflake.trust_center;
```

No row → feature off.

**2. Is this scanner remediable?** Look the scanner up in the live coverage catalog:

```sql
SELECT scanner_id, risk_id, action_type, scope_dimensions, risk_level,
       reversible, required_permissions, platform_supported
FROM   snowflake.trust_center.remediation_scopes
WHERE  scanner_id = '<SCANNER_ID>'
  AND  platform_supported = TRUE;
```

Row(s) → programmatic remediation is available for this scanner. `platform_supported = TRUE` means a platform action template implements the contract (executable SQL); `FALSE` means messaging-only, no SQL.

`remediation_scopes` is the authoritative live coverage source — prefer it over any static scanner list when present.

## Role gate

The entire API is granted only to application role `trust_center_admin`. `trust_center_viewer` cannot preview, record, or execute a remediation (it has incidental read-only access to the `remediation_scopes` catalog, nothing more).

## Procedures

| Procedure | Purpose | Signature |
|---|---|---|
| `snowflake.trust_center.preview_remediation` | Read-only. Renders and validates the remediation SQL for a finding and returns `execution_id`, `rendered_sql`, risk, reversibility, and required permissions. Does not execute. | `(finding_identifier VARCHAR, customer_inputs OBJECT DEFAULT NULL) RETURNS OBJECT` |
| `snowflake.trust_center.record_remediation_result` | Records the structured outcome (`status` enum) of a single-action remediation after the caller has executed `rendered_sql`. | `(execution_id VARCHAR, status VARCHAR, error_message VARCHAR DEFAULT NULL, comment VARCHAR DEFAULT NULL) RETURNS OBJECT` |
| `snowflake.trust_center.record_remediation_action_result` | Records the per-action, per-entity structured outcome for PER_ENTITY / multi-action remediations (one call per `action_seq`). | `(execution_id VARCHAR, action_seq NUMBER, status VARCHAR, entity_results OBJECT DEFAULT OBJECT_CONSTRUCT()) RETURNS OBJECT` |

### `preview_remediation`

Pass the finding's `FINDING_IDENTIFIER` (read from the finding row — do not hand-construct it). Pass `NULL` for `customer_inputs` to accept secure defaults — the normal path. Supply an OBJECT only to override a default on explicit user request; out-of-envelope values raise `invalid remediation inputs: …` — surface that error verbatim.

Returns:

```jsonc
{
  "execution_id":               "<uuid>",                 // pass to record_* calls
  "finding_identifier":         "<key>",
  "rendered_sql":               [ "ALTER ACCOUNT SET …;" ], // execute in array order; PER_ENTITY → one stmt per entity
  "rendered_rollback_sql":      [ … ],                     // empty when not reversible
  "affected_entities":          [ … ],
  "resolved_scope_dimensions":  { … },                     // effective values after defaults + overrides
  "risk_level":                 "LOW|MEDIUM",
  "reversible":                 true|false,                // false if ANY action is non-reversible (no partial rollback)
  "required_permissions":       [ "MANAGE ACCOUNT PARAMETERS" ],
  "post_execution_state_claim": "FULLY_RESOLVES_FINDING"
}
```

Present `rendered_sql`, `risk_level`, `reversible`, and `required_permissions` to the user — the preview is the natural confirm gate.

### Recording — structured, NOT prose

The recorded outcome is the `status` enum, not a description.

| Field | Records | Rule |
|---|---|---|
| `status` | The authoritative outcome — **this is the result**. | Exactly one of `SUCCEEDED` / `FAILED` / `PARTIALLY_SUCCEEDED`. |
| `error_message` | The raw error returned by the executed SQL. | Populate **only** on `FAILED` / `PARTIALLY_SUCCEEDED`; omit on `SUCCEEDED`. Raw error, not a paraphrase. |
| `comment` | Optional **human-authored** note (rationale, ticket ref). | Omit unless a person added a note. NOT a slot for an agent summary. |
| `entity_results` (via `record_remediation_action_result`) | Per-entity status map, e.g. `{"USER_A":"SUCCEEDED","USER_B":"FAILED"}`. | Structured map keyed by entity. Never prose. |

**Do NOT write a natural-language description of the result into `comment`, `error_message`, or any field.** The prose summary belongs in the chat reply to the user; the record stores only the structured value.

```sql
-- success (single-action)
CALL snowflake.trust_center.record_remediation_result('<execution_id>', 'SUCCEEDED');

-- failure — raw SQL error, comment omitted
CALL snowflake.trust_center.record_remediation_result(
    '<execution_id>', 'FAILED',
    'SQL access control error: Insufficient privileges to operate on account');

-- PER_ENTITY / multi-action — structured per-entity map (action_seq is 0-based, matches rendered_sql order)
CALL snowflake.trust_center.record_remediation_action_result(
    '<execution_id>', 0, 'PARTIALLY_SUCCEEDED',
    OBJECT_CONSTRUCT('USER_A','SUCCEEDED','USER_B','FAILED'));
```

## Error handling

- **15-minute preview TTL.** `record_*` raises `preview has expired (15-minute TTL)` if the preview aged out.
- **Finding drift.** `record_*` re-resolves the finding and raises `finding has changed since preview (FINDING_DRIFT)` if it changed between preview and record.
- On either, **re-preview** against the current finding. Never retry a stale `execution_id`.

## Coverage (PrPr)

CIS Benchmarks only — other frameworks have no contracts yet. The live, parameter-gated set is whatever `remediation_scopes` returns on the account; query it rather than assuming a fixed list. All current contracts declare `post_execution_state_claim = FULLY_RESOLVES_FINDING` — applying the remediation is expected to clear the finding on the next clean scan.
