---
name: openflow-platform-eai
description: Set up External Access Integrations (EAI) and Network Rules for Openflow SPCS deployments. Enables Openflow Runtimes to communicate with external data sources.
---

# External Access Integrations (EAI)

External Access Integrations allow Openflow Runtimes to communicate with external services (databases, APIs, etc.) through Snowflake's network security layer.

**Note:** These operations modify Snowflake account state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

**Getting infrastructure facts (by surface):** this reference looks up deployment/runtime facts (deployment type, runtime name/db/schema, execute-as role). The `cat ~/.snowflake/cortex/memory/...json | jq ...` snippets below are the **CLI** form (read from the local cache). On the **Snowsight / SQL-only surface** there is no cache — obtain the same values via SQL instead: `SHOW OPENFLOW DEPLOYMENTS`, `SHOW OPENFLOW RUNTIMES IN ACCOUNT`, `DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>` (see `references/core-session-sql.md`). Likewise, SQL shown below as `snow sql -c <CONNECTION> -q "..."` is the CLI form — on the Snowsight surface run the SQL statement directly (there is no `snow` CLI).

## SPCS Only

**This reference applies to SPCS (Snowflake-managed) deployments only.**

BYOC (Bring Your Own Cloud) deployments run in the customer's cloud account and have direct network access. They do not require EAI configuration.

Check your deployment type — `SHOW OPENFLOW DEPLOYMENTS` (the `type` column: `SNOWFLAKE` = SPCS, `BYOC` = BYOC). (CLI with a cache present: `jq '.deployments[].deployment_type'`.)

## Scope

- Network Rules and External Access Integrations for SPCS
- Enabling external connectivity for connectors and custom flows
- Does NOT apply to BYOC (which has direct network access)

## Prerequisites

**Database context is required.** Network Rules are schema-scoped objects. All Network Rule SQL commands must use fully qualified names (`<db>.<schema>.<rule_name>`) or the session must have a database and schema set. The examples below use fully qualified names.

Get the runtime's database and schema from its schema-qualified name — `SHOW OPENFLOW RUNTIMES IN ACCOUNT` (`database_name`, `schema_name` columns), or `DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>`. (CLI with a cache present: `jq '.deployments[].runtimes[] | {name: .runtime_name, database: .runtime_db, schema: .runtime_schema}'`.)

**Execute-as role is required.**

Identify the runtime's execute-as role by surface:
- **SQL surface (Snowsight, or CLI + Gen2):** `SHOW OPENFLOW RUNTIMES IN ACCOUNT;` then `DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>;` (read `execute_as_role`).
- **CLI (cache present):**
  ```bash
  cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json | jq '.deployments[].runtimes[] | {name: .runtime_name, role: .execute_as_role}'
  ```

| Result | Action |
|--------|--------|
| Execute-as role identified | Continue with EAI setup |
| Not found (CLI, no cache) | Load `references/bootstrap-cli.md` to run discovery |

## Tool Hierarchy

| Operation | Tool | Notes |
|-----------|------|-------|
| Create Network Rule | SQL | Snowflake account level |
| Create EAI | SQL | Snowflake account level |
| Attach EAI to Runtime | SQL on SOM / **UI** pre-SOM | `ALTER OPENFLOW RUNTIME` on SOM accounts; Openflow Control Plane UI on pre-SOM accounts (see Step 6) |

## Workflow: Check Existing EAIs First

**Always check what exists before creating.** EAIs and network rules may already cover the required domains, or an existing rule can be extended.

### Step 1: Query Existing EAIs Granted to Execute-As Role

```bash
snow sql -c <CONNECTION> -q "SHOW GRANTS TO ROLE <execute_as_role>;" --format json | jq '[.[] | select(.granted_on == "INTEGRATION" and .privilege == "USAGE") | .name]'
```

**Always run this fresh.** Do not rely on previously cached or remembered values.

### Step 2: Inspect Existing Network Rules

```sql
SHOW NETWORK RULES IN SCHEMA <db>.<schema>;
```

For each EAI found in Step 1, inspect its network rules:

```sql
DESCRIBE INTEGRATION <eai_name>;
```

Record `ALLOWED_NETWORK_RULES`.

Then inspect the network rule(s) it references:

```sql
DESCRIBE NETWORK RULE <db>.<schema>.<rule_name>;
```

### Step 3: Decision Point

Present findings to the user and ask:

| Situation | Prompt |
|-----------|--------|
| Existing EAI covers required domains | "It looks like `<eai_name>` already covers the domains needed for this connector. No changes needed." |
| Existing EAI partially covers domains | "I found `<eai_name>` attached to your runtime with network rule `<rule_name>`. It currently allows [domains]. Should I add [missing domains] to this rule, or would you prefer a separate EAI?" |
| No relevant EAIs exist | "No existing EAIs cover the required domains. I'll create a new network rule and EAI." |

**Reuse vs dedicated (Gen2):** A dedicated runtime naturally results in one EAI per connector, which keeps network rules scoped tightly. A shared EAI only makes sense when multiple connectors share a runtime. Do not mandate either model — let the user decide based on how their runtimes are organised.

**If reusing (add domains only):** Continue to [Workflow: Alter Existing Network Rule](#workflow-alter-existing-network-rule).

**If creating new:** Continue to [Workflow: Create EAI](#workflow-create-eai).

**Always include an explicit port** in every VALUE_LIST entry (e.g., `host.example.com:443`). Omitting the port will not work.

---

## Workflow: Alter Existing Network Rule

Use when adding domains to a network rule that is already referenced by an EAI attached to the runtime.

### Step 1: Get Current Domains

```sql
DESCRIBE NETWORK RULE <db>.<schema>.<existing_rule>;
```

Note the current `VALUE_LIST`.

### Step 2: Alter Network Rule

The VALUE_LIST is replaced in full, so include both existing and new domains:

```sql
USE ROLE SECURITYADMIN;

ALTER NETWORK RULE <db>.<schema>.<existing_rule> SET
  VALUE_LIST = ('<existing_domain1>:<port>', '<existing_domain2>:<port>', '<new_domain>:<port>');
```

If the rule predates this skill and its COMMENT does not yet carry the `[openflow]` tag, append the tag so it is discoverable later (append — never overwrite the existing comment):

```sql
ALTER NETWORK RULE <existing_rule> SET COMMENT = '<existing comment text>. [openflow]';
```

### Step 3: Verify

```sql
DESCRIBE NETWORK RULE <db>.<schema>.<existing_rule>;
```

Confirm the new domains appear in the VALUE_LIST. No further steps are needed -- the EAI already references this rule and is already attached to the runtime.

---

## Workflow: Create EAI

Use when no existing EAI is suitable. **Execute these steps in order. Do NOT run concurrently.**

### Required Privileges

Creating new Network Rules and External Access Integrations requires:

- **CREATE INTEGRATION** privilege on the account
- **USAGE** privilege on any secret the integration uses
- **USAGE** privilege on the secret's schema

Roles that typically have these privileges:
- **SECURITYADMIN** - Recommended for EAI/Network Rule management
- **ACCOUNTADMIN** - Also works, but broader than needed

If the admin role lacks CREATE INTEGRATION, an ACCOUNTADMIN can grant it:

```sql
-- Run as ACCOUNTADMIN
GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE <openflow_admin_role>;
```

### Pre-Flight Verification

Before creating anything, verify the current role has the required privileges:

```sql
-- Check grants on the role you intend to use
SHOW GRANTS TO ROLE <openflow_admin_role>;
```

```bash
# Filter for CREATE INTEGRATION specifically
snow sql -c <CONNECTION> --role <openflow_admin_role> -q "SHOW GRANTS TO ROLE <openflow_admin_role>;" --format json \
  | jq '[.[] | select(.privilege == "CREATE INTEGRATION" or .privilege == "ALL PRIVILEGES") | {privilege, granted_on}]'
```

| Result | Action |
|--------|--------|
| Shows CREATE INTEGRATION or ALL PRIVILEGES on ACCOUNT | Proceed to Step 1 |
| Empty list | Request grant from ACCOUNTADMIN (see above) |
| Role does not exist or access denied | Request to switch to ACCOUNTADMIN and investigate |

### Step 1: Create Network Rule

**Confirm the host(s) as their own question first.** Before creating the rule,
show the exact `host:port` value(s) that will be allowed for outbound egress and
confirm them on their own — do not fold this into a general "proceed?" prompt:

> "The network rule will allow egress to: `host.example.com:443`. Is this the correct host and port? If you're not sure of the host yet, we can pause here and add the rule once you know it."

Only run the SQL below once the user has confirmed the `host:port` value(s). If the
host is not yet known, defer this step rather than guessing.

```sql
USE ROLE SECURITYADMIN;

CREATE NETWORK RULE <db>.<schema>.<connector>_openflow_network_rule
  TYPE = HOST_PORT
  MODE = EGRESS
  VALUE_LIST = ('<domain1>:<port>', '<domain2>:<port>')
  COMMENT = 'Network rule for Openflow <Connector> egress. [openflow]';
```

### Step 2: Verify Network Rule

**Do not proceed until this succeeds:**

```sql
DESCRIBE NETWORK RULE <db>.<schema>.<connector>_openflow_network_rule;
```

| Result | Action |
|--------|--------|
| Returns rule details | Continue to Step 3 |
| Error | Check for typos, verify privileges |

### Step 3: Create External Access Integration

**Gen1 connectors / custom flows / no auth secret** (network access only):

```sql
USE ROLE SECURITYADMIN;

CREATE EXTERNAL ACCESS INTEGRATION <connector>_openflow_eai
  ALLOWED_NETWORK_RULES = (<db>.<schema>.<connector>_openflow_network_rule)
  ENABLED = TRUE
  COMMENT = 'External Access Integration for Openflow <Connector> connectivity. [openflow]';
```

### Step 4: Verify EAI

```sql
DESCRIBE INTEGRATION <connector>_openflow_eai;
```

### Step 5: Grant USAGE to Execute-As Role

```sql
GRANT USAGE ON INTEGRATION <connector>_openflow_eai TO ROLE <execute_as_role>;
```

Replace `<execute_as_role>` with the runtime's execute-as role (identified during session init).

### Step 6: Attach EAI to Runtime

On SOM accounts, attach via SQL (preferred):

```sql
ALTER OPENFLOW RUNTIME <db>.<schema>.<name> SET EXTERNAL_ACCESS_INTEGRATIONS = (<connector>_openflow_eai);
```

If the runtime already has EAIs attached, include all of them in the list — this replaces the full set.

If the SQL command fails or the account is pre-SOM, attach via the Openflow Control Plane UI:

1. Navigate to the **Openflow Control Plane**
2. Find the Runtime in the list
3. Click the vertical **"..."** menu
4. Select **"External access integrations"**
5. Select the EAI from the dropdown
6. Click **Save**

**Note:** Restarting the runtime is NOT required - changes apply immediately.

## Common Patterns

### Connector Required Domains

When setting up EAI for a pre-built Snowflake connector, fetch the current required domains from Snowflake documentation:

**URL:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list

Find the section for the specific connector and extract the required domains. This does not apply to custom flows or non-connector EAI work -- for those, use the host and port information provided by the user.

### Database Connectors (HOST_PORT Specific)

Database connectors require exact host:port specifications. The Network Rule controls both DNS resolution and TCP connectivity:

```sql
CREATE NETWORK RULE <db>.<schema>.my_postgres_network_rule
  TYPE = HOST_PORT
  MODE = EGRESS
  VALUE_LIST = ('<customer-database-host>:<port>');
```

> **The host must resolve when the rule is created.** `CREATE`/`ALTER NETWORK RULE` DNS-validates every `VALUE_LIST` entry at statement time and fails with `invalid value for property 'VALUE_LIST'` if a host does not resolve — a placeholder domain, a typo, or a source database that is currently stopped. Create the rule with the real, reachable endpoint; do not use a placeholder host to fill in later. (This is distinct from the runtime-egress checks below, which are about a host missing from an already-created rule.)

Default ports:
- PostgreSQL: 5432
- MySQL: 3306
- SQL Server: 1433

### SaaS Connectors (Multiple Rules)

SaaS connectors typically need multiple endpoints for authentication, APIs, and data access. These often require wildcards.

**Wildcard Limitation:** Snowflake wildcards only match a **single subdomain level**. For example:
- `*.example.com` matches `api.example.com` but NOT `api.v2.example.com`
- `*.sharepoint.com` matches `contoso.sharepoint.com` but NOT `files.contoso.sharepoint.com`

If you need to match deeper subdomains, only use a wildcard at the top most element.

**Example: SharePoint**

```sql
-- Single rule with all required endpoints
CREATE NETWORK RULE <db>.<schema>.sharepoint_network_rule
  TYPE = HOST_PORT
  MODE = EGRESS
  VALUE_LIST = (
    'login.microsoftonline.com:443',
    'login.microsoft.com:443',
    'graph.microsoft.com:443',
    '*.sharepoint.com:443'
  );

CREATE EXTERNAL ACCESS INTEGRATION sharepoint_eai
  ALLOWED_NETWORK_RULES = (<db>.<schema>.sharepoint_network_rule)
  ENABLED = TRUE;
```

**Key Pattern:** Some connectors need multiple endpoint types, preferably in a single rule:
- **Authentication endpoints** - OAuth, login services
- **API endpoints** - Graph API, REST APIs
- **Data endpoints** - The actual service hosting user data

## Troubleshooting

### "UnknownHostException" Error

**Cause:** Host not in any Network Rule -- DNS resolution is blocked. The Network Rule may be missing the required domain, or the EAI may not be created, granted to the execute-as role, or attached to the Runtime.

**Resolution:**
1. Check the full error message for the exact hostname -- it may be a redirect domain that differs from the configured host
2. Check the connector's required domains in the docs
3. Create/update the network rule to include the missing domain
4. Create the EAI if missing
5. Grant USAGE to execute-as role
6. Attach EAI to Runtime via `ALTER OPENFLOW RUNTIME ... SET EXTERNAL_ACCESS_INTEGRATIONS` (or UI if pre-SOM)

### "SocketTimeoutException" Error

**Cause:** DNS resolved successfully but TCP connection to the port failed. The port is not included in the Network Rule, or is blocked along the route.

**Resolution:**
- Check the full error message for a redirect domain -- services may redirect to a different host that also needs to be in the Network Rule
- Verify the Network Rule VALUE_LIST includes the correct port (e.g., `host:5432` not just `host`)
- See also [Blocked Ports on SPCS](#blocked-ports-on-spcs) if the port appears correct

### UnknownHostException Despite Wildcard

**Symptom:** You have a wildcard like `*.example.com` but still get UnknownHostException for a host like `api.v2.example.com`.

**Cause:** Snowflake wildcards usually only match a single subdomain level. `*.example.com` matches `api.example.com` but NOT `api.v2.example.com` (two levels deep).

**Resolution:**
- Add explicit entries for deeper subdomains: `api.v2.example.com:443`
- Or add wildcards only at the top level: `*.v2.example.com:443`
- Check the actual hostname in the error message and add it explicitly if the pattern is unclear

### "Insufficient privileges" or "Access Denied" on CREATE

**Cause:** The current role lacks CREATE INTEGRATION or CREATE NETWORK RULE privileges on the account.

**Resolution:**
1. Check which role is active: `SELECT CURRENT_ROLE();`
2. Run the pre-flight verification query (see [Pre-Flight Verification](#pre-flight-verification))
3. If the privilege is missing, ask the user to have an ACCOUNTADMIN run:
   ```sql
   GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE <their_role>;
   ```
4. After granting, re-run the pre-flight check to confirm

### "Integration not found" or USAGE Grant Fails

**Cause:** The EAI name is misspelled, was created in a different schema/database context, or the GRANT is being run with a role that does not own the integration.

**Resolution:**
1. List existing integrations: `SHOW INTEGRATIONS;`
2. Verify the exact name matches (case-sensitive)
3. Ensure the GRANT is run by the role that created the integration, or by ACCOUNTADMIN

### SQL Execution Fails with 404

**Cause:** Snowflake account identifier format may be incorrect.

- **Correct format:** `ORG-ACCOUNT` (e.g., `SFPSCOGS-MIGRATION_AWS_EAST`)
- **Probably incorrect:** Full URL format (e.g., `PTA96169.us-east-1.snowflakecomputing.com`)

### Blocked Ports on SPCS

**Symptom:** Connection fails despite apparently correct Network Rule and EAI configuration. DNS resolves, but TCP connection times out or is refused on a well-known low-numbered service port.

**Cause:** SPCS may block certain ports as a security measure without reporting that it is doing so. This is known to affect protocols that are common attack vectors (e.g., SMB on port 445).

**Resolution:** If the user is connecting on a well-known service port and everything else appears correct, discuss with the user whether the protocol's default port may be blocked by SPCS. Ask them to test with the source reconfigured on a different port. This primarily affects low-level service ports, not standard ports like 443 or typical database ports.

### Verify EAI is Granted and Attached

To check which EAIs are granted to an execute-as role:

```bash
snow sql -c <CONNECTION> -q "SHOW GRANTS TO ROLE <execute_as_role>;" --format json | jq '[.[] | select(.granted_on == "INTEGRATION" and .privilege == "USAGE") | .name]'
```

**Always run this fresh** rather than relying on previously remembered values. EAI grants change frequently.

This confirms the USAGE grant exists. To verify the EAI is also **attached** to the runtime (a separate step), check via SQL:

```bash
snow sql -c <CONNECTION> -q "DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>;" --format json | jq '.[0].external_access_integrations'
```

On pre-SOM accounts, check the Openflow Control Plane UI instead.

## Related References

- `references/bootstrap-cli.md` - Find execute-as role via discovery
- `references/core-guidelines.md` - Deployment types (SPCS vs BYOC)
