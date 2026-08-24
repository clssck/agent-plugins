---
name: sql-author
description: "Use for ANY task that writes, fixes, runs, or debugs Snowflake SQL. Especially use when the user provides a failed query, a Snowflake SQL error, asks to repair SQL, asks for data from tables/views, or needs query validation."
---

# SQL Author

Write or fix Snowflake SQL by grounding the answer in the actual schema and by validating the final statement before presenting it.

## Workflow

1. **Read the full request and failed SQL first.** Identify the user goal, the failing statement, the Snowflake error, and whether the task is a fix, a new query, or an investigation. Many failed fixes come from solving only the visible syntax error while missing the query's intended shape.

2. **Inspect real objects before changing columns or joins.** Use `DESCRIBE TABLE`, `SHOW TABLES`, `SHOW VIEWS`, or `INFORMATION_SCHEMA.COLUMNS` because Snowflake errors such as invalid identifier, ambiguous column, type mismatch, and object-not-found often require knowing the real column names and types. Guessing column names is faster but commonly creates a new compile error.

3. **Check table size.** Query `INFORMATION_SCHEMA.TABLES` for `ROW_COUNT` before running against unfamiliar tables. Add date/partition filters to avoid long query time. Tell the user: which table, what date range, what filters, how you're computing the metric. If any of these feel like guesses, stop and ask — a one-turn clarification beats a confident wrong answer.

4. **Use object search when the object is incomplete or ambiguous.** If the user gives a partial table name or the SQL references an object that may be a view, use `cortex search object "<name>"` before declaring it missing. Ask the user only when multiple plausible objects remain. For complex SQL, try `cortex semantic-views search "<topic>"`. Semantic views have verified metric definitions.

5. **Check unfamiliar Snowflake syntax and functions.** Use `cortex search docs "<function or syntax>"` or a tiny compile-only probe when you are not certain. Snowflake has sharp dialect rules around `QUALIFY`, `LATERAL FLATTEN`, recursive CTEs, `OBJECT_AGG`, `ARRAY_CAT`, `TRY_CAST`, `TYPEOF`, stage syntax, and `INFORMATION_SCHEMA` table functions.

6. **Fix the root cause, not just the first parser error.** Syntax cleanup can reveal deeper errors such as nested aggregates, wrong CTE scope, bad aliases, invalid casts, or unsupported correlated subqueries. After each change, reconsider whether the new SQL still satisfies the original user intent.

7. **Prefer conservative rewrites.** Preserve selected columns, filters, grouping grain, ordering, and limits unless they are the reason the query fails. A compiling query that changes the result shape is not a good fix.

8. **Handle common Snowflake gotchas deliberately.**
   - `!= 'value'` does not match NULLs; include `OR col IS NULL` when that is intended.
   - `COUNT(col)` excludes NULLs; `COUNT(*)` does not.
   - Use `QUALIFY` for window filters instead of wrapping when possible.
   - Use `ILIKE` instead of `LOWER(col) LIKE` for case-insensitive filters.
   - Use `DIV0NULL` or `NULLIF` for division safety.
   - Cast `VARIANT` fields explicitly before comparison or aggregation.
   - `ARRAY_CAT` takes two arrays; nest calls for more than two.

9. **Diagnose access errors instead of rewriting blindly.** When the error is privilege-related, run `CALL EXPLAIN_PRIVILEGES(statement => '<failing_sql>', missing_only => true, for_role => '<role>')`. SQL-authoring cannot fix a missing grant, but the user still needs a precise explanation.

10. **Validate the exact final SQL.** Before presenting the SQL to the user, call `snowflake_sql_execute` with `only_compile=true` on the complete final statement. Compile-only validation is cheap and catches the exact failure class this skill is meant to prevent: syntax errors, invalid identifiers, bad function signatures, and type mismatches. If validation fails, read the new error, revise the SQL, and validate again. Keep validating and fix the SQL to be presented until it passes the compile with no error.
