# Classification Concepts

The decision-relevant essentials for Snowflake data classification. For the full built-in semantic-category catalog and the complete privilege matrix, consult the official docs (linked below) rather than reproducing them here.

## Manual vs. automatic

| Approach | How | Use when |
|---|---|---|
| **Manual** | `CALL SYSTEM$CLASSIFY('db.schema.table' [, {...}])` | One-time analysis, testing, "show me what's in this table first" |
| **Automatic** | A **classification profile** monitors databases/schemas on a schedule | Production, ongoing account-wide coverage |

```sql
-- Automatic: create a profile, then associate it with a database/schema.
CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE <profile>(
  'minimum_object_age_for_classification_days': 1,
  'maximum_classification_validity_days': 90,
  'auto_tag': FALSE);   -- auto_tag=TRUE writes semantic-category tags onto discovered columns
```

`auto_tag=TRUE` modifies schema metadata (tags appear in `INFORMATION_SCHEMA`/`ACCOUNT_USAGE`) and those tags can drive tag-based masking — enable deliberately. Default to `auto_tag=FALSE` for a first pass.

## Built-in categories vs. custom (the key routing decision)

Snowflake ships built-in **semantic categories** (NAME, EMAIL, PHONE_NUMBER, ADDRESS, US_SSN, DATE_OF_BIRTH, PAYMENT_CARD, BANK_ACCOUNT, IBAN, …) tagged as `SNOWFLAKE.CORE.SEMANTIC_CATEGORY:<CATEGORY>`. For the authoritative, current list see the Snowflake docs: <https://docs.snowflake.com/en/user-guide/classify-intro>.

**If the sensitive data type is NOT built-in, `SYSTEM$CLASSIFY` and auto-classification will not detect it** — you must create a custom classifier first. Data types that are typically **not** built-in and need one: country-specific IDs (passport, UK NINO, Aadhaar), employee IDs, internal account/project codes, industry IDs (medical record numbers, VINs), and other business-specific identifiers.

```sql
-- Custom classifier (two steps): create, then add regex rule(s).
CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER <name>();
CALL <name>!ADD_REGEX(
  '<SEMANTIC_CATEGORY>',   -- e.g. 'EMPLOYEE_ID'
  '<PRIVACY_CATEGORY>',    -- IDENTIFIER | QUASI_IDENTIFIER | SENSITIVE
  '<regex>',               -- e.g. '^EMP-[0-9]{5}$'
  '<description>');
-- Then add the classifier to a classification profile so auto-classification detects it.
```

**Privacy categories:** `IDENTIFIER` (uniquely identifies a person), `QUASI_IDENTIFIER` (identifies in combination), `SENSITIVE` (sensitive but not directly identifying).

## Running and viewing results

```sql
CALL SYSTEM$CLASSIFY('db.schema.table');                       -- manual; returns JSON (column, category, confidence)
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST -- automatic results
  WHERE DATABASE_NAME = '<DB>' ORDER BY LAST_CLASSIFIED_ON DESC;
```

**Gotcha:** classification is invoked with `CALL`, not `SELECT`. "Unknown function SYSTEM$CLASSIFY" almost always means `SELECT` was used — switch to `CALL` (see `templates/manual-classify.sql`).

## Privileges

Manual classify needs `SELECT` on the object (+ `SNOWFLAKE.CORE_VIEWER`); `auto_tag` additionally needs `OWNERSHIP`/`APPLY TAG`; creating profiles/classifiers needs `SNOWFLAKE.CLASSIFICATION_ADMIN` and `CREATE …CLASSIFICATION_PROFILE`/`CUSTOM_CLASSIFIER` on the schema; associating a profile needs `EXECUTE AUTO CLASSIFICATION`. Pre-check with `SHOW GRANTS TO ROLE <role>` / `SHOW GRANTS ON <object>`; on "Insufficient privileges", tell the user which grant is missing and to contact their admin. Full matrix: <https://docs.snowflake.com/en/user-guide/classify-manage>.

## Verify before claiming success

After creating objects, confirm they exist (`SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER LIKE '<name>'`, `SHOW …CLASSIFICATION_PROFILE LIKE '<name>'`). Treat any of `Statement X failed`, `SQL compilation error`, `Object does not exist`, `Insufficient privileges` in the response as a FAILED step — never mark it successful.

## Good practice

Start manual to see what's really there → test with `auto_tag=FALSE` → use profiles for ongoing governance → add custom classifiers for domain-specific data → review `ACCOUNT_USAGE` results periodically → pair with tag-based masking for protection.
