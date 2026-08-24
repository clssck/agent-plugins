---
name: horizon-irc-connectivity-errors
description: "Debug Horizon IRC transport-level connectivity failures. Invoked when Step 1 receives no HTTP response at all."
parent_skill: horizon-irc-diagnose
---

# Connectivity Errors

## When to Load

Loaded by `horizon-irc-diagnose` when Step 1 fails — either **no HTTP response** (transport failure) or **HTTP 404** (endpoint not found).

> **Note**: Any other HTTP response (401, 403, 500, etc.) means connectivity is fine — the endpoint is up, DNS resolved, TLS succeeded. Those errors are diagnosed in later steps (authn, authz, storage).

---

## Workflow

```
Check error/status_code → Route: DNS failure / TCP refused / TLS error / Timeout / 404
       ↓
Apply fix → ⚠️ STOP → Re-run Step 1 → Return to test/SKILL.md
```

---

## Diagnosis

Check the `error` / `status_code` fields from the script output:

| Error | Cause | Fix |
|-------|-------|-----|
| `ConnectionError: ... Name or service not known` | DNS resolution failed — wrong account_id | See [Account ID Format](#account-id-format) |
| `ConnectionError: ... Connection refused` | TCP connect failed — wrong host or port | Verify account_id; Polaris must be enabled |
| `TLSError: ...` | TLS handshake failed | Check corporate proxy / SSL inspection settings |
| `Timeout after 15s` (no status_code) | TCP connect timed out — firewall blocking outbound HTTPS | Check VPN, network policy |
| `status_code: 403` | Horizon IRC not enabled on account, or IP blocked by network policy | Contact Snowflake support to enable Horizon IRC; check `SHOW NETWORK POLICIES` |
| `status_code: 404` | Endpoint path not found — Polaris/Horizon IRC not enabled on this account, or wrong base URL | Contact Snowflake support to enable Horizon IRC |

---

## Account ID Format

The base URL is:
```
https://<org_name>-<account_name>.snowflakecomputing.com/polaris/api/catalog
```

Common mistakes:

| Wrong | Correct |
|-------|---------|
| `myorg_myaccount` (underscores) | `myorg-myaccount` |
| `myorg-myaccount.us-east-1` (with region) | `myorg-myaccount` |
| `ab12345` (legacy locator) | Run SQL to get correct value |

Get the correct value:
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();
```

---

## Firewall / VPN

If the error is a timeout with no HTTP status:
- Verify outbound HTTPS (port 443) to `*.snowflakecomputing.com` is allowed
- Try connecting on VPN if behind a corporate firewall
- Check Snowflake network policies:
```sql
SHOW NETWORK POLICIES;
DESC NETWORK POLICY <policy_name>;
```

---

## Polaris Not Enabled

If DNS resolves but TCP is refused (or you consistently get connection errors on a valid account_id), Horizon IRC (Polaris) may not be enabled on the account. Contact your Snowflake account admin or Snowflake support.

---

## Stopping Points

- ✋ After identifying the cause: Confirm fix is applied before re-running

---

## Re-run Step 1

```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/config?warehouse=<DB>"
```

Any HTTP response other than 404 (e.g. 401, 403, 500) means connectivity is fixed.

---

## After Fixing

Once Step 1 returns any HTTP response other than 404 (e.g. 401, 403, 500):
→ **Return** to `test/SKILL.md` Step T2 and continue from Step 2 (authentication).

---

## Output

Step 1 returning a valid HTTP response; returned to `test/SKILL.md` for Step 2 onward.
