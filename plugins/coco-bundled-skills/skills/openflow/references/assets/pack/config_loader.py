"""Step 0 helper — load YAML/JSON, expand templated tokens, return references.

The loader **never resolves secret values**. Every secret stays a reference until
apply time, when the worker resolves it in memory only. The journal records the
reference + length + sha256 of the resolved value, never the value itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


_TOKEN_RE = re.compile(r"\$\{([a-zA-Z][a-zA-Z0-9_.|]*)\}")
_SECRET_SCHEMES = ("snowflake:",)


@dataclass
class ConnectorEntry:
    name: str
    overrides: dict[str, Any] = field(default_factory=dict)
    tables: list[str] | None = None
    tables_regex: str | None = None
    sizing: dict[str, Any] = field(default_factory=dict)

    @property
    def destination_database(self) -> str | None:
        """The Snowflake destination DB for this connector.

        Reads `overrides["Destination Database"]` (NiFi name) or its legacy
        alias `overrides["destination_database"]`. Returns None if neither
        is set. plan_md / result_md / reviewer all consume this property
        so they cannot drift on the lookup convention.
        """
        return (
            self.overrides.get("Destination Database")
            or self.overrides.get("destination_database")
        )


@dataclass
class Config:
    runtime: str
    connector_type: str
    shared: dict[str, Any]
    connectors: list[ConnectorEntry]
    raw: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None

    def connector_names(self) -> list[str]:
        return [c.name for c in self.connectors]


def load(path: str | Path) -> Config:
    """Load a YAML or JSON config file into a `Config`. Token expansion is deferred
    to `expand_tokens` (called per-connector inside the worker)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        if yaml is None:
            raise RuntimeError("PyYAML is required to load YAML configs")
        try:
            raw = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(f"Invalid YAML config {p}: {exc}") from exc
    elif p.suffix.lower() == ".json":
        try:
            raw = json.loads(text)
        except JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON config {p}: {exc}") from exc
    else:
        raise ValueError(f"Unsupported config extension: {p.suffix}")
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")
    connectors = [
        ConnectorEntry(
            name=c["name"],
            overrides=c.get("overrides", {}) or {},
            tables=c.get("tables"),
            tables_regex=c.get("tables_regex"),
            sizing=c.get("sizing", {}) or {},
        )
        for c in raw.get("connectors", [])
    ]
    return Config(
        runtime=raw.get("runtime", ""),
        connector_type=raw.get("connector_type", ""),
        shared=raw.get("shared", {}) or {},
        connectors=connectors,
        raw=raw,
        source_path=p,
    )


def is_secret_ref(value: Any) -> bool:
    """A value is a secret reference iff it is a string starting with `<` (cortex)
    or one of the known schemes."""
    if not isinstance(value, str):
        return False
    if value.startswith("<") and value.endswith(">"):
        return True
    return any(value.startswith(scheme) for scheme in _SECRET_SCHEMES)


def expand_tokens(value: str, *, connector_name: str, runtime: str) -> str:
    """Expand `${connector.name}`, `${connector.name|upper}`, `${connector.name|lower}`,
    `${runtime}`, `${env.VAR}` inside any string. Used both for secret references
    and for any other string value where templating helps fleet-scale configs."""
    if not isinstance(value, str):
        return value

    def repl(m: re.Match[str]) -> str:
        token = m.group(1)
        name, _, modifier = token.partition("|")
        if name == "connector.name":
            v = connector_name
        elif name == "runtime":
            v = runtime
        elif name.startswith("env."):
            v = os.environ.get(name[4:], "")
        else:
            return m.group(0)  # leave unknown tokens untouched
        if modifier == "upper":
            v = v.upper()
        elif modifier == "lower":
            v = v.lower()
        return v

    return _TOKEN_RE.sub(repl, value)


def fingerprint(value: str) -> dict[str, Any]:
    """Return a journal-safe fingerprint of a resolved secret value: length and
    sha256. Never includes the value itself."""
    encoded = value.encode("utf-8")
    return {
        "length": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }
