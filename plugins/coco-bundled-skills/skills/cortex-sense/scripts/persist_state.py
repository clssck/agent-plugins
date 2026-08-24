#!/usr/bin/env python3
"""persist_state.py — YAML validation, dedup, and doctor pre-flight for Cortex Sense.

Storage is handled by SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER — the skill
calls that SQL function directly. This module does NOT write to Snowflake.

Subcommands
-----------
merge       Read YAML/JSON from --from-file or stdin, run instruction dedup,
            validate, write merged YAML to stdout. Pipe through this before
            calling put-stage-file to deduplicate additional_instructions.
preview     Read a YAML state file and print a stripped preview (no ids,
            timestamps, or internal fields).
validate    Check a YAML state file against the builder state contract.
            Exit 0 if valid; prints all errors to stderr and exits 1 otherwise.
doctor      Pre-flight check: verify snow CLI, resolve DB/schema, report JSON.

Environment overrides (optional)
--------------------------------
CORTEX_SENSE_DB           Database hint for create-context. Default: TEMP.
CORTEX_SENSE_SCHEMA       Schema hint for create-context. Default: CORTEX_SENSE.
CORTEX_SENSE_CONNECTION   Snowflake CLI connection profile name.
CORTEX_SENSE_LOCAL_ROOT   (Testing only) Use a local directory instead of a
                          stage. Not surfaced to users.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ---- Instruction dedup (formerly merge_instructions.py) --------------------

_MERGE_BUCKETS = ("additional_instructions", "in_account_instructions")


def _merge_instructions(state: dict[str, Any]) -> dict[str, Any]:
    """Dedupe and supersede free-form instruction lists before saving.

    Deduplication is keyed on the normalised (lowercase, collapsed-whitespace)
    `user_prompt` text. When a later entry has the same key but different
    content or `suggested_by`, the earlier entry is marked `superseded_by`
    the new one (thin audit trail). Idempotent.
    """
    for bucket in _MERGE_BUCKETS:
        state.setdefault(bucket, [])
        state[bucket] = _dedupe_supersede_instructions(state[bucket])
    state.setdefault("status", "draft")
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state


def _dedupe_supersede_instructions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for r in entries:
        if not isinstance(r, dict):
            continue
        r.setdefault("id", str(uuid.uuid4()))
        key = _instruction_dedupe_key(r)
        if key in by_key:
            old = by_key[key]
            if old["id"] == r["id"]:
                continue
            if _instructions_equal(old, r):
                continue
            old["superseded_by"] = r["id"]
            out.append(r)
            by_key[key] = r
        else:
            out.append(r)
            by_key[key] = r
    return out


def _instruction_dedupe_key(r: dict[str, Any]) -> str:
    up = r.get("user_prompt")
    if not isinstance(up, str):
        return ""
    return " ".join(up.lower().split())


def _instructions_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("user_prompt") == b.get("user_prompt") and a.get("suggested_by") == b.get("suggested_by")


class PersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class VersionRef:
    domain: str
    version_id: str
    created_at: str
    note: str = ""
    # storage_location is the user-visible path where this version landed.
    # Set by save() so the skill can render the "Stored at @..." line without
    # needing to know about env vars or backend resolution. Empty for older
    # callers that don't populate it.
    storage_location: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "domain": self.domain,
            "version_id": self.version_id,
            "created_at": self.created_at,
            "note": self.note,
        }
        if self.storage_location:
            d["storage_location"] = self.storage_location
        return d


# Fields stripped from the state when rendering the user-facing review preview.
# `created_at` is version metadata and only meaningful at the top level; it is NOT
# in _STRIPPED_FIELD_NAMES so a nested `created_at` (e.g. inside an `extra` map)
# survives the recursive strip.
_STRIPPED_TOP_LEVEL = {"version_id", "created_at", "updated_at"}
_STRIPPED_FIELD_NAMES = {"id", "superseded_by"}

# Default DB/schema used in create-context when no env override is set.
# The stage name is always derived from the domain at call time.
_DEFAULT_DB = "TEMP"
_DEFAULT_SCHEMA = "CORTEX_SENSE"

# Keys written to the in-account file rather than the main manifest.
# These instructions are applied at inference time and never leave the account.
_ACCOUNT_KEYS = frozenset({"in_account_instructions"})

# In-account file format (YAML shape written to versions/in_account/):
#
#   business_domain: <domain>
#   version_id: <vid>           # same as main scope file
#   created_at: <ISO-8601>
#   updated_at: <ISO-8601>
#
#   in_account_instructions:    # applied at inference time; never leave the account
#     - user_prompt: "..."
#       suggested_by: <optional>  # name/email of person who added this


class PersistenceBackend(ABC):
    name: str = ""

    @abstractmethod
    def save_version(
        self, domain: str, payload: dict[str, Any], note: str = ""
    ) -> VersionRef: ...

    @abstractmethod
    def load_latest(
        self, domain: str
    ) -> tuple[VersionRef, dict[str, Any]] | None:
        """Return the most recently *saved* version (the LATEST pointer).

        This is the editing head used by the skills and may be a `draft`. It is
        distinct from the "live" version the scheduled builder consumes, which
        is the most recent version whose `status` is `active`. Each save writes
        a new immutable versioned file and advances the LATEST pointer, so a
        rollback (re-saving an older payload with `status: active`) becomes the
        new LATEST and therefore the new live version; older `active` files
        remain in the audit trail but are superseded by recency.
        """
        ...

    @abstractmethod
    def load_active(
        self, domain: str
    ) -> tuple[VersionRef, dict[str, Any]] | None:
        """Return the live version: the most recent version with status active.

        This enforces the "most recent active wins" invariant in code (the
        scheduled builder's selection), independent of the LATEST pointer. After
        a rollback (re-saving an older payload as a new active version via
        put-stage-file) this returns that newest active version. Returns None if
        no version is active. Scans newest-first and stops at the first active
        match.
        """
        ...

    @abstractmethod
    def load_version(
        self, domain: str, version_id: str
    ) -> tuple[VersionRef, dict[str, Any]] | None: ...

    @abstractmethod
    def list_versions(
        self, domain: str, limit: int | None = None
    ) -> list[VersionRef]:
        """Return version refs oldest→newest. If limit is set, only the newest
        `limit` versions are read (bounds stage downloads for long histories)."""
        ...


class LocalFileBackend(PersistenceBackend):
    """Local YAML files — offline / testing only (set CORTEX_SENSE_LOCAL_ROOT).

    Each domain gets its own subdirectory (mirroring the per-domain stage in
    production). Within that directory:
      - scope.yaml / in_account_scope.yaml  — fixed current files at domain root
      - versions/meta_<vid>.yaml            — shared VersionRef per version
      - versions/scope/                     — scope versioned payloads + LATEST
      - versions/in_account/               — in-account versioned payloads + LATEST
    """

    name = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _domain_dir(self, domain: str) -> Path:
        d = self.root / _safe(domain)
        (d / "versions" / "scope").mkdir(parents=True, exist_ok=True)
        (d / "versions" / "in_account").mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Split / merge helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (main_payload, account_payload)."""
        main = {k: v for k, v in payload.items() if k not in _ACCOUNT_KEYS}
        acct = {k: v for k, v in payload.items() if k in _ACCOUNT_KEYS}
        return main, acct

    @staticmethod
    def _merge(main: dict[str, Any], acct: dict[str, Any]) -> dict[str, Any]:
        """Re-combine main + in-account instructions into the full in-memory manifest."""
        merged = dict(main)
        for k in _ACCOUNT_KEYS:
            merged[k] = acct.get(k, [])
        return merged

    def save_version(
        self, domain: str, payload: dict[str, Any], note: str = ""
    ) -> VersionRef:
        if not domain:
            raise PersistenceError("domain is required")
        version_id = _new_version_id()
        created_at = datetime.now(timezone.utc).isoformat()
        payload = dict(payload)
        payload["version_id"] = version_id
        payload["updated_at"] = created_at
        if not payload.get("created_at"):
            payload["created_at"] = created_at

        main_payload, acct_payload = self._split(payload)
        # In-account envelope carries versioning metadata so it can be loaded
        # independently for audit purposes.
        acct_envelope = {
            "business_domain": domain,
            "version_id": version_id,
            "created_at": created_at,
            "updated_at": created_at,
            **acct_payload,
        }

        ref = VersionRef(
            domain=domain,
            version_id=version_id,
            created_at=created_at,
            note=note,
            storage_location=str(self._domain_dir(domain)),
        )
        ddir = self._domain_dir(domain)
        main_yaml = yaml.safe_dump(main_payload, sort_keys=False, default_flow_style=False)
        acct_yaml = yaml.safe_dump(acct_envelope, sort_keys=False, default_flow_style=False)
        # Fixed current files at domain root — overwritten on every save for quick access
        (ddir / "scope.yaml").write_text(main_yaml)
        (ddir / "in_account_scope.yaml").write_text(acct_yaml)
        # Shared VersionRef (postfix: meta_<vid>.yaml)
        (ddir / "versions" / f"meta_{version_id}.yaml").write_text(
            yaml.safe_dump(ref.to_dict(), sort_keys=False)
        )
        # Scope sub-folder: versioned payload + LATEST pointer
        (ddir / "versions" / "scope" / f"scope_{version_id}.yaml").write_text(main_yaml)
        (ddir / "versions" / "scope" / "LATEST").write_text(version_id)
        # In-account sub-folder: versioned payload + LATEST pointer
        (ddir / "versions" / "in_account" / f"in_account_scope_{version_id}.yaml").write_text(acct_yaml)
        (ddir / "versions" / "in_account" / "LATEST").write_text(version_id)
        return ref

    def load_latest(
        self, domain: str
    ) -> tuple[VersionRef, dict[str, Any]] | None:
        ddir = self._domain_dir(domain)
        latest = ddir / "versions" / "scope" / "LATEST"
        if not latest.exists():
            return None
        return self.load_version(domain, latest.read_text().strip())

    def load_active(
        self, domain: str
    ) -> tuple[VersionRef, dict[str, Any]] | None:
        ddir = self._domain_dir(domain)
        # meta_<vid>.yaml names sort lexically by vid, so reverse gives newest-first.
        ids = sorted(
            (p.name.removeprefix("meta_").removesuffix(".yaml")
             for p in (ddir / "versions").glob("meta_*.yaml")),
            reverse=True,
        )
        for vid in ids:
            result = self.load_version(domain, vid)
            if result is not None and result[1].get("status") == "active":
                return result
        return None

    def load_version(
        self, domain: str, version_id: str
    ) -> tuple[VersionRef, dict[str, Any]] | None:
        ddir = self._domain_dir(domain)
        body = ddir / "versions" / "scope" / f"scope_{version_id}.yaml"
        meta = ddir / "versions" / f"meta_{version_id}.yaml"
        if not body.exists() or not meta.exists():
            return None
        m = _safe_yaml_load(meta.read_text())
        main_state = _safe_yaml_load(body.read_text())

        # Load in-account instructions; fall back to empty if absent (e.g. older domains).
        acct_body = ddir / "versions" / "in_account" / f"in_account_scope_{version_id}.yaml"
        acct_state = _safe_yaml_load(acct_body.read_text()) if acct_body.exists() else {}

        return (
            VersionRef(
                domain=m["domain"],
                version_id=m["version_id"],
                created_at=m["created_at"],
                note=m.get("note", ""),
            ),
            self._merge(main_state, acct_state),
        )

    def list_versions(
        self, domain: str, limit: int | None = None
    ) -> list[VersionRef]:
        ddir = self._domain_dir(domain)
        files = sorted((ddir / "versions").glob("meta_*.yaml"), reverse=True)
        if limit is not None:
            files = files[:limit]
        out: list[VersionRef] = []
        for f in files:
            d = _safe_yaml_load(f.read_text())
            out.append(
                VersionRef(
                    domain=d["domain"],
                    version_id=d["version_id"],
                    created_at=d["created_at"],
                    note=d.get("note", ""),
                )
            )
        out.sort(key=lambda r: r.created_at)
        return out


# ---- State validation (reference: SCOPE_MANIFEST.md) -----------------------

_DOMAIN_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# Snowflake warehouse identifier: an unquoted identifier ([A-Za-z_][A-Za-z0-9_$]*)
# or a double-quoted identifier ("My WH"). Required top-level manifest field naming
# the virtual warehouse the offline build uses for compute.
_WAREHOUSE_RE = re.compile(r'^(?:[A-Za-z_][A-Za-z0-9_$]*|"[^"]+")$')
_STATUSES = frozenset({"draft", "active"})
_SOURCE_TYPES = frozenset({"snowflake_metadata", "horizon_context", "snowflake_content", "business_ontology"})

# Valid source names as defined in SCOPE_MANIFEST.md.
# Each name maps to exactly one (type, pipeline, content-type) triple.
# The validator also cross-checks that the source entry's `type` field
# matches the expected type for its `name` (see _SOURCE_TYPE_FOR_NAME below).
_KNOWN_SOURCE_NAMES = frozenset({
    # Snowflake-native metadata (type: snowflake_metadata)
    "catalog_objects",
    "roles_users_grants",
    "tags",
    "access_history",
    "si_artifacts",
    "cortex_agents_searches_threads",
    # Streamlit metadata-only record (no stage file patterns — metadata pipeline)
    "streamlit_apps_metadata",
    # Customer-data / source-code content (type: snowflake_content)
    "semantic_views",    # full DESCRIBE via refreshd CustomerData path
    "streamlit_apps",    # Streamlit source code via stage file patterns
    "dbt_projects",      # dbt manifest.json via file rule (stage + path)
    "stage_files",       # business docs / query-pattern files
    # Business Ontology integration (type: business_ontology)
    "business_ontology",
    # Horizon Context — BI dashboards (type: horizon_context)
    "tableau",
    "powerbi",
    "sigma",
    "looker",
    # Horizon Context — external databases (type: horizon_context)
    "databricks",
    "redshift",
    "sqlserver",
    "postgres",
    "dbt",
})

# Horizon Context BI dashboard sources — pattern rules on these require exact
# names (no wildcards) and support optional connector/path fields.
_HORIZON_BI_SOURCES = frozenset({"tableau", "powerbi", "sigma", "looker"})

# Sources whose `pattern` rules are object FQN globs (DB.SCHEMA.OBJECT). Database-level
# wildcard hygiene applies only to these — not to sources like `tags`, where `pattern`
# is a tag-name glob and `*` legitimately means "all tags".
_FQN_PATTERN_SOURCES = frozenset(
    {"catalog_objects", "semantic_views", "databricks", "redshift", "sqlserver", "postgres", "dbt"}
)

# Expected `type` value for each canonical source name.
# streamlit_apps_metadata uses snowflake_metadata (metadata pipeline only).
# semantic_views, streamlit_apps, and dbt_projects use snowflake_content (CustomerData / refreshd path).
_SOURCE_TYPE_FOR_NAME: dict[str, str] = {
    "catalog_objects":                  "snowflake_metadata",
    "semantic_views":                   "snowflake_content",
    "roles_users_grants":               "snowflake_metadata",
    "tags":                             "snowflake_metadata",
    "access_history":                   "snowflake_metadata",
    "si_artifacts":                     "snowflake_metadata",
    "cortex_agents_searches_threads":   "snowflake_metadata",
    "streamlit_apps_metadata":          "snowflake_metadata",
    "streamlit_apps":                   "snowflake_content",
    "dbt_projects":                     "snowflake_content",
    "stage_files":                      "snowflake_content",
    "business_ontology":                "business_ontology",
    "tableau":                          "horizon_context",
    "powerbi":                          "horizon_context",
    "sigma":                            "horizon_context",
    "looker":                           "horizon_context",
    "databricks":                       "horizon_context",
    "redshift":                         "horizon_context",
    "sqlserver":                        "horizon_context",
    "postgres":                         "horizon_context",
    "dbt":                              "horizon_context",
}
_RULE_TYPES = frozenset(
    {
        "pattern",
        "tag",
        "role",
        "file",
        "conversational",
        "lookback_days",
        "ontology_domain",
    }
)

# Every rule's verbatim builder phrasing lives in `user_prompt`.
_RULE_ALLOWED_KEYS: dict[str, frozenset[str]] = {
    "pattern": frozenset({"type", "pattern", "user_prompt", "description", "est_tables", "excluded", "provenance", "connector", "path"}),
    "tag": frozenset({"type", "tag", "values", "user_prompt", "provenance"}),
    "role": frozenset({"type", "role", "user_prompt", "provenance"}),
    "file": frozenset({"type", "stage", "file_pattern", "path", "user_prompt", "est_tables", "provenance"}),
    "conversational": frozenset({"type", "user_prompt", "provenance"}),
    # The window field is `days` (not `lookback_days`; that is the rule *type*).
    "lookback_days": frozenset({"type", "days", "user_prompt", "provenance"}),
    # ontology_domain: two sub-types per domain — must never be merged.
    #   Source rule:   domain + stage + file_pattern + user_prompt  (no count fields)
    #   Metadata rule: domain + count fields (no stage/file_pattern; user_prompt optional)
    # Count fields are display-only (from SYSTEM$GET_GLOSSARY_GRAPH); they do not affect
    # the build. The validator rejects any rule that mixes both sub-types.
    "ontology_domain": frozenset({
        "type", "domain", "stage", "file_pattern", "user_prompt", "provenance",
        "node_count", "relationship_count", "association_count", "source_file_count",
    }),
}

_SOURCE_ALLOWED_KEYS = frozenset({"name", "type", "enabled", "rules", "source_domain"})

# Relationship multiplicity values (optional on a relationship).
_MULTIPLICITIES = frozenset({"ManyToOne", "OneToOne", "ManyToMany"})

_CONCEPT_ALLOWED_KEYS = frozenset(
    {"name", "type", "domain", "description", "aliases", "formulas", "user_prompt", "extra", "id", "superseded_by", "provenance"}
)
_RELATIONSHIP_ALLOWED_KEYS = frozenset(
    {
        "source_concept",
        "source_domain",
        "relationship_type",
        "target_concept",
        "target_domain",
        "multiplicity",
        "verbalizes",
        "user_prompt",
        "extra",
        "id",
        "superseded_by",
        "provenance",
    }
)
_ASSOCIATION_ALLOWED_KEYS = frozenset(
    {
        "concept",
        "domain",
        "source",
        "fqn",
        "association_type",
        "user_prompt",
        "extra",
        "id",
        "superseded_by",
        "provenance",
    }
)
_INSTRUCTION_ALLOWED_KEYS = frozenset(
    {"user_prompt", "suggested_by", "id", "superseded_by", "provenance"}
)

# ---- Provenance -----------------------------------------------------------------
# Optional sub-object on every manifest entry. Carries the workflow state,
# the origin of the information, optional user attribution, and a list of
# sources the system used to derive or declare the entry.

_PROVENANCE_STATES = frozenset({"needs-feedback", "approved"})
_PROVENANCE_ORIGINS = frozenset({
    "declared-by-user", "inferred", "inferred-shown-to-user"
})
_PROVENANCE_ALLOWED_KEYS = frozenset({
    "state", "origin", "recorded_at", "initiated_by", "approved_by", "sources"
})
_PROVENANCE_SOURCE_ALLOWED_KEYS = frozenset({"type", "ref"})


def validate_state(
    state: dict[str, Any], *, domain: str | None = None
) -> list[str]:
    """Return human-readable validation errors. Empty list means valid."""
    errors: list[str] = []

    if not isinstance(state, dict):
        return ["root must be a YAML mapping"]

    bd = state.get("business_domain")
    if not isinstance(bd, str) or not bd.strip():
        errors.append("business_domain must be a non-empty string")
    else:
        # Domain names map 1:1 onto the stage path via _safe(); restricting the
        # charset keeps that mapping injective (e.g. "sales ops" and "sales_ops"
        # would otherwise both resolve to the path "sales_ops").
        if not _DOMAIN_RE.match(bd.strip()):
            errors.append(
                "business_domain must contain only letters, digits, underscores, "
                f"or hyphens (e.g. sales_ops); got {bd!r}"
            )
        if domain and bd.strip() != domain.strip():
            errors.append(
                f"business_domain {bd!r} does not match --domain {domain!r}"
            )

    status = state.get("status")
    if status is not None and status not in _STATUSES:
        errors.append(f"status must be one of {_STATUSES}, got {status!r}")

    # Required: the Snowflake virtual warehouse the offline build uses for compute.
    # Resolved from CURRENT_WAREHOUSE() during setup (see setup/SKILL.md).
    warehouse = state.get("warehouse")
    if warehouse is None:
        errors.append(
            "warehouse is required (the Snowflake warehouse the offline build runs on)"
        )
    elif not isinstance(warehouse, str) or not warehouse.strip():
        errors.append("warehouse must be a non-empty string")
    elif not _WAREHOUSE_RE.match(warehouse.strip()):
        errors.append(
            "warehouse must be a valid Snowflake warehouse identifier "
            f"(e.g. ANALYTICS_WH); got {warehouse!r}"
        )

    # `sources` is optional: a manifest with no catalog rules yet is a valid
    # early-authoring state (the build treats empty sources as "no rules yet").
    # When present it must still be a list of well-formed entries.
    if "sources" in state and not isinstance(state["sources"], list):
        errors.append("sources must be a list")
    elif "sources" in state:
        seen_names: set[str] = set()
        for i, src in enumerate(state["sources"]):
            prefix = f"sources[{i}]"
            if not isinstance(src, dict):
                errors.append(f"{prefix} must be a mapping")
                continue
            name = src.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{prefix}.name must be a non-empty string")
            elif name in seen_names:
                errors.append(f"duplicate source name {name!r}")
            else:
                seen_names.add(name)
                if name not in _KNOWN_SOURCE_NAMES:
                    errors.append(
                        f"{prefix}.name {name!r} is not a recognised source name; "
                        f"expected one of {sorted(_KNOWN_SOURCE_NAMES)}"
                    )
            st = src.get("type")
            if st not in _SOURCE_TYPES:
                errors.append(
                    f"{prefix}.type must be one of {sorted(_SOURCE_TYPES)}, got {st!r}"
                )
            # Cross-check: name and type must agree.
            if (
                isinstance(name, str)
                and name in _SOURCE_TYPE_FOR_NAME
                and st is not None
                and st != _SOURCE_TYPE_FOR_NAME[name]
            ):
                errors.append(
                    f"{prefix}: name {name!r} requires type "
                    f"{_SOURCE_TYPE_FOR_NAME[name]!r}, got {st!r}"
                )
            if "enabled" in src and not isinstance(src["enabled"], bool):
                errors.append(f"{prefix}.enabled must be a boolean")
            for key in src:
                if key not in _SOURCE_ALLOWED_KEYS:
                    errors.append(f"{prefix}: unexpected field {key!r}")
            # semantic_views should have at least one explicit, non-excluded pattern rule
            # when enabled. Emit a WARNING (not a hard error) so that existing manifests
            # persisted before this rule was introduced can still be saved via refine
            # without breaking — the agent instructions enforce the correct form on new
            # manifests. See INSTRUCTIONS.md "Semantic views — always write explicit rules".
            if name == "semantic_views" and src.get("enabled", True):
                sv_rules = src.get("rules")
                _has_include_pattern = isinstance(sv_rules, list) and any(
                    isinstance(r, dict)
                    and r.get("type") == "pattern"
                    and not r.get("excluded")
                    for r in sv_rules
                )
                if sv_rules is None or (isinstance(sv_rules, list) and not _has_include_pattern):
                    print(
                        f"WARNING {prefix}: semantic_views has no explicit include pattern rules — "
                        "add one rule per discovered SV (DATABASE.SCHEMA.SV_NAME) or at least "
                        "a database-scoped wildcard (DATABASE.SCHEMA.*); "
                        "omitting or using only excluded/non-pattern rules scopes to every SV in the account",
                        file=sys.stderr,
                    )

            if "rules" in src:
                if not isinstance(src["rules"], list):
                    errors.append(f"{prefix}.rules must be a list")
                else:
                    rules_list = src["rules"]

                    # business_ontology: at most one metadata rule per domain.
                    # A metadata rule is an ontology_domain rule with count fields but no stage/file_pattern.
                    if name == "business_ontology" and isinstance(rules_list, list):
                        _COUNT_KEYS = {"node_count", "relationship_count", "association_count", "source_file_count"}
                        _SOURCE_KEYS = {"stage", "file_pattern"}
                        meta_domains: dict[str, int] = {}
                        for j, rule in enumerate(rules_list):
                            if not isinstance(rule, dict):
                                continue
                            if rule.get("type") != "ontology_domain":
                                continue
                            has_count = bool(_COUNT_KEYS & set(rule))
                            has_source = bool(_SOURCE_KEYS & set(rule))
                            if has_count and not has_source:
                                dom = rule.get("domain", "")
                                if dom in meta_domains:
                                    errors.append(
                                        f"{prefix}: domain {dom!r} has more than one metadata "
                                        f"ontology_domain rule (rules[{meta_domains[dom]}] and "
                                        f"rules[{j}]) — each domain must have exactly one metadata rule"
                                    )
                                else:
                                    meta_domains[dom] = j

                    for j, rule in enumerate(rules_list):
                        errors.extend(
                            _validate_rule(rule, f"{prefix}.rules[{j}]", source_name=name)
                        )

    for list_name, validator in (
        ("concepts", _validate_concept),
        ("relationships", _validate_relationship),
        ("associations", _validate_association),
        ("additional_instructions", _validate_freeform_instruction),
        ("in_account_instructions", _validate_freeform_instruction),
    ):
        if list_name not in state:
            continue
        entries = state[list_name]
        if not isinstance(entries, list):
            errors.append(f"{list_name} must be a list")
            continue
        for i, entry in enumerate(entries):
            errors.extend(validator(entry, f"{list_name}[{i}]"))

    if "pending_asks" in state:
        errors.extend(_validate_pending_asks(state["pending_asks"]))

    if "targets" in state:
        errors.append(
            "targets is not supported (remove this key; may be reintroduced later)"
        )

    return errors


_PENDING_ASK_ALLOWED_KEYS = frozenset({"ask", "prompted_at", "provenance"})


def _validate_pending_asks(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return ["pending_asks must be a list"]
    errors: list[str] = []
    for i, entry in enumerate(entries):
        path = f"pending_asks[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{path} must be a mapping")
            continue
        for key in entry:
            if key not in _PENDING_ASK_ALLOWED_KEYS:
                errors.append(f"{path}: unexpected field {key!r}")
        ask = entry.get("ask")
        if not isinstance(ask, str) or not ask.strip():
            errors.append(f"{path}.ask must be a non-empty string")
        prompted = entry.get("prompted_at")
        if prompted is not None and (
            not isinstance(prompted, str) or not prompted.strip()
        ):
            errors.append(
                f"{path}.prompted_at must be a non-empty string when set"
            )
        errors.extend(_validate_provenance(entry.get("provenance"), f"{path}.provenance"))
    return errors


def _validate_rule(rule: Any, path: str, *, source_name: Any = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(rule, dict):
        return [f"{path} must be a mapping"]

    rtype = rule.get("type")
    if rtype not in _RULE_TYPES:
        return [
            f"{path}.type must be one of {sorted(_RULE_TYPES)}, got {rtype!r}"
        ]

    # Defined once here; reused by both the user_prompt check and the ontology_domain
    # section below. ontology_domain metadata rules carry count fields but no source
    # fields; they are system-generated so user_prompt is optional. Source rules and
    # domain-only rules (no counts, no stage) still require user_prompt.
    _COUNT_FIELDS: frozenset[str] = frozenset({"node_count", "relationship_count", "association_count", "source_file_count"})
    _SOURCE_FIELDS: frozenset[str] = frozenset({"stage", "file_pattern"})
    _is_ontology_metadata = (
        rtype == "ontology_domain"
        and bool(_COUNT_FIELDS & set(rule))
        and not (_SOURCE_FIELDS & set(rule))
    )
    up = rule.get("user_prompt")
    if not _is_ontology_metadata and (not isinstance(up, str) or not up.strip()):
        errors.append(f"{path}.user_prompt must be a non-empty string")

    allowed = _RULE_ALLOWED_KEYS[rtype]
    for key in rule:
        if key not in allowed:
            errors.append(f"{path}: unexpected field {key!r} for type {rtype!r}")

    if rtype == "pattern":
        if not isinstance(rule.get("pattern"), str) or not rule.get("pattern"):
            errors.append(f"{path}.pattern must be a non-empty string")
        if "excluded" in rule and not isinstance(rule["excluded"], bool):
            errors.append(f"{path}.excluded must be a boolean")
        errors.extend(_validate_est_tables(rule, path, allowed_type="pattern"))
        # Wildcard limitations differ for include vs exclude patterns (see below).
        # horizon_context sources (BI objects): pattern must be an exact name
        # (no wildcards); wildcards are only allowed in the path field.
        if source_name in _HORIZON_BI_SOURCES:
            pat = rule.get("pattern", "")
            if isinstance(pat, str) and any(c in pat for c in ("*", "?")):
                errors.append(
                    f"{path}.pattern must be an exact BI object name for "
                    f"horizon_context sources (no wildcards); use the 'path' "
                    f"field for folder-level wildcards"
                )
            if "connector" in rule:
                conn = rule["connector"]
                if not isinstance(conn, str) or not conn.strip():
                    errors.append(f"{path}.connector must be a non-empty string")
            if "path" in rule:
                p = rule["path"]
                if not isinstance(p, str) or not p.strip():
                    errors.append(f"{path}.path must be a non-empty string")
        elif source_name in _FQN_PATTERN_SOURCES:
            # Patterns whose glob is an object FQN (catalog_objects, semantic_views,
            # external-table horizon sources). Reject database-level wildcards for
            # includes — they scan every database and make the build slow. Excludes
            # are applied as post-filters (no DB scan), so cross-database patterns
            # like "*.*DEV*.*" are valid; only bare "*" is rejected.
            pat = rule.get("pattern", "")
            is_exclude = rule.get("excluded", False)
            if isinstance(pat, str) and pat:
                first_seg = pat.split(".", 1)[0]
                if is_exclude:
                    if pat.strip() == "*":
                        errors.append(
                            f"{path}.pattern: bare '*' would exclude everything"
                            f" — scope to a more specific pattern like '*.*DEV*.*'"
                            f" or 'DATABASE.SCHEMA.*' (got {pat!r})"
                        )
                elif pat.strip() == "*" or first_seg == "*":
                    errors.append(
                        f"{path}.pattern must name a database — database-level "
                        f"wildcards like '*' or '*.SCHEMA.*' scan every database and "
                        f"are too slow; scope to DATABASE.SCHEMA.* instead (got {pat!r})"
                    )
                # semantic_views patterns must carry the full database name
                # (no bare SCHEMA.* — that is ambiguous and matches nothing reliably).
                if source_name == "semantic_views" and pat.count(".") < 2:
                    errors.append(
                        f"{path}.pattern for semantic_views must include the full "
                        f"database (DATABASE.SCHEMA.OBJECT or DATABASE.SCHEMA.*), "
                        f"got {pat!r}"
                    )

    elif rtype == "tag":
        if not isinstance(rule.get("tag"), str) or not rule.get("tag"):
            errors.append(f"{path}.tag must be a non-empty string")
        if "values" in rule:
            vals = rule["values"]
            if vals is None:
                errors.append(f"{path}.values must not be null (use [] for all values)")
            elif not isinstance(vals, list):
                errors.append(f"{path}.values must be a list of strings")
            else:
                for k, v in enumerate(vals):
                    if not isinstance(v, str):
                        errors.append(f"{path}.values[{k}] must be a string")
        if "est_tables" in rule:
            errors.append(
                f"{path}: est_tables must be omitted for tag rules (got {rule['est_tables']!r})"
            )

    elif rtype == "role":
        if not isinstance(rule.get("role"), str) or not rule.get("role"):
            errors.append(f"{path}.role must be a non-empty string")
        if "est_tables" in rule:
            errors.append(
                f"{path}: est_tables must be omitted for role rules (got {rule['est_tables']!r})"
            )

    elif rtype == "file":
        stage = rule.get("stage")
        if not isinstance(stage, str) or not stage.strip():
            errors.append(
                f"{path}.stage must be a non-empty string (DATABASE.SCHEMA.STAGE_NAME)"
            )
        elif stage.count(".") != 2:
            errors.append(
                f"{path}.stage should be DATABASE.SCHEMA.STAGE_NAME (three dot-separated parts)"
            )
        if source_name == "dbt_projects":
            # dbt file rules use `path` (relative path to manifest.json), not file_pattern.
            if "file_pattern" in rule:
                errors.append(
                    f"{path}: dbt_projects file rules use 'path', not 'file_pattern'"
                )
            p = rule.get("path")
            if not isinstance(p, str) or not p.strip():
                errors.append(
                    f"{path}.path is required for dbt_projects file rules"
                )
            elif not p.strip().endswith("manifest.json"):
                errors.append(
                    f"{path}.path must be the full path up to and including "
                    f"'manifest.json' (got {p!r})"
                )
            if "est_tables" in rule:
                errors.append(
                    f"{path}: est_tables must be omitted for dbt_projects file rules"
                )
        else:
            # streamlit_apps / stage_files use file_pattern, not path.
            if "path" in rule:
                errors.append(
                    f"{path}: {source_name} file rules use 'file_pattern', not 'path'"
                )
            if "file_pattern" not in rule:
                errors.append(
                    f"{path}.file_pattern is required (use \"\" for all files in the stage)"
                )
            else:
                fp = rule["file_pattern"]
                if not isinstance(fp, str):
                    errors.append(f"{path}.file_pattern must be a string")
                elif fp.strip():
                    errors.extend(_validate_est_tables(rule, path, allowed_type="file"))
                elif "est_tables" in rule:
                    errors.append(
                        f"{path}: omit est_tables when file_pattern is empty (stage-wide)"
                    )

    elif rtype == "conversational":
        if "est_tables" in rule:
            errors.append(
                f"{path}: est_tables must be omitted for conversational rules"
            )

    elif rtype == "lookback_days":
        days = rule.get("days")
        if not isinstance(days, int) or days < 1:
            errors.append(f"{path}.days must be a positive integer")
        if "est_tables" in rule:
            errors.append(f"{path}: est_tables must be omitted for lookback_days rules")

    elif rtype == "ontology_domain":
        domain = rule.get("domain")
        if not isinstance(domain, str) or not domain.strip():
            errors.append(f"{path}.domain must be a non-empty string")

        has_count = bool(_COUNT_FIELDS & set(rule))
        has_source = bool(_SOURCE_FIELDS & set(rule))

        # Source rule and metadata rule must never be merged.
        if has_count and has_source:
            errors.append(
                f"{path}: count fields ({', '.join(sorted(_COUNT_FIELDS & set(rule)))})"
                " and source fields (stage, file_pattern) must not appear on the same"
                " ontology_domain rule — use a separate source rule and metadata rule per domain"
            )

        # Count fields must be non-negative integers when present.
        for _cf in _COUNT_FIELDS:
            if _cf in rule:
                _cv = rule[_cf]
                if not isinstance(_cv, int) or isinstance(_cv, bool) or _cv < 0:
                    errors.append(
                        f"{path}.{_cf} must be a non-negative integer, got {_cv!r}"
                    )

        # Source rule: stage and file_pattern are required together.
        stage = rule.get("stage")
        if stage is not None:
            if not isinstance(stage, str) or not stage.strip():
                errors.append(
                    f"{path}.stage must be a non-empty string (DATABASE.SCHEMA.STAGE_NAME)"
                )
            elif stage.count(".") != 2:
                errors.append(
                    f"{path}.stage should be DATABASE.SCHEMA.STAGE_NAME (three dot-separated parts)"
                )
            if "file_pattern" not in rule:
                errors.append(
                    f"{path}.file_pattern is required when stage is set"
                    ' (use "" for all files in the stage)'
                )
            else:
                fp = rule["file_pattern"]
                if not isinstance(fp, str):
                    errors.append(f"{path}.file_pattern must be a string")
        elif "file_pattern" in rule:
            errors.append(
                f"{path}: file_pattern requires stage to be set"
            )

    errors.extend(_validate_provenance(rule.get("provenance"), f"{path}.provenance"))
    return errors


def _validate_est_tables(
    rule: dict[str, Any], path: str, *, allowed_type: str
) -> list[str]:
    if "est_tables" not in rule:
        return []
    et = rule["est_tables"]
    if et is None:
        return [
            f"{path}.est_tables must be omitted, not null (per SCOPE_MANIFEST.md)"
        ]
    if not isinstance(et, int) or et < 0:
        return [f"{path}.est_tables must be a non-negative integer"]
    return []


def _validate_extra(extra: Any, path: str) -> list[str]:
    if extra is None:
        return []
    if not isinstance(extra, dict):
        return [f"{path}.extra must be a mapping of key-value pairs"]
    errors: list[str] = []
    for k, v in extra.items():
        if not isinstance(k, str) or not k.strip():
            errors.append(f"{path}.extra keys must be non-empty strings")
        if not isinstance(v, (str, int, float, bool)):
            errors.append(
                f"{path}.extra[{k!r}] must be a string, number, or boolean"
            )
    return errors


def _validate_allowed_keys(
    entry: dict[str, Any], path: str, allowed: frozenset[str]
) -> list[str]:
    return [
        f"{path}: unexpected field {key!r}"
        for key in entry
        if key not in allowed
    ]


def _validate_string_list(
    values: Any, path: str, field: str, *, required: bool = False
) -> list[str]:
    if values is None:
        return [f"{path}.{field} is required"] if required else []
    if not isinstance(values, list):
        return [f"{path}.{field} must be a list of strings"]
    errors: list[str] = []
    for i, v in enumerate(values):
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{path}.{field}[{i}] must be a non-empty string")
    return errors


def _validate_concept(entry: Any, path: str) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{path} must be a mapping"]
    errors = _validate_allowed_keys(entry, path, _CONCEPT_ALLOWED_KEYS)
    for legacy in ("term", "meaning", "ontology_regeneration_hint"):
        if legacy in entry:
            errors.append(
                f"{path}: remove {legacy!r} — use concepts[] fields "
                "(name, type, domain, description, aliases, formulas, …)"
            )
    for field in ("name", "type", "user_prompt"):
        val = entry.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{path}.{field} must be a non-empty string")
    # `domain` is part of concept identity (domain, name); optional, defaults to
    # the manifest's business_domain when omitted.
    if "domain" in entry and (
        not isinstance(entry["domain"], str) or not entry["domain"].strip()
    ):
        errors.append(f"{path}.domain must be a non-empty string when set")
    if "description" in entry and entry["description"] is not None:
        if not isinstance(entry["description"], str):
            errors.append(f"{path}.description must be a string")
    errors.extend(_validate_string_list(entry.get("aliases"), path, "aliases"))
    errors.extend(_validate_string_list(entry.get("formulas"), path, "formulas"))
    errors.extend(_validate_extra(entry.get("extra"), f"{path}"))
    errors.extend(_validate_provenance(entry.get("provenance"), f"{path}.provenance"))
    return errors


def _validate_relationship(entry: Any, path: str) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{path} must be a mapping"]
    errors = _validate_allowed_keys(entry, path, _RELATIONSHIP_ALLOWED_KEYS)
    for field in ("source_concept", "relationship_type", "target_concept", "user_prompt"):
        val = entry.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{path}.{field} must be a non-empty string")
    # Optional domain-qualified references and relationship vocab.
    for field in ("source_domain", "target_domain", "verbalizes"):
        if field in entry and (
            not isinstance(entry[field], str) or not entry[field].strip()
        ):
            errors.append(f"{path}.{field} must be a non-empty string when set")
    if "multiplicity" in entry and entry["multiplicity"] not in _MULTIPLICITIES:
        errors.append(
            f"{path}.multiplicity must be one of {sorted(_MULTIPLICITIES)} when set"
        )
    errors.extend(_validate_extra(entry.get("extra"), f"{path}"))
    errors.extend(_validate_provenance(entry.get("provenance"), f"{path}.provenance"))
    return errors


def _validate_association(entry: Any, path: str) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{path} must be a mapping"]
    errors = _validate_allowed_keys(entry, path, _ASSOCIATION_ALLOWED_KEYS)
    for field in ("concept", "source", "fqn", "association_type", "user_prompt"):
        if field not in entry:
            errors.append(f"{path}.{field} is required")
            continue
        val = entry[field]
        if field == "fqn":
            if not isinstance(val, str):
                errors.append(f"{path}.fqn must be a string (use \"\" if N/A)")
        elif not isinstance(val, str) or not val.strip():
            errors.append(f"{path}.{field} must be a non-empty string")
    if "domain" in entry and (
        not isinstance(entry["domain"], str) or not entry["domain"].strip()
    ):
        errors.append(f"{path}.domain must be a non-empty string when set")
    errors.extend(_validate_extra(entry.get("extra"), f"{path}"))
    errors.extend(_validate_provenance(entry.get("provenance"), f"{path}.provenance"))
    return errors


def _validate_freeform_instruction(entry: Any, path: str) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{path} must be a mapping"]
    errors = _validate_allowed_keys(entry, path, _INSTRUCTION_ALLOWED_KEYS)
    if "type" in entry:
        errors.append(
            f"{path}: remove type — use concepts/relationships/mappings "
            "for structured semantics; additional_* lists are user_prompt-only"
        )
    up = entry.get("user_prompt")
    if not isinstance(up, str) or not up.strip():
        errors.append(f"{path}.user_prompt must be a non-empty string")
    suggested = entry.get("suggested_by")
    if suggested is not None and (
        not isinstance(suggested, str) or not suggested.strip()
    ):
        errors.append(f"{path}.suggested_by must be a non-empty string when set")
    errors.extend(_validate_provenance(entry.get("provenance"), f"{path}.provenance"))
    return errors


def _validate_provenance(prov: Any, path: str) -> list[str]:
    """Validate the optional `provenance` sub-object on any manifest entry.

    Returns [] when `prov` is None or missing — provenance is always optional.
    """
    if prov is None:
        return []
    if not isinstance(prov, dict):
        return [f"{path} must be a mapping"]
    errors: list[str] = []
    for key in prov:
        if key not in _PROVENANCE_ALLOWED_KEYS:
            errors.append(f"{path}: unexpected field {key!r}")
    state_val = prov.get("state")
    if state_val not in _PROVENANCE_STATES:
        errors.append(
            f"{path}.state must be one of {sorted(_PROVENANCE_STATES)}, got {state_val!r}"
        )
    origin_val = prov.get("origin")
    if origin_val not in _PROVENANCE_ORIGINS:
        errors.append(
            f"{path}.origin must be one of {sorted(_PROVENANCE_ORIGINS)}, got {origin_val!r}"
        )
    for field in ("recorded_at", "initiated_by", "approved_by"):
        val = prov.get(field)
        if val is not None and (not isinstance(val, str) or not val.strip()):
            errors.append(f"{path}.{field} must be a non-empty string when set")
    sources = prov.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            errors.append(f"{path}.sources must be a list")
        else:
            for i, src in enumerate(sources):
                src_path = f"{path}.sources[{i}]"
                if not isinstance(src, dict):
                    errors.append(f"{src_path} must be a mapping")
                    continue
                for key in src:
                    if key not in _PROVENANCE_SOURCE_ALLOWED_KEYS:
                        errors.append(f"{src_path}: unexpected field {key!r}")
                if not isinstance(src.get("type"), str) or not src.get("type"):
                    errors.append(f"{src_path}.type must be a non-empty string")
                if not isinstance(src.get("ref"), str) or not src.get("ref"):
                    errors.append(f"{src_path}.ref must be a non-empty string")
    return errors


def _raise_if_invalid(state: dict[str, Any], *, domain: str | None = None) -> None:
    errors = validate_state(state, domain=domain)
    if errors:
        detail = "\n".join(f"  - {e}" for e in errors)
        raise PersistenceError(f"state validation failed:\n{detail}")


# ---- Preview ---------------------------------------------------------------


def strip_for_preview(state: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `state` with internal fields removed.

    What stays: domain, status, sources.rules, concepts, relationships, mappings,
    additional_instructions, in_account_instructions. What goes: version_id,
    created_at, updated_at, every `id` field, every `superseded_by` field.
    """
    return _strip(state, top_level=True)


def _strip(obj: Any, top_level: bool = False) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if top_level and k in _STRIPPED_TOP_LEVEL:
                continue
            if k in _STRIPPED_FIELD_NAMES:
                continue
            stripped = _strip(v)
            if stripped is None and k != "status":
                # drop empty derived fields, but keep status: null distinguishable
                if isinstance(v, (list, dict)) and not v:
                    continue
            out[k] = stripped
        return out
    if isinstance(obj, list):
        return [_strip(item) for item in obj]
    return obj


# ---- CLI -------------------------------------------------------------------


def _safe_yaml_load(text: str) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise PersistenceError(f"invalid YAML: {e}") from e
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise PersistenceError("YAML root must be a mapping")
    return loaded


def _dispatch_doctor() -> int:
    """Pre-flight: resolve DB+schema and verify they are reachable/creatable.

    Reports the database and schema that `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER
    create-context` will use. See `reference/STORAGE.md` for the JSON shape
    and the three branches the skill must handle. Always exits 0 and never raises.
    """
    import shutil

    snow_cli = "ok" if shutil.which("snow") else "missing"

    local_root = os.environ.get("CORTEX_SENSE_LOCAL_ROOT")
    if local_root:
        report = {
            "snow_cli": snow_cli,
            "storage_backend": "local",
            "storage_location": str(Path(local_root).resolve()),
            "storage_ready": True,
        }
        print(json.dumps(report))
        return 0

    database = os.environ.get("CORTEX_SENSE_DB")
    schema = os.environ.get("CORTEX_SENSE_SCHEMA")
    connection = os.environ.get("CORTEX_SENSE_CONNECTION")

    # Resolution: env var → built-in default (TEMP.CORTEX_SENSE).
    # CURRENT_DATABASE()/CURRENT_SCHEMA() is intentionally NOT used — it
    # returns user-personal schemas (e.g. MOUSAVI) that are not appropriate.
    db_source = "env" if database else "default"
    sc_source = "env" if schema else "default"
    database = database or _DEFAULT_DB
    schema = schema or _DEFAULT_SCHEMA

    report: dict[str, Any] = {
        "snow_cli": snow_cli,
        "database": database,
        "database_source": db_source,
        "schema": schema,
        "schema_source": sc_source,
        # Context lookup availability — the SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT SQL
        # fallback resolves account/deployment server-side, so it is usable
        # whenever the Snowflake connection works (no env vars required).
        "lookup_sql_available": snow_cli == "ok",
    }

    # Storage is handled by SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER.
    # The snow CLI only needs to be present; no stage provisioning is done here.
    report["storage_backend"] = "cortex_context_builder"
    report["storage_location"] = f"@{database.upper()}.{schema.upper()}.<DOMAIN>/"
    report["storage_ready"] = snow_cli == "ok"
    if snow_cli == "missing":
        report["storage_ready"] = False
    print(json.dumps(report))
    return 0


def _new_version_id() -> str:
    return f"v-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _safe(s: str) -> str:
    """Sanitize a domain into a stage path segment (allows hyphens).

    validate_state() already constrains business_domain to [A-Za-z0-9_-]+, so
    for validated state this is the identity transform. The substitution here is
    only a defensive fallback for callers that bypass validation; it is NOT
    collision-free, which is why the validator enforces the charset upstream.
    """
    out = "".join(c if c.isalnum() or c in "_-" else "_" for c in s)
    if not out:
        raise PersistenceError(f"domain {s!r} sanitizes to an empty path")
    return out


def _domain_to_stage(domain: str) -> str:
    """Derive the Snowflake stage name from a domain identifier.

    Hyphens are replaced with underscores (hyphens are valid in domain names
    but not in Snowflake stage identifiers). Result is uppercased.
    e.g. "sales_ops" → "SALES_OPS", "finance-2026" → "FINANCE_2026".
    """
    out = "".join(c.upper() if c.isalnum() or c == "_" else "_" for c in domain)
    if not out:
        raise PersistenceError(f"domain {domain!r} cannot be mapped to a stage name")
    return out


def main() -> int:
    p = argparse.ArgumentParser(prog="persist_state.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("--from-file", required=True)
    preview.add_argument(
        "--domain",
        help="If set, business_domain in the file must match",
    )

    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--from-file", required=True)
    validate_p.add_argument(
        "--domain",
        help="If set, business_domain in the file must match",
    )

    # merge intentionally accepts stdin in addition to --from-file: the skill
    # assembles the manifest YAML in memory and pipes it through before calling
    # put-stage-file, so there is no on-disk file to point --from-file at yet.
    merge_p = sub.add_parser("merge")
    merge_p.add_argument("--from-file")
    merge_p.add_argument(
        "--domain",
        help="If set, business_domain in the file must match",
    )

    # Pre-flight: verify snow CLI, resolve DB/schema, output JSON report.
    sub.add_parser("doctor")

    args = p.parse_args()

    try:
        return _dispatch(args)
    except PersistenceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _dispatch(args) -> int:
    if args.cmd == "doctor":
        return _dispatch_doctor()

    if args.cmd in ("preview", "validate", "merge"):
        from_file = getattr(args, "from_file", None)
        if args.cmd == "validate" and not from_file:
            raise SystemExit("--from-file is required")
        try:
            if from_file:
                state = _safe_yaml_load(Path(from_file).read_text())
            else:
                state = _safe_yaml_load(sys.stdin.read())
        except (OSError, PersistenceError) as e:
            raise SystemExit(f"cannot read input: {e}")
        domain = getattr(args, "domain", None)
        if args.cmd == "validate":
            errors = validate_state(state, domain=domain)
            if errors:
                for e in errors:
                    print(e, file=sys.stderr)
                return 1
            print(json.dumps({"ok": True}))
            return 0
        if args.cmd == "merge":
            state = _merge_instructions(state)
            _raise_if_invalid(state, domain=domain)
            sys.stdout.write(
                yaml.safe_dump(state, sort_keys=False, default_flow_style=False)
            )
            return 0
        _raise_if_invalid(state, domain=domain)
        sys.stdout.write(
            yaml.safe_dump(strip_for_preview(state), sort_keys=False, default_flow_style=False)
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
