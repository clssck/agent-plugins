# Adaptive Warehouse Limitations

## Edition Requirement

Adaptive Warehouses are available for **Enterprise edition and above** (Enterprise, Business Critical, VPS). Standard edition does not have access.

## What Cannot Be Converted to Adaptive

| Warehouse | Reason |
|-----------|--------|
| Snowpark-optimized warehouses | Not supported |
| Interactive warehouses | Not supported |
| X5LARGE or X6LARGE warehouses | Not supported |

## Workload Types Not Recommended for Adaptive

While technically supported, **workloads against hybrid tables are not recommended for Adaptive Warehouses**. Adaptive Compute is not optimized for hybrid table query patterns. Keep warehouses serving hybrid table workloads on Standard warehouse type.

**IMPORTANT:** When telling a customer their warehouse type or size is not supported for adaptive, do **NOT** provide any `ALTER WAREHOUSE` DDL — not even with a placeholder name. Providing conversion SQL alongside a "not supported" message is contradictory and confusing. Explain the limitation clearly and stop.

**IMPORTANT:** When answering a limitations question, focus exclusively on what is not supported. Do **NOT** include DDL or guidance for eligible warehouse types — doing so dilutes the limitation message and confuses the user.

## Revert

Any adaptive warehouse can be converted back to standard using `ALTER WAREHOUSE ... SET WAREHOUSE_TYPE = 'STANDARD';`. This is an online operation with no downtime.