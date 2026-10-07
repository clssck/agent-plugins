# Reserved Parameter Names

**Protected Jinja variables** — avoid redeclaring these as parameter names:
- `source_table` — array of provider/source table references
- `my_table` — array of consumer/local table references
- `join_columns_check` — internal join security validation
- `request_id` — execution tracking identifier
- `application_id` — app identification
- `at_timestamp` — timestamp when the analysis request was submitted
- `app_instance_id` — app instance identifier
- `privacy` — differential privacy settings object (contains `epsilon`, `differential`, etc.)

These names are injected by the platform as built-in context variables at runtime. If you define a `parameters` entry with the same name, the spec may validate without error, but the platform's runtime value will shadow or conflict with your parameter — producing unexpected behavior. Reframe any colliding parameter to a distinct name (e.g. `filter_column` instead of `join_columns_check`).

**Table alias convention:**
- `p1` = `identifier({{ source_table[0] }})` (first provider table)
- `p2` = `identifier({{ source_table[1] }})` (second provider table)
- `c1` = `identifier({{ my_table[0] }})` (first consumer/local table)
