---
name: openflow-connector-hubspot
description: HubSpot connector for syncing HubSpot CRM objects (contacts, companies, deals, tickets, engagements) to Snowflake using Private App Token authentication. Use for HubSpot CRM ingestion.
---

# HubSpot Connector

Syncs HubSpot CRM objects to Snowflake tables.

**Official Documentation:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/hubspot/setup

**Flow Name:** `hubspot`

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

This reference covers the HubSpot connector using **Private App Token** (bearer) authentication.

| Flow Name | Auth | Destination |
|-----------|------|-------------|
| `hubspot` | Private App Token | Snowflake tables |

For other connectors, see `references/connector-main.md`.

---

## Collect Checklist

Gather this information from the user **before** proceeding with deployment. Refer to [official documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/hubspot/setup) for current prerequisite requirements.

### HubSpot Configuration (Required)

| Item | How to Obtain | Collected |
|------|---------------|-----------|
| HubSpot Private App Access Token | HubSpot UI → Settings → Integrations → Private Apps → [App] → Auth → Access token (sensitive) | [ ] |
| Object Types | CSV list of HubSpot object types (e.g., `Contacts,Companies,Deals`). **Case-sensitive — match the casing shown in official docs.** | [ ] |
| Updated After (optional) | ISO date/time to only ingest objects updated after this point. | [ ] |
| Data Ingestion Schedule (optional) | Polling interval (e.g. `30 minutes`, `1 hour`). | [ ] |

### Snowflake Configuration (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| Destination Database | Database for ingested data | [ ] |
| Destination Schema | Schema within database | [ ] |
| Snowflake Role | Role with CREATE TABLE / INSERT privileges on destination | [ ] |
| Snowflake Warehouse | Warehouse for processing | [ ] |

### Prerequisites Checklist

| Prerequisite | Status |
|--------------|--------|
| User has reviewed [official Snowflake documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/hubspot/setup) | [ ] |
| Private App created in HubSpot (Settings → Integrations → Private Apps) | [ ] |
| Required scopes granted (match scopes to objects, e.g. `crm.objects.contacts.read`) | [ ] |
| Access token generated and stored securely | [ ] |
| HubSpot account has API access enabled (Professional/Enterprise tier or equivalent) | [ ] |

**Do not proceed until all items are collected and prerequisites confirmed.**

---

## Deployment Workflow

Follow the main workflow in `references/connector-main.md`. This section provides HubSpot-specific details for each step.

### 1. Network Access (SPCS Only)

Required domains for EAI (see `references/platform-eai.md`):
- `api.hubapi.com`

### 2. Network Validate (SPCS Only)

**Load** `references/ops-network-testing.md` and test connectivity:

```python
targets = [
    {"host": "api.hubapi.com", "port": 443, "type": "HTTPS"},
]
```

**If any tests fail:** Stop and resolve EAI configuration before proceeding.

### 3. Deploy

See `references/ops-flow-deploy.md`. Flow name: `hubspot`. Confirm exact name in the registry before deploying.

### 4. Handle Parameters

See [Parameters](#parameters) below, then `references/ops-parameters-main.md` for configuration commands.

**Important:** Parameter names vary by flow version. Inspect the deployed flow's parameter context before setting values. Do not hardcode names from this reference.

### 5. Asset Uploads

**None required.** Private App Token is passed as a text parameter.

### 6. Processor Updates

**None required.** Use default configuration unless the user requests specific object filters or polling intervals.

### 7. Verify Controllers

Verify controller configuration BEFORE enabling:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_processors=false
```

**If verification fails:** Fix parameter configuration before proceeding.

### 8. Enable Controllers

Enable controller services after verification passes.

See `references/ops-flow-lifecycle.md` (Enable Controllers Only section).

After enabling, check for errors:
- All controllers show `ENABLED`
- Check bulletins for authentication or connection errors

### 9. Verify Processors

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_controllers=false
```

### 10. Start

See `references/ops-flow-lifecycle.md` for starting the flow.

### 11. Validate

See [Validate Data Flow](#validate-data-flow) below.

---

## Parameters

See `references/ops-parameters-main.md` for inspection and configuration process.

| Parameter | Required | Notes |
|-----------|----------|-------|
| HubSpot Access Token | Always | Sensitive. Private App token. |
| Object Types | Always | CSV list, e.g. `Contacts,Companies,Deals`. Case-sensitive — use docs casing. |
| Updated After | Optional | Filter objects updated after this date/time. |
| Data Ingestion Schedule | Optional | Polling interval, e.g. `30 minutes`, `1 hour`. |
| Destination Database | Always | Case-sensitive. Use uppercase for unquoted identifiers. |
| Destination Schema | Always | Case-sensitive. Use uppercase for unquoted identifiers. |
| Snowflake Authentication Strategy | Always | Preferred: `SNOWFLAKE_MANAGED` (SPCS and BYOC with execute-as roles). BYOC alternative: `KEY_PAIR`. |
| Snowflake Account Identifier | KEY_PAIR only | `<org>-<account>`. Blank for managed token. |
| Snowflake Username | KEY_PAIR only | Service user. Blank for managed token. |
| Snowflake Private Key / Private Key File | KEY_PAIR only | PKCS8 PEM. One of the two is required. |
| Snowflake Private Key Password | KEY_PAIR only | If key is encrypted. |
| Snowflake Role | Always | Managed token: execute-as role. KEY_PAIR: service user role. |
| Snowflake Warehouse | Always | |
| Oversized Value Strategy | Optional | How to handle values exceeding 16 MB. |

**Sensitive values:** Ask user to provide directly. Cannot be read back once set. Never display these values - use `[REDACTED]` in confirmations.

For Snowflake authentication, see `references/ops-snowflake-auth.md`.

---

## Validate Data Flow

After starting, verify data is flowing.

### Step 1: Check Flow Status

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect:
- `running_processors` > 0
- `invalid_processors` = 0
- `bulletin_errors` = 0

### Step 2: Check Destination

The connector creates one table per object (uppercased, e.g. `CONTACTS`) plus a flattened view (`CONTACTS_VIEW`).

```sql
SHOW TABLES IN SCHEMA <database>.<schema>;
SELECT COUNT(*) FROM <database>.<schema>.CONTACTS;
SELECT * FROM <database>.<schema>.CONTACTS_VIEW LIMIT 5;
```

Initial sync for large HubSpot accounts may take several minutes.

---

## Known Issues

### StandardPrivateKeyService INVALID on SPCS

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID. Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Invalid or revoked token | Regenerate token in HubSpot Private App, update parameter |
| `403 Forbidden` on specific object | Scope not granted | Add required scope in HubSpot, regenerate token |
| `429 Too Many Requests` | HubSpot rate limit | Reduce polling frequency; check HubSpot API tier limits |
| `UnknownHostException: api.hubapi.com` | Missing EAI rule (SPCS) | Add `api.hubapi.com` to network rule |
| No data in destination | Wrong object type casing or unsupported object | Use docs casing (`Contacts`, not `contacts`); verify object name is supported |
| Destination write fails | Snowflake role lacks privileges | Grant CREATE TABLE / INSERT on schema |
| StandardPrivateKeyService INVALID | Expected on SPCS | Ignore |

Reference `references/core-troubleshooting.md` for general patterns.

---

## Next Step

After deployment and configuration, return to `references/connector-main.md` or the calling workflow.

## See Also

- `references/connector-main.md` - Connector workflow overview
- `references/ops-parameters-main.md` - Parameter configuration
- `references/ops-snowflake-auth.md` - Snowflake destination auth
- `references/platform-eai.md` - Network access (SPCS)
- `references/ops-network-testing.md` - Network connectivity testing
- `references/core-troubleshooting.md` - Error patterns
