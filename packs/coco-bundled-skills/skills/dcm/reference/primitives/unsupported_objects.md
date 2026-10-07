# Unsupported Object Types in DCM

Objects not supported by DEFINE must be managed with companion SQL scripts.

## Supported DEFINE Types

See the **Supported Entities** table in [`syntax_overview.md`](../syntax_overview.md#supported-entities) for the canonical list of object types that can be managed with DEFINE.

Everything else requires imperative SQL in companion scripts.

## Companion Scripts

These files are **optional** — only needed if your project uses object types not supported by DEFINE. Place them at the **project root** alongside `manifest.yml` (NOT in `sources/definitions/`, NOT referenced in manifest).

### `pre_deploy.sql` — Runs before `snow dcm plan`

Objects referenced by DEFINE statements that the planner validates at plan time. These must exist before `snow dcm plan` runs:
- Integrations, including the **storage integrations** referenced by `DEFINE STAGE ... STORAGE_INTEGRATION = ...` and the **notification integrations** referenced by `DEFINE PIPE ... INTEGRATION = ...` or `ERROR_INTEGRATION = ...` (requires ACCOUNTADMIN)
- Network rules and policies (requires SECURITYADMIN)
- Shares (requires CREATE SHARE privilege)

Begin the file with `USE ROLE ACCOUNTADMIN;` or run with `snow sql -f pre_deploy.sql --role ACCOUNTADMIN`.

### `post_deploy.sql` — Runs after `snow dcm deploy`

Objects that depend on DEFINE'd entities and must be created after `snow dcm deploy`:
- Semantic views

> **Not here:** external stages, streams, and pipes are all supported by `DEFINE` and belong
> in `sources/definitions/`, not in a companion script. See `primitives/stages.md`,
> `primitives/streams.md`, and `primitives/pipes.md`.
>
> Two of those have a cloud-side or account-level prerequisite that *does* belong in
> `pre_deploy.sql` — a storage integration for a private external stage, a notification
> integration for an `AUTO_INGEST` pipe. The prerequisite is the companion-script work, not
> the entity itself.

## Examples

```sql
-- pre_deploy.sql
USE ROLE ACCOUNTADMIN;
CREATE API INTEGRATION IF NOT EXISTS my_api_integration
    API_PROVIDER = aws_api_gateway
    API_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/my_role'
    API_ALLOWED_PREFIXES = ('https://my-api.example.com')
    ENABLED = TRUE;

CREATE STORAGE INTEGRATION IF NOT EXISTS my_s3_int
    TYPE = EXTERNAL_STAGE
    STORAGE_PROVIDER = 'S3'
    STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/snowflake-access'
    STORAGE_ALLOWED_LOCATIONS = ('s3://my-bucket/');
```

```sql
-- post_deploy.sql
CREATE SEMANTIC VIEW IF NOT EXISTS my_db.my_schema.my_semantic_view
    TABLES (my_db.my_schema.my_table);
```

## Important Notes

- **No Jinja**: Unlike DCM definition files, companion scripts do not support Jinja templating. `snow sql -f` has no Jinja renderer. For multi-environment setups, maintain separate files per target or use shell variable substitution.
- **No dependency management**: Unlike DEFINE'd objects, companion script objects are NOT part of DCM's dependency graph. You must manually ensure correct execution order within these files.
- **Idempotency**: Use `CREATE IF NOT EXISTS` for stable objects (integrations, network policies). Use `CREATE OR REPLACE` for objects you expect to redefine.

## Execution Order

```
pre_deploy.sql → snow dcm plan → confirm → snow dcm deploy → post_deploy.sql → post_deployment_grants.sql
```
