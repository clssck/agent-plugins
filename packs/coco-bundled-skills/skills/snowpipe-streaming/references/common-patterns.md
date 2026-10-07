# Common Patterns

Shared patterns across all Snowpipe Streaming integration methods (High-Performance Architecture).

---

## Profile JSON Format

All SDKs use the same profile format:

```json
{
    "account": "myorg-myaccount",
    "user": "STREAMING_USER",
    "url": "https://myorg-myaccount.snowflakecomputing.com:443",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----",
    "role": "STREAMING_ROLE"
}
```

**Note**: `private_key` is the key **content** (PEM string), not a file path.

---

## Key-Pair Generation

**This is the single source of truth for key-pair setup.** Other skill files reference this section.

### Generate the key pair

```bash
mkdir -p keys
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out keys/rsa_key.p8 -nocrypt
openssl rsa -in keys/rsa_key.p8 -pubout -out keys/rsa_key.pub
```

### Extract public key content (without headers)

```bash
grep -v "^-" keys/rsa_key.pub | tr -d '\n'
```

### Assign to Snowflake user

```sql
ALTER USER STREAMING_USER SET RSA_PUBLIC_KEY='MIIBIjANBgkqh...';
```

### Verify assignment

```sql
DESC USER STREAMING_USER;
-- Look for RSA_PUBLIC_KEY_FP — should show SHA256:xxxx
```

### Troubleshooting key issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Failed to parse private key` | Key is encrypted or wrong format | Regenerate with `-nocrypt` flag |
| `RSA_PUBLIC_KEY_FP is null` | Public key not assigned | Run ALTER USER again |
| `Token signature invalid` | Key mismatch | Verify public key matches private key |
| `Unauthorized` | Wrong user or role | Check profile.json user/role values |

### For Kafka Connect

Base64-encode the private key content:
```bash
cat keys/rsa_key.p8 | base64 | tr -d '\n'
```

Use in connector config:
```json
"snowflake.private.key": "<BASE64_ENCODED_KEY>"
```

---

## VARIANT Column Best Practices

```python
# CORRECT: Native dict — stored as OBJECT in Snowflake
row["payload"] = {"event_id": 101, "status": "active"}

# CORRECT: Native list — stored as ARRAY
row["tags"] = ["electronics", "sale"]

# WRONG: JSON string — stored as VARCHAR, not parsed
row["payload"] = '{"event_id": 101, "status": "active"}'
```

Verify:
```sql
SELECT payload, TYPEOF(payload) FROM my_table LIMIT 1;
-- Should return OBJECT, not VARCHAR
```

---

## Snowflake Object Setup

```sql
CREATE TABLE IF NOT EXISTS MY_TABLE (
    id NUMBER,
    name VARCHAR,
    payload VARIANT,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE ROLE IF NOT EXISTS STREAMING_ROLE;
GRANT USAGE ON DATABASE MY_DATABASE TO ROLE STREAMING_ROLE;
GRANT USAGE ON SCHEMA MY_DATABASE.MY_SCHEMA TO ROLE STREAMING_ROLE;
GRANT INSERT ON TABLE MY_DATABASE.MY_SCHEMA.MY_TABLE TO ROLE STREAMING_ROLE;
GRANT ROLE STREAMING_ROLE TO USER STREAMING_USER;
```

---

## Named Pipe with Pre-Clustering

```sql
CREATE OR REPLACE PIPE MY_DATABASE.MY_SCHEMA.MY_TABLE_STREAMING
    CLUSTER_AT_INGEST_TIME = TRUE
AS MY_DATABASE.MY_SCHEMA.MY_TABLE;
```
