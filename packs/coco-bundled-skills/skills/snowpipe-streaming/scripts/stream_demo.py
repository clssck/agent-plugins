#!/usr/bin/env python3
"""
stream_demo.py - End-to-end Snowpipe Streaming demo

Creates a table, opens a channel, streams sample rows, and verifies ingestion.

Usage:
    uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/stream_demo.py \
        --account <ACCOUNT> --user <USER> --private-key-path <KEY_PATH> \
        --database <DB> --schema <SCHEMA> --table <TABLE>
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime


def create_table(args):
    import snowflake.connector

    conn_params = {"account": args.account, "user": args.user}

    if args.connection:
        conn = snowflake.connector.connect(connection_name=args.connection)
    else:
        conn = snowflake.connector.connect(**conn_params)

    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {args.database}")
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {args.database}.{args.schema}")
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {args.database}.{args.schema}.{args.table} (
            id NUMBER,
            name VARCHAR,
            timestamp TIMESTAMP_NTZ,
            payload VARIANT,
            source VARCHAR
        )
    """)
    print(f"Table {args.database}.{args.schema}.{args.table} ready.")

    cursor.close()
    conn.close()


def stream_rows(args):
    from snowflake.ingest.streaming import StreamingIngestClient

    with open(args.private_key_path, "r") as f:
        private_key = f.read()

    profile = {
        "account": args.account,
        "user": args.user,
        "url": f"https://{args.account}.snowflakecomputing.com:443",
        "private_key": private_key,
    }

    if args.role:
        profile["role"] = args.role

    profile_path = "/tmp/stream_demo_profile.json"
    with open(profile_path, "w") as f:
        json.dump(profile, f)

    pipe_name = f"{args.table}-STREAMING"
    print(f"Connecting to pipe: {args.database}.{args.schema}.{pipe_name}")

    client = StreamingIngestClient(
        client_name="stream_demo_client",
        db_name=args.database,
        schema_name=args.schema,
        pipe_name=pipe_name,
        profile_json=profile_path,
    )

    channel, status = client.open_channel(channel_name="demo_channel")
    print(f"Channel opened. Status: {status}")

    sample_rows = [
        {
            "id": i,
            "name": f"demo_record_{i}",
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {"index": i, "demo": True, "tags": ["streaming", "v2"]},
            "source": "stream_demo.py",
        }
        for i in range(1, args.count + 1)
    ]

    print(f"Streaming {len(sample_rows)} rows...")

    for i, row in enumerate(sample_rows):
        channel.append_row(row, offset_token=str(i + 1))

    print("Waiting for flush...")
    channel.wait_for_flush(timeout_seconds=30)

    committed_token = channel.get_latest_committed_offset_token()
    print(f"Last committed offset: {committed_token}")

    channel.close()
    client.close()

    os.remove(profile_path)

    return len(sample_rows)


def verify_ingestion(args, expected_rows: int):
    import snowflake.connector

    time.sleep(3)

    if args.connection:
        conn = snowflake.connector.connect(connection_name=args.connection)
    else:
        conn = snowflake.connector.connect(account=args.account, user=args.user)

    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT COUNT(*) FROM {args.database}.{args.schema}.{args.table}
        WHERE source = 'stream_demo.py'
    """)
    count = cursor.fetchone()[0]
    print(f"\nVerification: {count} demo rows found (expected {expected_rows})")

    cursor.execute(f"""
        SELECT id, name, TYPEOF(payload) AS payload_type
        FROM {args.database}.{args.schema}.{args.table}
        WHERE source = 'stream_demo.py'
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print("\nSample rows:")
    for row in rows:
        print(f"  id={row[0]}, name={row[1]}, payload_type={row[2]}")

    if rows and rows[0][2] == "OBJECT":
        print("\nVARIANT stored correctly as OBJECT.")
    elif rows:
        print("\nWARNING: VARIANT stored as VARCHAR — check SDK usage.")

    cursor.close()
    conn.close()

    return count >= expected_rows


def main():
    parser = argparse.ArgumentParser(description="Snowpipe Streaming end-to-end demo")
    parser.add_argument("--account", required=True, help="Snowflake account identifier")
    parser.add_argument("--user", required=True, help="Snowflake username")
    parser.add_argument("--private-key-path", required=True, help="Path to RSA private key (PKCS#8)")
    parser.add_argument("--database", required=True, help="Target database")
    parser.add_argument("--schema", required=True, help="Target schema")
    parser.add_argument("--table", default="STREAMING_DEMO", help="Target table name")
    parser.add_argument("--role", default=None, help="Snowflake role")
    parser.add_argument("--count", type=int, default=10, help="Number of rows to stream")
    parser.add_argument("--connection", default=None, help="Snowflake connection name (for table creation/verification)")
    args = parser.parse_args()

    print("=" * 60)
    print("Snowpipe Streaming Demo")
    print("=" * 60)

    print("\nStep 1: Create target table...")
    create_table(args)

    print("\nStep 2: Stream sample data via SDK...")
    rows_sent = stream_rows(args)

    print("\nStep 3: Verify ingestion...")
    success = verify_ingestion(args, rows_sent)

    print("\n" + "=" * 60)
    if success:
        print("Demo SUCCEEDED — Snowpipe Streaming is working!")
    else:
        print("Demo FAILED — check errors above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
