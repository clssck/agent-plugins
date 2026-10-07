# DCM Primitive Reference: SQL Procedures

## Syntax

```sql
DEFINE PROCEDURE database_name.schema_name.procedure_name(
    [param_name param_type [, ...]]
)
RETURNS return_type
LANGUAGE SQL
[CALLED ON NULL INPUT | STRICT]
[VOLATILE | IMMUTABLE]
[COMMENT = 'description']
AS
$$
    -- procedure body (SQL)
$$;
```

## Minimal Example

```sql
DEFINE PROCEDURE my_db.my_schema.log_event(event_type VARCHAR, event_data VARIANT)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
    INSERT INTO my_db.my_schema.event_log (event_type, payload, created_at)
    VALUES (:event_type, :event_data, CURRENT_TIMESTAMP());
    RETURN 'OK';
$$;
```

## Immutable Properties

These cannot be changed after creation. To change them, the procedure must be dropped and recreated:

| Property | Notes |
|----------|-------|
| `LANGUAGE` | Always `SQL` for SQL procedures |
| Signature | Parameter names and types define the overload identity |

DCM will report an error if you try to change these. Use a new procedure name if the signature must change.

## Supported Changes

After creation, DCM can apply changes to:

| Property | Notes |
|----------|-------|
| Body (AS block) | Procedure logic between `$$` delimiters |
| `COMMENT` | Descriptive text |
| `CALLED ON NULL INPUT` / `STRICT` | Null-handling behavior |

## Body Quoting

The procedure body must be enclosed in `$$` delimiters (dollar-quoting). Single-quote strings inside the body normally, since `$$` quoting avoids conflicts:

```sql
DEFINE PROCEDURE my_db.my_schema.greet(user_name VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
    RETURN 'Hello, ' || :user_name || '!';
$$;
```

## Parameter References

Inside the body, reference parameters with a colon prefix (`:param_name`) or directly by name depending on context:

```sql
DEFINE PROCEDURE my_db.my_schema.update_status(record_id NUMBER, new_status VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
AS
$$
    UPDATE my_db.my_schema.records
    SET status = :new_status,
        updated_at = CURRENT_TIMESTAMP()
    WHERE id = :record_id;
    RETURN SQLROWCOUNT;
$$;
```

## File Organization

Place procedure definitions in a dedicated file at the project root:

```
sources/definitions/
  procedures.sql    ← DEFINE PROCEDURE statements
  tables.sql
  views.sql
```

## Jinja Templating

Use Jinja variables for environment-specific databases or schemas:

```sql
DEFINE PROCEDURE {{ database }}.{{ schema }}.process_events(batch_size NUMBER)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
    INSERT INTO {{ database }}.{{ schema }}.processed_events
    SELECT * FROM {{ database }}.{{ schema }}.raw_events
    LIMIT :batch_size;
    RETURN 'Processed ' || SQLROWCOUNT || ' rows';
$$;
```

Use Jinja loops to create per-environment or per-tenant variants:

```sql
{% for env in ['dev', 'prod'] %}
DEFINE PROCEDURE {{ env }}_db.analytics.refresh_summary()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
    INSERT OVERWRITE INTO {{ env }}_db.analytics.summary
    SELECT date_trunc('day', created_at) AS day, COUNT(*) AS cnt
    FROM {{ env }}_db.raw.events
    GROUP BY 1;
    RETURN 'OK';
$$;
{% endfor %}
```

## Notes

- SQL procedures are synchronous; the caller blocks until the procedure completes.
- Procedures support overloading: two procedures in the same schema can share a name if their parameter types differ. DCM treats each overload as a distinct object.
