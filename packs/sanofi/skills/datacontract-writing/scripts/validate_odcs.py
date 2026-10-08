#!/usr/bin/env python3
"""Validate ODCS YAML contracts against the official versioned JSON schema.

Usage: python3 validate_odcs.py CONTRACT.odcs.yaml [...] [--schema PATH_OR_URL]

Default schema: picked per contract from its `apiVersion` (v3.1.0 or v3.2.0);
anything else falls back to v3.1.0. Both files come from the immutable v3.2.0
release tag of bitol-io/open-data-contract-standard, whose v3.1.0 file carries
the silent v3.1.0 fixes (wider `id` pattern) the v3.1.0 tag lacks.
`--schema` forces one schema for every contract.
Requires jsonschema and pyyaml, e.g. `uv run --no-project --with jsonschema --with pyyaml python3 validate_odcs.py FILE`.
Exit codes: 0 valid, 1 invalid, 2 validator unavailable or unreadable input.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

SCHEMA_URL = (
    "https://raw.githubusercontent.com/bitol-io/open-data-contract-standard/"
    "v3.2.0/schema/odcs-json-schema-{v}.json"
)
SUPPORTED = ("v3.1.0", "v3.2.0")
DEFAULT_VERSION = "v3.1.0"


def load_schema(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as resp:
            return json.load(resp)
    with open(source, encoding="utf-8") as fh:
        return json.load(fh)


def schema_for(doc: object) -> str:
    version = doc.get("apiVersion") if isinstance(doc, dict) else None
    return SCHEMA_URL.format(v=version if version in SUPPORTED else DEFAULT_VERSION)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("contracts", nargs="+")
    parser.add_argument("--schema", help="schema path or URL; overrides apiVersion selection")
    args = parser.parse_args()

    try:
        import jsonschema
        import yaml
    except ImportError as exc:
        print(f"VALIDATION UNAVAILABLE: {exc}. Run via: uv run --no-project --with jsonschema --with pyyaml python3 {sys.argv[0]} ...")
        return 2

    validators: dict[str, object] = {}
    status = 0
    for path in args.contracts:
        try:
            with open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except Exception as exc:
            print(f"{path}: UNREADABLE: {exc}")
            status = max(status, 2)
            continue
        source = args.schema or schema_for(doc)
        if source not in validators:
            try:
                schema = load_schema(source)
            except Exception as exc:  # network or file errors
                print(f"VALIDATION UNAVAILABLE: cannot load schema {source}: {exc}")
                return 2
            validators[source] = jsonschema.validators.validator_for(schema)(schema)
        validator = validators[source]
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
        if not errors:
            print(f"{path}: VALID ({source.rsplit('/', 1)[-1]})")
            continue
        status = max(status, 1)
        print(f"{path}: INVALID ({len(errors)} errors)")
        for err in errors:
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            print(f"  {loc}: {err.message}")
    return status


if __name__ == "__main__":
    sys.exit(main())
