# profiles.yml Requirements

For Snowflake-native dbt execution, your `profiles.yml` has specific requirements.

## Required Fields

```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: ""                         # empty string OK in workspaces
      user: ""                            # empty string OK in workspaces
      role: "{{ env_var('DBT_CURRENT_ROLE') }}"
      database: "{{ env_var('DBT_CURRENT_DB') }}"
      warehouse: "{{ env_var('DBT_CURRENT_WH') }}"
      schema: "{{ env_var('DBT_CURRENT_SCHEMA') }}"
      threads: 4
```

## env_var() Usage

`env_var()` IS supported in `profiles.yml` when backed by an `env.yml` file in the project root. The `env.yml` defines the values that `env_var()` resolves from at runtime.

**Rules for env_var() in profiles.yml:**
- Variable names must be `DBT_`-prefixed and UPPERCASE (e.g., `DBT_CURRENT_ROLE`)
- Values come from the active environment in `env.yml`
- `account` and `user` can be set to `""` (empty string) or `"not needed"` — auth is handled by the Snowflake session

**Workspaces restriction:** When running in Workspaces, the `role` and `warehouse` fields only accept bare context functions via env.yml (e.g., `"{{ select CURRENT_ROLE() }}"` or `"{{ select CURRENT_WAREHOUSE() }}"` in env.yml). Complex SQL expressions for these two fields cause a validation error in Workspaces. The `database` and `schema` fields have no such restriction. This restriction does NOT apply to deployed dbt project objects.

## Forbidden Fields

These fields cause errors in Snowflake-native dbt:

| Field | Error | Why |
|-------|-------|-----|
| `password` | "Unsupported fields found: password" | Auth handled by Snowflake session |
| `authenticator` | "Unsupported fields found: authenticator" | Not needed |
| `private_key_path` | "Unsupported fields found: private_key_path" | Not needed |
| `private_key_passphrase` | "Unsupported fields found: private_key_passphrase" | Not needed |
| `token` | "Unsupported fields found: token" | Not needed |

## Valid Example (with env.yml)

```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: ""                         # empty string OK in workspaces
      user: ""                            # empty string OK in workspaces
      role: "{{ env_var('DBT_CURRENT_ROLE') }}"
      database: "{{ env_var('DBT_CURRENT_DB') }}"
      warehouse: "{{ env_var('DBT_CURRENT_WH') }}"
      schema: "{{ env_var('DBT_CURRENT_SCHEMA') }}"
      threads: 8
```

This requires a corresponding `env.yml` in the project root:
```yaml
env_config:
  default_environment: dev
  environments:
    - name: dev
      env:
        DBT_CURRENT_ROLE: "{{ select CURRENT_ROLE() }}"
        DBT_CURRENT_DB: <your_database>
        DBT_CURRENT_WH: "{{ select CURRENT_WAREHOUSE() }}"
        DBT_CURRENT_SCHEMA: "{{ select CURRENT_SCHEMA() }}"
```

## Valid Example (literal values, no env.yml)

If you don't need dynamic values or multi-environment support, hardcoded literals work too:

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
# ❌ WRONG - env_var keys must start with DBT_ (Snowflake only injects values from env.yml/--env-vars for DBT_-prefixed keys)
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "{{ env_var('SF_ACCOUNT') }}"    # Must be DBT_-prefixed
      user: "{{ env_var('SF_USER') }}"          # Must be DBT_-prefixed
      role: DBT_ROLE
      database: ANALYTICS
      warehouse: COMPUTE_WH
      schema: DBT_MODELS
```
