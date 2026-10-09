"""Tests for check_tags.py. Run from this folder:

    uv run --no-project python -B -m unittest discover -p 'test_*.py'
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_tags import validate

SCRIPT = Path(__file__).with_name("check_tags.py")
GOOD = {
    "team": "platform",
    "name": "user-service",
    "env": "dev",
    "version": "1.0.0",
    "service": "api",
    "cost_center": "apm-1234567",
    "contact": "platform-team@sanofi.com",
    "CE_Application_ID": "APM1234567",
    "CE_Application_Name": "Order Portal",
    "CE_Environment": "DEV",
}


def resource(address: str, after: dict, actions=("create",), after_unknown: dict | None = None) -> dict:
    return {
        "address": address,
        "mode": "managed",
        "change": {"actions": list(actions), "after": after, "after_unknown": after_unknown or {}},
    }


def run(plan: object, *args: str, raw: bytes | None = None) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "plan.json")
        path.write_bytes(raw if raw is not None else json.dumps(plan).encode())
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(path), *args], capture_output=True, text=True, check=False
        )


class ValidateTests(unittest.TestCase):
    def test_compliant_tags_pass(self):
        self.assertEqual(validate(GOOD), [])

    def test_missing_and_empty_tags_fail(self):
        tags = {**GOOD, "service": ""}
        del tags["contact"]
        problems = validate(tags)
        self.assertIn("missing or empty tag `service`", problems)
        self.assertIn("missing or empty tag `contact`", problems)

    def test_format_rules(self):
        cases = {
            "env": ("development", "`env` must be dev|test|prod"),
            "CE_Environment": ("Dev", "`CE_Environment` must be `DEV`"),
            "cost_center": ("12345", "`cost_center` must start with"),
            "CE_Application_ID": ("APM12", "must be APM + 7 digits"),
            "contact": ("someone@example.com", "@sanofi.com"),
            "team": ("platform team", "single word"),
        }
        for key, (value, expected) in cases.items():
            with self.subTest(key=key):
                problems = validate({**GOOD, key: value})
                self.assertTrue(any(expected in problem for problem in problems), problems)

    def test_apm_cost_center_must_match_application_id(self):
        problems = validate({**GOOD, "CE_Application_ID": "APM7654321"})
        self.assertTrue(any("does not match" in problem for problem in problems), problems)

    def test_cc_cost_center_skips_application_id_match(self):
        self.assertEqual(validate({**GOOD, "cost_center": "cc-1234", "CE_Application_ID": "APM7654321"}), [])


class CliTests(unittest.TestCase):
    def test_compliant_plan_exits_zero(self):
        result = run({"resource_changes": [resource("aws_s3_bucket.ok", {"tags_all": GOOD})]})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("checked 1 taggable resources: 0 failing, 0 unknown", result.stdout)

    def test_tags_all_wins_over_tags(self):
        after = {"tags": {"Name": "x"}, "tags_all": GOOD}
        self.assertEqual(run({"resource_changes": [resource("aws_s3_bucket.ok", after)]}).returncode, 0)

    def test_violation_exits_one(self):
        result = run({"resource_changes": [resource("aws_s3_bucket.bad", {"tags": {"team": "platform"}})]})
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL aws_s3_bucket.bad", result.stdout)

    def test_skips_untaggable_deleted_and_data(self):
        plan = {
            "resource_changes": [
                resource("aws_iam_role_policy.p", {"policy": "{}"}),
                resource("aws_s3_bucket.gone", {"tags": {}}, actions=("delete",)),
                {**resource("data.aws_region.r", {"tags": {}}), "mode": "data"},
            ]
        }
        result = run(plan)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("checked 0 taggable resources", result.stdout)

    def test_unknown_tags_warn_unless_strict(self):
        plan = {"resource_changes": [resource("aws_s3_bucket.later", {}, after_unknown={"tags_all": True})]}
        plan["resource_changes"][0]["change"]["after"] = {"tags_all": None}
        lenient = run(plan)
        self.assertEqual(lenient.returncode, 0)
        self.assertIn("WARN aws_s3_bucket.later", lenient.stdout)
        self.assertEqual(run(plan, "--strict").returncode, 1)

    def test_utf16_bom_input_accepted(self):
        raw = json.dumps({"resource_changes": [resource("aws_s3_bucket.ok", {"tags_all": GOOD})]}).encode("utf-16")
        self.assertEqual(run(None, raw=raw).returncode, 0)

    def test_unreadable_input_exits_two(self):
        self.assertEqual(run(None, raw=b"not json").returncode, 2)
        self.assertEqual(run({"format_version": "1.2"}).returncode, 2)


if __name__ == "__main__":
    unittest.main()
