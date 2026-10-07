# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""User- vs internal-error taxonomy for the eval/optimize surfacing path.

Every failure the eval/optimize SPROC surfaces is one of two kinds:

* :class:`UserError` — caller-actionable (bad spec / input / config). The
  message is shown to the customer verbatim so they can fix it.
* :class:`InternalError` — not caller-actionable (a bug, or a Snowflake-side
  failure). The customer sees a generic "system error" and the detail routes
  to a Snowflake incident instead.

Code raises these explicitly at the site that knows the intent. For the many
legacy raises that don't yet, :func:`classify` supplies a safe fallback so the
recorded run always carries an ``error_type`` and unexpected exceptions default
to *internal* (fire an incident) rather than blaming the customer.

The translation from these portable exceptions to the runtime ``_snowflake``
exception types happens only at the SPROC boundary (see
``sproc_decorators.surface_sproc_error``); this module stays import-free of
``_snowflake`` so it runs unchanged in local tests.
"""

from __future__ import annotations

from typing import Literal

ErrorType = Literal["user", "internal"]


class UserError(Exception):
    """A caller-actionable error — surfaced to the customer verbatim."""


class InternalError(Exception):
    """A non-actionable error (a bug, or a Snowflake-side failure).

    Surfaced as a generic system error plus an incident, not the raw message.
    """


def classify(exc: BaseException) -> ErrorType:
    """Map an exception to its surfacing kind.

    Explicit :class:`UserError` / :class:`InternalError` are authoritative.
    Builtin ``ValueError`` maps to ``"user"`` (the dominant validation-raise in
    this codebase). Everything else — including any unexpected/surprise
    exception — maps to ``"internal"``: an exception nobody explicitly raised is
    more likely a bug than validated input, so it should fire an incident rather
    than be attributed to the caller.
    """
    if isinstance(exc, UserError):
        return "user"
    if isinstance(exc, InternalError):
        return "internal"
    if isinstance(exc, ValueError):
        return "user"
    return "internal"


def incident_signature(phase: str) -> str:
    """Build a stable, low-cardinality Crash Manager signature.

    Crash Manager buckets incidents into JIRA tickets by this string, so it must
    stay low-cardinality: keep high-cardinality detail (experiment name, ids,
    row counts) OUT of the signature and in the error message. ``phase`` is a
    stable label such as a handler name.
    """
    cleaned = "".join(c if c.isalnum() else "_" for c in phase).strip("_").upper()
    return f"CAIFS_INCIDENT_{cleaned or 'UNKNOWN'}"
