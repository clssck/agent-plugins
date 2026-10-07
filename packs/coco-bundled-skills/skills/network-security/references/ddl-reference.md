# Network Policy DDL Reference

Quick reference for network policy and rule commands.

## Network Rules

```sql
-- Create a network rule
CREATE NETWORK RULE <db>.<schema>.<rule_name>
    TYPE = IPV4
    MODE = INGRESS  -- or EGRESS
    VALUE_LIST = ('ip1/cidr', 'ip2/cidr', ...);

-- Modify a network rule
ALTER NETWORK RULE <rule_name> SET VALUE_LIST = ('new_ip1', 'new_ip2');

-- Drop a network rule (must not be attached to any policy)
DROP NETWORK RULE <rule_name>;
```

## Network Policies

```sql
-- Create policy with network rules (recommended)
CREATE NETWORK POLICY <policy_name>
    ALLOWED_NETWORK_RULE_LIST = ('<db.schema.rule1>', '<db.schema.rule2>')
    BLOCKED_NETWORK_RULE_LIST = ('<db.schema.block_rule>')
    COMMENT = 'Description';

-- Create policy with IP lists (legacy)
CREATE NETWORK POLICY <policy_name>
    ALLOWED_IP_LIST = ('ip1', 'ip2')
    BLOCKED_IP_LIST = ('ip3')
    COMMENT = 'Description';

-- Modify a policy
ALTER NETWORK POLICY <policy_name> 
    SET ALLOWED_NETWORK_RULE_LIST = ('<new_rule>');

-- Drop a policy (must not be assigned to any user/account)
DROP NETWORK POLICY <policy_name>;
```

## Apply Policies

```sql
-- Apply to a specific user
ALTER USER <username> SET NETWORK_POLICY = '<policy_name>';

-- Remove from user
ALTER USER <username> UNSET NETWORK_POLICY;

-- Apply to entire account (ACCOUNTADMIN required)
ALTER ACCOUNT SET NETWORK_POLICY = '<policy_name>';

-- Remove from account
ALTER ACCOUNT UNSET NETWORK_POLICY;
```

## View Policy Assignments

```sql
-- Check user's network policy
SHOW PARAMETERS LIKE 'NETWORK_POLICY' FOR USER <username>;

-- Check account network policy
SHOW PARAMETERS LIKE 'NETWORK_POLICY' FOR ACCOUNT;

-- List all users with their policies
SELECT USER_NAME, NETWORK_POLICY 
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
WHERE NETWORK_POLICY IS NOT NULL;
```
