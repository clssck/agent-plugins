# Stages in DCM

DCM manages **both internal and external stages** with `DEFINE STAGE`. The `URL` parameter is what makes a stage external — omit it and Snowflake creates an internal stage.

## Syntax

### Internal Stage

```sql
DEFINE STAGE database_name.schema_name.stage_name
    [DIRECTORY = (ENABLE = TRUE)]
    [FILE_FORMAT = (TYPE = 'format' ...)]
    [ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')]
    [COPY_OPTIONS = (ON_ERROR = 'option' ...)]
    [COMMENT = 'description'];
```

### External Stage

```sql
DEFINE STAGE database_name.schema_name.stage_name
    URL = 'cloud_url'
    [STORAGE_INTEGRATION = integration_name]
    [DIRECTORY = (ENABLE = TRUE [AUTO_REFRESH = TRUE | FALSE])]
    [FILE_FORMAT = (FORMAT_NAME = 'database_name.schema_name.format_name')]
    [ENCRYPTION = (TYPE = 'encryption_type')]
    [COMMENT = 'description'];
```

`URL` by cloud provider:

| Provider | URL form | Common `ENCRYPTION` types |
|----------|----------|---------------------------|
| Amazon S3 | `s3://bucket[/path/]` | `AWS_SSE_S3`, `AWS_SSE_KMS`, `NONE` |
| Microsoft Azure | `azure://account.blob.core.windows.net/container[/path/]` | `NONE` |
| Google Cloud Storage | `gcs://bucket[/path/]` | `GCS_SSE_KMS`, `NONE` |

Client-side encryption types (`AWS_CSE`, `AZURE_CSE`) are omitted on purpose: they require a `MASTER_KEY` in the definition, which is never acceptable here — see below.

## ⚠️ Never Put Credentials in a Definition File

DCM does **not** identify or obfuscate secrets. Anything written into a definition file is stored in plain text in the rendered project files **and in the project's deployment history**, readable by anyone with access to the project.

Never write these into a `DEFINE STAGE`:

- `CREDENTIALS = (AWS_KEY_ID = ... AWS_SECRET_KEY = ... )`
- `CREDENTIALS = (AZURE_SAS_TOKEN = ... )`
- `ENCRYPTION = (... MASTER_KEY = ... )`

When the location requires authentication, use a **storage integration** — it holds the cloud credentials outside the project:

```sql
DEFINE STAGE FINANCE_DB.RAW.S3_LANDING
    URL = 's3://finance-landing/incoming/'
    STORAGE_INTEGRATION = FINANCE_S3_INT
    COMMENT = 'External S3 landing zone';
```

Storage integrations are **not** supported by `DEFINE` and require ACCOUNTADMIN. Create the integration in `pre_deploy.sql` so it exists before `snow dcm plan` validates the stage — see `primitives/unsupported_objects.md`.

If the user asks for an external stage with inline credentials, don't write them: explain the plaintext exposure and offer the storage-integration pattern instead.

## Supported Changes

Applies to both internal and external stages:

- `DIRECTORY` table settings (enable/disable)
- `COMMENT`

## Immutable

- `ENCRYPTION` type cannot be changed after creation. The stage must be dropped and recreated to change encryption.

Changing `URL` or `STORAGE_INTEGRATION` on a deployed external stage is not among the documented in-place changes. Run `snow dcm plan` and read the output before deploying such a change; if the planner won't apply it, drop and recreate the stage.

## Decision Guide: Internal vs External Stage

| Stage Type | Has URL? | Credentials | Notes |
|------------|----------|-------------|-------|
| Internal | No | None | Files stored inside Snowflake |
| External, private location | Yes | Storage integration (never inline) | Integration goes in `pre_deploy.sql` |
| External, public read-only location | Yes | None | `URL` alone; no storage integration needed |

Both use `DEFINE STAGE` and live in `infrastructure.sql` (or `stages.sql`).

## Examples

### Basic Internal Stage

```sql
DEFINE STAGE FINANCE_DB.RAW.UPLOAD_STAGE
    COMMENT = 'Internal stage for file uploads';
```

### Internal Stage With Directory Table and File Format

```sql
DEFINE STAGE FINANCE_DB.RAW.CSV_LANDING
    DIRECTORY = (ENABLE = TRUE)
    FILE_FORMAT = (TYPE = 'CSV' FIELD_DELIMITER = '|' SKIP_HEADER = 1)
    COMMENT = 'CSV landing stage with directory tracking';
```

### External S3 Stage With Storage Integration

```sql
DEFINE STAGE FINANCE_DB.RAW.S3_INVOICES
    URL = 's3://finance-invoices/incoming/'
    STORAGE_INTEGRATION = FINANCE_S3_INT
    DIRECTORY = (ENABLE = TRUE AUTO_REFRESH = TRUE)
    FILE_FORMAT = (FORMAT_NAME = 'FINANCE_DB.RAW.CSV_FORMAT')
    COMMENT = 'Vendor invoice drop location';
```

The matching `pre_deploy.sql`:

```sql
USE ROLE ACCOUNTADMIN;
CREATE STORAGE INTEGRATION IF NOT EXISTS FINANCE_S3_INT
    TYPE = EXTERNAL_STAGE
    STORAGE_PROVIDER = 'S3'
    STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/snowflake-access'
    STORAGE_ALLOWED_LOCATIONS = ('s3://finance-invoices/');
```

### External Azure Stage

```sql
DEFINE STAGE FINANCE_DB.RAW.AZURE_EXPORTS
    URL = 'azure://financeacct.blob.core.windows.net/exports/'
    STORAGE_INTEGRATION = FINANCE_AZURE_INT
    COMMENT = 'Azure blob export location';
```

### With Jinja Templating

Per-environment URLs are the common reason to template a stage:

```sql
DEFINE STAGE ETL_DB{{env_suffix}}.RAW.DATA_STAGE
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Encrypted upload stage for {{env_suffix}} environment';

DEFINE STAGE ETL_DB{{env_suffix}}.RAW.S3_SOURCE
    URL = 's3://{{ s3_bucket }}/raw/'
    STORAGE_INTEGRATION = {{ storage_integration }}
    COMMENT = 'External source for {{env_suffix}} environment';
```

Put `s3_bucket` and `storage_integration` in `templating.configurations` per target so DEV and PROD read from different buckets.

### Stage Referencing a DEFINE'd File Format

When a file format is defined in the same project, the stage can reference it by fully-qualified name:

```sql
DEFINE FILE FORMAT FINANCE_DB.RAW.CSV_FORMAT
    TYPE = 'CSV'
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"';

DEFINE STAGE FINANCE_DB.RAW.UPLOAD_STAGE
    FILE_FORMAT = (FORMAT_NAME = 'FINANCE_DB.RAW.CSV_FORMAT')
    COMMENT = 'Upload stage referencing a DEFINE''d file format';
```

DCM resolves the dependency automatically. This works for external stages too.
