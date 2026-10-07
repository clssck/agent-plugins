# Feature Transformation Patterns

Common patterns for defining features in Snowflake Feature Store using Snowpark Python and SQL.

---

## Per-Row Features

Functions applied to each row independently. One output row per input row.

```python
def compute_features(df: snowpark.DataFrame) -> snowpark.DataFrame:
    df = df.fillna({"foo": 0})
    df = df.with_column("zipcode", F.compute_zipcode(df["lat"], df["long"]))
    return df
```

```sql
SELECT *, CASE WHEN amount > 1000 THEN 'high' ELSE 'low' END AS amount_tier
FROM source_table;
```

---

## Per-Group Features

Aggregate values within a group. One output row per group.

```python
def group_features(df: snowpark.DataFrame) -> snowpark.DataFrame:
    return df.group_by("city").agg(
        F.sum("rainfall").alias("total_rainfall"),
        F.avg("temperature").alias("avg_temperature"),
        F.count("*").alias("num_readings")
    )
```

```sql
SELECT city,
       SUM(rainfall) AS total_rainfall,
       AVG(temperature) AS avg_temperature,
       COUNT(*) AS num_readings
FROM weather_data
GROUP BY city;
```

---

## Row-Based Window Features

Aggregate over a fixed window of rows. One output row per window frame.

```python
from snowflake.snowpark import Window

def sum_past_3_transactions(df: snowpark.DataFrame) -> snowpark.DataFrame:
    window = Window.partition_by("id").order_by("ts").rows_between(-2, Window.CURRENT_ROW)
    return df.select(
        "id", "ts",
        F.sum("amount").over(window).alias("sum_past_3_transactions")
    )
```

```sql
SELECT id, ts,
       SUM(amount) OVER (
           PARTITION BY id ORDER BY ts
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS sum_past_3_transactions
FROM transactions;
```

---

## Moving Aggregation Features

Compute moving statistics (sum, avg, min, max) within a specified window size. Uses the Snowpark analytics API.

```python
new_df = df.analytics.moving_agg(
    aggs={"AMOUNT": ["SUM", "AVG"]},
    window_sizes=[7, 30],
    order_by=["TX_DATE"],
    group_by=["CUSTOMER_ID"]
)
# Produces: AMOUNT_SUM_7, AMOUNT_SUM_30, AMOUNT_AVG_7, AMOUNT_AVG_30
```

---

## Cumulative Aggregation Features

Running totals from the start (or to the end) of a partition. One output row per input row.

```python
new_df = df.analytics.cumulative_agg(
    aggs={"SALESAMOUNT": ["SUM", "MIN", "MAX"]},
    order_by=["ORDERDATE"],
    group_by=["PRODUCTKEY"],
    is_forward=True
)
```

---

## Lag Features

Values from prior rows, offset by a specified number of rows. Useful for detecting trends.

```python
new_df = df.analytics.compute_lag(
    cols=["AMOUNT"],
    lags=[1, 7, 30],
    order_by=["TX_DATE"],
    group_by=["CUSTOMER_ID"]
)
# Produces: AMOUNT_LAG_1, AMOUNT_LAG_7, AMOUNT_LAG_30
```

---

## Lead Features

Values from subsequent rows.

```python
new_df = df.analytics.compute_lead(
    cols=["AMOUNT"],
    leads=[1, 7],
    order_by=["TX_DATE"],
    group_by=["CUSTOMER_ID"]
)
```

---

## Time-Based Window Aggregations (RANGE BETWEEN)

Aggregate over calendar time windows rather than row counts.

```sql
SELECT customer_id, tx_datetime, tx_amount,
    SUM(tx_amount) OVER (
        PARTITION BY customer_id ORDER BY tx_datetime
        RANGE BETWEEN INTERVAL '1 DAY' PRECEDING AND CURRENT ROW
    ) AS tx_amount_1d,
    SUM(tx_amount) OVER (
        PARTITION BY customer_id ORDER BY tx_datetime
        RANGE BETWEEN INTERVAL '7 DAYS' PRECEDING AND CURRENT ROW
    ) AS tx_amount_7d,
    COUNT(*) OVER (
        PARTITION BY customer_id ORDER BY tx_datetime
        RANGE BETWEEN INTERVAL '30 DAYS' PRECEDING AND CURRENT ROW
    ) AS tx_count_30d
FROM transactions;
```

---

## Tile-Based Aggregation (Feature Store Native)

Use the Feature Store's built-in Aggregation API for efficient pre-computed tiles. Requires `snowflake-ml-python >= 1.24.0`.

```python
from snowflake.ml.feature_store import Feature

amount = Feature("PURCHASE_AMOUNT", "Amount of each purchase")

fv = FeatureView(
    name="CUSTOMER_AGG_FEATURES",
    entities=[customer_entity],
    feature_df=transactions_df,
    feature_granularity="1 day",
    features=[
        amount.sum(windows=["7d", "30d"]).alias("TOTAL_SPEND"),
        amount.avg(windows=["7d", "30d"]).alias("AVG_SPEND"),
        amount.count(windows=["7d", "30d"]).alias("PURCHASE_CNT"),
        amount.std(windows=["30d"]).alias("SPEND_STD"),
    ],
    timestamp_col="TX_DATETIME",
    refresh_freq="1 day",
)
```

**How it works:** A Dynamic Table stores pre-computed partial aggregations (tiles). During dataset generation, tiles are merged for point-in-time correct results.

**Available functions:** `.sum()`, `.count()`, `.avg()`, `.min()`, `.max()`, `.std()`, `.var()`, `.approx_count_distinct()`, `.last_n()`, `.first_n()`

### Choosing `feature_granularity` (tile size)

Start from the data cadence:

| Data Type | `feature_granularity` |
|-----------|----------------------|
| Clickstream | `"1 hour"` |
| Transactions | `"1 day"` |
| Weekly reports | `"1 week"` |

When the feature view has explicit aggregation windows, the tile size must
satisfy these rules:

- **Divides every aggregation window evenly**, is **≤ the smallest window**, and
  is **≥ 1 minute** (the SDK floor).
- Aim for roughly `largest_window / 90` (rounded down to a divisor of all
  windows) so each window is covered by ~90 tiles. Finer tiles give more
  accurate, reusable partial aggregations; coarser tiles trade accuracy for
  cheaper storage/refresh.
- For continuous stream feature views, omitting `feature_granularity` defaults
  to `"1m"`; set it explicitly only when the windows require a coarser tile.

> This is the canonical tile-size guidance. Skills that generate or migrate
> aggregation feature views link here rather than restating the rules.

---

## Temporal Feature Patterns

Derive features from date, timestamp, or YYYYMM-encoded columns.

| Category | Features | SQL Pattern | When to Use |
|----------|----------|-------------|-------------|
| **Calendar extraction** | `ORIG_MONTH`, `ORIG_QUARTER`, `ORIG_YEAR` | `MOD(YYYYMM_COL, 100)`, `CEIL(MOD()/3.0)::INT`, `FLOOR(YYYYMM_COL/100)` | Any date/YYYYMM column |
| **Seasonality flags** | `IS_WINTER_ORIG`, `IS_Q4_ORIG`, `IS_WEEKEND` | `CASE WHEN month IN (...) THEN 1 ELSE 0 END` | Seasonal patterns expected |
| **Duration / span** | `LOAN_DURATION_YEARS`, `CONTRACT_MONTHS` | `DATEDIFF(...)` on static date pairs | Two date columns define a span |
| **Cyclical encoding** | `MONTH_SIN`, `MONTH_COS`, `DOW_SIN`, `DOW_COS` | `SIN(2 * PI() * val / period)`, `COS(...)` | Month/day-of-week should wrap |
| **Epoch / vintage** | `DAYS_SINCE_EPOCH`, `ORIG_YEAR_BUCKET` | `DATEDIFF('day', '1970-01-01', date_col)`, `FLOOR(YEAR/5)*5` | Absolute time position matters |
| **Relative position** | `MONTH_IN_QUARTER`, `WEEK_IN_YEAR` | `MOD(month - 1, 3) + 1`, `WEEKOFYEAR(...)` | Position within cycle matters |

---

## Combining Multiple Pattern Types

A feature view can combine multiple pattern types in a single Snowpark DataFrame pipeline:

```python
def build_customer_features(session, source_table):
    df = session.table(source_table)

    # Per-row: derive day of week
    df = df.with_column("DAY_OF_WEEK", F.dayofweek(F.col("TX_DATETIME")))

    # Per-group with window: rolling aggregates
    window_7d = Window.partition_by("CUSTOMER_ID").order_by("TX_DATETIME").range_between(-7*86400, 0)
    df = df.with_column("TX_SUM_7D", F.sum("TX_AMOUNT").over(window_7d))

    # Lag: previous transaction amount
    window_lag = Window.partition_by("CUSTOMER_ID").order_by("TX_DATETIME")
    df = df.with_column("PREV_TX_AMOUNT", F.lag("TX_AMOUNT", 1).over(window_lag))

    return df
```

---

## Incremental Refresh Compatibility

These patterns **block** incremental refresh on Dynamic Tables:

| Blocker | Fix |
|---------|-----|
| `MODE()` | Replace with `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY COUNT(*) DESC)` in a separate FV |
| `RANDOM()`, `UUID()` | Remove or compute outside the FV |
| `CURRENT_DATE()`, `CURRENT_TIMESTAMP()` | Remove — compute at query/inference time instead |
| Float-typed aggregation + JOINs | Remove JOINs or split into separate FVs |
| Float-typed aggregation + CASE comparison | Cast INPUT columns to `DECIMAL` before aggregation: `AVG(COL::DECIMAL(10,2))` |
| `STDDEV()` / `AVG()` on float columns | Cast input to DECIMAL: `STDDEV(COL::DECIMAL(10,2))::DECIMAL(10,2)` |
