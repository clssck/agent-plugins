---
name: openflow-observability-admin-ddl-assist
description: Customer-run admin DDL guidance for Openflow SQL action blockers such as missing grants, network rules, or external access integrations. Tier 2 -- load only when diagnostics prove an admin-owned DDL gap.
---

# Deferred Admin DDL Assist

`GRANT`, `CREATE NETWORK RULE`, and `CREATE EXTERNAL ACCESS INTEGRATION` can fix many EAI / privilege gaps, but they are Snowflake account admin operations, not Openflow runtime remediation. The agent MUST NOT execute them in the runtime-action MVP.

When diagnostics imply one of these is needed (for example, the EAI is missing, the EAI is not granted to the runtime role, or the network rule is missing a domain):

1. Prove the gap from live `SHOW`/`DESCRIBE` evidence -- not from the error string alone.
2. Identify the exact target: host, port, network rule name, EAI name, runtime FQN, runtime role from `DESCRIBE OPENFLOW RUNTIME`.
3. Present the proposed SQL as customer-run guidance, not as an agent action. Include a public docs link to [Create Snowflake role and EAI](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-create-rr).
4. State the required privileges (`ACCOUNTADMIN` or ownership on the integration / network rule). Tell the customer this is an account-level change and recommend an admin run it.
5. After the customer confirms they have applied the change, the agent MAY then run the corresponding `runtime.attach_eai` action under the standard MVP gates.

If this lane is eventually enabled for agent execution, it needs a stricter protocol than runtime actions: side-by-side current-vs-proposed config, blast-radius statement, an additional confirmation prompt, and a hard fallback to guidance if privileges or names cannot be verified. Until then, treat all admin DDL as guide-only.
