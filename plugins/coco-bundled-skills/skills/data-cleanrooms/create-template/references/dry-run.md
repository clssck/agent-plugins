# Reference: Dry Run Workflow

Detailed steps for running a dry run to validate template SQL before registration.

## Step 5.5a: Set Up Test Tables

Ask the user:

> Do you have local tables I can use to dry-run the template? They should have the same schema (column names + types) as the offerings the template references. If not, I'll create dummy tables with synthetic data matching the expected schema.

**If user provides tables:** Use those for substitution. Confirm the column names align with the template's references.

**If user has no tables:** Create dummy tables in a scratch schema. Use the schema you inferred from the user's request (or from `VIEW_DATA_OFFERINGS` in Mode A):

```sql
CREATE OR REPLACE TEMPORARY TABLE _dryrun_source_0 (
  HASHED_EMAIL VARCHAR,
  HASHED_PHONE VARCHAR,
  REGION VARCHAR,
  -- ... other columns from the source offering ...
);

INSERT INTO _dryrun_source_0 VALUES
  ('hash_a', 'phone_a', 'US'),
  ('hash_b', 'phone_b', 'EU'),
  -- ... a handful of rows with overlapping and non-overlapping values ...
;

CREATE OR REPLACE TEMPORARY TABLE _dryrun_my_0 (
  HASHED_EMAIL VARCHAR,
  CAMPAIGN_ID VARCHAR,
  -- ... other columns ...
);

INSERT INTO _dryrun_my_0 VALUES (...);
```

**Dummy data guidance:** include at least 3-5 rows per table with **deliberate overlap** on the join key (so you can verify the join produces non-zero matches) and **deliberate non-overlap** (so you verify the join filters correctly). For activation templates, include passthrough columns so you can verify they're emitted in the output.

## Step 5.5b: Render Jinja to SQL

The template's Jinja variables won't be auto-rendered outside a collaboration — substitute them manually for the dry run:

| Jinja variable | Dry-run substitution |
|----------------|---------------------|
| `{{ source_table[N] }}` | Quoted table name e.g. `'_dryrun_source_0'` (passed to `identifier()`) |
| `{{ my_table[N] }}` | Quoted table name e.g. `'_dryrun_my_0'` |
| `{{ join_columns[0] }}` or similar param | Concrete column name string |
| `{{ dimensions \| sqlsafe }}` | Concrete column list, comma-separated |
| Policy filters (`\| join_policy`, `\| column_policy`, etc.) | Strip for dry run — these are platform-applied at runtime |
| `{{ user_provided_value }}` parameters | Use a sample value matching the parameter's `type` |

Produce the **rendered SQL** as a single executable statement. Show it to the user before running:

> Here's the rendered SQL we'll run against the test tables. Notice that `identifier()` wraps the table refs and policy filters are stripped (platform-applied at runtime). Running now…

## Step 5.5c: Execute and Iterate

Run the rendered SQL. Possible outcomes:

| Outcome | Action |
|---------|--------|
| Success, results look reasonable | Proceed to Step 5.5d |
| Success, but results are wrong (zero rows when overlap expected, NULL when value expected, etc.) | Diagnose: join condition, column names, aggregation logic. Update the template SQL. Re-render. Re-run. |
| SQL error (column not found, type mismatch, syntax) | Diagnose from error message. Update the template SQL (often a column name typo or wrong table alias). Re-render. Re-run. |
| Jinja rendering error (unbalanced braces, undefined variable) | Fix the template's Jinja syntax. Re-render. Re-run. |

**Iterate up to 3 times.** If you can't get a clean run after 3 tries, stop and present what you found to the user — there may be a schema mismatch only the user can clarify.

Narrate every change:
> The first run failed with `invalid identifier 'EMAIL_HASH'`. Looking at your offering, the actual column is `HASHED_EMAIL`. I'll update the template's join clause and re-run.

## Step 5.5d: Update the Spec

Once a clean run is achieved, the **rendered SQL is your validation** — but the spec you register is still the Jinja-templated version. Apply any fixes you made (column name corrections, join logic updates, etc.) back into the `template` field of the spec.

Present the **updated spec** to the user:

> Dry run succeeded. Here's the updated template spec with the fixes applied. Ready to register?

**⚠️ MANDATORY STOPPING POINT** — The user must re-confirm the updated spec before handoff to register. Do not skip this confirmation just because the dry run passed.

## Step 5.5e: Cleanup

If you created dummy tables, drop them:

```sql
DROP TABLE IF EXISTS _dryrun_source_0;
DROP TABLE IF EXISTS _dryrun_my_0;
```
