# Jinja Filter Reference

The DCR Jinja engine registers these filters:

| Filter | Purpose | Example |
|--------|---------|---------|
| `sqlsafe` | Raw SQL identifier (UNSAFE for user values) | `{{ column_name | sqlsafe }}` |
| `join_policy` | Restricts to allowed join columns | `{{ col \| join_policy }}` |
| `column_policy` | Restricts to allowed analysis columns | `{{ col \| column_policy }}` |
| `activation_policy` | Restricts to allowed activation columns | `{{ col \| activation_policy }}` |
| `join_and_column_policy` | Combined join + analysis restriction | `{{ col \| join_and_column_policy }}` |
| `bind` | Parameterizes value for safe SQL (auto-applied — see below) | `{{ threshold \| bind }}` |
| `inclause` | Array-safe binding for IN clauses | `WHERE col IN ({{ arr \| inclause }})` |

**Auto-binding:** The engine automatically wraps every `{{ var }}` with `| bind` unless it already ends in `| bind`, `| inclause`, or `| sqlsafe`. This means:
- `{{ my_param }}` → auto-parameterized (safe, no injection risk)
- `{{ my_param | sqlsafe }}` → raw SQL injection (by design — for identifiers and column names only)
- `{{ my_array | inclause }}` → array-safe binding for IN clauses

**Rule of thumb:** Use `| sqlsafe` only for column names and identifiers. Never use `| sqlsafe` on user-supplied values — with one exception: trusted-collaborator raw-SQL parameters (like `where_clause`) that are explicitly documented as accepting arbitrary SQL predicates. These require `| sqlsafe` to function as intended and carry an inherent injection risk acknowledged by the collaboration trust model. For array parameters in `WHERE ... IN (...)`, always use `| inclause`.

**Policy filter syntax (transitional):**
```sql
{{ col | join_policy }}            -- restricts join columns
{{ col | column_policy }}          -- restricts analysis columns
{{ col | activation_policy }}      -- restricts activation columns
{{ col | join_and_column_policy }} -- restricts both join and analysis columns (combined)
```

**Known limitation:** Policy filters break with table aliases:
```sql
p1.{{ col | join_policy }}  -- BROKEN — filter cannot parse alias prefix
```

**Workaround:** Pass alias-qualified column as parameter value (leaks internals).

**Future state:** Per the Scalable SQL Jinja PRD, policy enforcement will move to the platform layer. Policies declared via `schema_and_template_policies` on data offerings will be enforced automatically at runtime. Template authors will eventually not need to embed policy filters.

**Recommendation:** Use `schema_and_template_policies` on data offerings where possible. Only embed policy filters when you need fine-grained control not available through offering-level policies.
