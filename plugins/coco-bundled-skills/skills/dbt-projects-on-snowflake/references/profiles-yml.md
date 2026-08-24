# profiles.yml Requirements

For Snowflake-native dbt execution, your `profiles.yml` has specific requirements.

## Required Fields

```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: MY_ACCOUNT
      user: MY_USER
      role: MY_ROLE
      database: MY_DATABASE
      warehouse: MY_WAREHOUSE
      schema: MY_SCHEMA
      threads: 4
```

## Forbidden Fields

These fields cause errors in Snowflake-native dbt:

| Field | Error | Why |
|-------|-------|-----|
| `password` | "Unsupported fields found: password" | Auth handled by Snowflake session |
| `authenticator` | "Unsupported fields found: authenticator" | Not needed |
| `{{ env_var('...') }}` | "Env var required but not provided" | dbt runs inside Snowflake, not locally |

## Valid Example

```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: MYORG-MYACCOUNT
      user: DBT_USER
      role: DBT_ROLE
      database: ANALYTICS
      warehouse: COMPUTE_WH
      schema: DBT_MODELS
      threads: 4
```

## Invalid Examples

```yaml
# ❌ WRONG - has password field
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: MYORG-MYACCOUNT
      user: DBT_USER
      password: "secret123"  # REMOVE THIS
      role: DBT_ROLE
      database: ANALYTICS
      warehouse: COMPUTE_WH
      schema: DBT_MODELS
```

```yaml
# ❌ WRONG - uses env_var()
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "{{ env_var('SF_ACCOUNT') }}"  # REPLACE WITH LITERAL
      user: "{{ env_var('SF_USER') }}"        # REPLACE WITH LITERAL
      role: DBT_ROLE
      database: ANALYTICS
      warehouse: COMPUTE_WH
      schema: DBT_MODELS
```
