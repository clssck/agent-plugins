# Horizon IRC API Reference

Quick reference for Horizon IRC (Iceberg REST Catalog) API endpoints, authentication, and URL construction.

---

## Base URL

```
https://<org_name>-<account_name>.snowflakecomputing.com/polaris/api/catalog
```

The script normalizes account IDs automatically: underscores → hyphens, lowercased.

**Example**:
- Account: `MYORG-MYACCOUNT`
- Base URL: `https://myorg-myaccount.snowflakecomputing.com/polaris/api/catalog`

---

## Endpoints (4 Diagnostic Steps)

| Step | Method | Path | Auth | Purpose |
|------|--------|------|------|---------|
| 1 | GET | `/v1/config?warehouse=<CATALOG>` | None | Verify endpoint reachability |
| 2 | POST | `/v1/oauth/tokens` | PAT or JWT as `client_secret` | Obtain bearer token |
| 3 | GET | `/v1/<CATALOG>/namespaces` | Bearer token | List available namespaces |
| 4 | GET | `/v1/<CATALOG>/namespaces/<SCHEMA>/tables/<TABLE>` | Bearer token | Load table metadata |

---

## OAuth Token Request (Step 2)

**Method**: `POST /v1/oauth/tokens`  
**Content-Type**: `application/x-www-form-urlencoded`

**Form fields**:

| Field | Value |
|-------|-------|
| `grant_type` | `client_credentials` |
| `scope` | `session:role:<ROLE_NAME>` |
| `client_secret` | `<PAT or JWT value>` |

**Note**: `scope` is case-sensitive. Role name must match exactly as granted in Snowflake. There is no `client_id` — the PAT or JWT is the only credential.

**Example**:
```bash
curl -X POST "https://myorg-myaccount.snowflakecomputing.com/polaris/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&scope=session:role:SYSADMIN&client_secret=<PAT_OR_JWT>"
```

**Success response**:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## Bearer Token Usage (Steps 3 & 4)

Pass the token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Tokens expire (default: 1 hour). If step 3 or 4 returns `401` after step 2 succeeded, re-run step 2 to get a fresh token using `--step 2`, then resume with `--step <N> --token <new_token>`.

---

## Namespace Path Format

Horizon IRC namespaces map 1:1 to Snowflake schemas. In the API path:

```
/v1/<CATALOG>/namespaces/<SCHEMA>/tables/<TABLE>
```

- `<CATALOG>` = Snowflake database / catalog name (e.g. `MY_CATALOG`)
- `<SCHEMA>` = Snowflake schema / IRC namespace (e.g. `MY_SCHEMA`)
- `<TABLE>` = Iceberg table name (e.g. `MY_TABLE`)

Identifiers are case-sensitive in the REST API path.

---

## Catalog Role Grants

To allow a role to access Horizon IRC namespaces and tables:

```sql
-- Grant a catalog role to a Snowflake role
GRANT CATALOG ROLE <catalog_name>.<catalog_role> TO ROLE <snowflake_role>;

-- Check catalog roles available on a catalog
SHOW CATALOG ROLES IN CATALOG <catalog_name>;

-- Check what a role has been granted
SHOW GRANTS TO ROLE <role_name>;
```

---

## Curl Commands Reference

**Step 1 — Endpoint reachability:**
```bash
curl -i --max-time 15 "https://<account_url>/polaris/api/catalog/v1/config?warehouse=<DB>"
```

**Step 2 — Authentication (PAT or JWT as client_secret):**
```bash
curl -i --max-time 15 -X POST "https://<account_url>/polaris/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=session:role:<ROLE>" \
  --data-urlencode "client_secret=<PAT_OR_JWT>"
```

**Step 3 — List namespaces:**
```bash
curl -i --max-time 15 "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces" \
  -H "Authorization: Bearer $TOKEN"
```

**Step 4a — Read credential vending:**
```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces/<SCHEMA>/tables/<TABLE>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Iceberg-Access-Delegation: vended-credentials"
```

**Step 4b — Write access verification (via SQL, not HTTP):**

The loadTable endpoint always falls back to read-delegation silently — the response does not indicate read vs read-write. Verify write access by checking grants:

```sql
SHOW GRANTS ON TABLE "<db>"."<schema>"."<table>";
```

- SELECT only → credentials are read-only
- OWNERSHIP → credentials include read+write
- Write DML requires: INSERT, UPDATE, DELETE, TRUNCATE on table

**Example write-delegation failure** (seen in Spark/engine logs when vended credentials lack write permissions):
```
com.amazonaws.services.s3.model.AmazonS3Exception:
  Access Denied (Service: Amazon S3; Status Code: 403; Error Code: AccessDenied)
  for s3:PutObject on resource: arn:aws:s3:::<bucket>/<path>/
```
This means Snowflake vended read-only credentials — the role likely lacked the write grants (INSERT/UPDATE/DELETE/TRUNCATE) needed for Snowflake to issue write-capable S3 credentials. Check `SHOW GRANTS ON TABLE` to confirm.

---

## Generating a JWT (Key-Pair Auth)

Use SnowSQL to mint a JWT from your RSA private key:

```bash
snowsql --private-key-path "<path_to_rsa_key.p8>" \
  --generate-jwt \
  -h "<org-account>.snowflakecomputing.com" \
  -a "<account_locator>" \
  -u "<username>"
```

The output JWT is valid for up to 1 hour. Use it as `client_secret` in the Step 2 OAuth token request.

SnowSQL install: https://docs.snowflake.com/en/user-guide/snowsql
