---
name: network-security
description: "Recommend, evaluate, and migrate Snowflake network policies using built-in security procedures. Use when: generating network policy recommendations from access history, evaluating candidate policies before deployment, migrating existing policies to use Snowflake-managed SaaS rules, creating hybrid policies combining custom rules with SaaS rules. Triggers: recommend network policy, evaluate network policy, candidate policy, migrate policy, SaaS rules, hybrid policy."
---

# Network Security

Foundational knowledge for managing Snowflake network rules and policies.

## Core Concepts

- **Network rules** define lists of IP addresses (IPV4, INGRESS/EGRESS). They live in a database and schema.
- **Network policies** reference one or more network rules to allow or block traffic. Policies are account-level objects (no database/schema).
- **Hybrid policies** combine custom network rules with Snowflake-managed SaaS rules. This is the recommended pattern because SaaS rules are automatically updated by Snowflake when providers change their IP ranges.
- **Snowflake SaaS rules** are pre-built network rules in `SNOWFLAKE.NETWORK_SECURITY` for common integrations (dbt, Tableau, Power BI, Qlik, GitHub Actions, Sigma, ThoughtSpot, etc.).

### Internal vs External IPs

- **Internal IPs**: `10.x.x.x`, `172.16-31.x.x`, `192.168.x.x`, `0.0.0.0` (Snowflake infrastructure/VPN). These won't match SaaS rules — this is expected. Include them in custom rules.
- **External IPs**: All other public IPs. These may be covered by Snowflake SaaS rules.

### Creation Order

**Network rules MUST be created BEFORE the network policy that references them.** The policy creation will fail if a referenced network rule does not exist.

---

## SaaS Coverage Check

Use this query to determine which IPs are covered by Snowflake's pre-built SaaS network rules.

```sql
WITH input_ips AS (
    -- Replace with the IPs to check
    SELECT column1 as ip FROM VALUES
        ('<ip1>'), ('<ip2>'), ('<ip3>')
),
snowflake_saas_rules AS (
    SELECT name, value_list
    FROM snowflake.account_usage.network_rules 
    WHERE database = 'SNOWFLAKE' AND schema = 'NETWORK_SECURITY'
    AND deleted IS NULL
),
flattened_cidrs AS (
    SELECT 
        name as rule_name,
        TRIM(f.value::STRING) as cidr_block
    FROM snowflake_saas_rules,
    LATERAL FLATTEN(input => SPLIT(value_list, ',')) f
),
ip_to_int AS (
    SELECT 
        ip,
        (SPLIT_PART(ip, '.', 1)::INT * 16777216) + 
        (SPLIT_PART(ip, '.', 2)::INT * 65536) + 
        (SPLIT_PART(ip, '.', 3)::INT * 256) + 
        (SPLIT_PART(ip, '.', 4)::INT) as ip_int
    FROM input_ips
),
cidr_ranges AS (
    SELECT 
        rule_name,
        cidr_block,
        (SPLIT_PART(SPLIT_PART(cidr_block, '/', 1), '.', 1)::INT * 16777216) + 
        (SPLIT_PART(SPLIT_PART(cidr_block, '/', 1), '.', 2)::INT * 65536) + 
        (SPLIT_PART(SPLIT_PART(cidr_block, '/', 1), '.', 3)::INT * 256) + 
        (SPLIT_PART(SPLIT_PART(cidr_block, '/', 1), '.', 4)::INT) as network_int,
        COALESCE(TRY_TO_NUMBER(SPLIT_PART(cidr_block, '/', 2)), 32) as prefix_len
    FROM flattened_cidrs
)
SELECT 
    i.ip as checked_ip,
    c.rule_name as snowflake_saas_rule,
    c.cidr_block as matching_cidr
FROM ip_to_int i
JOIN cidr_ranges c 
    ON i.ip_int >= c.network_int 
    AND i.ip_int <= c.network_int + POW(2, 32 - c.prefix_len)::INT - 1
ORDER BY i.ip, c.rule_name;
```

**Interpreting results:**

| Result | Action |
|--------|--------|
| IPs covered by SaaS rules | Use Snowflake-provided rules in hybrid policy |
| No coverage | IPs go into a custom network rule |
| Mixed (most common) | Create hybrid policy combining SaaS rules + custom rule |

---

## Creating a Hybrid Network Policy

A hybrid policy uses both custom network rules (for environment-specific IPs) and Snowflake-managed SaaS rules (auto-updated).

### Step 1: Gather Database Context

Network rules require a database and schema.

**Ask user:**
```
To create the network rule, I need:
1. **Database name**: Which database should contain the network rule?
2. **Schema name**: Which schema in that database? (e.g., PUBLIC)
```

### Step 2: Create Custom Network Rule

```sql
CREATE OR REPLACE NETWORK RULE <db>.<schema>.<RULE_NAME>
    TYPE = IPV4
    MODE = INGRESS
    VALUE_LIST = (
        -- Internal IPs (Snowflake infrastructure/VPN)
        '<internal_ip1>/32', '<internal_ip2>/32',
        -- External IPs NOT covered by SaaS rules
        '<external_ip1>/32', '<external_ip2>/32'
    );
```

### Step 3: Verify Rule Creation

```sql
SHOW NETWORK RULES LIKE '<RULE_NAME>' IN <db>.<schema>;
```

### Step 4: Create Hybrid Policy

```sql
CREATE OR REPLACE NETWORK POLICY <POLICY_NAME>
    ALLOWED_NETWORK_RULE_LIST = (
        '<db>.<schema>.<RULE_NAME>',
        'SNOWFLAKE.NETWORK_SECURITY.<SAAS_RULE_1>',
        'SNOWFLAKE.NETWORK_SECURITY.<SAAS_RULE_2>'
    )
    COMMENT = 'Hybrid policy: custom IPs + SaaS rules';
```

**Common Error:** If you see `Network rule 'X' does not exist or not authorized`, ensure the network rule was created successfully and the fully qualified name is correct.

---

## DDL Reference

**Load** [references/ddl-reference.md](references/ddl-reference.md) for full DDL syntax (CREATE/ALTER/DROP for network rules and policies, policy assignment, view assignments).

---

## Network Policy Advisor

Advisory workflows for Snowflake network policies using built-in security procedures.

### Intent Detection

**Ask user:**
```
What would you like to do?
1. Generate network policy recommendations
2. Evaluate a candidate network policy
3. Migrate existing policy to use SaaS rules
```

- **Option 1** → Continue to [Recommend Workflow](#recommend-workflow)
- **Option 2** → Continue to [Evaluate Workflow](#evaluate-workflow)
- **Option 3** → Continue to [Migrate Workflow](#migrate-workflow)

---

### Recommend Workflow

#### Step 1: Gather Parameters

**Ask user:**
```
To generate network policy recommendations:

1. **Scope**: User-level or Account-level?
   - User-level: Provide username (e.g., "JOHN_DOE")
   - Account-level: Skip this parameter

2. **Lookback period**: How many days of history? (default: 90)
```

**⚠️ STOP**: Confirm parameters before proceeding.

#### Step 2: Execute Recommendation Procedure

**For user-level recommendation:**
```sql
CALL snowflake.network_security.recommend_network_policy('<USERNAME>', <LOOKBACK_DAYS>);
```

**For account-level recommendation:**
```sql
CALL snowflake.network_security.recommend_network_policy(lookback_days => <LOOKBACK_DAYS>);
```

#### Step 3: Present Results

1. **ALWAYS display the complete raw output** from the procedure in a code block:
   ```
   <full procedure output here - do not truncate or summarize>
   ```

2. **Identify external IPs** from the recommendation (see [Internal vs External IPs](#internal-vs-external-ips)).

#### Step 4: Automatic SaaS Coverage Check

**ALWAYS automatically check** whether any external IPs are covered by Snowflake SaaS rules. Use the [SaaS Coverage Check](#saas-coverage-check) query with all external IPs from the recommendation.

#### Step 5: Present Hybrid Policy Recommendation

**ALWAYS recommend a hybrid policy by default.** Present the recommendation to the user:

```
Based on the analysis, I recommend creating a **hybrid network policy**:

**SaaS Rules (auto-updated by Snowflake):**
- SNOWFLAKE.NETWORK_SECURITY.<MATCHING_RULE_1>
- SNOWFLAKE.NETWORK_SECURITY.<MATCHING_RULE_2>
- ... (list all matching SaaS rules)

**Custom Rule (for remaining IPs):**
- X internal IPs (Snowflake infrastructure/VPN)
- Y external IPs (not covered by SaaS rules)

This approach ensures:
1. SaaS provider IPs stay automatically updated by Snowflake
2. You only manage custom IPs that are specific to your environment
```

**⚠️ STOP**: Get user approval before creating the policy.

#### Step 6: Create Hybrid Network Policy

Follow the [Creating a Hybrid Network Policy](#creating-a-hybrid-network-policy) pattern to:
1. Gather database/schema context
2. Create the custom network rule
3. Create the hybrid policy referencing both the custom rule and matched SaaS rules

#### Step 7: Offer to Evaluate the Policy

After creating the hybrid policy, **always offer to evaluate it**:

```
The hybrid policy has been created. Would you like me to evaluate it against
the same lookback period to confirm 100% coverage?
```

If user agrees, run:
```sql
CALL snowflake.network_security.evaluate_candidate_network_policy(
    '<USERNAME>_HYBRID_NETWORK_POLICY',
    '<USERNAME>',
    <LOOKBACK_DAYS>
);
```

Present evaluation results showing allowed vs blocked IPs. If any IPs would be blocked, offer to expand the custom rule.

#### Stopping Points (Recommend)

- ✋ Step 1: After gathering parameters
- ✋ Step 5: After presenting hybrid policy recommendation (get approval)
- ✋ Step 7: After offering evaluation

#### Notes (Recommend)

- The procedure executes with CALLER privileges and accesses sensitive user activity data
- Recommended lookback periods:
  - Quick review: 7-14 days
  - Standard analysis: 30 days
  - Comprehensive audit: 90+ days

---

### Evaluate Workflow

Evaluate a candidate network policy against user activity to simulate the effect if that policy had been applied to either the account level or a specific user.

#### Step 1: Gather Parameters

**Ask user:**
```
To evaluate a network policy:

1. **Policy name**: Name of the network policy to evaluate
2. **User scope**: Specific user or all users?
   - Specific user: Provide username (e.g., "JOHN_DOE")
   - All users: Skip this parameter
3. **Lookback period**: How many days of history? (default: 90)
```

**⚠️ STOP**: Confirm parameters before proceeding.

#### Step 2: Execute Evaluation Procedure

**IMPORTANT**: Use `CALL` syntax (not `SELECT * FROM TABLE()`).

```sql
CALL snowflake.network_security.evaluate_candidate_network_policy(
    '<POLICY_NAME>',
    '<USERNAME>',  -- or NULL for all users
    <LOOKBACK_DAYS>
);
```

#### Step 3: Present Results

1. **ALWAYS display the complete tabular output** from the procedure
2. **Then** provide analysis:
   - Users/IPs that would be blocked
   - Users/IPs that would be allowed
   - Potential access disruptions
   - Compliance summary

**⚠️ STOP**: Review results with user.

#### Step 4: Recommendations

Based on results, suggest:
- Policy adjustments if too restrictive
- Additional IP ranges to include/exclude
- Users who may need exceptions

#### Stopping Points (Evaluate)

- ✋ Step 1: After gathering parameters
- ✋ Step 3: After presenting evaluation results

#### Notes (Evaluate)

- Executes with CALLER privileges - access to sensitive security data
- Use cases:
  - Test policies before deployment to avoid lockouts

---

### Migrate Workflow

Analyze an existing network policy to identify IP addresses that can be replaced with Snowflake-managed SaaS rules (auto-updated).

#### Step 1: Select Existing Policy

**List policies:**
```sql
SHOW NETWORK POLICIES IN ACCOUNT;
```

**Ask user:** Which policy would you like to analyze for SaaS migration?

**⚠️ STOP**: Confirm policy selection.

#### Step 2: Extract IP Addresses

**Get policy details:**
```sql
DESCRIBE NETWORK POLICY <selected_policy>;
```

Parse the `ALLOWED_IP_LIST` column to extract all IP addresses. If the policy uses `ALLOWED_NETWORK_RULE_LIST`, describe each rule:
```sql
DESCRIBE NETWORK RULE <db>.<schema>.<rule_name>;
```

#### Step 3: SaaS Coverage Check

Use the [SaaS Coverage Check](#saas-coverage-check) query with the extracted IPs.

#### Step 4: Present Migration Recommendation

Present results:
```
**SaaS Coverage Analysis for <policy_name>:**

IPs covered by SaaS rules (can be replaced):
- <ip1> -> SNOWFLAKE.NETWORK_SECURITY.<RULE_NAME>
- <ip2> -> SNOWFLAKE.NETWORK_SECURITY.<RULE_NAME>

IPs not covered (keep in custom rule):
- <ip3>, <ip4>, ...

**Recommendation:** Create hybrid policy with:
- SaaS rules: <list matching rules>
- Custom rule: <remaining IPs>
```

**⚠️ STOP**: Get user approval before creating replacement policy.

#### Step 5: Create Replacement Policy

Follow the [Creating a Hybrid Network Policy](#creating-a-hybrid-network-policy) pattern to create:
1. Custom network rule (non-SaaS IPs only)
2. Hybrid network policy (custom rule + SaaS rules)

#### Step 6: Evaluate and Swap

1. **Evaluate** new policy using [Evaluate Workflow](#evaluate-workflow)
2. If successful, swap policies (see [Policy Assignment](#policy-assignment)):
```sql
-- If assigned to user
ALTER USER <username> SET NETWORK_POLICY = '<new_hybrid_policy>';

-- If assigned to account
ALTER ACCOUNT SET NETWORK_POLICY = '<new_hybrid_policy>';

-- Remove old policy
DROP NETWORK POLICY <old_policy>;
```

**⚠️ STOP**: Confirm before swapping policies.

#### Stopping Points (Migrate)

- ✋ Step 1: After selecting policy
- ✋ Step 4: After presenting migration recommendation
- ✋ Step 6: Before swapping policies
