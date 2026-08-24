# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""SQL and DDL manipulation utilities for Snowflake AI functions."""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snowflake.snowpark import Session

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

# Default language reported/assumed for AI functions (SQL scalar UDFs).
_FUNCTION_LANGUAGE_DEFAULT = "SQL"

# argument_mapping key that denotes a positional argument (1-indexed). An
# unquoted Snowflake identifier cannot start with "$", so this namespace never
# collides with a named-argument (parameter) name.
POSITIONAL_ARG_RE = re.compile(r"^\$(\d+)$")


def build_temp_function_name(function_name: str, prefix: str) -> str:
    """Build a thread-safe temporary function name from a fully qualified function name.

    Args:
        function_name: Fully qualified function name (DB.SCHEMA.FUNC or
            DB.SCHEMA.FUNC(VARCHAR, ...)).
        prefix: Prefix for the temp function (e.g., ``"__OPT_TEMP"``
            or ``"__OPT_TEST"``).

    Returns:
        Fully qualified temp function name like ``DB.SCHEMA.__OPT_TEMP_FUNC_<tid>``.
        For an unqualified ``function_name`` (fewer than three dotted parts —
        e.g. a builtin AI function name like ``AI_COMPLETE``), returns an
        unqualified ``<prefix>_<func>_<tid>`` label. The temp name is advisory
        (used for tracing/labels, not to create a database object), so a
        session-relative label is sufficient.

    """
    import threading

    base_name = function_name.split("(")[0] if "(" in function_name else function_name
    parts = base_name.split(".")
    tid = threading.current_thread().ident or 0
    if len(parts) >= 3:
        db, schema, func = parts[0], parts[1], parts[2]
        return f"{db}.{schema}.{prefix}_{func}_{tid}"
    func = parts[-1]
    return f"{prefix}_{func}_{tid}"


def quote_identifier(name: str) -> str:
    """Quote a Snowflake identifier for dynamic SQL usage."""
    return '"' + str(name).replace('"', '""') + '"'


def escape_sql_string(s: str) -> str:
    r"""Escape a string for use inside a Snowflake SQL single-quoted literal.

    Snowflake string literals process backslash escape sequences (``\\"`` ->
    ``"``, ``\\n`` -> newline, etc.), so a literal backslash must be doubled
    or it silently mangles the value at parse time.  This bites hardest on
    embedded JSON: ``json.dumps`` emits ``\\"`` for a quoted substring (e.g. an
    output-field ``description`` containing ``"``), and without backslash
    doubling Snowflake collapses ``\\"`` -> ``"`` before ``PARSE_JSON`` runs,
    producing ``Error parsing JSON: missing comma`` at execution time.

    Escape order matters: double backslashes FIRST, then single quotes, so the
    quote-doubling never re-doubles a backslash we just added.

    Args:
        s: The string to escape.

    Returns:
        The escaped string (without surrounding quotes).

    """
    return s.replace("\\", "\\\\").replace("'", "''")


@dataclass(frozen=True)
class FunctionArg:
    """A single function parameter: its declared name and SQL type.

    ``name`` is un-quoted (``""`` escapes collapsed); ``type`` is the SQL type
    text as reported by ``DESCRIBE FUNCTION`` (e.g. ``VARCHAR``, ``NUMBER(38,0)``,
    ``FILE``, ``ARRAY``).
    """

    name: str
    type: str


def _split_signature_params(signature: str) -> list[str]:
    """Split a function signature into its raw per-parameter substrings.

    Accepts the ``signature`` value from ``DESCRIBE FUNCTION`` (outer parens
    optional). Splits only on paren-depth-0 commas so parametrized types such
    as ``NUMBER(10,2)`` stay intact. Returns ``[]`` for a no-argument signature.
    """
    s = signature.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    if not s.strip():
        return []

    raw_params: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            raw_params.append("".join(current))
            current = []
        else:
            current.append(ch)
    if "".join(current).strip():
        raw_params.append("".join(current))

    return [p.strip() for p in raw_params if p.strip()]


def _split_param_name_and_type(param: str) -> tuple[str, str]:
    """Split one ``<name> <type>`` parameter into ``(name, type)``.

    Handles double-quoted names with ``""`` escapes. The type is the remaining
    text after the name (may contain spaces/parens, e.g. ``NUMBER(38,0)``).
    """
    param = param.strip()
    if param.startswith('"'):
        # Quoted name: read to the closing quote, honoring "" escapes.
        j = 1
        while j < len(param):
            if param[j] == '"':
                if j + 1 < len(param) and param[j + 1] == '"':
                    j += 2
                    continue
                break
            j += 1
        name = param[1:j].replace('""', '"')
        type_str = param[j + 1 :].strip()
    else:
        bits = param.split(None, 1)
        name = bits[0]
        type_str = bits[1].strip() if len(bits) > 1 else ""
    return name, type_str


def parse_signature_param_names(signature: str) -> list[str]:
    """Return the ordered parameter names from a function signature string.

    Accepts the ``signature`` value returned by ``DESCRIBE FUNCTION`` (e.g.
    ``(a NUMBER(38,0), b NUMBER(38,0))``) — outer parentheses optional — and
    returns each parameter's name in declaration order, without surrounding
    double quotes. Only paren-depth-0 commas separate parameters, so types that
    contain commas (e.g. ``NUMBER(10,2)``) are handled correctly. Returns ``[]``
    for a no-argument signature.
    """
    return [
        _split_param_name_and_type(p)[0] for p in _split_signature_params(signature)
    ]


def parse_signature_args(signature: str) -> list[FunctionArg]:
    """Parse a ``DESCRIBE FUNCTION`` ``signature`` into ordered ``FunctionArg``s.

    e.g. ``(input_text VARCHAR, img FILE)`` ->
    ``[FunctionArg("input_text", "VARCHAR"), FunctionArg("img", "FILE")]``.
    Outer parentheses optional; parametrized types (``NUMBER(38,0)``) are kept
    intact. Returns ``[]`` for a no-argument signature.
    """
    args: list[FunctionArg] = []
    for param in _split_signature_params(signature):
        name, type_str = _split_param_name_and_type(param)
        args.append(FunctionArg(name=name, type=type_str))
    return args


def resolve_param_name(key: str, ddl_param_names: list[str]) -> str:
    """Resolve an ``argument_mapping`` key to an AI-function parameter name.

    A ``$N`` key (1-indexed) resolves to the Nth parameter name from the
    function's DDL. A named key is matched case-insensitively against the DDL
    parameter names and resolved to the DDL's exact casing (e.g. ``text`` ->
    ``TEXT``), so callers that quote the resolved name (``col AS "TEXT"``) align
    with how the function body references the parameter — an unquoted ``TEXT``
    in the body folds to ``TEXT`` and matches. A named key with no
    case-insensitive match is returned unchanged.
    """
    m = POSITIONAL_ARG_RE.match(key)
    if not m:
        for name in ddl_param_names:
            if name.casefold() == key.casefold():
                return name
        return key
    idx = int(m.group(1))
    if idx < 1 or idx > len(ddl_param_names):
        raise ValueError(
            f"Positional argument '{key}' is out of range for a function with "
            f"{len(ddl_param_names)} parameter(s)"
        )
    return ddl_param_names[idx - 1]


def _extract_balanced_paren_content(text: str) -> str:
    """Extract the content inside the outermost parentheses, handling nesting.

    Used to pull the type list out of a ``SHOW FUNCTIONS`` ``arguments`` value
    such as ``FUNC(VARCHAR, ARRAY) RETURN VARCHAR``.
    """
    start = text.find("(")
    if start < 0:
        raise ValueError(f"Could not parse function signature: {text}")
    depth = 0
    content_start = -1
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == "(":
            depth += 1
            if depth == 1:
                content_start = idx + 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and content_start >= 0:
                return text[content_start:idx]
    raise ValueError(f"Could not parse function signature: {text}")


def _resolve_typed_signature(session: "Session", function_name: str) -> tuple[str, str]:
    """Resolve a function name to its base name and typed signature.

    ``function_name`` may carry an overload signature
    (``DB.SCHEMA.FUNC(VARCHAR, ARRAY)``). Uses ``SHOW FUNCTIONS`` to find the
    (possibly overloaded) function and returns
    ``(base_name, "DB.SCHEMA.FUNC(TYPE, ...)")`` — the typed signature that
    ``DESCRIBE FUNCTION`` expects.
    """
    base_name = function_name
    provided_signature = None
    if "(" in function_name:
        paren_idx = function_name.index("(")
        base_name = function_name[:paren_idx]
        provided_signature = function_name[paren_idx:]

    parts = base_name.split(".")
    if len(parts) != 3:
        raise ValueError(
            f"Function name must be fully qualified (DB.SCHEMA.FUNC): {function_name}"
        )
    db, schema, func = parts

    rows = session.sql(
        f"SHOW FUNCTIONS LIKE '{func}' IN SCHEMA {db}.{schema}"
    ).collect()
    if not rows:
        raise ValueError(f"Function not found: {function_name}")

    if provided_signature and len(rows) > 1:
        target_sig = f"{func}{provided_signature}"
        matching = next(
            (r for r in rows if r["arguments"].upper() == target_sig.upper()), None
        )
        if matching is None:
            raise ValueError(f"No function overload matches signature: {function_name}")
        arguments = matching["arguments"]
    else:
        arguments = rows[0]["arguments"]

    param_types = _extract_balanced_paren_content(arguments)
    return base_name, f"{base_name}({param_types})"


@dataclass
class FunctionDefinition:
    """A Snowflake function modeled from ``DESCRIBE FUNCTION`` output.

    Replaces ad-hoc regex parsing of raw DDL text with structured fields.
    ``body`` is the raw function body exactly as ``DESCRIBE FUNCTION`` returns
    it — un-escaped and without ``$$``/``'...'`` wrapping. ``properties`` keeps
    every DESCRIBE row (lowercased keys) so :meth:`render_create_ddl` can
    reproduce clauses not surfaced as explicit fields.
    """

    name: str  # DB.SCHEMA.FUNC base name (no parameter list)
    args: list[FunctionArg]
    returns: str
    language: str
    body: str
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def arg_names(self) -> list[str]:
        return [a.name for a in self.args]

    @property
    def arg_types(self) -> list[str]:
        return [a.type for a in self.args]

    @property
    def signature(self) -> str:
        """Parenthesized ``(name type, ...)`` as DESCRIBE reported it."""
        raw = self.properties.get("signature", "").strip()
        if raw:
            return raw if raw.startswith("(") else f"({raw})"
        inner = ", ".join(f"{a.name} {a.type}".strip() for a in self.args)
        return f"({inner})"

    @property
    def typed_signature(self) -> str:
        """``DB.SCHEMA.FUNC(TYPE, ...)`` — types only; a DESCRIBE/SHOW target."""
        return f"{self.name}({', '.join(self.arg_types)})"

    def render_create_ddl(
        self,
        *,
        name: str | None = None,
        temporary: bool = False,
        or_replace: bool = True,
        body: str | None = None,
        returns: str | None = None,
    ) -> str:
        """Emit a runnable ``CREATE FUNCTION`` statement from this definition.

        Every field defaults from ``self``; override ``name`` (e.g. a temp
        function name), ``temporary``, ``body`` (e.g. an optimized body), or
        ``returns`` as needed. Null-handling and volatility are reproduced when
        ``DESCRIBE`` surfaced them. The body is emitted between ``$$``
        delimiters, so no single-quote escaping is required.
        """
        fn_name = name or self.name
        ret = returns if returns is not None else self.returns
        fn_body = body if body is not None else self.body
        lang = self.language or _FUNCTION_LANGUAGE_DEFAULT

        header = "CREATE "
        if or_replace:
            header += "OR REPLACE "
        if temporary:
            header += "TEMPORARY "
        header += f"FUNCTION {fn_name}{self.signature}"

        lines = [header, f"RETURNS {ret}", f"LANGUAGE {lang}"]
        null_handling = self.properties.get("null handling", "").strip().upper()
        if null_handling in {"CALLED ON NULL INPUT", "RETURNS NULL ON NULL INPUT"}:
            lines.append(null_handling)
        volatility = self.properties.get("volatility", "").strip().upper()
        if volatility in {"VOLATILE", "IMMUTABLE"}:
            lines.append(volatility)
        lines.append("AS")
        lines.append(f"$$\n{fn_body}\n$$")
        return "\n".join(lines)


def build_query_text_function_def(
    query_text: str,
    input_columns: list,
    *,
    name: str,
    returns: str = "VARIANT",
) -> FunctionDefinition:
    """Synthesize a :class:`FunctionDefinition` for a builtin AI function.

    The optimizer machinery (GEPA candidate generation, ``TempAIFunction``
    inline evaluation) is built around a ``FunctionDefinition`` whose ``body``
    is the AI function's SQL body and whose ``args`` are its parameters — all
    normally read from ``DESCRIBE FUNCTION``. A **builtin** AI function has no
    such object; it is supplied inline as a ``query_text`` scalar expression
    (e.g. ``AI_COMPLETE('llama3.1-70b', 'Answer: ' || question)``) that
    references dataset columns directly.

    This models that expression as the function ``body`` and the dataset
    columns it consumes as ``VARCHAR`` parameters, so every optimize mode can
    seed its candidate program from the ``query_text`` without a DDL round-trip.
    The columns bind by name (identity) at candidate-evaluation time, matching
    how the ``query_text`` references them. ``name`` is a fully-qualified
    placeholder (``DB.SCHEMA.FUNC``) used only for temp-object naming/tracing.
    """
    base_name = name.split("(")[0] if "(" in name else name
    # Args are typed VARCHAR: an AI_COMPLETE prompt is text, so the columns a
    # query_text feeds it are text. (If a query_text ever references an
    # ARRAY/OBJECT/VARIANT column directly, semi-structured PARSE_JSON wrapping
    # would need real column types threaded in here — not supported today.)
    args = [
        FunctionArg(name=str(c).strip('"').strip("'"), type="VARCHAR")
        for c in input_columns
    ]
    return FunctionDefinition(
        name=base_name,
        args=args,
        returns=returns,
        language=_FUNCTION_LANGUAGE_DEFAULT,
        body=query_text,
        properties={},
    )


def describe_function(session: "Session", function_name: str) -> FunctionDefinition:
    """Introspect a Snowflake function via ``DESCRIBE FUNCTION``.

    Resolves ``function_name`` (optionally carrying an overload signature such
    as ``DB.SCHEMA.FUNC(VARCHAR, ARRAY)``) to a typed signature via
    ``SHOW FUNCTIONS``, runs ``DESCRIBE FUNCTION``, and returns a structured
    :class:`FunctionDefinition`.

    ``DESCRIBE`` is used instead of fetching the full DDL because it needs only
    ``USAGE`` (not ownership) on the function, so caller's-rights stored
    procedures can introspect functions they do not own.

    Raises:
        ValueError: if the function is not found, or ``DESCRIBE`` returns no
            readable ``body`` (e.g. a SECURE or non-SQL function).
    """
    base_name, typed_signature = _resolve_typed_signature(session, function_name)
    rows = session.sql(f"DESCRIBE FUNCTION {typed_signature}").collect()
    if not rows:
        raise ValueError(f"DESCRIBE FUNCTION returned no rows for {typed_signature}")

    props: dict[str, str] = {}
    for r in rows:
        key = str(r[0]).strip().lower()
        val = r[1]
        props[key] = "" if val is None else str(val)

    body = props.get("body", "")
    if not body.strip():
        raise ValueError(
            f"DESCRIBE FUNCTION did not return a readable body for {typed_signature}. "
            "The function may be SECURE or implemented in a non-SQL language, so its "
            "definition cannot be introspected."
        )

    return FunctionDefinition(
        name=base_name,
        args=parse_signature_args(props.get("signature", "")),
        returns=props.get("returns", ""),
        language=props.get("language", _FUNCTION_LANGUAGE_DEFAULT),
        body=body,
        properties=props,
    )


def validate_dotted_identifier(
    name: str,
    *,
    kind: str = "identifier",
    min_parts: int = 1,
    max_parts: int = 3,
    quote: bool = False,
) -> str:
    """Validate a dotted Snowflake identifier for safe SQL interpolation.

    Splits *name* on ``.`` (respecting double-quoted segments) and validates
    each part as either a bare identifier matching ``IDENTIFIER_RE`` or a
    properly-escaped double-quoted identifier.

    Args:
        name: The identifier string (e.g. ``DB.SCHEMA.FUNC`` or ``"my-db"."schema"``).
        kind: Label used in error messages (e.g. ``"experiment_name"``).
        min_parts: Minimum number of dot-separated parts (default 1).
        max_parts: Maximum number of dot-separated parts (default 3).
        quote: If True, return the fully quoted form (``"DB"."SCHEMA"."FUNC"``).
            If False, return the stripped input unchanged.

    Returns:
        The quoted identifier string when *quote* is True, otherwise the
        stripped input.

    Raises:
        ValueError: On empty input, unterminated quotes, invalid part count,
            or invalid identifier characters.

    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{kind} cannot be empty")

    raw = name.strip()

    # Split on '.' respecting double-quoted segments
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in raw:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "." and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))

    if in_quotes:
        raise ValueError(f"Unterminated quoted {kind}: {raw!r}")

    if not min_parts <= len(parts) <= max_parts:
        raise ValueError(
            f"{kind} must be a {min_parts}-{max_parts} part identifier "
            f"(e.g., DB.SCHEMA.NAME), got {len(parts)} parts: {raw!r}"
        )

    quoted_parts: list[str] = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            raise ValueError(f"Empty identifier part in {kind}: {raw!r}")

        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 1:
            # Quoted identifier — validate interior escaping
            inner = stripped[1:-1]
            i = 0
            while i < len(inner):
                if inner[i] == '"':
                    if i + 1 < len(inner) and inner[i + 1] == '"':
                        i += 2
                        continue
                    raise ValueError(
                        f"Invalid quoted identifier (unescaped quote) in "
                        f"{kind}: {stripped!r}"
                    )
                i += 1
            # Unescape doubled quotes for the logical name
            inner = inner.replace('""', '"')
        elif IDENTIFIER_RE.match(stripped):
            inner = stripped
        else:
            raise ValueError(
                f"Invalid identifier {stripped!r} in {kind} {raw!r}. "
                f"Each part must be alphanumeric/underscore or double-quoted."
            )

        if quote:
            quoted_parts.append(quote_identifier(inner))

    if quote:
        return ".".join(quoted_parts)
    return raw
