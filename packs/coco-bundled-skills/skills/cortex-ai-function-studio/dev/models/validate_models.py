#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.
"""Fetch model prices from Snowhouse and validate each model with AI_COMPLETE.

This script:
1. Fetches the latest model prices from the Snowhouse pricing table.
2. Tests each model with a simple AI_COMPLETE('model', 'Say hello') call
   against a target Snowflake connection.
3. Writes only validated (callable) models to src/models.json.

Usage:
    python dev/models/validate_models.py --fetch-connection SNOWHOUSE \
      --validate-connection snowhouse
    python dev/models/validate_models.py --validate-only \
      --validate-connection snowhouse
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

MODELS_JSON = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "snowflake-ai-optimize-core"
    / "src"
    / "snowflake_ai_optimize"
    / "core"
    / "models.json"
)

# Models to exclude from output entirely (deprecated, aliased, or retired).
# This is the single source of truth -- used both in the Snowhouse fetch SQL
# (WHERE NOT IN) and when filtering models loaded from models.json.
BLACKLISTED_MODELS = frozenset(
    {
        "claude-3-5-sonnet",
        "claude-3-7-sonnet",
        "claude-4-opus",
        "claude-4-sonnet",
        "claude-opus-4-6-long-context",
        "claude-sonnet-4-5-long-context",
        "claude-sonnet-4-6-long-context",
        "gemini-3-pro",
        "gemini-3-pro-long-context",
        "gemini-3.1-pro-long-context",
        "llama2-70b-chat",
        "llama3-70b",
        "llama3-70b fine-tuned",
        "llama3-8b",
        "llama3-8b fine-tuned",
        "llama3.1-70b fine-tuned",
        "llama3.1-8b fine-tuned",
        "mistral-7b fine-tuned",
        "mixtral-8x7b fine-tuned",
        "openai-gpt-5.4-long-context",
        "snowflake-arctic",
        "snowflake-llama-3.1-405b",
        "snowflake-llama-3.3-70b",
    }
)


def _build_fetch_sql() -> str:
    """Build the model-prices query, using BLACKLISTED_MODELS for the NOT IN filter."""
    not_in = ", ".join(f"'{m}'" for m in sorted(BLACKLISTED_MODELS))
    return f"""\
WITH latest AS (
    SELECT product_name, subtype_name, credit_conversion_rate
    FROM snowtower.external_data.product_feature_ai_price_card_v
    WHERE true
      AND approval_status = 'Approved'
      AND product_name ILIKE '%ai_complete%'
      AND publish_status = 'Published'
      AND start_date <= CURRENT_DATE()
      AND subtype_name ILIKE '%ai_service_cortex_function%'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY product_name, subtype_name ORDER BY version DESC) = 1
),
pivoted AS (
    SELECT REPLACE(product_name, 'AI_COMPLETE - ', '') AS product_name,
           price_input_tokens,
           price_output_tokens,
    FROM latest
        PIVOT(MAX(credit_conversion_rate) FOR subtype_name IN (
            'AI_SERVICE_CORTEX_FUNCTION_INPUT_TOKENS',
            'AI_SERVICE_CORTEX_FUNCTION_OUTPUT_TOKENS'
        )) AS p (product_name, price_input_tokens, price_output_tokens)
)
SELECT OBJECT_AGG(
    product_name,
    OBJECT_CONSTRUCT('input_cost', price_input_tokens, 'output_cost', price_output_tokens)
) AS result
FROM pivoted
WHERE product_name NOT IN ({not_in})
"""


def fetch_models(connection: str) -> dict:
    """Fetch latest model prices from Snowhouse and return the parsed model dict."""
    sql = _build_fetch_sql()
    result = subprocess.run(
        ["snow", "sql", "-q", sql, "--connection", connection, "--format", "JSON"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: snow sql fetch failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    rows = json.loads(result.stdout)
    raw = json.loads(rows[0]["RESULT"])
    return raw


def validate_model(
    model_name: str, connection: str, retries: int = 2, timeout: int = 90
) -> tuple[bool, str]:
    """Test a single model with AI_COMPLETE. Returns (success, detail).

    Retries up to `retries` times on timeout or transient errors.
    """
    sql = f"SELECT AI_COMPLETE('{model_name}', 'Say hello') AS response"
    last_err = "unknown error"
    for attempt in range(1 + retries):
        try:
            result = subprocess.run(
                [
                    "snow",
                    "sql",
                    "-q",
                    sql,
                    "--connection",
                    connection,
                    "--format",
                    "JSON",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return True, "ok"
            last_err = (
                result.stderr.strip().split("\n")[-1]
                if result.stderr.strip()
                else "unknown error"
            )
        except subprocess.TimeoutExpired:
            last_err = f"timed out after {timeout}s"
        except Exception as exc:
            last_err = str(exc)

        if attempt < retries:
            wait = 5 * (attempt + 1)
            print(
                f"         retry {attempt + 1}/{retries} for {model_name} in {wait}s..."
            )
            time.sleep(wait)

    return False, last_err


def main():
    parser = argparse.ArgumentParser(description="Fetch and validate Cortex AI models.")
    parser.add_argument(
        "--fetch-connection",
        default="SNOWHOUSE",
        help="Connection name for fetching prices (default: SNOWHOUSE)",
    )
    parser.add_argument(
        "--validate-connection",
        default="snowhouse",
        help="Connection name for AI_COMPLETE validation (default: snowhouse)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip fetching; validate models already in src/models.json",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Print results but do not remove failing models from the output file",
    )
    args = parser.parse_args()

    # --- Fetch or load models ---
    if args.validate_only:
        if not MODELS_JSON.exists():
            print(
                f"ERROR: {MODELS_JSON} not found. Run without --validate-only first.",
                file=sys.stderr,
            )
            sys.exit(1)
        models = json.loads(MODELS_JSON.read_text())
        print(f"Loaded {len(models)} models from {MODELS_JSON}")
    else:
        print(f"Fetching model prices via {args.fetch_connection}...")
        models = fetch_models(args.fetch_connection)
        print(f"Fetched {len(models)} models from Snowhouse")

    # --- Validate each model ---
    passed = {}
    failed = {}

    blacklisted_count = 0
    for model_name, pricing in sorted(models.items()):
        if model_name in BLACKLISTED_MODELS:
            blacklisted_count += 1
            continue

        ok, detail = validate_model(model_name, args.validate_connection)
        if ok:
            passed[model_name] = pricing
            print(f"  PASS  {model_name}")
        else:
            failed[model_name] = detail
            print(f"  FAIL  {model_name}: {detail}")

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(
        f"Results: {len(passed)} passed, {len(failed)} failed, {blacklisted_count} blacklisted"
    )
    if failed:
        print("\nFailed models:")
        for name, err in sorted(failed.items()):
            print(f"  - {name}: {err}")

    # --- Write output ---
    if args.no_prune:
        output = models
        print(f"\n--no-prune: writing all {len(output)} models (including failures)")
    else:
        output = passed
        if failed:
            print(f"\nPruned {len(failed)} failing model(s) from output")

    # Sort and write with consistent formatting
    sorted_output = dict(sorted(output.items()))
    formatted = json.dumps(sorted_output, indent=2, ensure_ascii=False)
    MODELS_JSON.write_text(formatted + "\n")
    print(f"Wrote {len(sorted_output)} models to {MODELS_JSON}")


if __name__ == "__main__":
    main()
