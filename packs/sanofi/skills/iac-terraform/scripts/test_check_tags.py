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
            "name": ("two words", "`name` must be alphanumeric"),
            "version": ("latest", "`version` must be SemVer"),
        }
        for key, (value, expected) in cases.items():
            with self.subTest(key=key):
                problems = validate({**GOOD, key: value})
                self.assertTrue(any(expected in problem for problem in problems), problems)

    def test_name_accepts_alphanumeric_hyphen_underscore(self):
        for value in ("user-service", "user_service", "UserService2", "a", "-", "_"):
            with self.subTest(name=value):
                self.assertEqual(validate({**GOOD, "name": value}), [])

    def test_name_rejects_other_characters(self):
        for value in ("user.service", "user service", "user/service", "service!", "café", "user-service\n"):
            with self.subTest(name=value):
                problems = validate({**GOOD, "name": value})
                self.assertTrue(any("`name` must be alphanumeric" in problem for problem in problems), problems)

    def test_version_accepts_semver(self):
        for value in ("0.0.0", "1.0.0", "10.20.30", "1.0.0-rc.1", "1.0.0-alpha-1", "1.0.0+build.5", "1.0.0-beta+exp.sha.5114f85"):
            with self.subTest(version=value):
                self.assertEqual(validate({**GOOD, "version": value}), [])

    def test_version_rejects_non_semver(self):
        for value in ("latest", "v1.0.0", "1.0", "1", "1.0.0.0", "01.0.0", "1.0.0-", "1.0.0-01", "1.0.0 ", "1.0.0\n", "１.０.０"):
            with self.subTest(version=value):
                problems = validate({**GOOD, "version": value})
                self.assertTrue(any("`version` must be SemVer" in problem for problem in problems), problems)

    def test_unknown_name_and_version_are_not_format_errors(self):
        tags = {key: value for key, value in GOOD.items() if key not in ("name", "version")}
        self.assertEqual(validate(tags, frozenset({"name", "version"})), [])

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

    def test_partially_unknown_tags_warn_not_missing(self):
        known = {k: v for k, v in GOOD.items() if k != "service"}
        res = resource("aws_s3_bucket.part", {"tags_all": known}, after_unknown={"tags_all": {"service": True}})
        plan = {"resource_changes": [res]}
        lenient = run(plan)
        self.assertEqual(lenient.returncode, 0, lenient.stdout)
        self.assertIn("WARN aws_s3_bucket.part: values unknown until apply: `service`", lenient.stdout)
        self.assertNotIn("FAIL", lenient.stdout)
        self.assertEqual(run(plan, "--strict").returncode, 1)

    def test_partially_unknown_still_fails_invalid_known_values(self):
        known = {k: v for k, v in GOOD.items() if k != "service"} | {"env": "staging"}
        res = resource("aws_s3_bucket.part", {"tags_all": known}, after_unknown={"tags_all": {"service": True}})
        result = run({"resource_changes": [res]})
        self.assertEqual(result.returncode, 1)
        self.assertIn("`env` must be dev|test|prod", result.stdout)
        self.assertNotIn("missing or empty tag `service`", result.stdout)

    def test_unknown_tags_omitted_from_after(self):
        res = resource("aws_s3_bucket.later", {}, after_unknown={"tags": True, "tags_all": True})
        result = run({"resource_changes": [res]})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN aws_s3_bucket.later", result.stdout)

    def test_known_null_tags_fail_without_strict(self):
        result = run({"resource_changes": [resource("aws_s3_bucket.null", {"tags": None})]})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FAIL aws_s3_bucket.null", result.stdout)
        self.assertIn("missing or empty tag `team`", result.stdout)
        self.assertNotIn("WARN", result.stdout)

    def test_known_null_tags_all_fail_without_strict(self):
        result = run({"resource_changes": [resource("aws_s3_bucket.null", {"tags_all": None})]})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FAIL aws_s3_bucket.null", result.stdout)
        self.assertNotIn("WARN", result.stdout)

    def test_null_map_marked_unknown_warns_not_fails(self):
        for field in ("tags", "tags_all"):
            res = resource("aws_s3_bucket.later", {field: None}, after_unknown={field: True})
            lenient = run({"resource_changes": [res]})
            self.assertEqual(lenient.returncode, 0, lenient.stdout)
            self.assertIn("WARN aws_s3_bucket.later", lenient.stdout)
            self.assertNotIn("FAIL", lenient.stdout)
            self.assertEqual(run({"resource_changes": [res]}, "--strict").returncode, 1)

    def test_asg_without_tags_fails_even_strict(self):
        res = {**resource("aws_autoscaling_group.a", {"tag": []}), "type": "aws_autoscaling_group"}
        result = run({"resource_changes": [res]}, "--strict")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL aws_autoscaling_group.a", result.stdout)
        self.assertIn("missing or empty tag `team`", result.stdout)

    def test_asg_noncompliant_and_compliant_blocks(self):
        def blocks(propagate: bool, **override: str) -> list[dict]:
            tags = {**GOOD, **override}
            return [{"key": k, "value": v, "propagate_at_launch": propagate} for k, v in tags.items()]

        def asg(name: str, tag: list[dict]) -> dict:
            return {**resource(f"aws_autoscaling_group.{name}", {"tag": tag}), "type": "aws_autoscaling_group"}

        bad = run({"resource_changes": [asg("bad", blocks(True, env="staging"))]})
        self.assertEqual(bad.returncode, 1)
        self.assertIn("`env` must be dev|test|prod", bad.stdout)
        no_propagate = run({"resource_changes": [asg("np", blocks(False))]})
        self.assertEqual(no_propagate.returncode, 1)
        self.assertIn("propagate_at_launch", no_propagate.stdout)
        ok = run({"resource_changes": [asg("ok", blocks(True))]}, "--strict")
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.assertIn("checked 1 taggable resources: 0 failing, 0 unknown", ok.stdout)

    def test_asg_unknown_propagate_at_launch_warns_and_fails_strict(self):
        blocks = [{"key": k, "value": v, "propagate_at_launch": True} for k, v in GOOD.items()]
        blocks[0] = {"key": "team", "value": GOOD["team"], "propagate_at_launch": None}
        marks = [{} for _ in blocks]
        marks[0] = {"propagate_at_launch": True}
        res = {
            **resource("aws_autoscaling_group.later", {"tag": blocks}, after_unknown={"tag": marks}),
            "type": "aws_autoscaling_group",
        }
        plan = {"resource_changes": [res]}
        lenient = run(plan)
        self.assertEqual(lenient.returncode, 0, lenient.stdout)
        self.assertIn("WARN aws_autoscaling_group.later: propagate_at_launch unknown until apply: `team`", lenient.stdout)
        self.assertNotIn("FAIL", lenient.stdout)
        self.assertIn("0 failing, 1 unknown", lenient.stdout)
        self.assertEqual(run(plan, "--strict").returncode, 1)

    def test_utf16_bom_input_accepted(self):
        raw = json.dumps({"resource_changes": [resource("aws_s3_bucket.ok", {"tags_all": GOOD})]}).encode("utf-16")
        self.assertEqual(run(None, raw=raw).returncode, 0)

    def test_unreadable_input_exits_two(self):
        self.assertEqual(run(None, raw=b"not json").returncode, 2)
        self.assertEqual(run({"format_version": "1.2"}).returncode, 2)

    def test_wrong_shape_plan_exits_two_without_traceback(self):
        for plan in (
            None,
            [],
            "plan",
            {"resource_changes": None},
            {"resource_changes": "aws_s3_bucket.x"},
            {"resource_changes": {"address": "aws_s3_bucket.x"}},
            {"resource_changes": [None]},
            {"resource_changes": [resource("aws_s3_bucket.ok", {"tags_all": GOOD}), "junk"]},
        ):
            with self.subTest(plan=plan):
                result = run(plan)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_empty_resource_changes_exits_zero(self):
        self.assertEqual(run({"resource_changes": []}).returncode, 0)


if __name__ == "__main__":
    unittest.main()
