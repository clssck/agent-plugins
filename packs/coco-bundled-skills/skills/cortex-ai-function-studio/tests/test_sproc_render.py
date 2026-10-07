# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for create_sproc.py — inline SPROC assembly correctness.

Verifies that when Python source files are concatenated for inline SPROCs,
all names referenced in the code are still defined after inter-file imports
are stripped. Catches bugs where ``import X as Y`` aliases are removed by
the import-stripping regex but ``Y`` is still used in the code.

Run:
    uv run --group test pytest tests/test_create_sproc.py -v
"""

from __future__ import annotations

import ast
import re
import textwrap

import pytest

from snowflake_ai_optimize.core.sproc_render import (
    _INTER_FILE_IMPORT_RE,
    _build_inline_body,
    _load_sproc_config,
    _minify_python,
    _resolve_module_path,
)


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed for unit tests."""
    yield


def _sproc_types() -> list[str]:
    """Return all SPROC types from sproc_config.yaml."""
    return list(_load_sproc_config().keys())


def _unescape_inline_body(body: str) -> str:
    r"""Undo the \x24\x24 escaping applied by _build_inline_body so the
    result is parseable Python.
    """  # noqa: D205
    return body.replace("\\x24\\x24", "$$")


def _collect_defined_names(tree: ast.Module) -> set[str]:
    """Walk an AST and collect all names that are defined (bound)."""
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                defined.add(alias.asname or alias.name)
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.With):
            for item in node.items:
                if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                    defined.add(item.optional_vars.id)
    return defined


def _collect_stripped_aliases(sproc_type: str) -> dict[str, str]:
    """Find all ``X as Y`` aliases inside inter-file imports that get stripped.

    Returns:
        dict mapping alias_name -> original_name

    """
    config = _load_sproc_config()
    cfg = config[sproc_type]
    aliases: dict[str, str] = {}
    for module_path in cfg["sources"]:
        source_path = _resolve_module_path(module_path)
        content = source_path.read_text()
        for match in _INTER_FILE_IMPORT_RE.finditer(content):
            block = match.group(0)
            for m in re.finditer(r"(\w+)\s+as\s+(\w+)", block):
                original, alias = m.group(1), m.group(2)
                aliases[alias] = original
    return aliases


class TestInlineBodyValidity:
    """Verify inlined Python bodies are syntactically valid."""

    @pytest.mark.parametrize("sproc_type", _sproc_types())
    def test_inline_body_parses_as_valid_python(self, sproc_type: str):
        """The inlined Python body must parse without SyntaxError."""
        body, _handler = _build_inline_body(sproc_type)
        body_clean = _unescape_inline_body(body)
        # ast.parse raises SyntaxError if the code is malformed
        ast.parse(body_clean)


class TestInlineHandlerDefined:
    """Verify the handler function exists in the inlined body."""

    @pytest.mark.parametrize("sproc_type", _sproc_types())
    def test_inline_handler_is_defined(self, sproc_type: str):
        """The handler function from sproc_config.yaml must be defined in
        the inlined body.
        """  # noqa: D205
        config = _load_sproc_config()
        handler = config[sproc_type]["handler"]

        body, returned_handler = _build_inline_body(sproc_type)
        assert returned_handler == handler

        body_clean = _unescape_inline_body(body)
        tree = ast.parse(body_clean)
        defined = _collect_defined_names(tree)

        assert handler in defined, (
            f"Handler function '{handler}' for SPROC type '{sproc_type}' "
            f"is not defined in the inlined body"
        )


class TestMinifyPython:
    """Verify AST-based minification preserves semantics."""

    def test_strips_docstrings(self):
        source = '''
def foo():
    """This docstring should be removed."""
    return 42

class Bar:
    """Class docstring."""
    def method(self):
        """Method docstring."""
        pass
'''
        result = _minify_python(source)
        assert "This docstring should be removed" not in result
        assert "Class docstring" not in result
        assert "Method docstring" not in result

    def test_strips_comments(self):
        source = "# This is a comment\nx = 1  # inline comment\n"
        result = _minify_python(source)
        assert "comment" not in result
        assert "x = 1" in result

    def test_preserves_string_literals(self):
        source = 'x = "not a docstring"\ny = f"hello {x}"\n'
        result = _minify_python(source)
        assert "not a docstring" in result

    def test_preserves_runtime_behavior(self):
        source = '''
def add(a, b):
    """Add two numbers."""
    # sum them
    return a + b

result = add(3, 4)
'''
        result = _minify_python(source)
        namespace: dict = {}
        exec(compile(result, "<test>", "exec"), namespace)
        assert namespace["result"] == 7

    def test_empty_body_after_docstring_gets_pass(self):
        source = '''
def placeholder():
    """Only a docstring, no real body."""
'''
        result = _minify_python(source)
        compiled = compile(result, "<test>", "exec")
        exec(compiled)

    def test_indent_compressed_to_one_space_per_level(self):
        """ast.unparse 4-space indent is compressed to 1 space per level."""
        source = """
def outer():
    if True:
        for i in range(3):
            x = i + 1
            if x > 1:
                pass
"""
        result = _minify_python(source)
        lines = result.splitlines()
        # 'if True:' — 1 level deep → 1 leading space
        if_line = next(l for l in lines if l.strip().startswith("if True"))
        assert if_line.startswith(" ") and not if_line.startswith("  "), (
            f"Expected 1-space indent, got: {if_line!r}"
        )
        # 'for i' — 2 levels → 2 leading spaces
        for_line = next(l for l in lines if l.strip().startswith("for i"))
        assert for_line.startswith("  ") and not for_line.startswith("   "), (
            f"Expected 2-space indent, got: {for_line!r}"
        )
        # 'pass' — 4 levels → 4 leading spaces
        pass_line = next(l for l in lines if l.strip() == "pass")
        assert pass_line.startswith("    ") and not pass_line.startswith("     "), (
            f"Expected 4-space indent, got: {pass_line!r}"
        )

    def test_indent_compression_preserves_string_content(self):
        """Spaces inside string literals are not affected by indent compression."""
        source = 'x = "    four leading spaces in string"\n'
        result = _minify_python(source)
        # The string value must be unchanged
        assert "four leading spaces in string" in result
        # Top-level assignment has no leading indent
        assert result.startswith("x =")

    def test_indent_compression_preserves_runtime_behavior(self):
        """Compressed output executes identically to the original."""
        source = """
def compute(n):
    total = 0
    for i in range(n):
        if i % 2 == 0:
            total += i
    return total
"""
        result = _minify_python(source)
        namespace: dict = {}
        exec(compile(result, "<test>", "exec"), namespace)
        assert namespace["compute"](10) == 20  # 0+2+4+6+8

    def test_indent_compression_reduces_size(self):
        """Compression saves ≥8% vs 4-space ast.unparse on deeply nested code.

        The savings scale with nesting depth and line count — exactly the
        profile of the SPROC bundle (deeply nested try/for/if blocks, hundreds
        of lines at 3-6 indent levels).  This fixture has ~100 lines at
        varying depths to give a stable, representative measurement.
        """
        import ast as _ast

        # Representative block: 5 indent levels, many lines per level.
        source = "def run(items, flags, config):"
        for i in range(10):
            new_block = f"""
                for item_{i} in items:
                    if flags.get('enable_{i}', False):
                        try:
                            result = config['{i}'] * item_{i}
                            if result > 0:
                                yield result
                        except KeyError:
                            pass
                """
            source += textwrap.indent(textwrap.dedent(new_block), "    ")

        four_space = _ast.unparse(_ast.parse(source))
        compressed = _minify_python(source)

        four_space_bytes = len(four_space.encode())
        compressed_bytes = len(compressed.encode())
        savings_pct = (four_space_bytes - compressed_bytes) / four_space_bytes * 100

        assert compressed_bytes < four_space_bytes, (
            "Compressed output must be smaller than 4-space ast.unparse output"
        )
        assert savings_pct >= 8, (
            f"Expected ≥8% savings from indent compression, got {savings_pct:.1f}% "
            f"({four_space_bytes} → {compressed_bytes} bytes)"
        )

    @pytest.mark.parametrize("sproc_type", _sproc_types())
    def test_minified_inline_body_compiles(self, sproc_type: str):
        """The minified inline body must still parse as valid Python.

        This is the key integration test — _build_inline_body now calls
        _minify_python, so the full pipeline must produce compilable code.
        """
        body, _handler = _build_inline_body(sproc_type)
        body_clean = _unescape_inline_body(body)
        compile(body_clean, f"<{sproc_type}_inline>", "exec")

    @pytest.mark.parametrize("sproc_type", _sproc_types())
    def test_minification_reduces_size(self, sproc_type: str):
        """Minification should meaningfully reduce the inline body size."""
        config = _load_sproc_config()
        sources = config[sproc_type]["sources"]
        original_size = sum(len(_resolve_module_path(f).read_text()) for f in sources)
        body, _ = _build_inline_body(sproc_type)
        assert len(body) < original_size * 0.75, (
            f"Expected at least 25% size reduction for {sproc_type}, "
            f"got {original_size} -> {len(body)}"
        )


class TestInlineAliasIntegrity:
    """Verify that ``import X as Y`` aliases survive the inlining process.

    When inter-file imports are stripped during inlining, any ``as`` aliases
    are lost. If the code still references the alias name, it will cause a
    NameError at runtime inside Snowflake. This test catches that.
    """

    @pytest.mark.parametrize("sproc_type", _sproc_types())
    def test_inline_body_has_no_dangling_aliases(self, sproc_type: str):
        """Every alias from stripped inter-file imports must still be
        resolvable in the inlined body — either the alias itself is defined,
        or no code references it.
        """  # noqa: D205
        aliases = _collect_stripped_aliases(sproc_type)
        if not aliases:
            pytest.skip(f"No aliased inter-file imports for '{sproc_type}'")

        body, _handler = _build_inline_body(sproc_type)
        body_clean = _unescape_inline_body(body)
        tree = ast.parse(body_clean)
        defined = _collect_defined_names(tree)

        dangling: list[str] = []
        for alias, original in aliases.items():
            # The alias is used in the body (not just in the stripped import)
            alias_used = bool(re.search(rf"\b{alias}\b", body_clean))
            alias_defined = alias in defined

            if alias_used and not alias_defined:
                dangling.append(
                    f"'{alias}' (alias for '{original}') is used in the "
                    f"inlined body but not defined — the stripped import "
                    f"'import {original} as {alias}' created this binding"
                )

        assert not dangling, (
            f"Dangling alias(es) in '{sproc_type}' inline SPROC:\n"
            + "\n".join(f"  - {msg}" for msg in dangling)
            + "\n\nFix: either use the original name directly in the code, "
            "or add an explicit assignment (e.g., "
            f"'{next(iter(aliases.keys()))} = {next(iter(aliases.values()))}') "
            "in the source file."
        )


class TestOptimizeBundleShipsOnlyBodyMode:
    """The inline ``optimize`` bundle must ship ONLY the ``body`` optimize mode.

    This bundle backs ``EXECUTE_AI_FUNCTION_EVAL_OPTS`` and
    ``OPTIMIZE_AI_FUNCTION``. Prompt mode (``gepa/optimize_prompt.py``) and every
    experiment mode (``evolve*`` / ``coco*`` in the ``snowflake-ai-optimize-evolve``
    package, ``body_agent*`` in ``snowflake-ai-optimize-gepa-dev``) are
    deliberately kept out of the ``optimize`` source list in ``sproc_config.yaml``.
    Their handler functions are therefore never concatenated into the bundle, so
    ``register_all()`` can only bind ``body`` (the ``prompt`` registration is a
    guarded import that fails with ``ImportError``/``NameError`` inline) and
    ``resolve_mode()`` rejects every other mode. This test fails loudly if a
    future source-list change silently ships an experimental optimizer to
    customers.
    """

    #: The one production mode that MUST be in the bundle.
    _BODY_MODE_HANDLER = "_body_mode_handler"

    #: Handler function names for every non-body optimize mode. None of these
    #: may be defined in the inline bundle (their source packages/modules are
    #: excluded from the ``optimize`` block of sproc_config.yaml).
    _EXCLUDED_MODE_HANDLERS = (
        "_prompt_mode_handler",  # prompt            (gepa/optimize_prompt.py)
        "_evolve_handler",  # evolve                 (evolve/_registry.py)
        "_evolve_agent_handler",  # evolve_agent
        "_evolve_agent_single_session_handler",  # evolve_agent_single_session
        "_coco_handler",  # coco_one_shot
        "_coco_no_tools_handler",  # coco_no_tools
        "_body_agent_handler",  # body_agent         (gepa_dev/_registry.py)
        "_body_agent_single_session_handler",  # body_agent_single_session
    )

    def _bundle_defined_names(self) -> set[str]:
        body, _handler = _build_inline_body("optimize")
        tree = ast.parse(_unescape_inline_body(body))
        return _collect_defined_names(tree)

    def test_body_mode_handler_is_bundled(self):
        """Body mode must be present — it is the only supported optimize mode."""
        assert self._BODY_MODE_HANDLER in self._bundle_defined_names(), (
            f"'{self._BODY_MODE_HANDLER}' (body mode) is missing from the "
            "inline 'optimize' bundle — the sproc would have no runnable mode"
        )

    def test_non_body_mode_handlers_are_excluded(self):
        """Prompt and all experiment-mode handlers must NOT reach the bundle."""
        defined = self._bundle_defined_names()
        leaked = [h for h in self._EXCLUDED_MODE_HANDLERS if h in defined]
        assert not leaked, (
            "EXECUTE_AI_FUNCTION_EVAL_OPTS / OPTIMIZE_AI_FUNCTION must ship only "
            f"the 'body' optimize mode, but non-body mode handler(s) leaked into "
            f"the inline bundle: {leaked}. Remove the offending source from the "
            "'optimize' block in templates/sproc_config.yaml."
        )
