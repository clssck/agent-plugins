"""Openflow CDC connector packing — minimal pure-compute helpers.

The skill itself is the markdown reference `cdc-connector-packing.md`; the agent
(CoCo) drives the workflow directly via `nipyapi`, `sql_execute`, `runSubagent`,
and `ask_user_question`. Only the deterministic, agent-shouldn't-re-derive bits
ship as Python:

  - `config_loader`: YAML/JSON load, secret-ref detection, `${...}` token
    expansion, sha256 fingerprint of resolved values.
  - `aliases`: legacy YAML key -> NiFi parameter-name canonicalization.
  - `sizing`: active-table / EPS math against the runtime sizing ceilings.
  - `schema.json`: JSON Schema for config validation (load with stdlib json).

Everything else lives in `cdc-connector-packing.md` as prose + inline nipyapi
snippets, the way `ops-flow-deploy.md` works for the bundled openflow skill.
"""
from . import config_loader, aliases, sizing  # noqa: F401

__version__ = "2.0.0"
