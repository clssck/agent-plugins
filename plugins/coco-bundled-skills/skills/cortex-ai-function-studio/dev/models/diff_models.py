#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.
"""Compare two models.json files and produce a human-readable diff summary.

Usage:
    python dev/models/diff_models.py old_models.json new_models.json
    python dev/models/diff_models.py old_models.json new_models.json --format slack
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def diff_models(old: dict, new: dict) -> dict:
    """Compare two model dicts and return structured diff.

    Returns:
        {
            "added": {model: {input_cost, output_cost}},
            "removed": {model: {input_cost, output_cost}},
            "changed": {model: {field: {old, new}, ...}},
            "unchanged": int,
        }
    """
    old_names = set(old.keys())
    new_names = set(new.keys())

    added = {m: new[m] for m in sorted(new_names - old_names)}
    removed = {m: old[m] for m in sorted(old_names - new_names)}

    changed = {}
    unchanged = 0
    for model in sorted(old_names & new_names):
        diffs = {}
        for field in ("input_cost", "output_cost"):
            old_val = old[model].get(field)
            new_val = new[model].get(field)
            if old_val != new_val:
                diffs[field] = {"old": old_val, "new": new_val}
        if diffs:
            changed[model] = diffs
        else:
            unchanged += 1

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
    }


def format_text(diff: dict) -> str:
    """Format diff as plain text."""
    lines = []

    if diff["added"]:
        lines.append(f"Models added ({len(diff['added'])}):")
        for model, pricing in diff["added"].items():
            lines.append(
                f"  + {model}: input={pricing['input_cost']}, output={pricing['output_cost']}"
            )

    if diff["removed"]:
        if lines:
            lines.append("")
        lines.append(f"Models removed ({len(diff['removed'])}):")
        for model, pricing in diff["removed"].items():
            lines.append(
                f"  - {model}: input={pricing['input_cost']}, output={pricing['output_cost']}"
            )

    if diff["changed"]:
        if lines:
            lines.append("")
        lines.append(f"Price changes ({len(diff['changed'])}):")
        for model, fields in diff["changed"].items():
            parts = []
            for field, vals in fields.items():
                parts.append(f"{field}: {vals['old']} -> {vals['new']}")
            lines.append(f"  ~ {model}: {', '.join(parts)}")

    if not lines:
        lines.append("No changes detected.")

    lines.append("")
    lines.append(f"Unchanged: {diff['unchanged']} model(s)")
    return "\n".join(lines)


def format_slack(diff: dict) -> str:
    """Format diff as Slack mrkdwn."""
    lines = []

    if diff["added"]:
        lines.append(f"*Models added ({len(diff['added'])})* :new:")
        for model, pricing in diff["added"].items():
            lines.append(
                f"\u2022 `{model}` \u2014 input: {pricing['input_cost']}, output: {pricing['output_cost']}"
            )

    if diff["removed"]:
        if lines:
            lines.append("")
        lines.append(f"*Models removed ({len(diff['removed'])})* :x:")
        for model, pricing in diff["removed"].items():
            lines.append(
                f"\u2022 `{model}` \u2014 input: {pricing['input_cost']}, output: {pricing['output_cost']}"
            )

    if diff["changed"]:
        if lines:
            lines.append("")
        lines.append(
            f"*Price changes ({len(diff['changed'])})* :chart_with_upwards_trend:"
        )
        for model, fields in diff["changed"].items():
            parts = []
            for field, vals in fields.items():
                parts.append(f"{field}: {vals['old']} \u2192 {vals['new']}")
            lines.append(f"\u2022 `{model}` \u2014 {', '.join(parts)}")

    if not lines:
        return "No changes detected."

    lines.append(f"\n_{diff['unchanged']} model(s) unchanged_")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff two models.json files.")
    parser.add_argument("old", help="Path to old models.json")
    parser.add_argument("new", help="Path to new models.json")
    parser.add_argument(
        "--format",
        choices=["text", "slack"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    old = json.loads(Path(args.old).read_text())
    new = json.loads(Path(args.new).read_text())

    result = diff_models(old, new)

    if args.format == "slack":
        print(format_slack(result))
    else:
        print(format_text(result))


if __name__ == "__main__":
    main()
