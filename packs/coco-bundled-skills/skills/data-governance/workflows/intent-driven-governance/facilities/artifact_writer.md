# Artifact Writer Facility

Use this facility whenever writing Markdown, YAML, or SQL artifacts to `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES`.

## Goal

Write durable stage artifacts with normal text formatting using one stable Snowflake SQL pattern. Do not invent ad hoc artifact-writing SQL.

Every customer-facing phase artifact is a review document, not a raw state dump. The state object may stay structured for validation, but the rendered artifact shown to the customer should read like a formal governance record.

Each rendered artifact should include:

- A clear title and one-sentence purpose.
- The decision the customer is being asked to make.
- Scope and evidence sources, including Snowflake objects inspected or state paths used.
- The substantive findings, intent, plan, SQL, or execution results in plain English.
- Explicit no-change, intentionally-unprotected, deferred, unsupported, and remaining-gap sections when applicable.
- Traceability: artifact path, state path, relevant digest/version, and progress.
- Working-state metadata: base committed version, working status (`dirty`, `awaiting_customer_approval`, or `clean`), latest update time/session when available, and whether a committed version exists yet.
- A natural customer decision prompt.

Do not render artifacts as terse key/value lists when the customer needs to understand business meaning. Use short sections, bullets, and tables. Keep exact SQL in code blocks and preserve object FQNs exactly.

## Applies To

- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/observation_summary.md`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/consolidated_intent_summary.md`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/execution_summary.md`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/drift_summary/drift_summary_current_observe_<timestamp>.md`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/drift_summary/drift_summary_<timestamp>.md`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/revert_summary/revert_summary_current_observe_<timestamp>.md`
- `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/revert_summary/revert_summary_<timestamp>_<target_version>.md`

For committed snapshots, write/update the working files first, then use `COPY FILES` to snapshot the working folder into the committed version.

## Required SQL Pattern

Preferred implementation: write the artifact content to a local scratch file, then run `scripts/control_plane.py write-artifact-sql <stage-path> <content-file>` and execute the generated single `COPY INTO` statement. This helper applies the line-preserving CSV format and placeholder escaping below, including the special `.sql` artifact handling. Use the manual patterns in this file only when the helper is unavailable.

Use one `VALUES` row per output line. Preserve blank lines as `$$$$`. Keep the numeric line column numeric and the text line column text.

```sql
COPY INTO @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/<target_folder>/<artifact_name>
FROM (
  SELECT line
  FROM (VALUES
    (1, $$first line$$),
    (2, $$$$),
    (3, $$third line$$)
  ) AS t(line_number, line)
  ORDER BY line_number
)
FILE_FORMAT = (
  TYPE = CSV
  COMPRESSION = NONE
  FIELD_DELIMITER = '~!~!~'
  RECORD_DELIMITER = '\n'
  FIELD_OPTIONALLY_ENCLOSED_BY = NONE
  ESCAPE_UNENCLOSED_FIELD = NONE
  EMPTY_FIELD_AS_NULL = FALSE
  TRIM_SPACE = FALSE
  NULL_IF = ()
)
SINGLE = TRUE
OVERWRITE = TRUE;
```

Do not write a separate `current/` mirror. After successful execution, snapshot the approved six-file working set into `versions/vNNN/`; the latest immutable version is the deployed baseline. Then clean `working/` so it retains only `governance_spec.md` and a cleaned `state.yaml`.

## Required Pattern For `.sql` Artifacts

When writing `governance_implementation.sql`, keep the artifact-writing statement safe to submit as one statement even when the artifact content contains executable SQL. Therefore the artifact-writing statement must not contain literal SQL-artifact semicolons or literal `$$` body delimiters inside `VALUES` lines.

Use placeholders in line text and expand them in the outer `SELECT`:

- Write `<SC>` where the artifact line needs a semicolon (`;`).
- Write `<DD>` where the artifact line needs a standard SQL scripting body delimiter (`$$`).
- Do not put literal `;`, `$$`, or named delimiters such as `$proc$` inside any `VALUES` line for a `.sql` artifact.
- The staged artifact must contain the real characters after replacement, and `EXECUTE IMMEDIATE FROM ... DRY_RUN = TRUE` must be run against that final staged artifact before requesting approval.

```sql
COPY INTO @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql
FROM (
  SELECT
    REPLACE(REPLACE(line, '<SC>', CHR(59)), '<DD>', CHR(36) || CHR(36)) AS line
  FROM (VALUES
    (1, $$CREATE MASKING POLICY GOVERNANCE_INTENT_WORKSPACE.POLICIES.MASK_DOB$$),
    (2, $$  AS (VAL DATE) RETURNS DATE ->$$),
    (3, $$  CASE WHEN IS_ROLE_IN_SESSION('DATA_GOVERNOR') THEN VAL ELSE NULL END<SC>$$),
    (4, $$CREATE OR REPLACE PROCEDURE GOVERNANCE_INTENT_WORKSPACE.MONITORING.RUN_GOVERNANCE_DRIFT_CHECK()$$),
    (5, $$RETURNS STRING LANGUAGE SQL AS <DD>$$),
    (6, $$BEGIN$$),
    (7, $$  RETURN 'ok'<SC>$$),
    (8, $$END<SC>$$),
    (9, $$<DD><SC>$$)
  ) AS t(line_number, line)
  ORDER BY line_number
)
FILE_FORMAT = (
  TYPE = CSV
  COMPRESSION = NONE
  FIELD_DELIMITER = '~!~!~'
  RECORD_DELIMITER = '\n'
  FIELD_OPTIONALLY_ENCLOSED_BY = NONE
  ESCAPE_UNENCLOSED_FIELD = NONE
  EMPTY_FIELD_AS_NULL = FALSE
  TRIM_SPACE = FALSE
  NULL_IF = ()
)
SINGLE = TRUE
OVERWRITE = TRUE;
```

If a SQL artifact write or dry-run fails, return to Generate SQL and produce a revised artifact for approval. Do not repair and execute SQL during Execute SQL.

For normal setup phases, `<target_folder>` is `working`. For Drift Review, `<target_folder>` is `drift_summary`, and the artifact name must include the UTC timestamp. For Revert Mode, `<target_folder>` is `revert_summary`, and the main summary artifact name must include both the UTC timestamp and target version.

## Committed Version Snapshot

After successful execution, the working folder must contain exactly the six allowed files. Then snapshot it:

```sql
COPY FILES INTO @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/
FROM @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/;
```

Use the next zero-padded version folder, such as `v002`, `v003`, and so on, when prior committed versions exist.

After the snapshot is verified, remove stale working files and rewrite the cleaned working state:

```text
working/governance_spec.md
working/state.yaml
```

## Verification

After every artifact write, verify the path exists:

```sql
LIST @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/<target_folder> PATTERN='.*<artifact_name>$';
```

After commit, verify the committed version exists, then verify `working/` contains only the retained governance spec and cleaned state:

```sql
LIST @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working;
LIST @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001;
LIST @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions;
```

Before commit, the working listing must contain exactly:

- `state.yaml`
- `observation_summary.md`
- `consolidated_intent_summary.md`
- `governance_spec.md`
- `governance_implementation.sql`
- `execution_summary.md`

## Do Not Use

- `SPLIT_TO_TABLE` to split one large artifact string into lines.
- `ORDER BY` on columns emitted by `SPLIT_TO_TABLE` for artifact writes.
- `FIELD_DELIMITER = NONE`.
- One-off stage-writing SQL patterns invented during the conversation.
- Literal trailing backslashes (`\`) as newline markers.

## If An Artifact Contains `$$`

If a line contains `$$`, use a different dollar-quoted delimiter for that line, for example `$ARTIFACT$...$ARTIFACT$`, or rewrite the line to avoid the delimiter. Keep one row per output line.
