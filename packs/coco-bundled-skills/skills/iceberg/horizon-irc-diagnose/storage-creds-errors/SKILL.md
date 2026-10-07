---
name: horizon-irc-storage-creds-errors
description: "Debug Horizon IRC storage credential failures. Invoked from table-access-errors when Step 4 or SQL validation indicates a storage/credential issue."
parent_skill: horizon-irc-diagnose
---

# Storage Credential Errors (Step 5)

## When to Load

Loaded from `table-access-errors/SKILL.md` when the error body or SQL failure indicates a storage/credential issue:
- Step 4 body contains storage signals (`S3Exception`, `AzureException`, `credential vending`, etc.), OR
- Snowflake SQL validation failed with a storage-related error, OR
- Step 4 403 persists after SQL validation passed ✅ and re-authentication was tried

---

## Workflow

```
Classify error body (storage signals) → Check EV inheritance chain (DB + table)
       ↓
EV exists? → Confirm with user → ⚠️ STOP → Load iceberg-external-volume skill
No EV?    → ⚠️ STOP → Create EV → attach → restart horizon-irc-diagnose
       ↓
After fix: Re-run Step 4 → Return to test/SKILL.md
```

---

## Diagnosis

Read `steps.4_table_metadata.body` from the script JSON output and use judgment to classify:

| Signal in body | Meaning |
|---|---|
| `S3Exception`, `AzureException`, `StorageException` + `"access denied"` / `"not authorized"` / `"kms:Decrypt"` | Cloud provider rejected vended credentials — IAM/permissions issue on the external volume |
| `IllegalArgumentException`, `UnprocessableEntityException` + `"credential vending"` / `"subscoped credentials"` | Polaris could not generate credentials — external volume missing or misconfigured on the database |
| `"owner does not have required privileges on external volume"` | Table owner's role lacks `USAGE ON EXTERNAL VOLUME` — grant it before re-running |

Both cases require external volume diagnosis.

---

## Route to iceberg-external-volume

**Before delegating**, verify the external volume inheritance chain is correct:

### 1. Check DATABASE level

```sql
DESCRIBE DATABASE "<db>";
```

Look for `EXTERNAL_VOLUME` property.

### 2. Check TABLE level

```sql
SHOW ICEBERG TABLES LIKE '<table>' IN SCHEMA "<db>"."<schema>";
```

Look for `external_volume_name` column — a non-empty value means the table overrides the DB-level EV.

### Evaluate the chain

| DB has EV | Table has EV | Result |
|---|---|---|
| ✅ | ❌ (inherits DB) | Table uses DB-level EV — confirm this is the intended one |
| ✅ | ✅ (override) | Table uses its own EV — confirm this is the intended one |
| ❌ | ✅ | Table uses its own EV — confirm this is the intended one |
| ❌ | ❌ | **No EV in chain** — stop here, set up an external volume first, then restart |

**If no EV exists anywhere in the chain:**

**⚠️ STOP**: Your database and table have no external volume configured. Iceberg tables require an external volume to store data files.

1. Set up an external volume using the `iceberg-external-volume` skill
2. Once created, attach it — choose one:

```sql
-- Option A: set at database level (all tables inherit it)
CREATE OR REPLACE DATABASE "<db>"
  EXTERNAL_VOLUME = '<external_volume_name>'
  CATALOG = 'SNOWFLAKE';

-- Option B: set at table level only
ALTER ICEBERG TABLE "<db>"."<schema>"."<table>"
  SET EXTERNAL_VOLUME = '<external_volume_name>';
```

3. Then **restart** the `horizon-irc-diagnose` skill from the beginning (Prereq 3 — creating the database with `EXTERNAL_VOLUME` set).

---

**⚠️ STOP**: Confirm with the user that the external volume shown is the one they intend to use before delegating.

Once the chain is confirmed and the EV name is known:

→ **Load** the `iceberg-external-volume` skill to diagnose and fix the external volume itself, providing:
- The external volume name
- The failure signal from the error body (IAM rejection vs. credential vending failure)

> **Quick fix to try first**: If the external volume exists but credentials are stale, refresh it before escalating:
> ```sql
> ALTER EXTERNAL VOLUME <external_volume_name> REFRESH;
> ```
> Then re-run Step 4. If it still fails, proceed with `iceberg-external-volume` skill.

---

## Stopping Points

- ✋ No EV in chain: Before delegating to iceberg-external-volume
- ✋ EV chain confirmed: Before loading iceberg-external-volume with EV details

---

## Re-run Step 4 (after iceberg-external-volume fixes are applied)

```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces/<SCHEMA>/tables/<TABLE>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Iceberg-Access-Delegation: vended-credentials"
```

✅ HTTP 200 + `storage-credentials` in response = success.

---

## After Fixing

Once Step 4 passes:
→ **Return** to `test/SKILL.md` Step T4 to present the final success summary.

---

## Output

External volume fixed and Step 4 passing; returned to `test/SKILL.md` for final summary.
