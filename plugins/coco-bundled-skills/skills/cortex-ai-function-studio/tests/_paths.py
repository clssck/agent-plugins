# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Shared path resolution for e2e tests.

Provides filesystem path constants and a module-path resolver so e2e tests
can locate source files (for stage uploads) and scripts (for subprocess calls)
after the namespace package refactoring.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = PROJECT_ROOT / "packages"
HANDLERS_DIR = PROJECT_ROOT / "handlers"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

_PACKAGE_ROOTS: dict[str, Path] = {
    "snowflake_ai_optimize.core": (
        PACKAGES_DIR
        / "snowflake-ai-optimize-core"
        / "src"
        / "snowflake_ai_optimize"
        / "core"
    ),
    "snowflake_ai_optimize.gepa": (
        PACKAGES_DIR
        / "snowflake-ai-optimize-gepa"
        / "src"
        / "snowflake_ai_optimize"
        / "gepa"
    ),
    "snowflake_ai_optimize.synthetic": (
        PACKAGES_DIR
        / "snowflake-ai-optimize-synthetic"
        / "src"
        / "snowflake_ai_optimize"
        / "synthetic"
    ),
}


def resolve_module_path(module_path: str) -> Path:
    """Resolve a dotted module path to its .py file on disk.

    Used by e2e tests to upload source files to Snowflake stages.

    Handles:
    - snowflake_ai_optimize.core.session -> packages/.../core/session.py
    - snowflake_ai_optimize.gepa.adapter -> packages/.../gepa/adapter.py
    - handlers.evaluate_handler -> handlers/evaluate_handler.py
    - models.json -> packages/.../core/models.json (special case)
    """
    # Special case: models.json
    if module_path == "models.json":
        return _PACKAGE_ROOTS["snowflake_ai_optimize.core"] / "models.json"

    if module_path.startswith("handlers."):
        rel = module_path[len("handlers.") :].replace(".", "/") + ".py"
        return HANDLERS_DIR / rel

    for prefix in sorted(_PACKAGE_ROOTS, key=len, reverse=True):
        if module_path.startswith(prefix + "."):
            remainder = module_path[len(prefix) + 1 :]
            rel = remainder.replace(".", "/") + ".py"
            return _PACKAGE_ROOTS[prefix] / rel

    raise ValueError(f"Cannot resolve module path: {module_path!r}")
