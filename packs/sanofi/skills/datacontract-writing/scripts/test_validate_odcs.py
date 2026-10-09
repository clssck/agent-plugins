import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from validate_odcs import SCHEMA_URL, schema_for

SCRIPT = Path(__file__).with_name("validate_odcs.py")
UV = shutil.which("uv")

# Offline stand-in for the ODCS schema: closed root, a few required keys.
SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind", "id", "version", "status"],
    "properties": {k: {"type": "string"} for k in ("apiVersion", "kind", "id", "version", "status")},
    "additionalProperties": False,
}
VALID = "apiVersion: v3.1.0\nkind: DataContract\nid: abc\nversion: 1.0.0\nstatus: draft\n"


class SchemaSelection(unittest.TestCase):
    def test_picks_schema_from_api_version(self):
        for version in ("v3.1.0", "v3.2.0"):
            with self.subTest(version=version):
                self.assertEqual(schema_for({"apiVersion": version}), SCHEMA_URL.format(v=version))

    def test_unknown_or_missing_version_falls_back_to_v310(self):
        for doc in ({"apiVersion": "v3.0.2"}, {}, None, []):
            with self.subTest(doc=doc):
                self.assertEqual(schema_for(doc), SCHEMA_URL.format(v="v3.1.0"))


@unittest.skipUnless(UV, "uv not on PATH")
class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.schema = self.tmp / "schema.json"
        self.schema.write_text(json.dumps(SCHEMA), encoding="utf-8")

    def run_script(self, *args):
        return subprocess.run([UV, "run", "--quiet", str(SCRIPT), *args], capture_output=True, text=True)

    def contract(self, text):
        path = self.tmp / "c.odcs.yaml"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_help_exits_zero(self):
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage", result.stdout)

    def test_valid_contract_exits_zero(self):
        result = self.run_script(self.contract(VALID), "--schema", str(self.schema))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VALID (schema.json)", result.stdout)

    def test_extra_field_exits_one(self):
        result = self.run_script(self.contract(VALID + "enum: [a]\n"), "--schema", str(self.schema))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("INVALID", result.stdout)

    def test_unreadable_contract_exits_two(self):
        result = self.run_script(str(self.tmp / "missing.yaml"), "--schema", str(self.schema))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("UNREADABLE", result.stdout)

    def test_missing_schema_exits_two(self):
        result = self.run_script(self.contract(VALID), "--schema", str(self.tmp / "nope.json"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("VALIDATION UNAVAILABLE", result.stdout)


if __name__ == "__main__":
    unittest.main()
