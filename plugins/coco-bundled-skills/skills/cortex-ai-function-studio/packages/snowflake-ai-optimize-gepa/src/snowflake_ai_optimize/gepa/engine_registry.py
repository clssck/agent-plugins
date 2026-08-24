# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Pluggable engine registry for GEPA optimization.

Decouples engine dispatch from ``snow_gepa_optimize_anything.py`` so that
research engines can be developed and benchmarked without becoming
dependency debt in the shipped production skill.

The production skill only registers ``"default"`` (no engine patching).
Research engines are registered at runtime by importing
``dev/engines/register_all.py`` — which the benchmark framework does
automatically but the shipped skill does not.

Usage::

    from snowflake_ai_optimize.gepa.engine_registry import resolve_engine

    engine_ctx, pool_ctx = resolve_engine(
        engine_name, session=session, models=models,
        max_concurrency=max_concurrency,
    )
    with pool_ctx, engine_ctx:
        ...  # run optimization
"""

from __future__ import annotations

import contextlib
import importlib
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EngineSpec:
    """Specification for a pluggable GEPA engine.

    Attributes:
        module_path: Python module name containing the engine class
            (e.g., ``"snow_gepa_adaptive_engine"``).
        class_name: Name of the engine class within the module
            (e.g., ``"AdaptiveSamplingEngine"``).
        setup: Optional callable that returns ``(engine_ctx, pool_ctx)``
            context managers. Receives keyword arguments:
            ``session``, ``models``, ``max_concurrency``.
            When None, ``(patched_engine(cls), nullcontext())`` is used.

    """

    module_path: str
    class_name: str
    setup: (
        Callable[..., tuple[AbstractContextManager, AbstractContextManager]] | None
    ) = None


_REGISTRY: dict[str, EngineSpec] = {}


def register_engine(name: str, spec: EngineSpec) -> None:
    """Register an engine by name.

    Overwrites any existing registration for the same name.
    """
    _REGISTRY[name] = spec
    logger.debug(f"Registered engine: {name} -> {spec.module_path}.{spec.class_name}")


def available_engines() -> list[str]:
    """Return sorted list of currently registered engine names."""
    return sorted(_REGISTRY.keys())


def resolve_engine(
    name: str,
    *,
    session: Any = None,
    models: list[str] | None = None,
    max_concurrency: int = 8,
) -> tuple[AbstractContextManager, AbstractContextManager]:
    """Resolve an engine name to ``(engine_ctx, pool_ctx)`` context managers.

    Args:
        name: Engine name (must be registered).
        session: Active Snowpark session (passed to engine setup if needed).
        models: List of model names being optimized.
        max_concurrency: Max concurrent I/O operations.

    Returns:
        Tuple of context managers: ``engine_ctx`` patches the GEPAEngine
        class for the duration of the block; ``pool_ctx`` manages any
        concurrency resources.

    Raises:
        ValueError: If the engine name is not registered.

    """
    if name not in _REGISTRY:
        registered = ", ".join(available_engines()) or "(none)"
        raise ValueError(f"Unknown engine: '{name}'. Available: {registered}")

    spec = _REGISTRY[name]

    if spec.setup is not None:
        return spec.setup(
            session=session, models=models, max_concurrency=max_concurrency
        )

    # Fallback for research engines registered without a setup function.
    # gepa.engine is not included in the inline optimize SPROC bundle, so this
    # path is only reachable outside the SPROC (e.g. benchmark / dev mode).
    from snowflake_ai_optimize.gepa.engine import patched_engine

    module = importlib.import_module(spec.module_path)
    cls = getattr(module, spec.class_name)
    return patched_engine(cls), contextlib.nullcontext()


# ---------------------------------------------------------------------------
# Built-in registration: "default" engine (no patching, stock GEPAEngine)
# ---------------------------------------------------------------------------

register_engine(
    "default",
    EngineSpec(
        module_path="snowflake_ai_optimize.gepa.engine",
        class_name="SnowGEPAEngine",
        setup=lambda **_kwargs: (contextlib.nullcontext(), contextlib.nullcontext()),
    ),
)
