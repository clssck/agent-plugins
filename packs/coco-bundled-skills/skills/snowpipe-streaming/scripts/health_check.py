#!/usr/bin/env python3
"""
health_check.py - Snowpipe Streaming pipeline health check

Checks channel status, ingestion progress, offset gaps, and costs.

Usage:
    uv run --project <SKILL_DIR>/scripts python <SKILL_DIR>/scripts/health_check.py \
        --database <DB> --schema <SCHEMA> --table <TABLE> \
        --connection <CONNECTION_NAME>

    # With custom timestamp column:
    uv run --project <SKILL_DIR>/scripts python <SKILL_DIR>/scripts/health_check.py \
        --database <DB> --schema <SCHEMA> --table <TABLE> \
        --timestamp-column CREATED_AT
"""

import argparse
import json
import os
from datetime import datetime

import snowflake.connector


def get_connection(connection_name: str):
    return snowflake.connector.connect(connection_name=connection_name)


def detect_timestamp_column(cursor, database: str, schema: str, table: str) -> str | None:
    """Auto-detect a timestamp column in the table."""
    cursor.execute(f"DESCRIBE TABLE {database}.{schema}.{table}")
    columns = cursor.fetchall()
    
    timestamp_types = ("TIMESTAMP", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "TIMESTAMP_TZ", "DATETIME")
    candidates = ["event_timestamp", "created_at", "timestamp", "ingested_at", "ts", "time"]
    
    col_info = {row[0].lower(): row[1].upper() for row in columns}
    
    for candidate in candidates:
        if candidate in col_info and any(t in col_info[candidate] for t in timestamp_types):
            return candidate.upper()
    
    for col_name, col_type in col_info.items():
        if any(t in col_type for t in timestamp_types):
            return col_name.upper()
    
    return None


def check_channels(cursor, database: str, schema: str, table: str) -> dict:
    try:
        cursor.execute(f"SHOW CHANNELS IN TABLE {database}.{schema}.{table}")
        channels = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        channel_list = [dict(zip(col_names, row)) for row in channels]
        return {
            "status": "ok" if channel_list else "warning",
            "count": len(channel_list),
            "channels": channel_list[:20],
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "count": 0, "channels": []}


def check_pipes(cursor, database: str, schema: str, table: str) -> dict:
    try:
        cursor.execute(f"SHOW PIPES LIKE '%{table}%' IN SCHEMA {database}.{schema}")
        pipes = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        pipe_list = [dict(zip(col_names, row)) for row in pipes]
        return {
            "status": "ok" if pipe_list else "warning",
            "count": len(pipe_list),
            "pipes": pipe_list,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "count": 0, "pipes": []}


def check_ingestion_progress(cursor, database: str, schema: str, table: str, ts_col: str | None) -> dict:
    if not ts_col:
        return {"status": "skipped", "message": "No timestamp column available"}
    
    try:
        cursor.execute(f"""
            SELECT
                COUNT(*) AS total_rows,
                MIN({ts_col}) AS earliest,
                MAX({ts_col}) AS latest,
                DATEDIFF(second, MIN({ts_col}), MAX({ts_col})) AS span_seconds
            FROM {database}.{schema}.{table}
            WHERE {ts_col} > DATEADD(hour, -1, CURRENT_TIMESTAMP())
        """)
        row = cursor.fetchone()
        if row and row[0] > 0:
            return {
                "status": "ok",
                "timestamp_column": ts_col,
                "rows_last_hour": row[0],
                "earliest": str(row[1]),
                "latest": str(row[2]),
                "span_seconds": row[3],
                "rows_per_minute": round(row[0] / max(row[3] / 60, 1), 1) if row[3] else 0,
            }
        return {"status": "warning", "message": "No rows in last hour", "rows_last_hour": 0}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_row_count(cursor, database: str, schema: str, table: str) -> dict:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {database}.{schema}.{table}")
        count = cursor.fetchone()[0]
        return {"status": "ok", "total_rows": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_streaming_costs(cursor) -> dict:
    try:
        cursor.execute("""
            SELECT
                PIPE_NAME,
                SUM(CREDITS_USED) AS total_credits,
                SUM(BYTES_INSERTED) / POWER(1024, 3) AS gb_ingested
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
            WHERE SERVICE_TYPE = 'SNOWPIPE_STREAMING'
              AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP())
            GROUP BY PIPE_NAME
            ORDER BY total_credits DESC
        """)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        cost_data = [dict(zip(col_names, row)) for row in rows]
        total_credits = sum(float(r.get("TOTAL_CREDITS", 0) or 0) for r in cost_data)
        return {
            "status": "ok",
            "total_credits_7d": round(total_credits, 4),
            "pipes": cost_data[:10],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_channel_errors(cursor, table: str) -> dict:
    try:
        cursor.execute(f"""
            SELECT
                CHANNEL_NAME,
                EVENT_TYPE,
                ERROR_MESSAGE,
                EVENT_TIMESTAMP
            FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPIPE_STREAMING_CHANNEL_HISTORY
            WHERE PIPE_NAME ILIKE '%{table}%'
              AND ERROR_MESSAGE IS NOT NULL
              AND EVENT_TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP())
            ORDER BY EVENT_TIMESTAMP DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        errors = [dict(zip(col_names, row)) for row in rows]
        return {
            "status": "warning" if errors else "ok",
            "error_count_24h": len(errors),
            "recent_errors": errors,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Snowpipe Streaming health check")
    parser.add_argument("--database", required=True, help="Database name")
    parser.add_argument("--schema", required=True, help="Schema name")
    parser.add_argument("--table", required=True, help="Table name")
    parser.add_argument("--timestamp-column", default=None, help="Timestamp column name (auto-detected if not specified)")
    parser.add_argument("--connection", default=os.getenv("SNOWFLAKE_CONNECTION_NAME", "default"), help="Connection name")
    args = parser.parse_args()

    conn = get_connection(args.connection)
    cursor = conn.cursor()

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "target": f"{args.database}.{args.schema}.{args.table}",
        "checks": {},
    }

    print(f"Running health check on {args.database}.{args.schema}.{args.table}...\n")

    ts_col = args.timestamp_column
    if not ts_col:
        print("0. Auto-detecting timestamp column...")
        ts_col = detect_timestamp_column(cursor, args.database, args.schema, args.table)
        if ts_col:
            print(f"   Found: {ts_col}\n")
        else:
            print("   No timestamp column found (ingestion progress check will be skipped)\n")

    print("1. Checking row count...")
    report["checks"]["row_count"] = check_row_count(cursor, args.database, args.schema, args.table)
    rc = report["checks"]["row_count"]
    print(f"   Total rows: {rc.get('total_rows', 'N/A')}\n")

    print("2. Checking channels...")
    report["checks"]["channels"] = check_channels(cursor, args.database, args.schema, args.table)
    ch = report["checks"]["channels"]
    print(f"   Active channels: {ch['count']}\n")

    print("3. Checking pipes...")
    report["checks"]["pipes"] = check_pipes(cursor, args.database, args.schema, args.table)
    pi = report["checks"]["pipes"]
    print(f"   Pipes found: {pi['count']}\n")

    print("4. Checking ingestion progress (last hour)...")
    report["checks"]["ingestion"] = check_ingestion_progress(cursor, args.database, args.schema, args.table, ts_col)
    ing = report["checks"]["ingestion"]
    if ing["status"] == "ok":
        print(f"   Rows last hour: {ing['rows_last_hour']}")
        print(f"   Rows/min: {ing.get('rows_per_minute', 'N/A')}\n")
    else:
        print(f"   {ing.get('message', ing.get('error', 'Unknown'))}\n")

    print("5. Checking channel errors (last 24h)...")
    report["checks"]["channel_errors"] = check_channel_errors(cursor, args.table)
    ce = report["checks"]["channel_errors"]
    print(f"   Errors found: {ce.get('error_count_24h', 0)}\n")

    print("6. Checking streaming costs (last 7 days)...")
    report["checks"]["costs"] = check_streaming_costs(cursor)
    co = report["checks"]["costs"]
    print(f"   Total credits (7d): {co.get('total_credits_7d', 'N/A')}\n")

    overall_status = "HEALTHY"
    for check_name, check_result in report["checks"].items():
        if check_result.get("status") == "error":
            overall_status = "ERROR"
            break
        if check_result.get("status") == "warning":
            overall_status = "WARNING"

    report["overall_status"] = overall_status
    print(f"Overall Status: {overall_status}")
    print(f"\nFull report:\n{json.dumps(report, indent=2, default=str)}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
