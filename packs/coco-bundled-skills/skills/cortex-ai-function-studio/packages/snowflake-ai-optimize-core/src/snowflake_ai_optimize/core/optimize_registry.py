# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Pluggable mode registry for GEPA optimization.

Decouples mode dispatch from ``snow_gepa_optimize.py`` so that
research/experiment modes can be developed and benchmarked without becoming
dependency debt in the shipped production skill.

The production skill only registers ``"prompt"`` and ``"body"`` (the two
standard modes exposed via ``OPTIMIZE_AI_FUNCTION``).  Experiment modes
(``body_agent``, ``body_agent_single_session``, ``evolve``, ``evolve_agent``,
``coco_one_shot``) are registered at runtime by importing
``dev/modes/register_all.py`` — which the benchmark framework does
automatically but the shipped skill does not.

Usage::

    from snowflake_ai_optimize.core.optimize_registry import resolve_mode, register_mode

    handler = resolve_mode(optimize_mode)
    return handler(**kwargs)
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_MODE_REGISTRY: dict[str, Callable[..., dict]] = {}


def register_mode(name: str, fn: Callable[..., dict]) -> None:
    """Register a mode handler by name.

    Overwrites any existing registration for the same name.
    """
    _MODE_REGISTRY[name] = fn
    logger.debug("Registered optimize mode: %s", name)


def available_modes() -> list[str]:
    """Return sorted list of currently registered mode names."""
    return sorted(_MODE_REGISTRY.keys())


def resolve_mode(name: str) -> Callable[..., dict]:
    """Resolve a mode name to its handler callable.

    Args:
        name: Mode name (must be registered).

    Returns:
        The handler callable registered for the mode.

    Raises:
        ValueError: If the mode name is not registered, with a clear message
            listing the available modes.

    """
    if name not in _MODE_REGISTRY:
        available = ", ".join(f"'{m}'" for m in available_modes()) or "(none)"
        raise ValueError(f"Unknown optimize_mode: {name!r}.  Available: {available}")
    return _MODE_REGISTRY[name]
