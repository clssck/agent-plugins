# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""SPROC DDL rendering for AI function stored procedures.

Stateless module that renders Jinja2 templates into CREATE PROCEDURE DDL.
Handles inline Python bundling (AST minification, import stripping,
source concatenation) and stage-based IMPORTS clause generation.

No session or IO dependencies beyond reading templates and source files
from disk.
"""

from __future__ import annotations

import ast
import base64
import functools
import re
import zlib
from pathlib import Path

import yaml
from jinja2 import Template

from snowflake_ai_optimize.core.sql_utils import validate_dotted_identifier

SPROC_TEMPLATES = {
    "optimize": "optimize_sproc.sql.j2",
    "evaluate": "evaluate_sproc.sql.j2",
    "synthetic": "synthetic_data_sproc.sql.j2",
    "optimize_async": "optimize_async_sproc.sql.j2",
    "evaluate_async": "evaluate_async_sproc.sql.j2",
}

WORKSPACE_ROOT = Path(__file__).resolve().parents[5]  # core/ → ... → project root
PACKAGES_DIR = WORKSPACE_ROOT / "packages"
HANDLERS_DIR = WORKSPACE_ROOT / "handlers"
TEMPLATES_DIR = WORKSPACE_ROOT / "templates"

# Map package prefixes to their source roots.
_PACKAGE_ROOTS: dict[str, Path] = {
    "snowflake_ai_optimize.core": PACKAGES_DIR
    / "snowflake-ai-optimize-core"
    / "src"
    / "snowflake_ai_optimize"
    / "core",
    "snowflake_ai_optimize.gepa": PACKAGES_DIR
    / "snowflake-ai-optimize-gepa"
    / "src"
    / "snowflake_ai_optimize"
    / "gepa",
    "snowflake_ai_optimize.synthetic": PACKAGES_DIR
    / "snowflake-ai-optimize-synthetic"
    / "src"
    / "snowflake_ai_optimize"
    / "synthetic",
}

_INTER_FILE_IMPORT_RE = re.compile(
    r"^\s*from\s+(?:"
    r"snowflake_ai_optimize(?:\.\w+)*"
    r"|handlers(?:\.\w+)*"
    r")\s+import\s+"
    r"(?:\([^)]*\)|[^\n]+)",
    re.MULTILINE,
)


def get_template_path(sproc_type: str) -> Path:
    """Get the path to the SQL template file."""
    template_file = SPROC_TEMPLATES.get(sproc_type)
    if not template_file:
        raise ValueError(
            f"Unknown SPROC type: '{sproc_type}'. "
            f"Available: {list(SPROC_TEMPLATES.keys())}"
        )
    return TEMPLATES_DIR / template_file


def render_sproc_sql(
    sproc_type: str,
    database: str,
    schema: str,
    stage_name: str = "",
    *,
    anonymous: bool = False,
    inline: bool = False,
    proc_name: str = "OPTIMIZE_AI_FUNCTION",
    extra_imports: list[str] | None = None,
    handler: str | None = None,
) -> str:
    """Render the SPROC SQL from a Jinja2 template.

    Args:
        sproc_type: Type of SPROC ('optimize', 'evaluate', 'synthetic', etc.)
        database: Database name.
        schema: Schema name.
        stage_name: Stage name (required unless inline=True).
        anonymous: Output anonymous SPROC format (WITH...AS PROCEDURE).
        inline: Embed Python source directly instead of using IMPORTS.
        proc_name: Name for the stored procedure.
        extra_imports: Additional stage paths for the IMPORTS clause.
        handler: Override the HANDLER clause value.

    Returns:
        Rendered SQL string.

    """
    validate_dotted_identifier(database, kind="database", max_parts=1)
    validate_dotted_identifier(schema, kind="schema", max_parts=1)
    if not inline:
        validate_dotted_identifier(stage_name, kind="stage_name", max_parts=1)
    if not anonymous:
        validate_dotted_identifier(proc_name, kind="proc_name", max_parts=1)

    template_path = get_template_path(sproc_type)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    inline_body = ""
    inline_handler = ""
    if inline:
        raw_body, inline_handler = _build_inline_body(sproc_type)
        inline_body = _compress_inline_body(raw_body)

    vendor_dirs: list[str] = []
    config = _load_sproc_config()
    sproc_cfg = config.get(sproc_type, {})
    if not inline:
        vendor_dirs = _vendor_dir_names(sproc_cfg)

    template_content = template_path.read_text()
    template = Template(template_content)

    return str(
        template.render(
            database=database,
            schema=schema,
            stage_name=stage_name,
            anonymous=anonymous,
            inline=inline,
            inline_body=inline_body,
            inline_handler=inline_handler,
            proc_name=proc_name,
            vendor_dirs=vendor_dirs,
            extra_imports=extra_imports or [],
            handler=handler,
        )
    )


@functools.lru_cache
def _load_sproc_config() -> dict:
    """Load sproc_config.yaml."""
    config_path = TEMPLATES_DIR / "sproc_config.yaml"
    with open(config_path) as f:
        result: dict = yaml.safe_load(f)
    return result


def _vendor_dir_names(sproc_cfg: dict) -> list[str]:
    """Return imports_dirs from the SPROC config, filtered to those that exist."""
    out: list[str] = []
    evolve_src = (
        PACKAGES_DIR
        / "snowflake-ai-optimize-evolve"
        / "src"
        / "snowflake_ai_optimize"
        / "evolve"
    )
    for top in sproc_cfg.get("imports_dirs", []):
        if (evolve_src / top).exists():
            out.append(top)
    return out


def _resolve_module_path(module_path: str) -> Path:
    """Resolve a dotted module path to its .py file on disk."""
    if module_path.startswith("handlers."):
        rel = module_path[len("handlers.") :].replace(".", "/") + ".py"
        return HANDLERS_DIR / rel

    for prefix in sorted(_PACKAGE_ROOTS, key=len, reverse=True):
        if module_path.startswith(prefix + "."):
            remainder = module_path[len(prefix) + 1 :]
            rel = remainder.replace(".", "/") + ".py"
            return _PACKAGE_ROOTS[prefix] / rel

    raise ValueError(
        f"Cannot resolve module path: {module_path!r}. "
        f"Known prefixes: {sorted(_PACKAGE_ROOTS)}"
    )


def _minify_python(source: str) -> str:
    """Strip docstrings/comments and compress indentation via AST round-trip.

    Pass 1 — AST round-trip: drops comments, removes docstrings, produces
    uniform 4-space indented output.

    Pass 2 — indent compression (4 spaces → 1 space per level): safe because
    ast.unparse never embeds real newlines inside string literals.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module
        ):
            continue
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)
            if not node.body:
                node.body.append(ast.Pass())
    unparsed = ast.unparse(tree)
    lines = unparsed.splitlines()
    compressed = []
    for line in lines:
        leading = len(line) - len(line.lstrip(" "))
        assert leading % 4 == 0, (
            f"ast.unparse emitted unexpected indentation ({leading} spaces); "
            "indent compression assumes multiples of 4"
        )
        compressed.append(" " * (leading // 4) + line.lstrip(" "))
    return "\n".join(compressed)


def _build_inline_body(sproc_type: str) -> tuple[str, str]:
    """Read and concatenate Python sources for inline `$$...$$` embedding.

    Returns the raw (uncompressed) module source and the handler function name.
    ``render_sproc_sql`` wraps this body with :func:`_compress_inline_body`
    before embedding it; the raw source is returned here so unit tests can
    introspect the bundle (AST parse, defined-name / handler checks).

    Returns:
        (python_body, handler_function_name)

    """
    return build_bundle_source(sproc_type, escape_dollar=False)


def _compress_inline_body(body: str) -> str:
    """Wrap a raw module body in a self-decompressing inline SPROC stub.

    The concatenated bundle is ~290 KB of Python.  Embedded verbatim between
    ``AS $$ ... $$`` and pushed through the async-optimize path (which stores
    the anonymous procedure inside a serverless TASK definition), it overflows
    Snowflake's task-property size ceiling — the limit is measured on the
    *stored/compressed* size, and Snowflake's own compression of the source is
    only ~2.7x, leaving ~110 KB stored (over the empirical ~100 KB ceiling).

    Instead we gzip the body ourselves (zlib level 9 ≈ 4.5x) and base64-encode
    the result, then emit a tiny stub that decompresses and ``exec``s it into
    the module globals so the ``HANDLER`` name still resolves.  The base64
    payload is incompressible, so the rendered SQL size ≈ the stored task size
    (~85 KB for optimize) — comfortably under the ceiling, with headroom that
    grows in raw-code terms because future additions also compress ~4.5x.

    The payload alphabet (base64 + the fixed stub chars) contains no ``$``,
    backslash, or single quote, so it is safe between ``$$`` delimiters and
    inside the ``'...'`` literal — no ``$$``-escaping needed on this path
    (unlike the verbatim embedding this replaces).
    """
    payload = base64.b64encode(zlib.compress(body.encode("utf-8"), 9)).decode("ascii")
    # Import under private aliases to avoid clobbering names the bundle itself
    # binds at module scope (it does `import base64` / `import zlib`), and exec
    # into globals() so the decompressed definitions land at module scope where
    # Snowflake resolves HANDLER.
    return (
        "import base64 as _caifs_b64, zlib as _caifs_zlib\n"
        "exec(compile(_caifs_zlib.decompress(_caifs_b64.b64decode("
        f"'{payload}'"
        ")).decode('utf-8'), '<inline_bundle>', 'exec'), globals())\n"
    )


def build_bundle_source(
    sproc_type: str, *, escape_dollar: bool = False
) -> tuple[str, str]:
    """Concatenate + minify a SPROC type's Python sources into one module body.

    Shared by the inline `$$...$$` embedding path (``escape_dollar=True``) and
    the staged-zip packaging path (``escape_dollar=False``, which yields a
    plain importable module — see ``dev/scripts/package_caifs.py``).

    Returns:
        (python_body, handler_function_name)

    """
    config = _load_sproc_config()
    sproc_cfg = config.get(sproc_type)
    if sproc_cfg is None:
        raise ValueError(f"No inline config for SPROC type: {sproc_type}")

    parts: list[str] = []
    for module_path in sproc_cfg["sources"]:
        source_path = _resolve_module_path(module_path)
        if not source_path.exists():
            raise FileNotFoundError(
                f"Source file not found: {source_path} (from module: {module_path})"
            )
        content = source_path.read_text()
        content = _minify_python(content)
        content = _INTER_FILE_IMPORT_RE.sub("", content)
        content = re.sub(
            r"^\s*from\s+__future__\s+import\s+[^\n]+\n?",
            "",
            content,
            flags=re.MULTILINE,
        )
        parts.append(content)

    # Embed models.json as a Python constant so load_model_rates() works
    # inside the inline SPROC (where filesystem/importlib paths are unavailable).
    models_json_path = _PACKAGE_ROOTS["snowflake_ai_optimize.core"] / "models.json"
    if models_json_path.exists():
        models_data = models_json_path.read_text(encoding="utf-8").strip()
        parts.insert(0, f"_INLINE_MODEL_RATES = {models_data}")

    body = "from __future__ import annotations\n\n" + "\n".join(parts)
    if escape_dollar:
        body = body.replace("$$", "\\x24\\x24")
    return body, sproc_cfg["handler"]
