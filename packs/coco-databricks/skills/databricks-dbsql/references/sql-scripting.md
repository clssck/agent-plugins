# SQL Scripting, Stored Procedures, Recursive CTEs, and Transactions

> **Availability:** SQL Scripting requires Databricks Runtime 16.3+. Stored Procedures, Recursive CTEs, and Multi-Statement Transactions require Databricks Runtime 17.0+.

---

## SQL Scripting

SQL Scripting lets you execute multiple SQL statements as a single block using compound statements. It supports variables, control flow, loops, and exception handling directly in SQL.

### Compound Statements (BEGIN...END)

A compound statement groups multiple statements into one executable block. Statements inside are separated by semicolons.

```sql
BEGIN
  DECLARE total INT DEFAULT 0;
  SET total = (SELECT COUNT(*) FROM <catalog>.<schema>.orders);
  SELECT total AS order_count;
END;
```

**Key rules:**
- Compound statements can be used standalone, inside stored procedures, or as the body of `EXECUTE IMMEDIATE`.
- Variables declared inside a `BEGIN...END` block are scoped to that block.
- The outermost `BEGIN...END` does not require a label. Inner blocks can optionally be labeled.

### Variable Declaration (DECLARE)

Declare session variables within a compound statement. Variables must be declared before use.

**Syntax:**

```sql
DECLARE variable_name data_type [DEFAULT expression];
```

**Examples:**

```sql
BEGIN
  DECLARE order_count INT DEFAULT 0;
  DECLARE cutoff_date DATE DEFAULT CURRENT_DATE() - INTERVAL 30 DAYS;
  DECLARE customer_name STRING;

  SET order_count = (SELECT COUNT(*) FROM <catalog>.<schema>.orders WHERE order_date >= cutoff_date);
  SELECT order_count;
END;
```

Multiple variables can be declared in sequence:

```sql
BEGIN
  DECLARE x INT DEFAULT 1;
  DECLARE y INT DEFAULT 2;
  DECLARE z INT;
  SET z = x + y;
  SELECT z AS result;
END;
```

### Variable Assignment (SET / SET VAR)

Use `SET` or `SET VAR` to assign values to declared variables.

```sql
BEGIN
  DECLARE price DOUBLE;
  DECLARE quantity INT;
  DECLARE total DOUBLE;

  SET price = 29.99;
  SET VAR quantity = 5;
  SET total = price * quantity;
  SELECT total AS order_total;
END;
```

Assign from a query result:

```sql
BEGIN
  DECLARE max_amount DOUBLE;
  SET max_amount = (SELECT MAX(amount) FROM <catalog>.<schema>.invoices);
  SELECT max_amount;
END;
```

### Control Flow

#### IF / ELSEIF / ELSE

**Syntax:**

```sql
IF condition THEN
  statements;
[ELSEIF condition THEN
  statements;]
[ELSE
  statements;]
END IF;
```

**Example:**

```sql
BEGIN
  DECLARE status STRING;
  DECLARE cnt INT;
  SET cnt = (SELECT COUNT(*) FROM <catalog>.<schema>.orders WHERE status = 'pending');

  IF cnt > 100 THEN
    SET status = 'HIGH';
  ELSEIF cnt > 10 THEN
    SET status = 'MEDIUM';
  ELSE
    SET status = 'LOW';
  END IF;

  SELECT status AS pending_level;
END;
```

#### CASE Statement

**Simple CASE:**

```sql
BEGIN
  DECLARE region STRING DEFAULT 'EMEA';
  DECLARE discount DOUBLE;

  CASE region
    WHEN 'NA' THEN SET discount = 0.10;
    WHEN 'EMEA' THEN SET discount = 0.15;
    WHEN 'APAC' THEN SET discount = 0.12;
    ELSE SET discount = 0.05;
  END CASE;

  SELECT discount;
END;
```

**Searched CASE:**

```sql
BEGIN
  DECLARE score INT DEFAULT 85;
  DECLARE grade STRING;

  CASE
    WHEN score >= 90 THEN SET grade = 'A';
    WHEN score >= 80 THEN SET grade = 'B';
    WHEN score >= 70 THEN SET grade = 'C';
    ELSE SET grade = 'F';
  END CASE;

  SELECT grade;
END;
```

#### WHILE Loop

**Syntax:**

```sql
[label:] WHILE condition DO
  statements;
END WHILE [label];
```

**Example:**

```sql
BEGIN
  DECLARE counter INT DEFAULT 1;
  DECLARE total INT DEFAULT 0;

  WHILE counter <= 10 DO
    SET total = total + counter;
    SET counter = counter + 1;
  END WHILE;

  SELECT total AS sum_1_to_10;
END;
```

#### FOR Loop

Iterates over the result set of a query.

**Syntax:**

```sql
[label:] FOR row_variable IN (query) DO
  statements;
END FOR [label];
```

**Example:**

```sql
BEGIN
  DECLARE total_revenue DOUBLE DEFAULT 0.0;

  FOR row IN (SELECT amount FROM <catalog>.<schema>.invoices WHERE year = 2025) DO
    SET total_revenue = total_revenue + row.amount;
  END FOR;

  SELECT total_revenue;
END;
```

#### LOOP

An unconditional loop. Use `LEAVE` to exit.

**Syntax:**

```sql
[label:] LOOP
  statements;
END LOOP [label];
```

**Example:**

```sql
BEGIN
  DECLARE i INT DEFAULT 0;

  counter_loop: LOOP
    SET i = i + 1;
    IF i >= 5 THEN
      LEAVE counter_loop;
    END IF;
  END LOOP counter_loop;

  SELECT i AS final_value;
END;
```

#### REPEAT

Executes at least once, then repeats until the condition is true.

**Syntax:**

```sql
[label:] REPEAT
  statements;
UNTIL condition
END REPEAT [label];
```

**Example:**

```sql
BEGIN
  DECLARE n INT DEFAULT 1;
  DECLARE result INT DEFAULT 1;

  REPEAT
    SET result = result * n;
    SET n = n + 1;
  UNTIL n > 5
  END REPEAT;

  SELECT result AS factorial_5;
END;
```

#### LEAVE and ITERATE

- `LEAVE label` exits the named loop immediately.
- `ITERATE label` skips to the next iteration of the named loop.

```sql
BEGIN
  DECLARE i INT DEFAULT 0;
  DECLARE total INT DEFAULT 0;

  sum_loop: WHILE i < 10 DO
    SET i = i + 1;
    IF i = 5 THEN
      ITERATE sum_loop;  -- skip adding 5
    END IF;
    IF i = 8 THEN
      LEAVE sum_loop;    -- stop at 8
    END IF;
    SET total = total + i;
  END WHILE;

  SELECT total;  -- 1+2+3+4+6+7 = 23
END;
```

### Exception Handling

#### Condition Declaration

Assign a name to a specific SQLSTATE or general condition for use in handlers.

```sql
DECLARE condition_name CONDITION FOR SQLSTATE 'value';
```

#### Handler Declaration

Handlers catch exceptions and execute recovery logic. Only `EXIT` handlers are supported.

**Syntax:**

```sql
DECLARE EXIT HANDLER FOR { SQLEXCEPTION | NOT FOUND | SQLSTATE 'value' | condition_name }
BEGIN
  handler_statements;
END;
```

- `SQLEXCEPTION` catches any SQL error.
- `NOT FOUND` catches the condition when a `SELECT INTO` or cursor returns no rows.

**Example:**

```sql
BEGIN
  DECLARE exit_code INT DEFAULT 0;

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    SET exit_code = -1;
    SELECT exit_code AS error_code, 'An error occurred' AS message;
  END;

  -- This will raise an error (division by zero)
  SELECT 1 / 0;

  SET exit_code = 1;
  SELECT exit_code AS success_code;
END;
```

**NOT FOUND handler:**

```sql
BEGIN
  DECLARE result STRING DEFAULT 'not found';

  DECLARE EXIT HANDLER FOR NOT FOUND
  BEGIN
    SELECT result AS outcome;
  END;

  SET result = (SELECT name FROM <catalog>.<schema>.customers WHERE id = -999);
  SELECT result AS outcome;
END;
```

#### SIGNAL and RESIGNAL

`SIGNAL` raises a user-defined exception. `RESIGNAL` re-raises the current exception inside a handler, optionally modifying the message.

**SIGNAL:**

```sql
BEGIN
  DECLARE val INT DEFAULT -1;

  IF val < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Value must be non-negative';
  END IF;
END;
```

**RESIGNAL:**

```sql
BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    RESIGNAL SET MESSAGE_TEXT = 'Wrapped error: operation failed';
  END;

  SELECT 1 / 0;
END;
```

### EXECUTE IMMEDIATE (Dynamic SQL)

Build and execute SQL strings at runtime.

**Syntax:**

```sql
EXECUTE IMMEDIATE sql_string [INTO variable] [USING parameter, ...];
```

**Example:**

```sql
BEGIN
  DECLARE table_name STRING DEFAULT '<catalog>.<schema>.products';
  DECLARE cnt INT;

  EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || table_name INTO cnt;
  SELECT cnt AS row_count;
END;
```

**With USING parameters:**

```sql
BEGIN
  DECLARE result INT;

  EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM <catalog>.<schema>.orders WHERE status = ?'
    INTO result
    USING 'shipped';

  SELECT result AS shipped_count;
END;
```

---

## Stored Procedures

Stored procedures encapsulate reusable SQL logic. They support input, output, and bidirectional parameters, and can be invoked with `CALL`.

### CREATE PROCEDURE

**Syntax:**

```sql
CREATE [OR REPLACE] PROCEDURE catalog.schema.procedure_name (
  [parameter_mode] param_name data_type [DEFAULT value] [COMMENT 'text'],
  ...
)
[RETURNS data_type]
[LANGUAGE SQL]
[SQL SECURITY { INVOKER | DEFINER }]
[COMMENT 'description']
{ compound_statement | RETURN expression }
```

**Parameter modes:**
- `IN` (default) -- read-only input.
- `OUT` -- output parameter, set inside the procedure.
- `INOUT` -- bidirectional, passed in and modified.

**SQL Security:**
- `INVOKER` (default) -- executes with the caller's privileges.
- `DEFINER` -- executes with the owner's privileges.

**Example -- basic procedure:**

```sql
CREATE OR REPLACE PROCEDURE <catalog>.<schema>.get_order_count(
  IN status_filter STRING DEFAULT 'all'
)
RETURNS INT
LANGUAGE SQL
SQL SECURITY INVOKER
COMMENT 'Returns the count of orders, optionally filtered by status.'
BEGIN
  DECLARE cnt INT;

  IF status_filter = 'all' THEN
    SET cnt = (SELECT COUNT(*) FROM <catalog>.<schema>.orders);
  ELSE
    SET cnt = (SELECT COUNT(*) FROM <catalog>.<schema>.orders WHERE status = status_filter);
  END IF;

  RETURN cnt;
END;
```

**Example -- OUT parameter:**

```sql
CREATE OR REPLACE PROCEDURE <catalog>.<schema>.summarize_sales(
  IN year_val INT,
  OUT total_sales DOUBLE,
  OUT order_count INT
)
LANGUAGE SQL
BEGIN
  SET total_sales = (
    SELECT COALESCE(SUM(amount), 0)
    FROM <catalog>.<schema>.sales
    WHERE year(sale_date) = year_val
  );
  SET order_count = (
    SELECT COUNT(*)
    FROM <catalog>.<schema>.sales
    WHERE year(sale_date) = year_val
  );
END;
```

**Example -- DEFINER security:**

```sql
CREATE OR REPLACE PROCEDURE <catalog>.<schema>.archive_old_orders()
LANGUAGE SQL
SQL SECURITY DEFINER
BEGIN
  INSERT INTO <catalog>.<schema>.orders_archive
  SELECT * FROM <catalog>.<schema>.orders
  WHERE order_date < CURRENT_DATE() - INTERVAL 365 DAYS;

  DELETE FROM <catalog>.<schema>.orders
  WHERE order_date < CURRENT_DATE() - INTERVAL 365 DAYS;
END;
```

### CALL

Invoke a stored procedure:

```sql
CALL <catalog>.<schema>.get_order_count('pending');
```

With named parameters:

```sql
CALL <catalog>.<schema>.get_order_count(status_filter => 'shipped');
```

With OUT parameters:

```sql
DECLARE total DOUBLE;
DECLARE cnt INT;
CALL <catalog>.<schema>.summarize_sales(2025, total, cnt);
SELECT total, cnt;
```

### DROP PROCEDURE

```sql
DROP PROCEDURE [IF EXISTS] <catalog>.<schema>.get_order_count;
```

### DESCRIBE PROCEDURE

```sql
DESCRIBE PROCEDURE <catalog>.<schema>.get_order_count;
```

### SHOW PROCEDURES

```sql
SHOW PROCEDURES IN <catalog>.<schema>;
```

---

## Recursive CTEs

Recursive CTEs allow a query to reference itself, enabling traversal of hierarchical or graph-structured data.

### Syntax

```sql
WITH RECURSIVE cte_name (column_list) AS (
  -- Anchor member (non-recursive base query)
  SELECT ...
  UNION ALL
  -- Recursive member (references cte_name)
  SELECT ...
  FROM cte_name
  JOIN ...
)
SELECT * FROM cte_name;
```

**Rules:**
- The anchor member executes first and produces the initial result set.
- The recursive member executes repeatedly, joining with the previous iteration's results, until no new rows are produced.
- `UNION ALL` is required between anchor and recursive members.

### MAX RECURSION LEVEL

Limits recursion depth to prevent infinite loops. Default is 100.

```sql
WITH RECURSIVE hierarchy (id, name, parent_id, lvl) AS (
  SELECT id, name, parent_id, 0 AS lvl
  FROM <catalog>.<schema>.employees
  WHERE parent_id IS NULL

  UNION ALL

  SELECT e.id, e.name, e.parent_id, h.lvl + 1
  FROM <catalog>.<schema>.employees e
  JOIN hierarchy h ON e.parent_id = h.id
)
SELECT * FROM hierarchy
MAX RECURSION LEVEL 50;
```

### Use Cases

**Hierarchy traversal (org chart):**

```sql
WITH RECURSIVE org_chart (emp_id, emp_name, manager_id, depth) AS (
  SELECT id, name, manager_id, 0
  FROM <catalog>.<schema>.employees
  WHERE manager_id IS NULL

  UNION ALL

  SELECT e.id, e.name, e.manager_id, oc.depth + 1
  FROM <catalog>.<schema>.employees e
  JOIN org_chart oc ON e.manager_id = oc.emp_id
)
SELECT * FROM org_chart ORDER BY depth, emp_name;
```

**Bill of materials (graph traversal):**

```sql
WITH RECURSIVE bom (part_id, part_name, parent_part_id, quantity, lvl) AS (
  SELECT part_id, part_name, parent_part_id, quantity, 0
  FROM <catalog>.<schema>.parts
  WHERE parent_part_id IS NULL

  UNION ALL

  SELECT p.part_id, p.part_name, p.parent_part_id, p.quantity * b.quantity, b.lvl + 1
  FROM <catalog>.<schema>.parts p
  JOIN bom b ON p.parent_part_id = b.part_id
)
SELECT * FROM bom;
```

**Date series generation:**

```sql
WITH RECURSIVE date_series (dt) AS (
  SELECT DATE '2025-01-01'

  UNION ALL

  SELECT dt + INTERVAL 1 DAY
  FROM date_series
  WHERE dt < DATE '2025-12-31'
)
SELECT dt FROM date_series
MAX RECURSION LEVEL 366;
```

### Limitations

- Only `UNION ALL` is supported (not `UNION`, `INTERSECT`, or `EXCEPT`).
- The recursive member must reference the CTE exactly once.
- Aggregate functions (`GROUP BY`, `DISTINCT`) are not allowed in the recursive member.
- Window functions are not allowed in the recursive member.
- Subqueries referencing the CTE are not allowed in the recursive member.
- `LIMIT` in the recursive member is not supported.

---

## Multi-Statement Transactions

> **Note:** Multi-statement transactions are in **Public Preview**.

Transactions group multiple write operations into an atomic unit. Either all statements commit or all roll back.

### SQL Scripting Atomic Blocks

Wrap statements in `BEGIN ATOMIC...END` to execute them as a single transaction. If any statement fails, the entire block rolls back.

```sql
BEGIN ATOMIC
  INSERT INTO <catalog>.<schema>.accounts (id, balance)
  VALUES (1, 1000.00);

  UPDATE <catalog>.<schema>.accounts
  SET balance = balance - 200.00
  WHERE id = 1;

  INSERT INTO <catalog>.<schema>.transactions (account_id, amount, txn_type)
  VALUES (1, -200.00, 'withdrawal');
END;
```

### Explicit Transaction Control

Use `COMMIT` and `ROLLBACK` inside compound statements for manual control:

```sql
BEGIN
  DECLARE exit_handler INT DEFAULT 0;

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    SET exit_handler = 1;
  END;

  BEGIN TRANSACTION;

  DELETE FROM <catalog>.<schema>.staging_orders
  WHERE processed = true;

  INSERT INTO <catalog>.<schema>.orders
  SELECT * FROM <catalog>.<schema>.staging_orders;

  UPDATE <catalog>.<schema>.staging_orders
  SET processed = true;

  COMMIT;

  SELECT 'Transaction committed' AS result;
END;
```

### Isolation Levels

Databricks supports two isolation levels for Delta tables:

| Isolation Level | Description |
|---|---|
| **Write Serializable** (default) | Ensures serializable ordering for writes. Reads can see a snapshot from the start of the transaction. |
| **Snapshot** | Concurrent writers can proceed without conflict unless they modify the same files. Reads see a consistent snapshot. |

Set at the table level:

```sql
ALTER TABLE <catalog>.<schema>.accounts
SET TBLPROPERTIES ('delta.isolationLevel' = 'Serializable');
```

### Write Conflicts and Concurrency

- **Write Serializable:** Two concurrent transactions modifying overlapping data will conflict. The first to commit wins; the second is retried or aborted.
- **Snapshot isolation:** Transactions conflict only if they modify the same physical files. Non-overlapping writes succeed concurrently.

Conflict-prone operations: `UPDATE`, `DELETE`, `MERGE` on overlapping partitions or rows.

### Best Practices

- Keep transactions short to minimize lock contention.
- Use `BEGIN ATOMIC...END` for simple atomic blocks instead of manual `COMMIT`/`ROLLBACK`.
- Prefer `Write Serializable` isolation for correctness-critical workloads.
- Use `Snapshot` isolation for high-concurrency workloads with non-overlapping writes.
- Add exception handlers around transactions for graceful rollback.
- Avoid mixing DDL and DML in the same transaction.
