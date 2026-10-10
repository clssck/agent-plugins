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
1 = violations, 2 = unreadable input. Tags (or individual tag values) unknown
until apply are listed as warnings; add --strict to treat them as violations.
`aws_autoscaling_group` is checked through its `tag` blocks (default_tags
does not reach it); each mandatory tag needs propagate_at_launch = true.
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


def validate(tags: dict, unknown: frozenset[str] = frozenset()) -> list[str]:
    """Return problems with known values; keys in `unknown` are unresolved until apply, not missing."""
    problems = [f"missing or empty tag `{key}`" for key in REQUIRED if not tags.get(key) and key not in unknown]
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


def unknown_keys(marker: object) -> frozenset[str] | None:
    """Keys of a tag map marked unknown in `after_unknown`; None when the whole map is unknown."""
    if marker is True:
        return None
    if isinstance(marker, dict):
        return frozenset(key for key, value in marker.items() if value)
    return frozenset()


def asg_tags(after: dict, marker: object) -> tuple[dict | None, frozenset[str] | None, list[str]]:
    """Normalize `aws_autoscaling_group` `tag` blocks into a map, unknown keys, and block problems."""
    blocks = after.get("tag") or []
    if marker is True or not isinstance(blocks, list):
        return None, None, []
    marks = marker if isinstance(marker, list) else []
    tags: dict = {}
    unknown: set[str] = set()
    problems: list[str] = []
    for index, block in enumerate(blocks):
        raw = marks[index] if index < len(marks) else {}
        if raw is True:
            return None, None, []  # whole block unknown
        mark = raw if isinstance(raw, dict) else {}
        key = (block or {}).get("key")
        if mark.get("key"):
            return None, None, []  # a key unknown until apply could be any required tag
        if not key:
            continue
        if mark.get("value"):
            unknown.add(key)
        else:
            tags[key] = block.get("value")
        if key in REQUIRED and block.get("propagate_at_launch") is not True and not mark.get("propagate_at_launch"):
            problems.append(f"tag `{key}` must set propagate_at_launch = true")
    return tags, frozenset(unknown), problems


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
    unknown: list[tuple[str, str]] = []
    for rc in plan["resource_changes"]:
        change = rc.get("change", {})
        if rc.get("mode") != "managed" or change.get("actions") == ["delete"]:
            continue
        after = change.get("after") or {}
        unknown_after = change.get("after_unknown") or {}
        if rc.get("type") == "aws_autoscaling_group":
            # default_tags does not reach ASGs; their tags are `tag` blocks.
            tags, pending, block_problems = asg_tags(after, unknown_after.get("tag"))
        elif {"tags_all", "tags"} & (after.keys() | unknown_after.keys()):
            source = "tags_all" if isinstance(after.get("tags_all"), dict) or unknown_after.get("tags_all") else "tags"
            tags = after.get(source)
            pending, block_problems = unknown_keys(unknown_after.get(source)), []
        else:
            continue  # not taggable
        checked += 1
        if pending is None or not isinstance(tags, dict):
            unknown.append((rc["address"], "tags unknown until apply"))
            continue
        problems = block_problems + validate(tags, pending)
        if problems:
            violations.append((rc["address"], problems))
        unresolved = [key for key in REQUIRED if key in pending and not tags.get(key)]
        if unresolved:
            unknown.append((rc["address"], "values unknown until apply: " + ", ".join(f"`{key}`" for key in unresolved)))

    for address, problems in violations:
        print(f"FAIL {address}")
        for problem in problems:
            print(f"  - {problem}")
    for address, reason in unknown:
        print(f"WARN {address}: {reason}")
    print(f"checked {checked} taggable resources: {len(violations)} failing, {len(unknown)} unknown")
    return 1 if violations or (args.strict and unknown) else 0


if __name__ == "__main__":
    sys.exit(main())
