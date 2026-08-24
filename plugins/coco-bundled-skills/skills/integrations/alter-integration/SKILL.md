---
name: alter-integration
description: >
  Modify properties of an existing integration (generic). Use a type-specific ALTER command when available
---

# ALTER INTEGRATION


Modifies the properties for an existing integration.

## Syntax

```sql
ALTER <integration_type> INTEGRATION <object_name> <actions>
```

Where `<actions>` are specific to the object type.

For specific syntax, usage notes, and examples, see:

- ALTER API INTEGRATION
- ALTER CATALOG INTEGRATION
- ALTER EXTERNAL ACCESS INTEGRATION
- ALTER NOTIFICATION INTEGRATION
- ALTER SECURITY INTEGRATION
- ALTER STORAGE INTEGRATION
