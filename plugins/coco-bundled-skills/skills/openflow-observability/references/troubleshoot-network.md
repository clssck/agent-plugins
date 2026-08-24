---
name: openflow-observability-troubleshoot-network
description: Diagnose EAI, network rules, domain allowlists, source DB connectivity, and PrivateLink issues via SQL-only diagnostics.
---

# Troubleshoot: Network and Connectivity

Diagnostic workflow for network and connectivity failures in Openflow. Network issues frequently cause connector failures, timeouts, and data flow problems.

## Scope

- EAI and network rule configuration for SPCS deployments
- Per-connector domain allowlist validation
- Source database connectivity patterns
- BYOC network troubleshooting guidance
- PrivateLink configuration for runtime UI access
- All diagnostics are SQL-only (Snowsight)

---

## Entry Point: Identify Network Errors

Search error logs for network-related patterns. Run this query first to confirm a network root cause.

For runtime-scoped investigations, keep the exact namespace filter below. Only broaden to `LIKE 'runtime-%'` if the affected runtime is still unknown.


```sql
WITH openflow_parsed_logs AS (
  SELECT *, TRY_PARSE_JSON(value) AS parsed_log
  FROM {event_table}
  WHERE record_type = 'LOG'
    AND resource_attributes:"k8s.container.name"::STRING NOT ILIKE '%-gateway'
    AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
)
SELECT
  timestamp,
  COALESCE(
    parsed_log:"throwable":"message"::STRING,
    parsed_log:"message"::STRING
  ) AS error_message,
  COALESCE(
    record_attributes:"LoggerName"::STRING,
    parsed_log:"loggerName"::STRING
  ) AS logger,
  COALESCE(
    record_attributes:"severity_text"::STRING,
    record_attributes:"LogLevel"::STRING,
    parsed_log:"level"::STRING
  ) AS log_level,
  COALESCE(
    parsed_log:"formattedMessage"::STRING,
    parsed_log:"message"::STRING,
    value
  ) AS message
FROM openflow_parsed_logs
WHERE COALESCE(
    record_attributes:"severity_text"::STRING,
    record_attributes:"LogLevel"::STRING,
    parsed_log:"level"::STRING
  ) IN ('WARN', 'ERROR')
  AND (
    value ILIKE '%UnknownHostException%'
    OR value ILIKE '%SocketTimeoutException%'
    OR value ILIKE '%Connection refused%'
    OR value ILIKE '%SSLHandshakeException%'
    OR value ILIKE '%EAI_AGAIN%'
    OR value ILIKE '%ConnectTimeoutException%'
    OR value ILIKE '%ORA-17002%'
    OR value ILIKE '%Socket fail to connect%'
    OR value ILIKE '%could not be established%'
    OR value ILIKE '%Broker may not be available%'
    OR value ILIKE '%Communications link failure%'
  )
ORDER BY timestamp DESC
LIMIT 100;
```

**Interpretation:**

| Error Pattern | Likely Cause |
|---------------|--------------|
| `UnknownHostException` | Domain missing from network rule, EAI not created, EAI not granted, or EAI not attached to runtime |
| `SocketTimeoutException` | Network path exists but the connection is timing out: source DB firewall / allowlist, security controls, routing, or less commonly a missing port in the network rule |
| `Connection refused` | Source DB not listening on expected port, or firewall rejecting the connection |
| `SSLHandshakeException` | SSL certificate issue -- untrusted CA, expired cert, or hostname mismatch |
| `EAI_AGAIN` | DNS resolution failure -- same root causes as UnknownHostException |
| `ConnectTimeoutException` | Network path exists but connection times out -- firewall, security group, or routing issue |
| `ORA-17002` | Oracle JDBC IO error -- network path blocked, source DB unreachable, or wrong host/port |
| `Socket fail to connect` | TCP connection attempt failed -- firewall, security group, or host unreachable |
| `could not be established` | Generic connection failure -- verify host, port, and network path |
| `Broker may not be available` | Kafka broker unreachable -- check bootstrap server address, port, and network path (SPCS: EAI domain allowlist; BYOC: security group egress) |
| `Communications link failure` | JDBC connection dropped -- network interruption, idle timeout, or firewall terminating long-lived connections |

**Branching logic:**
- SPCS deployment -> continue to [SPCS: EAI and Network Rule Diagnostics](#spcs-eai-and-network-rule-diagnostics)
- BYOC deployment -> skip to [BYOC: Network Troubleshooting](#byoc-network-troubleshooting)
- SSL-specific errors against source databases -> see [Source DB Connectivity](#source-db-connectivity). SSL errors on runtime pod TLS (inter-service communication) -> **Load** `references/troubleshoot-runtime.md`
- PrivateLink issues -> see [PrivateLink](#privatelink)

**If zero results:** Run Event Time Bounds Check from `references/core-queries.md` before broadening to 6, then 24 hours. If still empty, verify the event table is configured and receiving data (run Deployment Info from `references/core-queries-resource.md`). If the event table has data but no network errors, the issue may not be network-related -- reconsider the triage routing.

---

## SPCS: EAI and Network Rule Diagnostics

SPCS runtimes run inside Snowflake's managed infrastructure. All outbound network access is controlled by External Access Integrations (EAI) and Network Rules. If a domain or port is not explicitly allowed, the connection is blocked.

### Step 1: Query Current EAI Configuration

```sql
SHOW EXTERNAL ACCESS INTEGRATIONS;
```

Look for integrations related to Openflow. Note the integration names and whether they are `ENABLED = TRUE`.

For details on a specific integration:

```sql
DESCRIBE EXTERNAL ACCESS INTEGRATION {eai_name};
```

Check the `ALLOWED_NETWORK_RULES` property to identify which network rules are associated.

### Step 2: Query Network Rules

```sql
SHOW NETWORK RULES;
```

For each rule associated with the EAI:

```sql
DESCRIBE NETWORK RULE {network_rule_name};
```

Check the `VALUE_LIST` property -- this contains the allowed domain:port combinations.

### Step 3: Compare Against Required Domains

Extract the hostname from the error message (the host in the `UnknownHostException` or `SocketTimeoutException`). Compare it against the `VALUE_LIST` from the network rule.

Interpret timeout signals carefully:
- `SocketTimeoutException`, `ConnectTimeoutException`, and JDBC `Communications link failure` do **not** prove that an EAI is missing. They usually mean DNS resolution succeeded and the connection path is being blocked or timing out after connect attempt.
- Only diagnose "missing EAI / missing network rule" when the evidence shows the host is not allowed or not resolvable, for example `UnknownHostException`, explicit domain-not-allowed signals, the network rule VALUE_LIST being empty or not containing the target host/port, or a confirmed missing host/port in the visible network rule configuration.
- If the connector had been replicating and then failed after a customer networking change, prefer "previously working network path regressed" over "connector was never configured correctly" unless the logs prove otherwise.

**Common findings:**

| Finding | Action |
|---------|--------|
| Domain missing from VALUE_LIST | Customer-run: update the network rule VALUE_LIST to add the missing domain. Requires ACCOUNTADMIN or ownership on the network rule. See Step 4. |
| Domain present but wrong port | Same as above -- customer updates the VALUE_LIST with the correct port. |
| Host/port looks allowed but connections time out | Treat as a connectivity-path problem first: verify source DB firewall / allowlist, PrivateLink or peering if applicable, and intermediate routing/security controls before concluding the EAI is wrong. |
| No EAI exists for this connector | Customer-run: create a network rule and EAI per the setup docs. Requires ACCOUNTADMIN. See Step 5. |
| EAI exists but not attached to runtime | Customer-run: attach the EAI via the Openflow UI (Runtimes > ... menu > External access integrations). See Step 6. |
| EAI not granted to runtime role | Customer-run: grant USAGE on the EAI to `{runtime_role}`. Requires ACCOUNTADMIN or ownership on the integration. See Step 5. |

### Step 4: Report Missing Domains

If the network rule exists but is missing required domains:

- **Root cause:** Network rule `{network_rule_name}` is missing domain `{source_host}` in its VALUE_LIST.
- Report the current VALUE_LIST (from DESCRIBE) and the missing domain(s).
- **Customer-run:** The customer or their Snowflake account admin can update the network rule VALUE_LIST directly to add the missing domain(s). Reference: [Create Snowflake role and EAI](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-create-rr)

### Step 5: Report Missing Network Rule / EAI

If no network rule or EAI exists for the connector:

- **Root cause:** No External Access Integration configured for {connector_type} connectivity.
- The connector needs a network rule (TYPE=HOST_PORT, MODE=EGRESS) for `{source_host}:{port}`, an EAI wrapping it, and USAGE granted to `{runtime_role}`.
- **Customer-run:** Guide the customer or their Snowflake account admin to create the network rule and EAI following [Create Snowflake role and EAI](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-create-rr). After creation, the EAI must be attached to the runtime via the Openflow UI.

### Step 6: Report EAI Not Attached

If the EAI exists and is properly configured but not attached to the runtime:

- **Root cause:** EAI `{eai_name}` is not attached to the runtime.
- **Customer-run:** Attach the EAI via the Openflow UI (Runtimes > ... menu > External access integrations).

#### Optional Openflow SQL action candidate

If the runtime is SQL-managed and the customer would prefer the agent attach the EAI for them, this is an MVP-allowlisted action.

- Internal action ID (do not show to customer): `runtime.attach_eai`
- Trigger phrase to offer the customer: "If your runtime is SQL-managed, I can attach `{eai_name}` for you with a single `ALTER OPENFLOW RUNTIME` after you confirm. Want me to preview the change?"
- On acceptance, hand off to **Openflow SQL Action Mode**: **Load** `references/openflow-sql/action-guidelines.md` and `references/openflow-sql/runtime-actions.md`, then follow the [runtime.attach_eai](openflow-sql/runtime-actions.md#runtimeattach_eai----attach-an-existing-eai-to-a-sql-managed-runtime) template. Every gate in [SKILL.md Openflow SQL Action Mode](../SKILL.md#openflow-sql-action-mode) must pass first.
- Do **not** offer this candidate when:
  - `SHOW OPENFLOW RUNTIMES` returns zero rows for the runtime (legacy or invisible) -- guide via UI instead.
  - The deployment is BYOC -- EAI does not apply.
  - The EAI does not exist or is not granted `USAGE` to the runtime role -- those are admin DDL gaps and remain customer-run guidance via `references/openflow-sql/admin-ddl-assist.md`.

### Wildcard Behavior

Snowflake wildcards only match a **single subdomain level**:
- `*.example.com` matches `api.example.com` but NOT `api.v2.example.com`
- `*.sharepoint.com` matches `contoso.sharepoint.com` but NOT `files.contoso.sharepoint.com`

If you see `UnknownHostException` despite having a wildcard, check if the actual hostname has deeper subdomains. Add explicit entries for deeper subdomains or use a wildcard at the appropriate level.

---

## Per-Connector Domain Allowlist Reference

Per-connector domain tables have been moved to the respective connector file under `references/connectors/`. **Load** the connector-specific file for domain requirements.

> **Note:** Domain allowlists are current as of this skill version. Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated recently.

| Connector | File |
|-----------|------|
| PostgreSQL CDC | `references/connectors/postgresql.md` |
| MySQL CDC | `references/connectors/mysql.md` |
| SQL Server CDC | `references/connectors/sql-server.md` |
| Oracle CDC | `references/connectors/oracle.md` |
| Kafka | `references/connectors/kafka.md` |
| Kinesis | `references/connectors/kinesis.md` |
| Salesforce | `references/connectors/salesforce.md` |
| SaaS connectors (Google Drive, SharePoint, Box, Jira, etc.) | `references/connectors/saas-connectors.md` |

### All Connectors (Snowflake Endpoints)

Every SPCS connector requires outbound access to the customer's Snowflake account endpoint for Snowpipe Streaming ingest. This is typically handled by the platform but should be verified if ingest-related errors appear.

---

## BYOC: Network Troubleshooting

BYOC deployments run in the customer's own cloud account. EAI and network rules do not apply. Network access is governed by the customer's cloud infrastructure: security groups, NAT gateways, VPC peering, route tables, and firewall rules.

### What SQL Can Tell You

Event table logs still capture error messages from BYOC runtimes. The entry point query above works for BYOC -- use it to identify the specific error pattern and target host.

However, SQL cannot verify cloud networking configuration. The customer must check their cloud environment directly.

For BYOC deployment-level OAuth failures, do not let account metadata queries override stronger event-table evidence:
- If DPS heartbeat logs show repeated OAuth `403` / token endpoint failures to Snowflake control-plane endpoints, treat the primary diagnosis as a deployment-level control-plane connectivity or allowlist problem.
- Do not conclude that the data plane integration was deleted only because `SHOW OPENFLOW DATA PLANE INTEGRATIONS` is empty or `DESCRIBE OPENFLOW DATA PLANE INTEGRATION` returns `does not exist or not authorized`.
- Do not conclude that Snowflake-side allowlist issues are ruled out only because `SHOW NETWORK POLICIES` returns no rows. Account-level policy visibility can be limited, and the relevant allowlist can still be missing or outdated.

### Common BYOC Network Issues

The guidance below uses AWS terminology. For GCP and Azure equivalents, see the GCP BYOC and Azure BYOC sections below.

**Cloud-specific terminology:** The steps below use AWS terminology. For GCP or Azure BYOC deployments, follow the same diagnostic steps but substitute the equivalent cloud terms from the GCP BYOC and Azure BYOC sections below.

**1. NAT Gateway missing or misconfigured**

BYOC runtimes in private subnets require a NAT Gateway for outbound internet access. If the NAT Gateway is missing or the route table does not route `0.0.0.0/0` to it, all outbound connections fail.

Ask the customer to verify:
- NAT Gateway exists and is in an `Available` state
- Route table for private subnets has a `0.0.0.0/0` route pointing to the NAT Gateway

**2. Security group blocking outbound traffic**

Default security groups may allow all outbound, but custom groups might restrict egress.

Ask the customer to verify:
- Security group attached to EKS worker nodes allows outbound to the target host:port
- For database connectors: outbound to the DB host on the DB port
- For SaaS connectors: outbound on port 443

**3. VPC peering or transit gateway not configured**

If the source database is in a different VPC, peering or transit gateway must be configured.

Ask the customer to verify:
- VPC peering connection exists and is `Active`
- Route tables in both VPCs have routes for the peer VPC CIDR

**4. Network policy blocking OAuth**

BYOC data plane agents authenticate to the Snowflake control plane via OAuth. If a Snowflake network policy blocks the agent's egress IP, the deployment shows as "Not Reporting" or "Inactive."

Ask the customer to verify:
- The Snowflake account's network policy allows inbound from the BYOC deployment's NAT Gateway IPs
- The `ALLOWED_NETWORK_RULE_LIST` on the account includes the BYOC IP range

When BYOC logs show heartbeat failures plus OAuth `403` or token endpoint failures, do not present this as only a cloud-side security group / NAT problem. The customer-facing recommendation must include both:
- Snowflake account network policy allowlist verification for the BYOC NAT egress IPs
- BYOC-side egress path checks such as NAT Gateway, route table, security group, network ACL, proxy, or firewall rules for outbound HTTPS to Snowflake control-plane endpoints

When these OAuth `403` signals are present, do not tell the customer that networking has been ruled out or that the integration is missing/deleted unless you have stronger evidence than the metadata queries above.

DPS heartbeat can be verified with DPS Heartbeat Check (BYOC variant) from `references/core-queries-resource.md`.

**5. BYOC Pre-flight Validation**

For new deployments or after AWS networking changes, the customer can run the BYOC Pre-flight Validation workflow documented in [Validate your BYOC deployment](https://docs.snowflake.com/en/user-guide/data-integration/openflow/byoc-validate-vpc-config). This is a CloudFormation-based tool that verifies:

- VPC components (subnets, gateways, routing)
- Network connectivity to Openflow services and endpoints
- Security group rules and IAM permissions

To use it:
1. Create a new BYOC deployment in the Openflow Control Plane
2. Download the CloudFormation template by clicking **Download Validator** in the confirmation dialog
3. Apply the template in AWS
4. SSH to the EC2 instance and run `/home/ec2-user/byoc-validator.sh`
5. Review the results file: `/home/ec2-user/byoc-validation-results-YYYYMMDDHHMMSS.txt`

For existing VPCs, use `/home/ec2-user/byo-vpc-validator.sh` instead.

### GCP BYOC

For GCP-based BYOC deployments, replace AWS-specific references:
- **Security groups** -> GCP VPC firewall rules
- **NAT Gateway** -> Cloud NAT
- **Route tables** -> VPC routes

The customer should verify GCP firewall rules allow egress to required domains on ports 443, 1433, 3306, 5432, and 1521 as applicable for their connectors.

### Azure BYOC

For Azure-based BYOC deployments:
- **Security groups** -> Network Security Groups (NSGs)
- **NAT Gateway** -> Azure NAT Gateway
- **VPC peering** -> VNet peering

The customer should verify NSG outbound rules allow traffic to required destinations. If using Azure Private Link, verify the private endpoint configuration.

---

## Source DB Connectivity

These patterns apply to both SPCS and BYOC when the runtime can resolve DNS but cannot establish a connection to the source database.

### Source DB Not Allowing Connections

**Symptom:** `Connection refused` or `SocketTimeoutException` after DNS resolves successfully.

**Guidance for the customer:**

For SPCS deployments:
- The source DB must allow inbound connections from Snowflake's SPCS egress IPs
- SPCS egress traffic uses NAT Gateway IPs specific to the deployment region
- The customer can find their SPCS egress IP range by running `SELECT SYSTEM$GET_SNOWFLAKE_PLATFORM_INFO()` as ACCOUNTADMIN, then add those IPs to their source DB's firewall allowlist
- Where possible, use DNS-based allowlisting rather than IP-based (NAT Gateway IPs may change during infrastructure updates)
- If the connector previously worked and now times out, describe this as a source-side or network-path regression unless you have direct evidence that the required host:port is missing from the EAI/network rule configuration

For BYOC deployments:
- The source DB must allow inbound connections from the BYOC VPC's NAT Gateway IP or VPC CIDR
- If the source DB is in the same VPC, ensure the security group allows inbound from the EKS worker node security group
- If the source DB is in a different VPC, ensure VPC peering and route tables are configured

### SSL Certificate Issues

**Symptom:** `SSLHandshakeException` when connecting to the source database. May also surface as a wrapped `Cannot create PoolableConnectionFactory` from postgres JDBC, or as a generic "Failed to connect to source database" message in the connector's canvas bulletin -- in those cases the inner cause may be `CertPathValidatorException` / `certificate verify failed`.

**Common causes:**
- Source DB uses a self-signed certificate not trusted by the JVM default truststore
- Source DB certificate has expired
- Certificate CN/SAN does not match the hostname used in the connector configuration
- Intermediate CA certificates are missing from the chain
- AWS RDS source DB still uses the expired `rds-ca-2019` CA and the connector is configured to validate the server certificate without trusting the matching RDS CA bundle

**Guidance for the customer:**
- Verify the source DB's SSL certificate is valid and not expired
- Ensure the hostname in the connector configuration matches the certificate's CN or SAN
- For BYOC, custom CA certificates can be managed through the deployment configuration
- For AWS RDS source DBs specifically: check the RDS instance's CA configuration. `rds-ca-2019` expired in August 2024. If the connector requires server certificate validation, the customer should rotate the RDS instance to a current RDS CA supported by their engine and make sure the connector runtime trusts the matching RDS CA bundle. Rotating the RDS CA and updating the client/runtime trust store are separate steps.

**Connector-specific SSL configuration paths:**

The right fix depends on which connector definition the customer is using:

| Connector capability | How SSL trust is configured |
| --- | --- |
| Connectors that expose a `Database Root Certificate` parameter context asset (the legacy PostgreSQL CDC connector, MySQL, SQL Server, Oracle) | Customer uploads the source DB's root CA cert as a parameter context asset. See [SSL Configuration](connectors/connector-shared-generic.md#ssl-configuration-database-connectors). |
| Connectors that take a single JDBC URL (the newer URL-based PostgreSQL CDC connector definitions, including SQL-managed `OPENFLOW_POSTGRES_CDC`) | No root-cert upload field. SSL behavior is controlled by JDBC URL params. For pgJDBC, `sslmode=require` encrypts without server certificate or hostname validation; `sslmode=verify-ca` and `sslmode=verify-full` validate the server certificate and require a trusted root CA. `sslfactory=org.postgresql.ssl.NonValidatingFactory` also disables certificate validation and should only be treated as a temporary diagnostic workaround with customer security approval, not as production guidance. If production requires server identity verification and there is no connector-level CA asset, escalate for a supported runtime truststore or connector configuration path. |

For SPCS deployments where the runtime truststore itself needs updating with a customer-managed CA, this requires Snowflake support.

### Source DB Firewall Configuration

**Symptom:** Intermittent `ConnectTimeoutException` or `SocketTimeoutException`.

**Guidance for the customer:**
- Check if the source DB has connection rate limiting or IP-based throttling
- Verify the source DB's max connections limit is not being exceeded by Openflow plus other clients
- For cloud-hosted databases (RDS, Cloud SQL, Azure SQL), check the cloud provider's network ACLs and security groups in addition to the DB-level firewall

---

## PrivateLink

PrivateLink allows customers to access the Openflow Runtime UI through private connectivity instead of the public internet. This is optional.

> **SPCS / AWS only.** For Azure Private Link or GCP Private Service Connect, guide the customer to follow their cloud provider's documentation for private endpoint configuration.

For full setup instructions, see [Set up PrivateLink UI access](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-configure-pr-ui).

### Determining PrivateLink URLs

The customer must run the following as ACCOUNTADMIN:

```sql
SELECT SYSTEM$GET_PRIVATELINK_CONFIG();
```

From the output, identify:
- `privatelink-vpce-id` -- the VPC endpoint service ID
- `openflow-privatelink-url` -- the PrivateLink URL for the Openflow UI (format: `<org>-<account>.openflow.<shard-id>.privatelink.snowflakecomputing.com`)

The Runtime UI PrivateLink URL follows the format:
- `of--<org>-<account>.spcs.<shard-id>.privatelink.snowflake.app`

### PrivateLink Setup Steps

1. Create a VPC endpoint in the customer's AWS account targeting the `privatelink-vpce-id`
2. Create a Route 53 private hosted zone for `privatelink.snowflakecomputing.com` associated with the deployment VPC
3. Create a Route 53 private hosted zone for `privatelink.snowflake.app` associated with the deployment VPC
4. Add CNAME records:
   - `openflow-privatelink-url` -> VPC endpoint DNS name
   - Runtime UI URL -> VPC endpoint DNS name
5. Verify DNS resolution from within the VPC
6. When creating a new SPCS deployment, ensure the **PrivateLink** option is enabled

If the Snowflake account previously had PrivateLink configured for Snowsight, the existing VPC endpoint can be reused -- just add the Openflow DNS records to Route 53.

### PrivateLink Troubleshooting

If the customer cannot access the Runtime UI via PrivateLink:

- Verify the VPC endpoint is in `Available` state
- Verify DNS resolution: the PrivateLink URLs should resolve to private IPs within the VPC
- Verify the Route 53 private hosted zones are associated with the correct VPC
- Verify the CNAME records point to the VPC endpoint's DNS name
- Check that the security group on the VPC endpoint allows inbound HTTPS (port 443)

---

## Escalation Criteria

Escalate to Snowflake support only when all customer-actionable steps have been exhausted:

- Network errors persist after verifying EAI, network rules, domain allowlists, and source DB firewall are all correct
- SSL errors persist after verifying certificate validity, hostname matching, and connector SSL configuration
- BYOC deployment shows "Not Reporting" after verifying network policy, OAuth connectivity, and NAT Gateway configuration
- SPCS runtime truststore needs a private CA certificate that cannot be handled through connector SSL parameters
- PrivateLink DNS resolution fails despite correct Route 53 configuration and VPC endpoint setup

Include in the escalation:
1. **Deployment ID**
2. **Error pattern** (exact exception from logs)
3. **Target host:port** from the error
4. **EAI and network rule configuration** (output of SHOW/DESCRIBE commands)
5. **Connector type**
6. **Steps already taken**

Use the escalation template from `references/escalation.md` for the full format.
