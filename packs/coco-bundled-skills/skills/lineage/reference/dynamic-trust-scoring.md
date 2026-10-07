# Dynamic Trust Scoring

**IMPORTANT:** Before executing any template containing dynamic placeholders, you MUST:

1. **Read** `config/schema-patterns.yaml`
2. **Build** the appropriate CASE statement dynamically from the patterns
3. **Replace** the placeholder in the SQL template (including the column name from the placeholder)

## Placeholder Syntax

Templates use this format: `/* PLACEHOLDER_TYPE:column_name */`

The `column_name` after the colon tells you which column to use in the generated CASE statement.

**Examples in templates:**
- `/* SCHEMA_TRUST_SCORING:m.schema_name */` → Use `m.schema_name` in CASE
- `/* SCHEMA_TRUST_TIER:fl.obj_schema */` → Use `fl.obj_schema` in CASE  
- `/* SCHEMA_RISK_SCORING:d.dep_schema */` → Use `d.dep_schema` in CASE

## Building Dynamic CASE Statements

Read `config/schema-patterns.yaml` and generate CASE statements based on the placeholder type:

**SCHEMA_TRUST_SCORING** - Returns numeric score (100=PRODUCTION, 60=STAGING, 40=RAW, 20=UNTRUSTED, else 50):
```sql
CASE
    WHEN UPPER(column_name) LIKE '%ANALYTICS%' THEN 100
    WHEN UPPER(column_name) LIKE '%STAG%' THEN 60
    -- ... (all patterns from trust_tiers section)
    ELSE 50
END
```

**SCHEMA_TRUST_TIER** - Returns tier name string:
```sql
CASE
    WHEN UPPER(column_name) LIKE '%ANALYTICS%' THEN 'PRODUCTION'
    WHEN UPPER(column_name) LIKE '%STAG%' THEN 'STAGING'
    -- ... (all patterns mapped to tier names)
    ELSE 'UNKNOWN'
END
```

**SCHEMA_RISK_SCORING** - Returns 'CRITICAL' or NULL:
```sql
CASE
    WHEN UPPER(column_name) LIKE '%FINANCE%' THEN 'CRITICAL'
    WHEN UPPER(column_name) LIKE '%REVENUE%' THEN 'CRITICAL'
    -- ... (all risk_critical_patterns)
    ELSE NULL
END
```

## Why Dynamic?

This approach allows customers to:
1. **Add new patterns** without modifying SQL templates
2. **Customize trust tiers** for their naming conventions
3. **Extend risk patterns** for their critical schemas
4. **Version control** pattern changes separately from logic
