---
name: openflow-observability-escalation
description: Escalation philosophy and template for Openflow troubleshooting. Load on demand when the investigation is about to hand off to Snowflake support.
---

# Escalation

## Escalation Philosophy

**Escalate only when Snowflake engineering must intervene.** Most issues are customer-actionable -- missing permissions, misconfigured parameters, expired credentials, network rules, or source database prerequisites. For these, explain the root cause and guide the customer through the fix. The customer's Snowflake account admin or DBA can resolve the vast majority of issues without a support ticket.

**Do not escalate for:**
- Missing grants or permissions -- explain what grant is needed and who can run it (ACCOUNTADMIN, SECURITYADMIN, or the object owner)
- EAI or network rule configuration -- guide the customer through creation or updates with the public docs
- Destination parameter errors (wrong role, warehouse, user, key) -- explain what needs to change in the Openflow UI
- Source database prerequisites (missing PK, replication not enabled, credentials expired) -- guide the customer to their DBA
- Resource constraints (OOM from undersized runtime) -- explain the sizing recommendation
- Rate limiting or transient API errors -- explain the retry behavior and any customer-side mitigation

**Escalate only when:**
- The root cause requires Snowflake-internal access (e.g., flow state corruption, platform-side certificate renewal, stuck deployment, DPS down)
- The behavior indicates a product defect (e.g., malformed SQL generation, stream name construction bug)
- All documented diagnostic and remediation steps have been exhausted with no resolution
- The customer needs infrastructure changes that only Snowflake can make (e.g., SPCS truststore updates for private CAs)

When escalation is genuinely needed, present the customer with the diagnostic context to include in their support case.

## Escalation Template

**Important:** Substitute all `{placeholder}` values before presenting.

> Based on the diagnostics, this issue requires Snowflake support investigation. Open a case with:
> 1. Deployment ID: `{deployment_id}`
> 2. Runtime name: `{runtime_name}`
> 3. Error timestamp: [UTC timestamp from queries]
> 4. Error summary: [key error message]
> 5. Diagnostics run: [list queries run and key findings from each]
> 6. Connector: [if applicable]
