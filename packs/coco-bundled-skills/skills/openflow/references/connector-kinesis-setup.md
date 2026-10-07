---
name: openflow-connector-kinesis-setup
description: Initial setup of the Openflow Connector for Amazon Kinesis Data Streams. Creates the required AWS objects (Kinesis stream, IAM user/policy/keys) and Snowflake objects (database, schema, destination table, role, grants), configures the connector parameters and secrets, and starts it under explicit user control. Load when performing initial Kinesis connector setup (AWS stream, IAM credentials, Snowflake table/role/grants).
---

# Kinesis Connector: Initial Setup

This reference walks through everything required to stand up the Openflow Connector for Amazon Kinesis Data Streams from scratch — on the **AWS** side and the **Snowflake / Openflow** side — then configures and starts the connector.

## Golden Rules (apply throughout)

1. **Confirm before every create or modify.** Any operation that creates, alters, grants, or deletes an object in AWS or Snowflake requires explicit user confirmation first. State exactly what you will run, then ask "Should I proceed?".
2. **Assume objects may already exist.** Before offering to create anything (stream, IAM user, database, schema, table, role), **ask for the existing name first**. Only offer to create it if the user confirms it does not exist.
3. **Separate confirmation gates.** Treat these as independent blocks, each gated on its own:
   - Creating the **Kinesis stream** (data plane).
   - Creating the **AWS IAM credentials** (user + policy + access keys for the connector).
   - Creating **Snowflake objects** (database / schema / table).
   - **Granting** the connector/execute-as role access.
4. **Never start the connector automatically.** After configuration and verification, always ask whether the agent should start it or the user will start it themselves.

---

## Prerequisites

**State these requirements to the user up front, before doing anything else**, so they can prepare:

- **AWS CLI installed and configured** with credentials that can access the **specific AWS account** where the Kinesis stream and IAM objects should live.
- **An Openflow runtime** to install the connector into. If unsure, **Load** `references/bootstrap-cli.md`.
- A naming convention (a shared prefix keeps resources easy to find and clean up).

### Preflight checks (must pass before any AWS work)

Do not create, read, or modify any AWS object until every check below passes. **If a check fails, stop and tell the user exactly what to configure, then continue only once they confirm it is done** — do not try to work around it.

1. **Ask which AWS account** (ID or alias) the user wants the resources created in. Record it as the **target account**.

2. **Verify the AWS CLI is installed and authenticated:**
   ```bash
   # Runs in CoCo bash sandbox (Linux) - safe on any host OS
   aws sts get-caller-identity
   ```
   - Command not found or not configured → **stop**: ask the user to install and configure the AWS CLI (`aws configure`, `aws configure sso`, or exported credentials), then resume.
   - `ExpiredTokenException` / `InvalidClientTokenId` → **stop**: ask the user to refresh their session (e.g. `aws sso login --profile <profile>`), then re-verify.

3. **Verify the CLI targets the TARGET account.** Compare the `Account` field returned above with the target account from step 1.
   - **If they differ, do NOT proceed** — the CLI is pointed at the wrong account. Ask the user to select the correct profile/credentials, e.g. `AWS_PROFILE=<profile>`. Note that environment variables (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`) override a named profile — unset them for the command if they shadow the intended profile. Re-run until `Account` matches the target.
   - Confirm the **region** with the user as well.

Only once the CLI is installed, authenticated, pointed at the confirmed target account, and the region is agreed may you continue to Section A.

---

## Section A — AWS Setup

> **GATE A0:** Confirm the preflight checks passed — the AWS CLI is authenticated, its `Account` matches the user's target account, and the region is agreed — before creating anything. If the CLI is on a different account, stop and resolve it first.

### A1. Kinesis stream

**Ask first:** "What is the name of your existing Kinesis stream?"

- If the user **has** a stream, record the name and skip creation. Optionally verify it:
  ```bash
  # Runs in CoCo bash sandbox (Linux) - safe on any host OS
  aws kinesis describe-stream-summary --stream-name "<STREAM_NAME>" --region <REGION>
  ```
- If the user does **not** have a stream, ask whether they want one created.

> **GATE A1 (separate):** Only if the user confirms, create the stream. On-demand mode is simplest for testing:
> ```bash
> # Runs in CoCo bash sandbox (Linux) - safe on any host OS
> aws kinesis create-stream \
>   --stream-name "<STREAM_NAME>" \
>   --stream-mode-details StreamMode=ON_DEMAND \
>   --region <REGION>
> ```
> Then wait for `ACTIVE`:
> ```bash
> # Runs in CoCo bash sandbox (Linux) - safe on any host OS
> aws kinesis describe-stream-summary --stream-name "<STREAM_NAME>" --region <REGION> \
>   --query 'StreamDescriptionSummary.StreamStatus'
> ```

### A2–A4. IAM credentials for the connector

> **GATE A2 (separate from the stream):** This whole block — IAM user, policy, and access keys — is a distinct decision. Confirm it independently before proceeding, even if the stream was just created.

**Ask first** whether an IAM user/role and access keys already exist for the connector. If they do, collect the **Access Key ID / Secret Access Key** and skip to Section B.

If they do not exist, after confirmation:

**A2. Create the IAM user**
```bash
# Runs in CoCo bash sandbox (Linux) - safe on any host OS
aws iam create-user --user-name "<IAM_USER>"
```

**A3. Create and attach the IAM policy.** The connector needs Kinesis stream access, Kinesis consumer (Enhanced Fan-Out) access, and DynamoDB access for checkpoints. Replace `${REGION}`, `${ACCOUNT_ID}`, `${STREAM_NAME}`, `${APPLICATION_NAME}`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KinesisStreamAccess",
      "Effect": "Allow",
      "Action": [
        "kinesis:DescribeStream",
        "kinesis:DescribeStreamConsumer",
        "kinesis:GetRecords",
        "kinesis:GetShardIterator",
        "kinesis:ListShards",
        "kinesis:RegisterStreamConsumer"
      ],
      "Resource": "arn:aws:kinesis:${REGION}:${ACCOUNT_ID}:stream/${STREAM_NAME}"
    },
    {
      "Sid": "KinesisConsumerAccess",
      "Effect": "Allow",
      "Action": [
        "kinesis:DeregisterStreamConsumer",
        "kinesis:DescribeStreamConsumer",
        "kinesis:SubscribeToShard"
      ],
      "Resource": "arn:aws:kinesis:${REGION}:${ACCOUNT_ID}:stream/${STREAM_NAME}/consumer/*"
    },
    {
      "Sid": "DynamoDBTableAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DeleteTable",
        "dynamodb:DescribeTable",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:UpdateItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${APPLICATION_NAME}",
        "arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${APPLICATION_NAME}_migration"
      ]
    }
  ]
}
```
```bash
# Runs in CoCo bash sandbox (Linux) - safe on any host OS
aws iam create-policy --policy-name "<POLICY_NAME>" --policy-document file://<policy>.json
aws iam attach-user-policy --user-name "<IAM_USER>" \
  --policy-arn "arn:aws:iam::${ACCOUNT_ID}:policy/<POLICY_NAME>"
```

**A4. Create access keys** (the secret is shown only once — capture it securely):
```bash
# Runs in CoCo bash sandbox (Linux) - safe on any host OS
aws iam create-access-key --user-name "<IAM_USER>"
```

**Note on DynamoDB:** Do **not** create the DynamoDB checkpoint table manually. The connector creates it automatically at first start, named after the `AWS Kinesis Application Name`. The IAM policy above only needs to *allow* creating/managing it. The `${APPLICATION_NAME}_migration` ARN and `dynamodb:DeleteTable` are only used for one-time migration from the legacy KCL connector and can be omitted if never used.

---

## Section B — Snowflake / Openflow Setup

### B1. Gather destination details (always ask)

Always ask the user for the destination and whether each object already exists:

1. **Database** name — does it exist?
2. **Schema** name — does it exist?
3. **Table** name — does it exist?
4. **Does the role/user that the connector uses in the runtime already have access to that table?**

Determine which Snowflake **identity the connector authenticates as** (the runtime identity by default, or a dedicated KEY_PAIR service user). The privileges must land on the role that this identity actually uses.

### B2. Create the destination table (only if missing)

If the table does not exist, offer to create it in the correct format. The connector maps the first-level JSON keys to columns and (with schema evolution) adds new columns automatically.

> **GATE B2:** Only after confirmation:
> ```sql
> CREATE TABLE <DB>.<SCHEMA>.<TABLE> (
>   kinesisMetadata OBJECT
> )
> ENABLE_SCHEMA_EVOLUTION = TRUE
> ERROR_LOGGING = TRUE;
> ```

### B3. Role and grants (only if missing / not granted)

If a dedicated role does not exist, offer to create one; then grant the privileges the connector needs.

> **GATE B3:** Only after confirmation:
> ```sql
> -- Create role (if needed)
> CREATE ROLE IF NOT EXISTS <KINESIS_ROLE>;
>
> -- Object access
> GRANT USAGE ON DATABASE <DB> TO ROLE <KINESIS_ROLE>;
> GRANT USAGE ON SCHEMA <DB>.<SCHEMA> TO ROLE <KINESIS_ROLE>;
> GRANT CREATE PIPE ON SCHEMA <DB>.<SCHEMA> TO ROLE <KINESIS_ROLE>;  -- auto-creates <TABLE>-STREAMING pipe (required for SNOWFLAKE_MANAGED / managed-runtime)
> GRANT OWNERSHIP ON TABLE <DB>.<SCHEMA>.<TABLE> TO ROLE <KINESIS_ROLE>;
> ```

**Critical — make the connector's identity actually see the objects.** The connector writes via Snowpipe Streaming to a managed pipe named `<TABLE>-STREAMING`. The authenticating identity's effective role must:
- have `CREATE PIPE` on the schema (to create that pipe), and
- be able to see/own the table.

If you transferred table OWNERSHIP to a **standalone** role that is not in the `SYSADMIN` hierarchy, system roles (including `ACCOUNTADMIN`) and the execute-as role will **not** see the table — Snowpipe Streaming returns `ERR_TABLE_DOES_NOT_EXIST_NOT_AUTHORIZED`. Fix it by granting the connector role into the hierarchy of whatever role the connector uses:

> **GATE B3b (conditional — required for SNOWFLAKE_MANAGED and other managed-runtime-identity deployments):** Only after user confirmation, run the role-hierarchy fix. On these deployments the execute-as role *inherits* privileges from the connector role (rather than holding them directly), which is why these grants are needed in addition to the direct-to-connector-role grants above:
```sql
-- So the runtime/effective role inherits USAGE + CREATE PIPE + table ownership
GRANT ROLE <KINESIS_ROLE> TO ROLE <RUNTIME_OR_EFFECTIVE_ROLE>;
-- And, if the connector authenticates as a specific user:
GRANT ROLE <KINESIS_ROLE> TO USER <CONNECTOR_USER>;
```
> If you are unsure which role the streaming uses, confirm with the user. On many deployments the runtime user's **default role** is the effective one, which may differ from `ACCOUNTADMIN`.

If you grant table OWNERSHIP away from the user's interactive role, that role can lose `SELECT`. Restore read access if the user needs it:

> **GATE B3c (conditional):** Only after user confirmation, restore SELECT access:
```sql
GRANT SELECT ON TABLE <DB>.<SCHEMA>.<TABLE> TO ROLE <USER_INTERACTIVE_ROLE>;
GRANT USAGE ON DATABASE <DB> TO ROLE <USER_INTERACTIVE_ROLE>;
GRANT USAGE ON SCHEMA <DB>.<SCHEMA> TO ROLE <USER_INTERACTIVE_ROLE>;
```

### B4. Network access (SPCS only)

On Snowflake (SPCS) deployments the runtime needs an External Access Integration allowing the Kinesis connector's domains. **Load** `references/platform-eai.md` to create/extend the network rule and EAI and attach it to the runtime.

Required domains (region-dependent; example for `us-west-2` — substitute your region):
- `kinesis.<region>.amazonaws.com:443`
- `kinesis-fips.<region>.api.aws:443`
- `kinesis-fips.<region>.amazonaws.com:443`
- `kinesis.<region>.api.aws:443`
- `*.control-kinesis.<region>.amazonaws.com:443`
- `*.control-kinesis.<region>.api.aws:443`
- `*.data-kinesis.<region>.amazonaws.com:443`
- `*.data-kinesis.<region>.api.aws:443`
- `dynamodb.<region>.amazonaws.com:443`

**DynamoDB caveat:** DynamoDB does not support Private DNS for its PrivateLink endpoint. If using outbound PrivateLink for Kinesis, still route DynamoDB through the **public** endpoint (`HOST_PORT`), not `PRIVATE_HOST_PORT`, or checkpoint writes time out.

---

## Section C — Configure and Start the Connector

### C1. Install the connector

If not already added to the runtime, **Load** `references/connector-main.md` and `references/ops-flow-deploy.md` to install `kinesis-high-performance`.

### C2. Populate parameters (including secrets)

Set the connector's parameters from the values gathered above. **Load** `references/ops-parameters-main.md` for how to set values and `references/ops-parameters-assets.md` for binary assets (e.g. a private key file).

| Parameter | Value |
|-----------|-------|
| AWS Access Key ID | from A4 |
| AWS Secret Access Key | from A4 (store as a sensitive parameter) |
| AWS Kinesis Region | the chosen region |
| AWS Kinesis Stream Name | from A1 |
| AWS Kinesis Application Name | becomes the DynamoDB checkpoint table name |
| AWS Kinesis Consumer Type | `SHARED_THROUGHPUT` (simplest) or `ENHANCED_FAN_OUT` |
| AWS Kinesis Initial Stream Position | `TRIM_HORIZON` (replay existing records) or `LATEST` |
| Snowflake Destination Database | `<DB>` (case-sensitive; uppercase for unquoted identifiers) |
| Snowflake Destination Schema | `<SCHEMA>` |
| Snowflake Destination Table | `<TABLE>` |

If the connector authenticates to Snowflake via KEY_PAIR rather than the runtime identity, also set the Snowflake user and private key — **Load** `references/connector-streaming-snowflake-auth.md`.

### C3. Verify, enable controllers, check for errors

- Enable controller services and verify configuration **before** starting. **Load** `references/ops-config-verification.md` and `references/ops-flow-lifecycle.md` (Enable Controllers Only).
- After enabling, check bulletins for errors (auth, network, table-not-found). Resolve before starting.

### C4. Start — ask first

> **GATE C4:** Do **not** start the connector automatically. Ask: "Configuration is verified and controllers are enabled. Would you like me to start the connector, or will you start it yourself?"

Only start it if the user explicitly asks you to. After starting, validate data flow (see `references/connector-main.md` → Validate Data Flow) and confirm rows land in the destination table.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `UnknownHostException: dynamodb.<region>.amazonaws.com` (or `kinesis...`) | EAI / network rule missing the domain (SPCS) | Add the required domains and attach the EAI — `references/platform-eai.md` |
| `Connect timed out` to DynamoDB | DynamoDB configured via `PRIVATE_HOST_PORT` | Use `HOST_PORT` (public) for DynamoDB; it has no Private DNS |
| `ERR_TABLE_DOES_NOT_EXIST_NOT_AUTHORIZED` on pipe `<TABLE>-STREAMING` | Effective role can't see the table (standalone owning role outside hierarchy) and/or lacks `CREATE PIPE` | Grant `CREATE PIPE` on schema to the connector role and `GRANT ROLE <KINESIS_ROLE> TO ROLE/USER <runtime identity>` (see B3) |
| `ExpiredTokenException` from AWS CLI | SSO/session token expired | Re-authenticate (`aws sso login --profile <profile>`), re-verify identity |
| Connector reads but no rows appear | Wrong `Initial Stream Position`, or schema/table mismatch | Confirm `TRIM_HORIZON` for replay; verify destination DB/schema/table names (case-sensitive) |

To reset consumer state (reprocess from the initial position): stop the connector, then either change the `AWS Kinesis Application Name` (creates a new DynamoDB table) or delete the existing DynamoDB table, then start again. Resetting may cause duplicate or skipped data depending on the initial position.

---

## See Also

- `references/connector-kinesis-main.md` — Kinesis router (setup vs customizations)
- `references/connector-main.md` — General connector deployment workflow
- `references/platform-eai.md` — Network access (EAI) for SPCS, required domains
- `references/connector-streaming-snowflake-auth.md` — Snowflake Private Key Auth (KEY_PAIR)
- `references/ops-parameters-main.md` — Setting parameters and secrets
- `references/ops-config-verification.md` — Verify configuration before start
- `references/ops-flow-lifecycle.md` — Enable controllers, start/stop, bulletins
