#!/usr/bin/env python3
"""
Run a .sql file statement-by-statement using Snowflake CLI (`snow sql`).

NOTE: Prefer using Cortex Code's built-in Snowflake connection when available—it
maintains session context automatically and provides a better experience. Use this
script as a fallback when Cortex Code's connection is unavailable.

Why this script exists:
- The skill test plan requires executing scripts "section by section (ending in ';')",
  not as a whole file.

Design goals:
- Split on semicolons that terminate statements, while being aware of:
  - single-quoted strings: '...'
  - double-quoted identifiers: "..."
  - Snowflake scripting blocks / $$-delimited bodies: $$ ... $$ (and custom $tag$ ... $tag$)
  - line comments: -- ...
  - block comments: /* ... */

This is not a full SQL parser, but is sufficient for our test scripts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class SplitResult:
    statements: list[str]


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch in ("_", "$")


def split_sql_statements(sql: str) -> SplitResult:
    statements: list[str] = []
    buf: list[str] = []

    in_squote = False
    in_dquote = False
    in_line_comment = False
    in_block_comment = False

    # Dollar-quoted blocks: $$...$$ or $tag$...$tag$
    dollar_tag: str | None = None  # e.g. "$$" or "$TAG$"

    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        # Handle line comments
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # Handle block comments
        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        # Handle dollar-quoted blocks
        if dollar_tag is not None:
            buf.append(ch)
            # detect closing tag
            if ch == "$":
                # try match at this position
                if sql.startswith(dollar_tag, i):
                    # append the rest of the tag
                    buf.append(sql[i + 1 : i + len(dollar_tag)])
                    i += len(dollar_tag)
                    dollar_tag = None
                    continue
            i += 1
            continue

        # Strings / identifiers
        if in_squote:
            buf.append(ch)
            if ch == "'":
                # escaped '' inside strings
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                    continue
                in_squote = False
            i += 1
            continue

        if in_dquote:
            buf.append(ch)
            if ch == '"':
                # escaped "" inside identifiers
                if nxt == '"':
                    buf.append(nxt)
                    i += 2
                    continue
                in_dquote = False
            i += 1
            continue

        # Not in any special mode: detect starts
        if ch == "-" and nxt == "-":
            buf.append(ch)
            buf.append(nxt)
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            buf.append(ch)
            buf.append(nxt)
            in_block_comment = True
            i += 2
            continue

        if ch == "'":
            buf.append(ch)
            in_squote = True
            i += 1
            continue

        if ch == '"':
            buf.append(ch)
            in_dquote = True
            i += 1
            continue

        # Dollar tag start: $...$
        if ch == "$":
            # Find tag: starts at i, ends at next '$' with identifier chars in between (or empty => $$)
            j = i + 1
            while j < n and _is_ident_char(sql[j]):
                j += 1
            if j < n and sql[j] == "$":
                tag = sql[i : j + 1]  # includes both $
                buf.append(tag)
                dollar_tag = tag
                i = j + 1
                continue

        # Statement terminator
        if ch == ";":
            buf.append(ch)
            stmt = "".join(buf).strip()
            buf = []
            if stmt:
                statements.append(stmt)
            i += 1
            continue

        # Default
        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return SplitResult(statements=statements)


def run_statements(
    *,
    connection: str,
    role: str | None,
    database: str | None,
    schema: str | None,
    warehouse: str | None,
    statements: list[str],
    out_path: str,
    err_path: str,
    stop_on_error: bool,
) -> int:
    rc_overall = 0
    with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
        for idx, stmt in enumerate(statements, start=1):
            now_utc = dt.datetime.now(dt.UTC)
            header = f"\n--- statement {idx}/{len(statements)} @ {now_utc.isoformat()} ---\n"
            out.write(header)
            out.write(stmt + ("\n" if not stmt.endswith("\n") else ""))
            out.flush()

            cmd = ["snow", "sql", "-c", connection, "-q", stmt]
            if role:
                cmd += ["--role", role]
            if database:
                cmd += ["--database", database]
            if schema:
                cmd += ["--schema", schema]
            if warehouse:
                cmd += ["--warehouse", warehouse]

            p = subprocess.run(cmd, stdout=out, stderr=err, text=True)
            if p.returncode != 0:
                rc_overall = p.returncode
                err.write(f"\n[runner] FAILED statement {idx} rc={p.returncode}\n")
                err.flush()
                if stop_on_error:
                    return rc_overall
    return rc_overall


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connection", "-c", required=True)
    ap.add_argument("--role", default=None)
    ap.add_argument("--database", default=None)
    ap.add_argument("--schema", default=None)
    ap.add_argument("--warehouse", default=None)
    ap.add_argument("--file", "-f", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--err", required=True)
    ap.add_argument("--stop-on-error", action="store_true", default=False)
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        sql = f.read()

    res = split_sql_statements(sql)
    if not res.statements:
        # treat empty as success
        open(args.out, "w", encoding="utf-8").write("[runner] no statements\n")
        open(args.err, "w", encoding="utf-8").write("")
        return 0

    return run_statements(
        connection=args.connection,
        role=args.role,
        database=args.database,
        schema=args.schema,
        warehouse=args.warehouse,
        statements=res.statements,
        out_path=args.out,
        err_path=args.err,
        stop_on_error=args.stop_on_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())


