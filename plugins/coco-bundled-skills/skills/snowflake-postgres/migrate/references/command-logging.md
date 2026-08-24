# Command Logging

All migration commands should be logged for audit purposes.

## Initialize Logging

```bash
# Connection details are set via environment variables (SOURCE_PGHOST, etc.)
init_logging
```

## Usage

```bash
run_logged "Description of action" command args...
```

## View Logs

```bash
cat "$MIGRATION_LOG_FILE"
ls -la ~/.pg_migration_logs/
tail -f "$MIGRATION_LOG_FILE"
```
