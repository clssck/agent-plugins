# Private Git Packages (Secrets)

When `packages.yml` uses `env_var()` to inject a git token for private repositories, the proper Snowflake approach is to use Snowflake secrets via the `secrets:` section of `env.yml`. This masks the token value (`****` in logs) and integrates with Snowflake's access control.

## Setup

### 1. Create a Snowflake SECRET

```sql
CREATE OR REPLACE SECRET <database>.<schema>.<secret_name>
  TYPE = GENERIC_STRING
  SECRET_STRING = '<git_token_value>';

GRANT READ ON SECRET <database>.<schema>.<secret_name> TO ROLE <your_role>;
```

### 2. Set Up Network Rule and EAI

```sql
-- Allow traffic to git host
CREATE OR REPLACE NETWORK RULE <database>.<schema>.dbt_network_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('hub.getdbt.com', 'github.com');

-- Create external access integration (scope to specific secret for least-privilege)
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION <eai_name>
  ALLOWED_NETWORK_RULES = (<database>.<schema>.dbt_network_rule)
  ALLOWED_AUTHENTICATION_SECRETS = (<database>.<schema>.<secret_name>)
  ENABLED = TRUE;

GRANT USAGE ON INTEGRATION <eai_name> TO ROLE <your_role>;
```

> **Note on `ALLOWED_AUTHENTICATION_SECRETS`:**
> - Prefer scoping to the specific secret: `= (<database>.<schema>.<secret_name>)` (least-privilege)
> - `= ALL` is acceptable too (secret access is still validated before it is used)
> - The secret must exist before it can be referenced in the EAI
> - If the EAI already exists, check its current value first:
>   ```sql
>   DESCRIBE EXTERNAL ACCESS INTEGRATION <eai_name>;
>   ```
>   Then:
>   - If `ALLOWED_AUTHENTICATION_SECRETS = ALL` → skip, no change needed
>   - If it lists specific secrets → add yours to the existing list
>   - If empty → set it to the new secret
>   ```sql
>   ALTER EXTERNAL ACCESS INTEGRATION <eai_name>
>     SET ALLOWED_AUTHENTICATION_SECRETS = (<existing_secrets>, <database>.<schema>.<secret_name>);
>   ```
>
> ⚠️ **MANDATORY CHECKPOINT — STOP HERE:**
> Present the exact ALTER statement to the user:
> ```sql
> ALTER EXTERNAL ACCESS INTEGRATION <eai_name>
>   SET ALLOWED_AUTHENTICATION_SECRETS = (<list_of_secrets>);
> ```
> Changing `ALLOWED_AUTHENTICATION_SECRETS` affects all projects using this integration.
> **Wait for explicit approval (Yes/No/Modify). NEVER proceed without user confirmation.**

### 3. Add secrets to env.yml

```yaml
env_config:
  default_environment: dev
  environments:
    - name: dev
      secrets:
        - snowflake_secret: <database>.<schema>.<secret_name>
          env_var_name: DBT_ENV_SECRET_GIT_TOKEN
      env:
        DBT_CURRENT_ROLE: "{{ select CURRENT_ROLE() }}"
        DBT_CURRENT_DB: "{{ select CURRENT_DATABASE() }}"
        DBT_CURRENT_SCHEMA: "{{ select CURRENT_SCHEMA() }}"
        DBT_CURRENT_WH: "{{ select CURRENT_WAREHOUSE() }}"
```

### 4. Update packages.yml

**CRITICAL:** The `env_var()` call in `packages.yml` MUST match the `env_var_name` from the `secrets:` section above. Rename the existing variable to use the `DBT_ENV_SECRET_` prefix:

```yaml
packages:
  - git: "https://{{env_var('DBT_ENV_SECRET_GIT_TOKEN')}}@github.com/org/repo.git"
    revision: main
```

### 5. Deploy with EAI

```bash
snow dbt deploy MY_PROJECT --source ./project --database DB --schema SCHEMA \
  --external-access-integration <eai_name> --default-env dev
```

The EAI must allow the secret — either `ALLOWED_AUTHENTICATION_SECRETS = ALL` or `= (<secret_name>)`.

## Key Rules

- Secret env var names MUST start with `DBT_ENV_SECRET_`
- NEVER put token values as plain text in the `env:` section
- The EAI must include the secret in its `ALLOWED_AUTHENTICATION_SECRETS` list

## Access Requirements

For the secret to resolve at runtime, **both** conditions must be met:
1. **EAI allows the secret** — via `ALLOWED_AUTHENTICATION_SECRETS = (<secret>)` or `= ALL`
2. **Executing role has READ on the secret** — `GRANT READ ON SECRET ... TO ROLE <role>`

The EAI alone is not sufficient — if the executing role lacks `READ` on the secret, the dbt project will fail with an access error even if the EAI uses `ALL`.

## Checklist

- [ ] Create Snowflake secret with git token
- [ ] Create network rule allowing git host
- [ ] Create or update external access integration
- [ ] Add `secrets:` section to env.yml with `env_var_name: DBT_ENV_SECRET_*`
- [ ] Rename `env_var()` in `packages.yml` to match the `DBT_ENV_SECRET_*` name from env.yml
- [ ] Deploy with `--external-access-integration`
