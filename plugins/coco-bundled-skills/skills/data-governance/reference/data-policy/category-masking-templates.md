# Category → Masking-Strategy Template Catalog

Recommendation source for the **category-seeded masking create flow** (launched from the
Snowsight classification wizard). Given one or more detected **classification (semantic)
categories**, this catalog suggests a per-category masking strategy and a type-appropriate
masked expression.

This is a *recommendation* surface only. The workflow that consumes it still asks the user to
confirm the policy shape, the authorized roles, and the name/location, and still shows the
generated SQL for pre-write approval.

> **Scope: masking only.** This catalog (per-category masked expressions + sample values) applies to
> **masking** policies. The category-seeded flow also creates **projection** policies, but those are
> role-based allow/deny with no value transform, so they do **not** use this catalog — projection
> guidance (allowed roles + `FAIL`/`NULLIFY` enforcement + body templates) lives in the workflow's
> Projection path.

---

## How to read this catalog

- **Parent category** — the Snowflake built-in semantic category the strategy is keyed on.
  Branch and match on **parent** names first (see the normalization rule below).
- **Expected data type(s)** — the *typical* physical type(s) the category lands on. This is a
  hint for grouping and advice only; the **actual** column type is confirmed later by the
  wizard at bind time, not here. A category (e.g. `AGE`) can land on columns of more than one
  physical type across tables.
- **Mask strategy** — the recommended treatment for unauthorized roles.
- **Type-appropriate masked expression** — an example expression for the *masked* (else) branch.
  It **must be assignable to the policy's declared return type**. A `NUMBER` policy cannot return
  `'***MASKED***'`; a `DATE` policy cannot return `SHA2(val, 256)`. When in doubt, `NULL` is
  always type-safe and fail-closed.

Every generated policy uses the split-friendly shape:

```sql
CASE WHEN <authorized> THEN val ELSE <masked_expression> END
```

where `<authorized>` uses `IS_ROLE_IN_SESSION('<role>')` (never `CURRENT_ROLE()`), and an
explicit `ELSE` branch makes the fail-closed path visible.

---

## Semantic-category normalization rule (read before branching)

Classification **recommendations** and the classification profile `tag_map` matching surface
operate on **parent** semantic categories. Subcategory names (e.g. `US_SSN`) are silently
never matched by `SET_TAG_MAP` — the auto-classifier emits the *parent* (`NATIONAL_IDENTIFIER`).
So:

1. **Branch primarily on parent category names.** When generating a category-aware policy body,
   the `WHEN` arms should match parent names.
2. **Normalize known aliases.** If the wizard or a classification result detail hands you a
   subcategory or an alternate spelling, map it to its parent via the alias table below before
   looking it up here. Add the subcategory as an *additional* `WHEN` arm only when you have
   confirmed the column actually carries that value.
3. **Do not assert an absolute.** Classification *result details* can surface subcategories, and
   some local references use alternate spellings. Treat the parent as the reliable key and use
   alias coverage for the rest.

> **`SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)` is valid only inside a masking or projection policy
> body.** It returns an error in a standalone `SELECT`, view, or UDF. To inspect what value a
> column actually carries for `SNOWFLAKE.CORE.SEMANTIC_CATEGORY`, use a **live**
> `INFORMATION_SCHEMA.TAG_REFERENCES` read or classification result metadata — never a direct
> `SELECT SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)`.

### Subcategory / spelling → parent alias table (non-exhaustive)

| Input you may receive | Normalize to (parent) |
|---|---|
| `US_SSN` | `NATIONAL_IDENTIFIER` |
| `IN_AADHAAR` | `NATIONAL_IDENTIFIER` |
| `UK_NATIONAL_INSURANCE_NUMBER` | `NATIONAL_IDENTIFIER` |
| `ADDRESS` | `STREET_ADDRESS` |
| `US_STREET_ADDRESS` | `STREET_ADDRESS` |
| `US_PHONE_NUMBER` | `PHONE_NUMBER` |
| `ADMIN_AREA_1` | `ADMINISTRATIVE_AREA_1` |
| `ADMIN_AREA_2` | `ADMINISTRATIVE_AREA_2` |

> Verify exact category names and country-scoping conventions against the current Snowflake
> classification docs — the taxonomy evolves and some categories accept `country_codes` on the
> parent rather than a distinct subcategory name.

---

## Catalog by strategy family

### Show last 4 (STRING) — identifiers

| Parent category | Expected type(s) | Mask strategy | Masked expression (else branch) |
|---|---|---|---|
| `NATIONAL_IDENTIFIER` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `PAYMENT_CARD` | STRING | Show last 4 | `CONCAT('****-****-****-', RIGHT(val, 4))` |
| `BANK_ACCOUNT` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `TAX_IDENTIFIER` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `PASSPORT` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `DRIVERS_LICENSE` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `MEDICARE_NUMBER` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `IMEI` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `VIN` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |
| `ORGANIZATION_IDENTIFIER` | STRING | Show last 4 | `CONCAT('****', RIGHT(val, 4))` |

### Partial / structural (STRING)

| Parent category | Expected type(s) | Mask strategy | Masked expression (else branch) |
|---|---|---|---|
| `EMAIL` | STRING | First 2 chars + domain | `CONCAT(LEFT(val, 2), '***@', SPLIT_PART(val, '@', 2))` |
| `PHONE_NUMBER` | STRING | Show last 4 | `CONCAT('***-***-', RIGHT(val, 4))` |
| `IP_ADDRESS` | STRING | Mask first 2 octets | `CONCAT('***.***.', SPLIT_PART(val, '.', 3), '.', SPLIT_PART(val, '.', 4))` |
| `URL` | STRING | Domain only | `REGEXP_SUBSTR(val, '^https?://[^/]+')` |

### Full redaction (STRING)

| Parent category | Expected type(s) | Mask strategy | Masked expression (else branch) |
|---|---|---|---|
| `NAME` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `STREET_ADDRESS` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `CITY` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `COUNTRY` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `POSTAL_CODE` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `ADMINISTRATIVE_AREA_1` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `ADMINISTRATIVE_AREA_2` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `GENDER` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `MARITAL_STATUS` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `ETHNICITY` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `OCCUPATION` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `MEDICAL_DATA` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |
| `MEDICAL_SPECIALTY` | STRING | Full redaction | `'***MASKED***'` (or `NULL`) |

> `MEDICAL_DATA` and `MEDICAL_SPECIALTY` are listed separately because Snowflake docs treat them
> as distinct categories. Confirm both names against current docs during implementation.

### Numeric (NUMBER)

| Parent category | Expected type(s) | Mask strategy | Masked expression (else branch) |
|---|---|---|---|
| `SALARY` | NUMBER | Zero / redact | `NULL` (or `0`) |
| `AGE` | NUMBER | Zero / redact | `NULL` (or `0`) |
| `YEAR_OF_BIRTH` | NUMBER | Zero / redact | `NULL` (or `0`) |
| `LATITUDE` | NUMBER / FLOAT | Redact / coarsen | `NULL` (or `ROUND(val, 0)`) |
| `LONGITUDE` | NUMBER / FLOAT | Redact / coarsen | `NULL` (or `ROUND(val, 0)`) |

> `LAT_LONG` may arrive as a single STRING (`"lat,long"`) or as two NUMBER columns. If STRING,
> treat as full redaction; if NUMBER, use the numeric row above. Confirm the physical type.

### Temporal (DATE / TIMESTAMP)

| Parent category | Expected type(s) | Mask strategy | Masked expression (else branch) |
|---|---|---|---|
| `DATE_OF_BIRTH` | DATE / TIMESTAMP | Epoch / coarsen | `NULL`, or `DATE '1970-01-01'`, or `DATE_TRUNC('YEAR', val)` |

---

## Representative sample values (for the effect preview)

The workflow shows a read-only before/after preview of what a policy does to data **before** the
user approves the `CREATE`. Because `SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)` cannot run in a plain
`SELECT`, the preview does **not** execute the whole policy body. Instead it evaluates each
category's **masked expression** (the `else`/`then` branch, a pure expression of `val`) against a
representative sample value, using a single read-only `SELECT`. The authorized-role case is shown
as the cleartext value unchanged.

Use these built-in sample values (no scanning of real data needed):

| Parent category | Sample value (STRING unless noted) |
|---|---|
| `NAME` | `Jane Smith` |
| `EMAIL` | `alice@corp.com` |
| `PHONE_NUMBER` | `415-555-0199` |
| `NATIONAL_IDENTIFIER` | `123-45-6789` |
| `PAYMENT_CARD` | `4111 1111 1111 1111` |
| `BANK_ACCOUNT` | `000123456789` |
| `TAX_IDENTIFIER` | `12-3456789` |
| `PASSPORT` | `X1234567` |
| `DRIVERS_LICENSE` | `D1234567` |
| `MEDICARE_NUMBER` | `1EG4-TE5-MK73` |
| `IMEI` | `490154203237518` |
| `VIN` | `1HGCM82633A004352` |
| `ORGANIZATION_IDENTIFIER` | `ORG-00417` |
| `IP_ADDRESS` | `192.168.1.42` |
| `URL` | `https://example.com/path?q=1` |
| `STREET_ADDRESS` | `500 Market St` |
| `CITY` | `New York` |
| `COUNTRY` | `Canada` |
| `POSTAL_CODE` | `94105` |
| `ADMINISTRATIVE_AREA_1` | `California` |
| `ADMINISTRATIVE_AREA_2` | `Santa Clara County` |
| `GENDER` | `Female` |
| `MARITAL_STATUS` | `Married` |
| `ETHNICITY` | `Hispanic` |
| `OCCUPATION` | `Nurse` |
| `MEDICAL_DATA` | `Type 2 diabetes` |
| `MEDICAL_SPECIALTY` | `Cardiology` |
| `SALARY` (NUMBER) | `125000` |
| `AGE` (NUMBER) | `37` |
| `YEAR_OF_BIRTH` (NUMBER) | `1987` |
| `LATITUDE` (NUMBER) | `37.7749` |
| `LONGITUDE` (NUMBER) | `-122.4194` |
| `DATE_OF_BIRTH` (DATE) | `1987-03-14` |

If a category is not in this table, pick any plausible value of the right type for the sample.

### How to build the preview query (read-only, no attach, no tag function)

For each in-scope category, evaluate its masked expression on the sample value in one combined
`SELECT` (via `UNION ALL`), so the whole preview is one read-only query. Example for a STRING
policy covering `CITY`, `COUNTRY`, `EMAIL`:

```sql
SELECT 'CITY'    AS category, 'New York'       AS sample_value, '***MASKED***'                                             AS masked_result
UNION ALL
SELECT 'COUNTRY',            'Canada',          '***MASKED***'
UNION ALL
SELECT 'EMAIL',              'alice@corp.com',  CONCAT(LEFT('alice@corp.com', 2), '***@', SPLIT_PART('alice@corp.com', '@', 2));
```

Present the result plus the authorized-role case (which returns the value unchanged). The preview
evaluates the per-category masked **expressions**, not the full policy — role checks and the
`SEMANTIC_CATEGORY` tag branch are not executed in the preview; state that briefly so the user
knows it illustrates per-category output, not live policy evaluation.

---

## Cross-type note (why type grouping matters)

A single detected category can land on columns of different physical types across tables (the
canonical case: `AGE` is usually `NUMBER` but occasionally `STRING`). A tag holds **at most one
masking policy per data type**, so fully protecting a tag whose categories span types can require
more than one policy (e.g. one `NUMBER` and one `STRING`). The consuming workflow surfaces this as
group-by-type advice rather than silently assuming a single type.
