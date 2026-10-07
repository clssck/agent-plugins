#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.
"""Fetch multimodal model capabilities from corvo-config, write model_capabilities.json.

This script:
1. Fetches the prod.yaml.tmpl from the corvo-config repository.
2. Strips Go-template directives and parses the YAML.
3. Extracts per-model multimodal capabilities (max_input_images, max_input_documents).
4. Cross-references against src/models.json (only emits models we ship).
5. Merges static per-family metadata (file size limits, supported formats).
6. Writes src/model_capabilities.json.

Usage:
    python dev/models/fetch_capabilities.py
    python dev/models/fetch_capabilities.py --corvo-path /path/to/prod.yaml.tmpl
    python dev/models/fetch_capabilities.py \
      --corvo-url https://api.github.com/repos/ORG/REPO/contents/PATH
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

_CORE_PKG = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "snowflake-ai-optimize-core"
    / "src"
    / "snowflake_ai_optimize"
    / "core"
)
MODELS_JSON = _CORE_PKG / "models.json"
CAPABILITIES_JSON = _CORE_PKG / "model_capabilities.json"

DEFAULT_CORVO_URL = (
    "https://api.github.com/repos/snowflake-eng/corvo-config/contents/"
    "overlaymgr/templates/configs/xp_config/prod.yaml.tmpl?ref=main"
)

# --------------------------------------------------------------------------
# Static per-family metadata not available in corvo-config.
# These change rarely and are maintained manually.
# --------------------------------------------------------------------------

# File size limits per model family (MB).
# Keys are regex patterns matched against model names.
_FILE_SIZE_LIMITS: dict[str, dict[str, float]] = {
    r"^openai-gpt": {"images": 5.0},
    r"^gemini": {"images": 37.5, "documents": 37.5},
    r"^claude": {"images": 3.75, "documents": 22.0},
    r"^llama4": {"images": 10.0},
    r"^pixtral": {"images": 10.0},
}

# Max document pages per model family.
_MAX_DOCUMENT_PAGES: dict[str, int] = {
    r"^gemini-3\.1-pro": 3000,
    r"^gemini": 1000,
    r"^claude": 100,
}

# Supported image formats per model family.
# IMPORTANT: _match_family returns the first match, so specific patterns must
# come before the catch-all r".*" entry at the end.
_IMAGE_FORMATS: dict[str, list[str]] = {
    r"^llama4": ["jpg", "jpeg", "png", "gif", "webp", "bmp"],
    r"^pixtral": ["jpg", "jpeg", "png", "gif", "webp", "bmp"],
    r".*": ["jpg", "jpeg", "png", "gif", "webp"],  # default — MUST remain last
}

# Supported document formats per model family.
_DOCUMENT_FORMATS: dict[str, list[str]] = {
    r"^claude": ["pdf", "txt", "doc", "docx", "xls", "xlsx", "csv", "xhtml"],
    r"^gemini": ["pdf", "txt"],
}


def _match_family(model_name: str, mapping: dict[str, Any]) -> Any | None:
    """Return the first value whose key regex matches model_name."""
    for pattern, value in mapping.items():
        if re.match(pattern, model_name):
            return value
    return None


# --------------------------------------------------------------------------
# Corvo-config parsing
# --------------------------------------------------------------------------


def _strip_go_templates(text: str) -> str:
    """Remove Go template directives (<<<- ... >>>) and pick the prod path.

    Strategy: remove all lines containing <<<...>>> directives. This drops
    conditional blocks for preprod-only models but keeps the prod-path content
    since prod models are outside conditionals or in the else branch.
    """
    # Remove inline directives
    cleaned = re.sub(r"<<<-?\s*.*?\s*-?>>>", "", text)
    return cleaned


def _fetch_corvo_yaml(source: str, token_env: str = "GH_TOKEN") -> str:
    """Fetch the raw YAML content from a file path or URL.

    For URL sources, reads a GitHub token from the environment variable named
    by `token_env` and sends it as an Authorization header (never in the URL).
    Uses the GitHub API contents endpoint with Accept: application/vnd.github.raw
    to retrieve raw file content from private repos.
    """
    if source.startswith("http://") or source.startswith("https://"):
        req = urllib.request.Request(source)
        token = os.environ.get(token_env, "")
        if token:
            req.add_header("Authorization", f"token {token}")
        # Request raw content from GitHub API (avoids base64 JSON wrapper)
        req.add_header("Accept", "application/vnd.github.raw")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    else:
        return Path(source).read_text(encoding="utf-8")


def _extract_model_configs_section(text: str) -> str:
    """Extract just the text_completion.model_configs array from the YAML.

    The full corvo-config file has duplicate YAML anchors across conditional
    branches (which are valid in Go templates but invalid after stripping).
    We only need the model_configs list, so we extract it with a targeted
    approach rather than parsing the entire file.
    """
    lines = text.split("\n")
    # Find the start of model_configs under text_completion
    in_text_completion = False
    text_completion_indent = -1
    model_configs_start = -1
    model_configs_indent = 0

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue
        current_indent = len(line) - len(stripped)

        if stripped.startswith("text_completion:"):
            in_text_completion = True
            text_completion_indent = current_indent
            continue

        # If we hit another top-level key at the same indent, we've left text_completion
        if (
            in_text_completion
            and current_indent <= text_completion_indent
            and not stripped.startswith("#")
        ) and not stripped.startswith("model_configs:"):
            break

        if (
            in_text_completion
            and stripped.startswith("model_configs:")
            and current_indent > text_completion_indent
        ):
            # Verify it's actually a child of text_completion (indented deeper)
            model_configs_start = i + 1
            model_configs_indent = current_indent
            break

    if model_configs_start < 0:
        return ""

    # Collect lines until we hit a sibling key at the same or lower indent
    section_lines = ["model_configs:"]

    for i in range(model_configs_start, len(lines)):
        line = lines[i]
        if not line.strip():
            continue
        current_indent = len(line) - len(line.lstrip())
        # Stop if we've un-indented to a sibling/parent key
        if (
            current_indent <= model_configs_indent
            and line.strip()
            and not line.strip().startswith("#")
        ):
            break
        section_lines.append(line)

    return "\n".join(section_lines)


def parse_corvo_config(raw_yaml: str) -> dict[str, dict]:
    """Parse corvo-config YAML and extract per-model multimodal capabilities.

    Returns:
        {model_name: {"max_input_images": int, "max_input_documents": int}}

    """
    cleaned = _strip_go_templates(raw_yaml)

    # Extract just the model_configs section to avoid duplicate anchor issues
    section = _extract_model_configs_section(cleaned)
    if not section:
        # Fallback: try full-file parse
        try:
            config = yaml.safe_load(cleaned)
            model_configs = config.get("text_completion", {}).get("model_configs", [])
        except yaml.YAMLError as e:
            print(f"ERROR: Could not parse corvo-config YAML: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            parsed = yaml.safe_load(section)
            model_configs = parsed.get("model_configs", []) if parsed else []
        except yaml.YAMLError as e:
            print(f"ERROR: Could not parse model_configs section: {e}", file=sys.stderr)
            sys.exit(1)

    capabilities = {}

    for entry in model_configs:
        if not isinstance(entry, dict):
            continue
        model_details = entry.get("model_details", {})
        name = model_details.get("name", "")
        if not name:
            continue

        max_images = entry.get("max_input_images", 0)
        max_docs = entry.get("max_input_documents", 0)

        # Only include models with multimodal support
        if max_images > 0 or max_docs > 0:
            caps: dict[str, int] = {}
            if max_images > 0:
                caps["max_input_images"] = max_images
            if max_docs > 0:
                caps["max_input_documents"] = max_docs
            capabilities[name] = caps

    return capabilities


# --------------------------------------------------------------------------
# Merge with static metadata
# --------------------------------------------------------------------------


def enrich_capabilities(
    raw_caps: dict[str, dict], shipped_models: set[str]
) -> dict[str, dict]:
    """Enrich raw capabilities with static metadata and filter to shipped models.

    Args:
        raw_caps: From parse_corvo_config().
        shipped_models: Model names present in src/models.json.

    Returns:
        Fully enriched capabilities dict, only for models we ship.

    """
    result = {}

    for model_name in sorted(raw_caps.keys()):
        if model_name not in shipped_models:
            continue

        caps = dict(raw_caps[model_name])

        # File size limits
        size_limits = _match_family(model_name, _FILE_SIZE_LIMITS)
        if (
            size_limits
            and caps.get("max_input_images", 0) > 0
            and "images" in size_limits
        ):
            caps["max_file_size_mb_images"] = size_limits["images"]
        if (
            size_limits
            and caps.get("max_input_documents", 0) > 0
            and "documents" in size_limits
        ):
            caps["max_file_size_mb_documents"] = size_limits["documents"]

        # Max document pages
        if caps.get("max_input_documents", 0) > 0:
            pages = _match_family(model_name, _MAX_DOCUMENT_PAGES)
            if pages:
                caps["max_document_pages"] = pages

        # Supported image formats
        if caps.get("max_input_images", 0) > 0:
            formats = _match_family(model_name, _IMAGE_FORMATS)
            if formats:
                caps["supported_image_formats"] = list(formats)

        # Supported document formats
        if caps.get("max_input_documents", 0) > 0:
            doc_formats = _match_family(model_name, _DOCUMENT_FORMATS)
            if doc_formats:
                caps["supported_document_formats"] = list(doc_formats)

        result[model_name] = caps

    return result


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch multimodal capabilities from corvo-config."
    )
    parser.add_argument(
        "--corvo-path",
        help="Local path to prod.yaml.tmpl (skips network fetch)",
    )
    parser.add_argument(
        "--corvo-url",
        default=DEFAULT_CORVO_URL,
        help=f"URL to fetch prod.yaml.tmpl (default: {DEFAULT_CORVO_URL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output to stdout instead of writing to file",
    )
    args = parser.parse_args()

    # Load shipped models
    if not MODELS_JSON.exists():
        print(f"ERROR: {MODELS_JSON} not found.", file=sys.stderr)
        sys.exit(1)
    shipped_models = set(json.loads(MODELS_JSON.read_text()).keys())
    print(f"Loaded {len(shipped_models)} shipped models from {MODELS_JSON.name}")

    # Fetch corvo-config
    source = args.corvo_path or args.corvo_url
    print(f"Fetching corvo-config from: {source}")
    raw_yaml = _fetch_corvo_yaml(source)
    print(f"Fetched {len(raw_yaml)} bytes")

    # Parse capabilities
    raw_caps = parse_corvo_config(raw_yaml)
    print(f"Found {len(raw_caps)} multimodal models in corvo-config")

    # Enrich and filter
    capabilities = enrich_capabilities(raw_caps, shipped_models)
    print(f"Emitting {len(capabilities)} models (intersection with models.json)")

    # Sanity check: if suspiciously few models parsed, abort rather than
    # writing a near-empty file that would wipe the registry.
    MIN_EXPECTED_MODELS = 5
    if len(capabilities) < MIN_EXPECTED_MODELS:
        print(
            f"FATAL: Only {len(capabilities)} models found (minimum {MIN_EXPECTED_MODELS}). "
            "This likely indicates a parse failure or structural change in corvo-config. "
            "Refusing to write model_capabilities.json.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Models in corvo but not shipped
    not_shipped = set(raw_caps.keys()) - shipped_models
    if not_shipped:
        print(f"\nSkipped (not in models.json): {sorted(not_shipped)}")

    # Models shipped but not in corvo multimodal list
    shipped_no_multimodal = shipped_models - set(raw_caps.keys())
    if shipped_no_multimodal:
        print(f"Text-only (no multimodal in corvo): {sorted(shipped_no_multimodal)}")

    # Output
    formatted = json.dumps(capabilities, indent=2, ensure_ascii=False)
    if args.dry_run:
        print(f"\n--- model_capabilities.json ---\n{formatted}")
    else:
        CAPABILITIES_JSON.write_text(formatted + "\n")
        print(f"\nWrote {len(capabilities)} models to {CAPABILITIES_JSON}")


if __name__ == "__main__":
    main()
