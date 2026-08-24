# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Production mode registration for the GEPA package.

Registers the ``"body"`` and ``"prompt"`` optimize modes into the core
mode registry. Called by ``gepa/__init__.py`` on package import.
"""

from __future__ import annotations

from snowflake_ai_optimize.core.optimize_registry import register_mode


def register_all() -> None:
    """Register production body + prompt modes. Idempotent.

    Prompt mode is optional — it lives in ``optimize_prompt.py`` which is
    excluded from the inline SPROC bundle to keep the task definition under
    Snowflake's size limit.  When the module is unavailable (inline deploy),
    only body mode is registered.
    """
    from snowflake_ai_optimize.gepa.optimize_body import _body_mode_handler

    register_mode("body", _body_mode_handler)

    try:
        from snowflake_ai_optimize.gepa.optimize_prompt import _prompt_mode_handler

        register_mode("prompt", _prompt_mode_handler)
    except (ImportError, NameError):
        pass  # prompt mode unavailable in inline/bundled deployment


# Auto-register when this module is loaded.  In package mode this is
# triggered by gepa/__init__.py.  In inline SPROC mode the bundler
# concatenates this file directly, so the module-level call ensures
# modes are registered before the handler runs.
register_all()
