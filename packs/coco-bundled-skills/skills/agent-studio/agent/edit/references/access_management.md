# Agent Access Management

This reference covers granting, revoking, and inspecting access on Cortex Agents. Run each statement via `snowflake_sql_execute`.

## Grant Access to Users/Roles

```sql
-- Grant usage on the agent
GRANT USAGE ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> TO ROLE <ROLE_NAME>;

-- Also grant access to underlying resources
GRANT USAGE ON DATABASE <DATABASE> TO ROLE <ROLE_NAME>;
GRANT USAGE ON SCHEMA <DATABASE>.<SCHEMA> TO ROLE <ROLE_NAME>;

-- For Analyst tools: grant access to semantic view and warehouse
GRANT USAGE ON SEMANTIC VIEW <DATABASE>.<SCHEMA>.<SEMANTIC_VIEW> TO ROLE <ROLE_NAME>;
GRANT USAGE ON WAREHOUSE <WAREHOUSE> TO ROLE <ROLE_NAME>;

-- For Search tools: grant access to search service
GRANT USAGE ON CORTEX SEARCH SERVICE <DATABASE>.<SCHEMA>.<SEARCH_SERVICE> TO ROLE <ROLE_NAME>;
```

## Revoke Access

```sql
REVOKE USAGE ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> FROM ROLE <ROLE_NAME>;
```

## Check Current Grants

```sql
SHOW GRANTS ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
SHOW GRANTS TO ROLE <ROLE_NAME>;
```
