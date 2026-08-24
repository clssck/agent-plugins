---
name: tri-secret-secure
description: "Manage Tri-Secret Secure (TSS) encryption with customer-managed keys (CMK) in Snowflake. Use for: checking CMK status, registering CMK, activating TSS, configuring TSS for Postgres, enabling private connectivity for TSS, deactivating TSS, rekeying CMK, viewing TSS change history. Triggers: tri-secret secure, TSS, customer-managed key, CMK, encryption key, BYOK, bring your own key, CMK info, activate CMK, register CMK, deactivate CMK, TSS history, change history, CMK history, tri-secret secure history."
---

# Tri-Secret Secure Management

## Step 0: Intent Detection (Execute BEFORE Prerequisites)

Determine the user's intent **before** running prerequisite checks.

| User Intent | Keywords | Route |
|-------------|----------|-------|
| View change history | TSS history, change history, CMK history, CMK usage history, encryption history, audit log | **Load** [change-history/SKILL.md](change-history/SKILL.md) |
| All other TSS operations | check CMK, activate, deactivate, register, rekey, rotate, private connectivity, Postgres | Continue to Prerequisites below |

If the user's request matches **change history**, load the workflow immediately — do NOT run the prerequisites below (the workflow has its own prerequisite check that accepts ACCOUNTADMIN or SECURITY_VIEWER).

For all other intents, proceed to Prerequisites.

---

## Prerequisites (MANDATORY — Execute FIRST)

You **MUST** execute both prerequisite checks below **before** proceeding to the workflow. Do NOT skip these checks. Do NOT proceed to any workflow step until both checks pass. (Step 0 intent detection runs before these checks — if the user wants change history, the workflow is loaded directly without these prerequisites.)

### Check 1: Role Verification (REQUIRED)

**Always execute this SQL first:**

```sql
SELECT CURRENT_ROLE();
```

If the current role is **ACCOUNTADMIN**, proceed to Check 2.

If the current role is **not ACCOUNTADMIN**, check whether the user has access to the ACCOUNTADMIN role:

```sql
SHOW ROLES;
```

- If ACCOUNTADMIN appears in the results, switch to it automatically:
  ```sql
  USE ROLE ACCOUNTADMIN;
  ```
  Then proceed to Check 2.

- If ACCOUNTADMIN does **not** appear, **STOP immediately** and inform the user:

> Your current role is `<role>` and you do not have access to the ACCOUNTADMIN role.
> Tri-Secret Secure operations require the ACCOUNTADMIN role.
> Please contact your Snowflake administrator to be granted ACCOUNTADMIN.

**Do NOT continue to any other step unless the active role is ACCOUNTADMIN.**

### Check 2: Cloud Provider & Account Info (REQUIRED)

**Always execute this SQL second:**

```sql
SELECT SYSTEM$GET_SNOWFLAKE_PLATFORM_INFO();
```

This returns a JSON object. Parse it to determine the **cloud provider** — the `cloud` field indicates which cloud service provider the account is hosted on: **AWS**, **Azure**, or **GCP**. Store this information — it determines which CMK format and policy instructions to use in later steps:
   - **AWS**: CMK is an ARN (e.g., `arn:aws:kms:...`)
   - **Azure**: CMK is a Key Vault URI (e.g., `https://<vault>.vault.azure.net/keys/...`)
   - **GCP**: CMK is a Key Resource ID (e.g., `projects/.../locations/.../keyRings/.../cryptoKeys/...`)

After determining the cloud provider, **remind the user**:

> **Note:** Tri-Secret Secure requires your account to be on Business Critical edition or higher. Please confirm your account meets this requirement before proceeding.

---

## Workflow

**Only proceed here after both prerequisite checks above have passed.**

### Step 1: Detect Intent

**Ask** the user what they need:

```
What would you like to do with Tri-Secret Secure?

1. Check CMK status for my account
2. Check CMK status for Postgres
3. Activate Tri-Secret Secure (standard)
4. Activate Tri-Secret Secure with private connectivity
5. Activate Tri-Secret Secure for Postgres
6. Deactivate Tri-Secret Secure
7. Change or rotate CMK
```

**Route:**
- Option 1 → Step 2
- Option 2 → Step 3
- Option 3 → Step 4
- Option 4 → Step 6
- Option 5 → Step 5
- Option 6 → Step 7
- Option 7 → Step 8

---

### Step 2: Check CMK Status (Account)

**Execute:**
```sql
SELECT SYSTEM$GET_CMK_INFO();
```

**Present** the result to the user, interpreting the status:
- `...is registered...` — CMK registered but not yet activated
- `...is being activated...` — Rekeying in progress, not yet complete
- `...is activated...` — TSS is active with this CMK
- `...is being rekeyed...` — CMK change in progress
- No CMK registered — No TSS configuration exists

**Done.** Ask if the user needs further action.

---

### Step 3: Check CMK Status (Postgres)

**Execute:**
```sql
SELECT SYSTEM$GET_CMK_INFO_POSTGRES();
```

**Present** the result, interpreting the status:
- `...is activated...` — Postgres TSS is active
- No CMK registered — No Postgres TSS configuration exists

Note: Postgres TSS does not support rekeying of existing instances. Only new instances created after activation use the CMK.

**Done.** Ask if the user needs further action.

---

### Step 4: Activate Tri-Secret Secure (Standard)

**Step 4a: Collect CMK**

**Ask** the user for their CMK identifier. Based on the cloud provider detected in the prerequisites:
- **AWS**: Request the KMS key ARN (e.g., `arn:aws:kms:us-east-1:123456789012:key/...`)
- **Azure**: Request the Key Vault URI (e.g., `https://<vault>.vault.azure.net/keys/<key-name>/<version>`)
- **GCP**: Request the Key Resource ID (e.g., `projects/<project>/locations/<location>/keyRings/<ring>/cryptoKeys/<key>`)

The user must have already created the CMK in their cloud provider's KMS.

**Step 4b: Register CMK**

**⚠️ MANDATORY CHECKPOINT**: Confirm the CMK value with the user before registering.

```sql
SELECT SYSTEM$REGISTER_CMK_INFO('<cmk_value>');
```

If registration fails because a different CMK already exists, inform the user they must deregister the existing CMK first:
```sql
SELECT SYSTEM$DEREGISTER_CMK_INFO();
```
Then retry registration.

After successful registration, inform the user:
> An email notification has been sent to account administrators. You must **wait 72 hours** before activation.

**Step 4c: Check Registration Status**

```sql
SELECT SYSTEM$GET_CMK_INFO();
```

Confirm the CMK shows as registered.

**Step 4d: Generate Cloud Provider Policy**

```sql
SELECT SYSTEM$GET_CMK_CONFIG();
```

For Azure-hosted accounts, the tenant_id must be passed:
```sql
SELECT SYSTEM$GET_CMK_CONFIG('<tenant_id>');
```

**⚠️ MANDATORY STOPPING POINT**: Present the output to the user.

> Use the configuration above to authorize your Snowflake account to access your CMK on your cloud provider platform.
> Once you have applied the policy, let me know to proceed with verification.

**Step 4e: Verify Connectivity**

```sql
SELECT SYSTEM$VERIFY_CMK_INFO();
```

**If verification fails:**
- Re-run `SYSTEM$GET_CMK_CONFIG()` and present the policy output again
- Ask the user to verify the policy is correctly applied on their cloud provider
- Retry verification after the user confirms

**If verification succeeds:**

> Your Snowflake account can successfully access your key. Connectivity verification passed.

Proceed to activation.

**Step 4f: Activate TSS**

```sql
SELECT SYSTEM$ACTIVATE_CMK_INFO();
```

**If the 72-hour waiting period has not elapsed**, the function returns an error with the remaining wait time. Inform the user:

> The 72-hour waiting period has not passed yet. Please come back after the waiting period and run activation again.

**If activation succeeds:**

> Tri-Secret Secure activation has started. The rekeying process can take up to 24 hours.
> You will receive an email when it completes.
>
> **Critical:** Your CMK is now required for accessing your Snowflake data. **NEVER** delete or revoke access to this CMK — doing so will make your data **unrecoverable**.

**Done.**

---

### Step 5: Activate Tri-Secret Secure for Postgres

**Step 5a: Collect CMK**

**Ask** the user for their CMK identifier.

**Step 5b: Register CMK**

**⚠️ MANDATORY CHECKPOINT**: Confirm the CMK value with the user before registering.

```sql
SELECT SYSTEM$REGISTER_CMK_INFO_POSTGRES('<cmk_value>');
```

If registration fails because a different CMK already exists:
```sql
SELECT SYSTEM$DEREGISTER_CMK_INFO_POSTGRES();
```
Then retry registration.

**Step 5c: Check Registration Status**

```sql
SELECT SYSTEM$GET_CMK_INFO_POSTGRES();
```

**Step 5d: Generate Cloud Provider Policy**

```sql
SELECT SYSTEM$GET_CMK_CONFIG_POSTGRES();
```

For Azure-hosted accounts:
```sql
SELECT SYSTEM$GET_CMK_CONFIG_POSTGRES('<tenant_id>');
```

**⚠️ MANDATORY STOPPING POINT**: Present the output to the user.

> Use the configuration above to authorize your Snowflake account to access your CMK on your cloud provider.
> Once you have applied the policy, let me know to proceed with verification.

**Step 5e: Verify Connectivity**

```sql
SELECT SYSTEM$VERIFY_CMK_INFO_POSTGRES();
```

If verification fails, re-run `SYSTEM$GET_CMK_CONFIG_POSTGRES()` and have the user recheck their cloud provider policy.

**If verification succeeds:**

> Your Snowflake account can successfully access your Postgres key. Connectivity verification passed.

Proceed to activation.

**Step 5f: Activate Postgres TSS**

```sql
SELECT SYSTEM$ACTIVATE_CMK_INFO_POSTGRES();
```

> Snowflake Postgres Tri-Secret Secure is now active.
>
> **Important:** Only Postgres instances created **after** activation will use this CMK.
> Existing instances are not rekeyed. Replicas and forks use the CMK of their primary instance.

**Done.**

---

### Step 6: Activate Tri-Secret Secure with Private Connectivity

**Step 6a: Provision Private Endpoint**

```sql
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT_TSS();
```

**⚠️ MANDATORY STOPPING POINT**: Present the output to the user.

> A private endpoint has been provisioned. You must now **approve** this endpoint on your cloud provider:
> - **Azure**: Approve in the Azure portal as the owner of the API Management resource
> - **AWS**: Accept the VPC endpoint connection
> - **GCP**: Accept the Private Service Connect endpoint
>
> Let me know once the endpoint is approved.

**Step 6b: Collect and Register CMK with Private Connectivity**

**Ask** the user for their CMK identifier.

**⚠️ MANDATORY CHECKPOINT**: Confirm the CMK value before registering.

```sql
SELECT SYSTEM$REGISTER_CMK_INFO('<cmk_value>', 'true');
```

The second argument `'true'` enables private connectivity for the CMK.

After registration:
> An email notification has been sent. You must **wait 72 hours** before activation.

**Step 6c: Check Status, Generate Config, Verify**

Follow the same steps as Step 4c through 4e:
- `SYSTEM$GET_CMK_INFO()` to check status
- `SYSTEM$GET_CMK_CONFIG()` (or with tenant_id for Azure) to generate policy
- Have user apply policy on cloud provider
- `SYSTEM$VERIFY_CMK_INFO()` to verify connectivity

**Step 6d: Activate**

```sql
SELECT SYSTEM$ACTIVATE_CMK_INFO();
```

Same 72-hour waiting period and rekeying behavior as Step 4f.

**Done.**

#### Enable Private Connectivity for an Already-Active CMK

If the user already has TSS active and wants to add private connectivity without rekeying:

1. Provision endpoint:
   ```sql
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT_TSS();
   ```

2. Have user approve the endpoint on cloud provider.

3. Re-register CMK with private connectivity flag:
   ```sql
   SELECT SYSTEM$REGISTER_CMK_INFO('<cmk_value>', 'true');
   ```

4. Activate with UPDATE_PRIVATELINK (no rekeying, completes quickly):
   ```sql
   SELECT SYSTEM$ACTIVATE_CMK_INFO('UPDATE_PRIVATELINK');
   ```

5. Optionally verify:
   ```sql
   SELECT SYSTEM$GET_CMK_INFO();
   ```

---

### Step 7: Deactivate Tri-Secret Secure

**⚠️ MANDATORY CHECKPOINT**: Warn the user before proceeding.

> **Warning:** Deactivating Tri-Secret Secure will remove your CMK from the encryption hierarchy.
> Snowflake will revert to using only Snowflake-managed keys.
> Are you sure you want to proceed?

```sql
SELECT SYSTEM$DEACTIVATE_CMK_INFO();
```

After deactivation, remind the user:

> **Critical:** Do **NOT** delete or revoke access to your old CMK until you have confirmed the rekey process has fully completed and you have received the completion email from Snowflake. Premature removal of the old CMK will make your data unrecoverable.

**Done.**

---

### Step 8: Change or Rotate CMK

**Ask** the user what they need:

**Option A: Replace with a new CMK** — Follow Step 4 (standard activation) with the new key. The system functions handle the transition; `SYSTEM$GET_CMK_INFO()` will show `...is being rekeyed...` during the process.

> **Critical:** Do **NOT** delete or revoke access to your old CMK until rekeying completes and you receive the completion email. After rekeying completes, your new CMK becomes required for accessing your data — **NEVER** delete or revoke access to the new CMK, or your data will be **unrecoverable**.

**Option B: Rekey with the same CMK (automatic key rotation)** — If the user's cloud provider rotated the key version:

```sql
SELECT SYSTEM$ACTIVATE_CMK_INFO('REKEY_SAME_CMK');
```

> Rekeying has started with the latest version of your CMK. You will receive an email when complete.
> **Critical:** Do **NOT** remove access to the old key version until rekeying completes. Your CMK remains required for accessing your data — **NEVER** delete the CMK, or your data will be **unrecoverable**.

---

## Private Connectivity Management

Additional functions for managing the private endpoint:

| Action | SQL |
|--------|-----|
| Deprovision endpoint | `SELECT SYSTEM$DEPROVISION_PRIVATELINK_ENDPOINT_TSS();` |
| Restore deprovisioned endpoint | `SELECT SYSTEM$RESTORE_PRIVATELINK_ENDPOINT_TSS();` |

---

## Stopping Points

- ✋ Prerequisites: Stop if role is not ACCOUNTADMIN; remind user that Business Critical edition is required
- ✋ Step 4b/5b/6b: Before registering a CMK — confirm key value with user
- ✋ Step 4d/5d: After generating cloud provider policy — user must apply it
- ✋ Step 6a: After provisioning private endpoint — user must approve on cloud provider
- ✋ Step 4f/6d: If 72-hour wait not elapsed — inform user to come back later
- ✋ Step 7: Before deactivation — explicit user confirmation required

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| `SYSTEM$REGISTER_CMK_INFO` fails — existing CMK | Call `SYSTEM$DEREGISTER_CMK_INFO()` first, then retry |
| `SYSTEM$ACTIVATE_CMK_INFO` — waiting period error | The 72-hour period hasn't passed. Inform user of remaining time |
| `SYSTEM$VERIFY_CMK_INFO` fails | Re-run `SYSTEM$GET_CMK_CONFIG()`, have user verify cloud provider policy |
| Insufficient privileges | Must use ACCOUNTADMIN role |
| Account edition error | TSS requires Business Critical or higher — remind user to confirm their edition |
| Postgres TSS — existing instances not encrypted | By design: only new instances created after activation use the CMK |

## Output

- CMK registration and activation status
- Cloud provider policy configuration for CMK authorization
- Step-by-step guided activation with checkpoints
- Status monitoring during rekeying
