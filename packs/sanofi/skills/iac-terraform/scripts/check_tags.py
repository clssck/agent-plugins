#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check Sanofi mandatory tags on every taggable resource in a Terraform plan.

Usage:
    terraform show -json tfplan > plan.json
    uv run check_tags.py plan.json          # or: ... | uv run check_tags.py -

Evaluates effective tags (`tags_all`, falling back to `tags`), so module and
provider `default_tags` propagation is honoured. Exit codes: 0 = compliant,
1 = violations, 2 = unreadable input. Resources whose tags are unknown until
apply are listed as warnings; add --strict to treat them as violations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

REQUIRED = (
    "team",
    "name",
    "env",
    "version",
    "service",
    "cost_center",
    "contact",
    "CE_Application_ID",
    "CE_Application_Name",
    "CE_Environment",
)
ENV_TO_CE = {"dev": "DEV", "test": "TEST", "prod": "PROD"}
COST_CENTER = re.compile(r"^(cc|dp|apm)-\S+$")
APPLICATION_ID = re.compile(r"^APM[0-9]{7}$")
CONTACT = re.compile(r"@sanofi\.com$")


def validate(tags: dict) -> list[str]:
    problems = [f"missing or empty tag `{key}`" for key in REQUIRED if not tags.get(key)]
    env = tags.get("env")
    if env and env not in ENV_TO_CE:
        problems.append(f"`env` must be dev|test|prod, got `{env}`")
    elif env and tags.get("CE_Environment") and tags["CE_Environment"] != ENV_TO_CE[env]:
        problems.append(f"`CE_Environment` must be `{ENV_TO_CE[env]}` for env `{env}`, got `{tags['CE_Environment']}`")
    cost_center = tags.get("cost_center")
    if cost_center and not COST_CENTER.match(cost_center):
        problems.append(f"`cost_center` must start with cc-, dp-, or apm-, got `{cost_center}`")
    app_id = tags.get("CE_Application_ID")
    if app_id and not APPLICATION_ID.match(app_id):
        problems.append(f"`CE_Application_ID` must be APM + 7 digits, got `{app_id}`")
    if cost_center and cost_center.startswith("apm-") and app_id and app_id != "APM" + cost_center[4:]:
        problems.append(f"`CE_Application_ID` `{app_id}` does not match apm- cost_center `{cost_center}`")
    contact = tags.get("contact")
    if contact and not CONTACT.search(contact):
        problems.append(f"`contact` must be an @sanofi.com email, got `{contact}`")
    if tags.get("team") and re.search(r"\s", tags["team"]):
        problems.append("`team` must be a single word")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", help="plan JSON file, or - for stdin")
    parser.add_argument("--strict", action="store_true", help="treat unknown tags as violations")
    args = parser.parse_args()

    try:
        data = sys.stdin.buffer.read() if args.plan == "-" else open(args.plan, "rb").read()
        # Windows PowerShell 5.1 `>` writes UTF-16 with a BOM; accept it alongside UTF-8.
        plan = json.loads(data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        print(f"error: cannot read plan JSON: {err}", file=sys.stderr)
        return 2
    if "resource_changes" not in plan:
        print("error: input has no resource_changes; use `terraform show -json <planfile>`", file=sys.stderr)
        return 2

    checked = 0
    violations: list[tuple[str, list[str]]] = []
    unknown: list[str] = []
    for rc in plan["resource_changes"]:
        change = rc.get("change", {})
        if rc.get("mode") != "managed" or change.get("actions") == ["delete"]:
            continue
        after = change.get("after") or {}
        if "tags_all" not in after and "tags" not in after:
            continue  # not taggable
        checked += 1
        tags = after.get("tags_all")
        if not isinstance(tags, dict):
            tags = after.get("tags")
        unknown_after = change.get("after_unknown") or {}
        if unknown_after.get("tags_all") is True or unknown_after.get("tags") is True or not isinstance(tags, dict):
            unknown.append(rc["address"])
            continue
        problems = validate(tags)
        if problems:
            violations.append((rc["address"], problems))

    for address, problems in violations:
        print(f"FAIL {address}")
        for problem in problems:
            print(f"  - {problem}")
    for address in unknown:
        print(f"WARN {address}: tags unknown until apply")
    print(f"checked {checked} taggable resources: {len(violations)} failing, {len(unknown)} unknown")
    return 1 if violations or (args.strict and unknown) else 0


if __name__ == "__main__":
    sys.exit(main())
