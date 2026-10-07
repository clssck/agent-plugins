#!/usr/bin/env python3
"""
Connection management for Snowflake Postgres using standard PostgreSQL files.

Uses:
- ~/.pg_service.conf - connection profiles (host, port, dbname, user, sslmode)
- ~/.pgpass - passwords (enforced 0600 permissions by PostgreSQL clients)

Also handles CREATE INSTANCE and RESET ACCESS operations via Snowflake,
saving credentials securely without exposing them in chat.

Credentials are never logged to console.
"""

import argparse
import configparser
import json
import os
import re
import socket
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization
except ImportError:
    snowflake = None
    serialization = None

# Make ./shared/ importable when this script is run directly (pytest already
# injects it via pythonpath). Operators running `python scripts/pg_connect.py`
# otherwise hit ModuleNotFoundError for pg_common.
_SHARED_DIR = Path(__file__).resolve().parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

# Generic-PG credential plumbing lives in pg_common so migration scripts can
# reuse it without importing Snowflake-specific code. Re-exported here so
# existing `from pg_connect import load_pgpass` call sites keep working.
# Note: tests that patch file locations must target pg_common.PG_SERVICE_FILE /
# pg_common.PGPASS_FILE, since the functions resolve the constants in that
# module's namespace.
from pg_common import (  # noqa: F401, E402
    PG_SERVICE_FILE,
    PGPASS_FILE,
    check_snowflake_connector,
    load_service_file,
    save_service_file,
    get_service_entry,
    save_service_entry,
    delete_service_entry,
    list_service_entries,
    load_pgpass,
    save_pgpass,
    find_pgpass_entry,
    upsert_pgpass_entry,
    delete_pgpass_entry,
    validate_pg_database_name,
)

# Also bind the module itself: validate_connection() calls pg_common.connect /
# pg_common.PgError, which the names imported above don't provide.
import pg_common  # noqa: E402

# CA certificate storage for SSL server identity verification (sslmode=verify-ca)
CERT_DIR = Path.home() / ".snowflake" / "postgres" / "certs"

# Snowflake CLI config paths (for --create and --reset to connect to Snowflake)
# These are standard Snowflake CLI locations - the script reads them directly
# when executed standalone (not through the agent's SQL tool)
_SF_CONFIG_DIR = Path.home() / ".snowflake"
_SF_CONNECTIONS_TOML = _SF_CONFIG_DIR / "connections.toml"
_SF_CONFIG_TOML = _SF_CONFIG_DIR / "config.toml"
_SF_AGENT_SETTINGS = _SF_CONFIG_DIR / "cortex" / "settings.json"

_SF_ALLOWED_CONFIG_KEYS = {
    "account", "user", "password", "authenticator",
    "private_key_path", "private_key_passphrase",
    "host", "database", "schema", "warehouse", "role",
    "token", "token_file_path",
}


_VALID_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_SQL_STRING_RE = re.compile(r"^[^'\\;]+$")
_VALID_AUTH_AUTHORITIES = {"POSTGRES", "POSTGRES_OR_SNOWFLAKE"}


def _validate_sql_string(value: str, param_name: str) -> None:
    """Reject SQL string literals containing injection characters.

    Snowflake string params should never contain single quotes,
    backslashes, or semicolons. Raises ValueError on bad input.
    """
    if not _VALID_SQL_STRING_RE.match(value):
        raise ValueError(
            f"Invalid characters in {param_name}: must not contain "
            f"single quotes, backslashes, or semicolons"
        )


def validate_instance_name(name: str) -> str | None:
    """Validate a Snowflake SQL identifier (instance name).

    Returns None if valid, or an error message string if invalid.
    Snowflake unquoted identifiers allow letters, digits, and underscores,
    and must start with a letter or underscore.
    """
    if not name:
        return "Instance name cannot be empty"
    if _VALID_IDENTIFIER_RE.match(name):
        return None
    # Check leading digit before reporting bad characters
    if name[0].isdigit():
        suggestion = re.sub(r"[^A-Za-z0-9_]", "_", f"_{name}")
        return (
            f"Invalid instance name '{name}': must start with a letter or underscore, not a digit.\n"
            f"  Suggestion: use '{suggestion}' instead"
        )
    bad_chars = set(ch for ch in name if not ch.isalnum() and ch != "_")
    suggestion = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return (
        f"Invalid instance name '{name}': "
        f"contains invalid character(s): {bad_chars}\n"
        f"  Snowflake identifiers only allow letters, digits, and underscores.\n"
        f"  Suggestion: use '{suggestion}' instead"
    )


def _row_to_dict(columns: list, row: list | tuple) -> dict:
    """Convert a SQL result row to a dict using column names."""
    return {col.lower(): val for col, val in zip(columns, row)}


def parse_create_response(response_file: str) -> dict:
    """
    Extract connection params from CREATE POSTGRES INSTANCE JSON response.
    
    Handles two formats:
    1. Direct dict: {"host": "...", "access_roles": [...]}
    2. SQL result: {"columns": [...], "rows": [[...]]}
    
    Returns dict with:
    - host, port, database, sslmode (connection info)
    - user, password (primary user - snowflake_admin)
    - access_roles: list of {"name": str, "password": str} for all roles
    """
    if not Path(response_file).exists():
        raise FileNotFoundError(
            f"Response file not found: {response_file}\n"
            "The temp file may have been cleaned up. To add this connection:\n"
            "  • Ask your assistant to reset credentials for this instance, or\n"
            "  • Manually add your connection to ~/.pg_service.conf and password to ~/.pgpass"
        )
    
    with open(response_file) as f:
        data = json.load(f)
    
    # Handle list wrapper
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    
    # Handle SQL result format: {"columns": [...], "rows": [[...]]}
    if "columns" in data and "rows" in data:
        columns = data["columns"]
        rows = data["rows"]
        if not rows:
            raise ValueError("No rows in response")
        data = _row_to_dict(columns, rows[0])
    
    host = data.get("host")
    if not host:
        raise ValueError("No 'host' field found in response")
    
    # Extract access_roles (may be JSON string or already parsed)
    access_roles = data.get("access_roles", [])
    if isinstance(access_roles, str):
        try:
            access_roles = json.loads(access_roles)
        except json.JSONDecodeError:
            access_roles = []
    
    # Extract all roles with passwords
    # Handles two formats:
    # 1. Dict format: {"role_name": "password", ...} (real Snowflake response)
    # 2. List format: [{"name": "...", "password": "..."}, ...] (legacy/test format)
    roles_with_passwords = []
    admin_password = None
    
    if isinstance(access_roles, dict):
        # Dict format: keys are role names, values are passwords
        for role_name, password in access_roles.items():
            if role_name and password:
                roles_with_passwords.append({
                    "name": role_name,
                    "password": password,
                })
                if role_name == "snowflake_admin":
                    admin_password = password
    elif isinstance(access_roles, list):
        # List format: each item has "name" and "password" keys
        for role in access_roles:
            if isinstance(role, dict) and role.get("name") and role.get("password"):
                roles_with_passwords.append({
                    "name": role["name"],
                    "password": role["password"],
                })
                if role["name"] == "snowflake_admin":
                    admin_password = role["password"]
    
    if not admin_password:
        raise ValueError("No snowflake_admin password found in access_roles")
    
    return {
        "host": host,
        "port": 5432,
        "database": "postgres",
        "user": "snowflake_admin",
        "password": admin_password,
        "sslmode": "require",
        "access_roles": roles_with_passwords,
    }


def _extract_password(payload: object) -> str | None:
    """Extract a password from common response shapes."""
    if isinstance(payload, list) and payload:
        return _extract_password(payload[0])

    if isinstance(payload, dict):
        if payload.get("password"):
            return payload["password"]

        access_roles = payload.get("access_roles")
        if isinstance(access_roles, list):
            for role in access_roles:
                if isinstance(role, dict) and role.get("password"):
                    return role["password"]

        if "data" in payload:
            return _extract_password(payload["data"])

        # Handle SQL result format: {"columns": ["col1", ...], "rows": [[val1, ...], ...]}
        if "columns" in payload and "rows" in payload:
            columns = payload["columns"]
            rows = payload["rows"]
            if isinstance(columns, list) and isinstance(rows, list) and rows:
                # Find password column index (case-insensitive)
                col_lower = [c.lower() if isinstance(c, str) else c for c in columns]
                if "password" in col_lower:
                    pwd_idx = col_lower.index("password")
                    first_row = rows[0]
                    if isinstance(first_row, (list, tuple)) and len(first_row) > pwd_idx:
                        return first_row[pwd_idx]

        if "rows" in payload:
            return _extract_password(payload["rows"])

    return None


def parse_reset_response(response_file: str) -> str:
    """
    Extract password from RESET ACCESS response JSON.
    """
    if not Path(response_file).exists():
        raise FileNotFoundError(
            f"Reset response file not found: {response_file}\n"
            "The temp file may have been cleaned up. To update this connection:\n"
            "  • Ask your assistant to reset credentials again, or\n"
            "  • Manually update your password in ~/.pgpass"
        )
    
    with open(response_file) as f:
        data = json.load(f)

    password = _extract_password(data)
    if not password:
        raise ValueError("No password field found in reset response")

    return password


def parse_connection_string(conn_str: str) -> dict:
    """
    Parse a postgres:// connection string into components.
    
    Returns dict with: host, port, database, user, password, sslmode
    """
    parsed = urlparse(conn_str)
    
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError(f"Invalid scheme: {parsed.scheme}. Expected postgres:// or postgresql://")
    
    # Extract query params (like sslmode)
    query_params = parse_qs(parsed.query)
    
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": (parsed.path.lstrip("/") or None) if parsed.path else None,
        "user": parsed.username,
        "password": unquote(parsed.password) if parsed.password else None,
        "sslmode": query_params.get("sslmode", ["require"])[0],
    }


def build_connection_string(params: dict) -> str:
    """
    Build a connection string from parameters.
    Password is masked in the output.
    """
    password_display = "****" if params.get("password") else ""
    return (
        f"postgres://{params.get('user', '')}:{password_display}@"
        f"{params.get('host', '')}:{params.get('port', 5432)}/"
        f"{params.get('database', '')}?sslmode={params.get('sslmode', 'require')}"
    )


_POSTGRES_DSN_RE = re.compile(
    r"(?P<prefix>postgres(?:ql)?://[^:\s/@]+:)(?P<password>[^@\s]*)(?P<suffix>@)",
    re.IGNORECASE,
)


def _redact_postgres_dsn(text: str) -> str:
    """Mask passwords embedded in postgres:// connection strings."""
    return _POSTGRES_DSN_RE.sub(
        lambda match: f"{match.group('prefix')}[REDACTED]{match.group('suffix')}",
        text,
    )


def sanitize_error(error_msg: str, params: dict) -> str:
    """Remove any credentials from error messages."""
    msg = str(error_msg)
    if params.get("connection"):
        msg = msg.replace(params["connection"], _redact_postgres_dsn(params["connection"]))
    if params.get("password"):
        msg = msg.replace(params["password"], "[REDACTED]")
    if params.get("user"):
        msg = msg.replace(f"user={params['user']}", "user=[REDACTED]")
    return _redact_postgres_dsn(msg)


def categorize_connection_error(error: Exception, params: dict) -> str:
    """Provide helpful error messages for common connection issues."""
    error_str = str(error).lower()
    
    if "connection refused" in error_str or "could not connect" in error_str:
        return (
            "Connection refused. Possible causes:\n"
            "  • Your IP may not be in the network policy allow list\n"
            "  • The Postgres instance may be suspended\n"
            "  • Firewall blocking port 5432\n"
            "  Run: network_policy_check.py to verify your IP is allowed"
        )
    elif "timeout" in error_str or "timed out" in error_str:
        return (
            "Connection timed out. Possible causes:\n"
            "  • Network connectivity issues\n"
            "  • Firewall blocking the connection\n"
            "  • Instance may be starting up"
        )
    elif "authentication failed" in error_str or "password" in error_str:
        return (
            "Authentication failed. Possible causes:\n"
            "  • Incorrect username or password\n"
            "  • Password may need URL encoding for special characters\n"
            "  • User may not exist on this instance"
        )
    elif "certificate verify failed" in error_str or "sslrootcert" in error_str:
        return (
            "SSL certificate verification failed. Possible causes:\n"
            "  • CA certificate is missing or expired\n"
            "  • sslrootcert path points to a wrong or stale file\n"
            "  Refresh with: pg_connect.py --fetch-cert --instance-name <NAME>"
        )
    elif "ssl" in error_str:
        return (
            "SSL error. Ensure your connection uses sslmode=require or verify-ca.\n"
            "  To upgrade to verified connections:\n"
            "  pg_connect.py --fetch-cert --instance-name <NAME>"
        )
    elif "does not exist" in error_str:
        return (
            f"Database '{params.get('database')}' not found.\n"
            "  • Check the database name\n"
            "  • Default database is usually 'postgres'"
        )
    else:
        return f"Connection failed: {sanitize_error(error, params)}"


def validate_connection(params: dict) -> tuple[bool, str]:
    """
    Test a connection to verify it works.
    
    Returns (success, message). Never exposes credentials in error messages.
    """
    try:
        conn = pg_common.connect(
            host=params["host"],
            port=params["port"],
            dbname=params["database"],
            user=params["user"],
            password=params["password"],
            sslmode=params.get("sslmode", "require"),
            sslrootcert=params.get("sslrootcert"),
            connect_timeout=10,
        )
        conn.close()
        return True, "Connection successful"
    except pg_common.PgError as e:
        return False, categorize_connection_error(e, params)
    except Exception as e:
        return False, f"Unexpected error: {sanitize_error(e, params)}"


# --- Snowflake Connection (for CREATE/RESET operations) ---

def _read_agent_connection_name() -> str | None:
    """Read default connection name from agent settings if available."""
    if not _SF_AGENT_SETTINGS.exists():
        return None
    try:
        data = json.loads(_SF_AGENT_SETTINGS.read_text())
    except json.JSONDecodeError:
        return None
    return data.get("cortexAgentConnectionName")


def _load_snowflake_connection_config(connection_name: str | None) -> tuple[str, dict]:
    """Load Snowflake connection config from ~/.snowflake/connections.toml or config.toml."""
    connections: dict[str, dict] = {}
    default_name = None

    if _SF_CONNECTIONS_TOML.exists():
        data = tomllib.loads(_SF_CONNECTIONS_TOML.read_text())
        default_name = data.get("default_connection_name")
        for key, value in data.items():
            if key != "default_connection_name" and isinstance(value, dict):
                connections[key] = value
    elif _SF_CONFIG_TOML.exists():
        data = tomllib.loads(_SF_CONFIG_TOML.read_text())
        default_name = data.get("default_connection_name")
        connections = data.get("connections", {})

    if not connections:
        raise RuntimeError(
            "No Snowflake connection config found in ~/.snowflake/connections.toml or ~/.snowflake/config.toml"
        )

    target = (
        connection_name
        or os.environ.get("SNOWFLAKE_CONNECTION_NAME")
        or os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME")
        or default_name
        or _read_agent_connection_name()
    )
    if not target:
        target = next(iter(connections.keys()))

    if target not in connections:
        raise RuntimeError(
            f"Connection '{target}' not found. Available: {', '.join(connections.keys())}"
        )

    return target, connections[target]


def _load_private_key(path: str, passphrase: str | None) -> object:
    """Load a private key from file for Snowflake key-pair auth."""
    key_bytes = Path(path).read_bytes()
    password = passphrase.encode() if passphrase else None
    return serialization.load_pem_private_key(key_bytes, password=password)


def get_snowflake_connection(
    connection_name: str | None = None,
    authenticator: str | None = None,
    role: str | None = None,
):
    """
    Get a Snowflake connection using available configuration.

    Priority:
    1. Environment variables (SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, etc.)
    2. Connection name from ~/.snowflake/connections.toml

    If `role` is provided, it overrides the role from env/config without
    mutating the underlying config file. The override only applies to this
    connection instance.
    """
    check_snowflake_connector()
    env_account = os.environ.get("SNOWFLAKE_ACCOUNT")
    env_user = os.environ.get("SNOWFLAKE_USER")
    if env_account and env_user:
        connect_args = {"account": env_account, "user": env_user}
        if authenticator:
            connect_args["authenticator"] = authenticator
        elif os.environ.get("SNOWFLAKE_AUTHENTICATOR"):
            connect_args["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
        elif os.environ.get("SNOWFLAKE_PASSWORD"):
            connect_args["password"] = os.environ["SNOWFLAKE_PASSWORD"]
        if role:
            connect_args["role"] = role
        elif os.environ.get("SNOWFLAKE_ROLE"):
            connect_args["role"] = os.environ["SNOWFLAKE_ROLE"]
        return snowflake.connector.connect(**connect_args)

    target_name, config = _load_snowflake_connection_config(connection_name)
    connect_args = {k: v for k, v in config.items() if k in _SF_ALLOWED_CONFIG_KEYS}

    if authenticator:
        connect_args["authenticator"] = authenticator

    if role:
        connect_args["role"] = role

    if connect_args.get("private_key_path"):
        connect_args["private_key"] = _load_private_key(
            connect_args["private_key_path"],
            connect_args.get("private_key_passphrase"),
        )
        connect_args.pop("private_key_path", None)
        connect_args.pop("private_key_passphrase", None)

    if connect_args.get("token_file_path"):
        token_path = Path(connect_args.pop("token_file_path"))
        if token_path.exists():
            connect_args["token"] = token_path.read_text().strip()

    return snowflake.connector.connect(**connect_args)


def execute_snowflake_sql(
    query: str,
    connection_name: str | None = None,
    authenticator: str | None = None,
    role: str | None = None,
) -> dict:
    """Execute a SQL query on Snowflake and return {query, columns, rows}.

    Routes through SnowflakeSession so this works whether the in-process
    connector is available (mac/linux/x64-Windows) or only the `snow` CLI
    is (Windows ARM64). Result shape is preserved for backwards compat with
    parse_create_response / parse_reset_response / ensure_cert callers —
    `columns` is a list of column names (lowercased; callers already
    case-fold) and `rows` is a list of tuples.
    """
    from sf_session import SnowflakeSession  # noqa: E402

    with SnowflakeSession(
        connection=connection_name,
        role=role,
        authenticator=authenticator,
    ) as session:
        row_dicts = session.execute(query)

    if not row_dicts:
        return {"query": query, "columns": [], "rows": []}

    columns = list(row_dicts[0].keys())
    rows = [tuple(row.get(c) for c in columns) for row in row_dicts]
    return {"query": query, "columns": columns, "rows": rows}


def write_secure_json(path: str, payload: dict) -> None:
    """Write JSON to a file with 0600 permissions."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    os.chmod(output_path, 0o600)


def _is_postgres_keyword_syntax_error(lower: str) -> bool:
    """Detect syntax errors where Snowflake rejects the POSTGRES keyword itself."""
    if "syntax error" not in lower or "postgres" not in lower:
        return False

    keyword_markers = (
        "near 'postgres'",
        'near "postgres"',
        "near postgres",
        "unexpected 'postgres'",
        'unexpected "postgres"',
        "unexpected postgres",
    )
    return any(marker in lower for marker in keyword_markers)


def translate_snowflake_error(error: Exception, current_role: str | None = None) -> str | None:
    """Map common Snowflake errors to agent-facing guidance.

    Returns a hint string the agent can surface to the user, or None if the
    error is not a known pattern and should pass through unchanged.

    The messages are written for the agent to translate to the user — they
    reference script flags (e.g. `--use-role`) that the user never sees directly.
    """
    msg = str(error)
    lower = msg.lower()

    if "insufficient privileges" in lower:
        role_part = f" (current role: {current_role})" if current_role else ""
        return (
            f"Insufficient privileges{role_part}.\n"
            "The current Snowflake role lacks the required privilege for this operation.\n"
            "Agent guidance:\n"
            "  • For CREATE POSTGRES INSTANCE, the role needs CREATE POSTGRES INSTANCE ON ACCOUNT.\n"
            "  • Retry with --use-role ACCOUNTADMIN (or another role that has the grant).\n"
            "  • If no role has it, ask an account admin to run:\n"
            "      GRANT CREATE POSTGRES INSTANCE ON ACCOUNT TO ROLE <role>;"
        )

    if "internal_error" in lower or "team_iam_role_arn_not_found" in lower:
        return (
            "Snowflake returned an internal error while handling a Postgres operation.\n"
            "This is usually a service-side issue, not a client-side syntax or "
            "connection-string mistake.\n"
            "Agent guidance:\n"
            "  • Retry once — transient backend issues sometimes resolve on retry.\n"
            "  • If it persists, verify the account/region supports Snowflake Postgres.\n"
            "  • Escalate with the exact error text if the feature should already be enabled."
        )

    if (
        "unsupported feature" in lower
        or ("postgres instance" in lower and "does not exist" in lower and "create" in lower)
        or _is_postgres_keyword_syntax_error(lower)
    ):
        return (
            "Snowflake Postgres may not be enabled on this account/region.\n"
            "Agent guidance:\n"
            "  • Try `SHOW POSTGRES INSTANCES;` — if that also fails, the feature may not be available.\n"
            "  • Verify the account's region supports Snowflake Postgres.\n"
            "  • Ask the account admin to confirm enablement if availability is unclear."
        )

    return None


def ensure_cert(
    instance_name: str,
    connection_name: str | None = None,
    snowflake_connection: str | None = None,
    authenticator: str | None = None,
    role: str | None = None,
) -> Path | None:
    """
    Fetch the CA certificate for a Postgres instance via DESCRIBE and cache it locally.

    Runs DESCRIBE POSTGRES INSTANCE to get the PEM certificate, then writes it
    to CERT_DIR/<connection_name>.pem (chmod 600). The cert is a self-signed
    per-account root CA used for sslmode=verify-ca server identity verification.

    Returns the cert file path on success, or None if no certificate was found
    in the DESCRIBE output.
    """
    err = validate_instance_name(instance_name)
    if err:
        raise ValueError(err)
    result = execute_snowflake_sql(
        f"DESCRIBE POSTGRES INSTANCE {instance_name};",
        snowflake_connection,
        authenticator,
        role,
    )

    # DESCRIBE returns property/value pairs: each row is [property_name, value]
    rows = result.get("rows", [])
    if not rows:
        return None

    cert_pem = None
    for row in rows:
        if len(row) >= 2 and isinstance(row[0], str) and row[0].lower() == "certificate":
            cert_pem = row[1]
            break
    if not cert_pem or not cert_pem.strip():
        return None

    cert_pem = cert_pem.strip()
    if not cert_pem.startswith("-----BEGIN CERTIFICATE-----"):
        return None

    # Store using the connection name (lowercased instance name) as the identifier
    identifier = (connection_name or instance_name).lower()
    CERT_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    cert_path = CERT_DIR / f"{identifier}.pem"

    cert_path.write_text(cert_pem + "\n")
    os.chmod(cert_path, 0o600)

    return cert_path


PROBE_TIMEOUT_SECONDS = 20


def probe_postgres_port(host: str, port: int = 5432, timeout: int = PROBE_TIMEOUT_SECONDS) -> dict:
    """Attempt a plain TCP connect to the instance's Postgres port.

    Returns a dict with:
      - reachable: bool
      - status: one of "reachable", "refused", "timeout", "dns_error", "error"
      - message: human-readable summary for the agent

    This is a lightweight probe with no auth or TLS — it only verifies that
    the port accepts a TCP connection. A successful probe means the instance
    is responding and the local network route is open (no firewall/policy
    blocking). A failed probe tells the agent which follow-up to suggest.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {
                "reachable": True,
                "status": "reachable",
                "message": f"Port {port} reachable on {host}",
            }
    except socket.timeout:
        return {
            "reachable": False,
            "status": "timeout",
            "message": (
                f"Port {port} on {host} timed out after {timeout}s.\n"
                "Likely cause: no network policy allowing this IP on the instance.\n"
                "Agent guidance: proactively offer to set up a network policy next — "
                "psql/any Postgres client will hang until one is configured."
            ),
        }
    except ConnectionRefusedError:
        return {
            "reachable": False,
            "status": "refused",
            "message": (
                f"Port {port} on {host} refused the connection.\n"
                "Likely cause: instance is still provisioning and not yet listening.\n"
                "Agent guidance: run `pg_connect.py --ensure-ready --instance-name <name>` "
                "to wait for READY, then re-probe or try psql."
            ),
        }
    except socket.gaierror as e:
        return {
            "reachable": False,
            "status": "dns_error",
            "message": (
                f"DNS resolution failed for {host}: {e}.\n"
                "Agent guidance: the host may not be propagated yet — "
                "wait 30-60s and retry, or verify the instance was created."
            ),
        }
    except OSError as e:
        return {
            "reachable": False,
            "status": "error",
            "message": f"TCP probe failed: {e}",
        }


def create_postgres_instance(
    instance_name: str,
    compute_pool: str,
    storage: int,
    enable_ha: bool = False,
    postgres_version: str | None = None,
    network_policy: str | None = None,
    auth_authority: str = "POSTGRES",
    storage_integration: str | None = None,
    postgres_settings: str | None = None,
    comment: str | None = None,
    snowflake_connection: str | None = None,
    authenticator: str | None = None,
    role: str | None = None,
    database: str | None = None,
) -> dict:
    """
    Create a Snowflake Postgres instance and save connection securely.

    `database` selects which Postgres database the saved ~/.pg_service.conf
    entry (and matching ~/.pgpass row) points at. A new instance always has a
    `postgres` database, so that stays the default; pass another name when the
    tables you care about live in a different database on this instance.

    Returns dict with instance info (host) without exposing passwords.
    """
    err = validate_instance_name(instance_name)
    if err:
        raise ValueError(err)
    if database:
        validate_pg_database_name(database)

    _validate_sql_string(compute_pool, "compute_pool")
    if auth_authority not in _VALID_AUTH_AUTHORITIES:
        raise ValueError(
            f"Invalid auth_authority '{auth_authority}'. "
            f"Must be one of: {', '.join(sorted(_VALID_AUTH_AUTHORITIES))}"
        )
    if postgres_version and not str(postgres_version).isdigit():
        raise ValueError(f"postgres_version must be a number, got '{postgres_version}'")
    if network_policy:
        _validate_sql_string(network_policy, "network_policy")
    if storage_integration:
        _validate_sql_string(storage_integration, "storage_integration")
    if postgres_settings:
        _validate_sql_string(postgres_settings, "postgres_settings")
    if comment:
        _validate_sql_string(comment, "comment")

    # Build optional clauses
    optional_clauses = []
    if enable_ha:
        optional_clauses.append("HIGH_AVAILABILITY = TRUE")
    if postgres_version:
        optional_clauses.append(f"POSTGRES_VERSION = {postgres_version}")
    if network_policy:
        optional_clauses.append(f"NETWORK_POLICY = '{network_policy}'")
    if storage_integration:
        optional_clauses.append(f"STORAGE_INTEGRATION = '{storage_integration}'")
    if postgres_settings:
        optional_clauses.append(f"POSTGRES_SETTINGS = '{postgres_settings}'")
    if comment:
        optional_clauses.append(f"COMMENT = '{comment}'")
    
    optional_sql = "\n  ".join(optional_clauses)
    if optional_sql:
        optional_sql = "\n  " + optional_sql
    
    query = f"""CREATE POSTGRES INSTANCE {instance_name}
  COMPUTE_FAMILY = '{compute_pool}'
  STORAGE_SIZE_GB = {storage}
  AUTHENTICATION_AUTHORITY = {auth_authority}{optional_sql};"""

    response = execute_snowflake_sql(query, snowflake_connection, authenticator, role)

    # Write to temp file for debugging/recovery. Use the OS temp dir so this
    # also works on native Windows (where `/tmp/` doesn't exist by default).
    tmp_path = str(Path(tempfile.gettempdir()) / f"pg_create_{instance_name}.json")
    write_secure_json(tmp_path, response)
    
    # Parse and save connection
    conn_info = parse_create_response(tmp_path)
    # Point the saved connection at the requested database (default: postgres).
    # Everything downstream (service entry + pgpass) keys off conn_info["database"].
    if database:
        conn_info["database"] = database
    connection_name = instance_name.lower()
    
    # Fetch CA cert via DESCRIBE and save with verify-ca if available
    cert_path = None
    try:
        cert_path = ensure_cert(instance_name, connection_name, snowflake_connection, authenticator, role)
    except Exception as e:
        print(f"Note: cert fetch failed ({e}), using sslmode=require", file=sys.stderr)

    save_service_entry(
        connection_name, conn_info,
        sslrootcert=str(cert_path) if cert_path else None,
    )
    upsert_pgpass_entry(
        host=conn_info["host"],
        port=int(conn_info.get("port", 5432)),
        database=conn_info.get("database", "postgres"),
        user=conn_info.get("user", "snowflake_admin"),
        password=conn_info["password"],
    )

    probe = probe_postgres_port(
        conn_info["host"],
        port=int(conn_info.get("port", 5432)),
    )

    return {
        "instance_name": instance_name,
        "connection_name": connection_name,
        "host": conn_info["host"],
        "cert_path": str(cert_path) if cert_path else None,
        "probe": probe,
        "network_policy_set": bool(network_policy),
    }


def reset_postgres_access(
    instance_name: str,
    role: str = "snowflake_admin",
    host: str | None = None,
    snowflake_connection: str | None = None,
    authenticator: str | None = None,
    use_role: str | None = None,
    database: str | None = None,
) -> dict:
    """
    Reset credentials for a Snowflake Postgres role and update saved password.
    
    If --host is provided, creates the service entry if missing.
    Otherwise requires an existing connection in ~/.pg_service.conf.

    `role` is the Postgres role to reset (snowflake_admin or application).
    `use_role` is the Snowflake session role override for the ALTER command.
    `database` selects the Postgres database for a newly created service entry
    (default: postgres). When the entry already exists its database is left
    untouched — the reset only rotates the password for that saved profile.
    """
    err = validate_instance_name(instance_name)
    if err:
        raise ValueError(err)
    if database:
        validate_pg_database_name(database)
    _validate_sql_string(role, "role")
    query = f"ALTER POSTGRES INSTANCE {instance_name} RESET ACCESS FOR '{role}';"
    
    response = execute_snowflake_sql(query, snowflake_connection, authenticator, use_role)

    # Write to temp file for debugging/recovery (cross-platform tmpdir).
    tmp_path = str(Path(tempfile.gettempdir()) / f"pg_reset_{instance_name}.json")
    write_secure_json(tmp_path, response)
    
    # Parse password and update pgpass
    new_password = parse_reset_response(tmp_path)
    connection_name = instance_name.lower()
    
    # Get existing service entry or create from --host
    service_entry = get_service_entry(connection_name)
    if not service_entry:
        if host:
            # Create new service entry with provided host
            service_entry = {
                "host": host,
                "port": 5432,
                "database": database or "postgres",
                "user": "snowflake_admin",
                "sslmode": "require",
            }
            save_service_entry(connection_name, service_entry)
        else:
            return {
                "success": False,
                "instance_name": instance_name,
                "message": f"No existing connection '{connection_name}' in ~/.pg_service.conf. Use --host to create one.",
                "tmp_path": tmp_path,
            }
    
    # If service entry lacks cert verification, try to fetch cert now
    cert_path = None
    if not service_entry.get("sslrootcert"):
        try:
            cert_path = ensure_cert(instance_name, connection_name, snowflake_connection, authenticator, use_role)
            if cert_path:
                save_service_entry(connection_name, service_entry, sslrootcert=str(cert_path))
        except Exception as e:
            print(f"Note: cert fetch failed ({e}), keeping sslmode=require", file=sys.stderr)

    # Update password in pgpass for the specific role being reset
    upsert_pgpass_entry(
        host=service_entry["host"],
        port=int(service_entry.get("port", 5432)),
        database=service_entry.get("database", "postgres"),
        user=role,
        password=new_password,
    )
    
    return {
        "success": True,
        "instance_name": instance_name,
        "connection_name": connection_name,
        "role": role,
        "cert_upgraded": cert_path is not None,
    }


# --- Combined Operations ---

def save_connection(name: str, params: dict) -> dict:
    """
    Save a connection to both service file and pgpass.
    
    If params contains 'access_roles' (from CREATE response), saves all roles
    to pgpass. Otherwise saves just the primary user/password.
    
    Returns dict with:
      - service_existed: bool - True if service file already existed
      - connection_existed: bool - True if this connection name already existed
      - pgpass_existed: bool - True if pgpass file already existed
      - password_updated: bool - True if password entry was updated (vs created)
      - roles_saved: list[str] - names of roles saved to pgpass
    """
    result = {
        "service_existed": PG_SERVICE_FILE.exists(),
        "connection_existed": get_service_entry(name) is not None,
        "pgpass_existed": PGPASS_FILE.exists(),
        "password_updated": False,
        "roles_saved": [],
    }
    
    host = params["host"]
    port = params.get("port", 5432)
    database = params.get("database", "postgres")
    
    # Check if primary pgpass entry already exists
    if params.get("password"):
        existing_pgpass = find_pgpass_entry(
            host, port, database,
            params.get("user", "snowflake_admin"),
        )
        result["password_updated"] = existing_pgpass is not None
    
    # Save service entry (no password, uses primary user)
    save_service_entry(name, params)
    
    # Save passwords to pgpass - either all access_roles or just primary user
    access_roles = params.get("access_roles", [])
    if access_roles:
        # CREATE response with multiple roles - save all to pgpass
        for role in access_roles:
            if role.get("name") and role.get("password"):
                upsert_pgpass_entry(host, port, database, role["name"], role["password"])
                result["roles_saved"].append(role["name"])
    elif params.get("password"):
        # Single user/password (e.g., from connection string)
        user = params.get("user", "snowflake_admin")
        upsert_pgpass_entry(host, port, database, user, params["password"])
        result["roles_saved"].append(user)
    
    return result


def get_connection(name: str) -> dict | None:
    """
    Get a connection by service name.
    Combines service entry with password from pgpass.
    """
    service = get_service_entry(name)
    if not service:
        return None
    
    # Look up password from pgpass
    pgpass_entry = find_pgpass_entry(
        service["host"],
        service["port"],
        service["database"],
        service["user"],
    )
    
    if pgpass_entry:
        service["password"] = pgpass_entry["password"]
    
    return service


def delete_connection(name: str) -> bool:
    """Delete a connection from both service file and pgpass."""
    service = get_service_entry(name)
    
    service_deleted = delete_service_entry(name)
    pgpass_deleted = False
    
    if service:
        pgpass_deleted = delete_pgpass_entry(
            service["host"],
            service.get("port", 5432),
            service.get("database", "postgres"),
            service.get("user", "snowflake_admin"),
        )
    
    return service_deleted or pgpass_deleted


def list_connections() -> list[str]:
    """List all saved connection names (from service file)."""
    return list_service_entries()


def repoint_connection_database(name: str, database: str) -> bool:
    """Repoint a saved connection at a different Postgres database.

    Rewrites the ~/.pg_service.conf entry's dbname to `database` and migrates
    the matching ~/.pgpass row (same host/port/user) so the password is found
    under the new database. No-op (returns False) when the entry is missing or
    already targets `database`. Never logs or echoes the password.

    Used so `pg_connect.py --ensure-ready --database <db>` leaves a saved
    connection that psql / the Python driver can use to reach the database the
    user's tables actually live in — not just the `postgres` default.
    """
    validate_pg_database_name(database)
    service = get_service_entry(name)
    if not service:
        return False
    old_database = service.get("database", "postgres")
    if old_database == database:
        return False

    host = service["host"]
    port = int(service.get("port", 5432))
    user = service.get("user", "snowflake_admin")

    # Migrate the password row to the new database (keep the old row too so a
    # connection still targeting the old db keeps working).
    existing = find_pgpass_entry(host, port, old_database, user)
    if existing and existing.get("password"):
        upsert_pgpass_entry(host, port, database, user, existing["password"])

    # Preserve verify-ca: re-pass sslrootcert so save_service_entry keeps it.
    sslrootcert = service.get("sslrootcert")
    updated = dict(service)
    updated["database"] = database
    save_service_entry(name, updated, sslrootcert=sslrootcert)
    return True


def update_password(name: str, new_password: str) -> bool:
    """
    Update password for an existing saved connection.
    """
    service = get_service_entry(name)
    if not service:
        return False
    
    upsert_pgpass_entry(
        service["host"],
        service.get("port", 5432),
        service.get("database", "postgres"),
        service.get("user", "snowflake_admin"),
        new_password,
    )
    return True


def get_connect_params(connection: str = None, connection_name: str = None) -> dict:
    """
    Get connection parameters from either a connection string or saved name.
    
    Priority: connection string > connection name > 'default'
    """
    if connection:
        return parse_connection_string(connection)
    
    name = connection_name or "default"
    params = get_connection(name)
    
    if not params:
        raise ValueError(
            f"No connection found with name '{name}'. "
            f"Provide --connection or save one with --save"
        )
    
    return params


READY_POLL_INTERVAL = 15
READY_TIMEOUT = 360  # 6 minutes — covers resume (3-5 min) with margin


def ensure_instance_ready(
    instance_name: str,
    snowflake_connection: str | None = None,
    authenticator: str | None = None,
    auto_resume: bool = True,
    timeout: int = READY_TIMEOUT,
    role: str | None = None,
) -> dict:
    """
    Check instance state and optionally resume if suspended.

    Polls DESCRIBE POSTGRES INSTANCE until state is READY or timeout.
    If auto_resume is True and state is SUSPENDED, issues RESUME first.

    Routes through SnowflakeSession so this also works on hosts that only
    have the `snow` CLI (e.g. Windows ARM64). On the connector backend the
    TCP connection stays open across the poll loop; on the CLI backend each
    poll shells out to `snow sql` — fine for a 15s-interval loop.
    """
    err = validate_instance_name(instance_name)
    if err:
        raise ValueError(err)

    from sf_session import SnowflakeSession  # noqa: E402

    start = time.time()
    resumed = False
    state = "UNKNOWN"

    with SnowflakeSession(
        connection=snowflake_connection,
        authenticator=authenticator,
        role=role,
    ) as session:
        while True:
            rows = session.execute(
                f"DESCRIBE POSTGRES INSTANCE {instance_name}"
            )
            state = _extract_instance_state(rows)

            elapsed = time.time() - start
            if elapsed > timeout:
                return {
                    "success": False,
                    "instance": instance_name,
                    "error": f"Timed out after {int(elapsed)}s waiting for READY",
                    "last_state": state,
                }

            if state == "READY":
                return {
                    "success": True,
                    "instance": instance_name,
                    "state": "READY",
                    "resumed": resumed,
                    "waited_seconds": int(elapsed),
                }

            if state == "SUSPENDED" and auto_resume and not resumed:
                print(
                    f"Instance {instance_name} is SUSPENDED, resuming...",
                    file=sys.stderr,
                )
                session.execute(
                    f"ALTER POSTGRES INSTANCE {instance_name} RESUME"
                )
                resumed = True

            if state in ("FAILED", "DESTROYING"):
                return {
                    "success": False,
                    "instance": instance_name,
                    "state": state,
                    "error": f"Instance is in terminal state: {state}",
                }

            print(
                f"Instance {instance_name} state: {state}, "
                f"waiting... ({int(elapsed)}s elapsed)",
                file=sys.stderr,
            )
            time.sleep(READY_POLL_INTERVAL)


def _extract_instance_state(rows: list[dict]) -> str:
    """Extract state from DESCRIBE POSTGRES INSTANCE rows.

    Snowflake returns one of two shapes depending on response format:
      - property/value: rows = [{"property": "state", "value": "READY"}, ...]
      - flat columns:   rows = [{"name": "...", "state": "READY", ...}]
    Both are handled. Empty rows or missing state column yield "UNKNOWN" so
    the poll loop can keep retrying rather than blowing up on a transient
    shape mismatch.
    """
    if not rows:
        return "UNKNOWN"
    first = rows[0]
    if set(first.keys()) == {"property", "value"}:
        props = {
            r["property"].lower(): r["value"]
            for r in rows
            if isinstance(r.get("property"), str)
        }
        return str(props.get("state", "UNKNOWN")).upper()
    if "state" in first:
        return str(first["state"]).upper()
    return "UNKNOWN"


def main():
    from pg_common import configure_stdio_utf8
    configure_stdio_utf8()
    parser = argparse.ArgumentParser(
        description="Manage Postgres connections using standard PostgreSQL files",
        epilog="Connections stored in ~/.pg_service.conf and ~/.pgpass",
    )
    parser.add_argument("--connection", "-c", help="Connection string (postgres://...)")
    parser.add_argument("--connection-name", "-n", default="default", help="Name for saved connection")
    parser.add_argument(
        "--database", "--dbname", dest="database", default=None,
        help="Target Postgres database the saved connection points at "
             "(default: postgres). Set this when the tables you need live in a "
             "different database on the instance — the ~/.pg_service.conf entry "
             "and ~/.pgpass row are written for this database so psql / the "
             "Python driver reach it. Applies to --create, --reset, "
             "--from-response --save, and --connection --save. When a "
             "--connection postgres://... URL already names a database, an "
             "explicit --database overrides it.",
    )
    parser.add_argument("--save", "-s", action="store_true", help="Save the connection")
    parser.add_argument("--test", "-t", action="store_true", help="Test the connection")
    parser.add_argument("--list", "-l", action="store_true", help="List saved connections")
    parser.add_argument("--delete", "-d", help="Delete a saved connection")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    # Extract credentials from CREATE/DESCRIBE response file (agent-safe)
    parser.add_argument("--from-response", help="Extract credentials from CREATE INSTANCE JSON response file")
    # Extract password from RESET ACCESS response file (agent-safe)
    parser.add_argument("--from-reset-response", help="Extract password from RESET ACCESS JSON response file")
    
    # Snowflake operations: CREATE and RESET (execute SQL + save connection)
    parser.add_argument("--create", action="store_true", help="Create a new Postgres instance")
    parser.add_argument("--reset", action="store_true", help="Reset credentials for an existing instance")
    parser.add_argument("--instance-name", "-i", help="Instance name (for --create or --reset)")
    parser.add_argument("--compute-pool", help="Compute family for --create")
    parser.add_argument("--storage", type=int, help="Storage in GB for --create")
    parser.add_argument("--enable-ha", action="store_true", help="Enable high availability for --create")
    parser.add_argument("--postgres-version", help="Postgres version for --create (e.g., 16)")
    parser.add_argument("--network-policy", help="Network policy name for --create")
    parser.add_argument("--auth-authority", default="POSTGRES",
                        choices=["POSTGRES", "POSTGRES_OR_SNOWFLAKE"],
                        help="Authentication authority for --create (default: POSTGRES)")
    parser.add_argument("--storage-integration", help="Storage integration name for --create (pg_lake)")
    parser.add_argument("--postgres-settings", help="JSON Postgres settings for --create (e.g. '{\"postgres:work_mem\": \"128MB\"}')")
    parser.add_argument("--comment", help="Comment for --create")
    parser.add_argument("--role", default="snowflake_admin", choices=["snowflake_admin", "application"], 
                        help="Postgres role for --reset (snowflake_admin or application)")
    parser.add_argument("--host", help="Host for --reset (creates service entry if missing)")
    parser.add_argument("--snowflake-connection", help="Snowflake connection name from ~/.snowflake/connections.toml")
    parser.add_argument("--authenticator", help="Snowflake authenticator (e.g., externalbrowser)")
    parser.add_argument("--use-role",
                        help="Snowflake session role override (e.g., ACCOUNTADMIN). "
                             "Passed to the connector for this invocation only — does not mutate config files. "
                             "Use when the default role lacks CREATE POSTGRES INSTANCE or similar privileges.")
    parser.add_argument("--ensure-ready", action="store_true",
                        help="Check instance state, auto-resume if suspended, wait for READY")
    parser.add_argument("--no-auto-resume", action="store_true",
                        help="With --ensure-ready: only check state, don't auto-resume")
    
    # Certificate management
    parser.add_argument("--fetch-cert", action="store_true",
                        help="Fetch CA cert via DESCRIBE and update service entry to verify-ca")
    parser.add_argument("--upgrade-ssl", action="store_true",
                        help="Upgrade all saved connections without sslrootcert to verify-ca")
    
    args = parser.parse_args()

    if args.database:
        try:
            validate_pg_database_name(args.database)
        except ValueError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)

    # Handle --from-response: extract credentials from CREATE response file
    if args.from_response:
        try:
            args._params_from_args = parse_create_response(args.from_response)
        except FileNotFoundError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"❌ Failed to parse response file: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.from_reset_response:
        try:
            args._update_password_from_file = parse_reset_response(args.from_reset_response)
        except FileNotFoundError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"❌ Failed to parse reset response file: {e}", file=sys.stderr)
            sys.exit(1)
    
    output = {"success": True, "message": "", "data": None}
    
    try:
        # Validate instance name early if provided (used by --create, --reset, --fetch-cert)
        if args.instance_name:
            name_error = validate_instance_name(args.instance_name)
            if name_error:
                print(f"❌ {name_error}", file=sys.stderr)
                sys.exit(1)

        # Handle --ensure-ready: Check/wait for instance READY state
        if args.ensure_ready:
            if not args.instance_name:
                print("❌ --instance-name is required for --ensure-ready", file=sys.stderr)
                sys.exit(1)

            result = ensure_instance_ready(
                instance_name=args.instance_name,
                snowflake_connection=args.snowflake_connection,
                authenticator=args.authenticator,
                auto_resume=not args.no_auto_resume,
                role=args.use_role,
            )

            if result["success"]:
                parts = [f"Instance {result['instance']} is READY"]
                if result.get("resumed"):
                    parts.append("(resumed from SUSPENDED)")
                if result.get("waited_seconds", 0) > 0:
                    parts.append(f"waited {result['waited_seconds']}s")
                output["message"] = " — ".join(parts)
                # If a target database was requested, repoint the saved
                # connection (if any) so psql/the Python driver reach it.
                if args.database:
                    conn_name = args.connection_name if args.connection_name != "default" else args.instance_name.lower()
                    if repoint_connection_database(conn_name, args.database):
                        output["message"] += (
                            f" — connection '{conn_name}' now targets database '{args.database}'"
                        )
            else:
                output["success"] = False
                output["message"] = result.get("error", "Failed to reach READY state")
            output["data"] = result

        # Handle --create: Create Postgres instance via Snowflake
        elif args.create:
            if not args.instance_name:
                print("❌ --instance-name is required for --create", file=sys.stderr)
                sys.exit(1)
            if not args.compute_pool:
                print("❌ --compute-pool is required for --create", file=sys.stderr)
                sys.exit(1)
            if not args.storage:
                print("❌ --storage is required for --create", file=sys.stderr)
                sys.exit(1)
            if args.role != "snowflake_admin":
                print("❌ --role is for --reset, not --create (CREATE creates all roles automatically)", file=sys.stderr)
                sys.exit(1)
            
            result = create_postgres_instance(
                instance_name=args.instance_name,
                compute_pool=args.compute_pool,
                storage=args.storage,
                enable_ha=args.enable_ha,
                postgres_version=args.postgres_version,
                network_policy=args.network_policy,
                auth_authority=args.auth_authority,
                storage_integration=args.storage_integration,
                postgres_settings=args.postgres_settings,
                comment=args.comment,
                snowflake_connection=args.snowflake_connection,
                authenticator=args.authenticator,
                role=args.use_role,
                database=args.database,
            )

            probe = result.get("probe") or {}
            probe_status = probe.get("status", "unknown")
            output["data"] = {
                "host": result["host"],
                "probe_status": probe_status,
                "network_policy_set": result.get("network_policy_set", False),
            }

            cert_line = (
                "✅ CA certificate saved, sslmode=verify-ca\n"
                if result.get("cert_path")
                else "⚠️  CA certificate not available, using sslmode=require\n"
            )

            # Probe-driven next-step guidance for the agent. The four branches
            # map to distinct follow-up actions the agent should take.
            # KEEP IN SYNC: these status keywords ("Port 5432 reachable",
            # "Port 5432 not reachable (timed out)", "Port 5432 refused",
            # "Host DNS not propagated") are referenced by
            # manage/SKILL.md Step 7's probe-outcome table. If you change the
            # wording here, update that table too and run tests/test_pg_connect
            # to confirm the probe-string assertions still pass.
            if probe_status == "reachable":
                next_step = (
                    "✅ Port 5432 reachable — instance ready for psql\n"
                    f"   Connect with: psql \"service={result['connection_name']} connect_timeout=10\""
                )
            elif probe_status == "timeout":
                next_step = (
                    "⚠️  Port 5432 not reachable (timed out)\n"
                    "   Likely cause: no network policy allowing this IP.\n"
                    "   REQUIRED NEXT STEP (agent must offer this): set up a network policy.\n"
                    "   psql will hang until a network policy is configured."
                )
            elif probe_status == "refused":
                next_step = (
                    "⏳ Port 5432 refused — instance still provisioning\n"
                    "   Agent next step: run --ensure-ready to wait for READY state,\n"
                    "   then offer network policy setup before psql is used."
                )
            elif probe_status == "dns_error":
                next_step = (
                    "⏳ Host DNS not propagated yet\n"
                    "   Agent next step: wait 30-60s, then run --ensure-ready\n"
                    "   before attempting psql connections."
                )
            else:
                next_step = (
                    f"⚠️  TCP probe inconclusive: {probe.get('message', 'unknown')}\n"
                    "   Agent next step: run --ensure-ready before psql."
                )

            output["message"] = (
                f"Created instance {result['instance_name']}\n"
                f"   Host: {result['host']}\n"
                f"✅ Connection saved to ~/.pg_service.conf\n"
                f"✅ Password saved to ~/.pgpass\n"
                f"{cert_line}"
                f"{next_step}"
            )
        
        # Handle --reset: Reset credentials via Snowflake
        elif args.reset:
            if not args.instance_name:
                print("❌ --instance-name is required for --reset", file=sys.stderr)
                sys.exit(1)
            
            result = reset_postgres_access(
                instance_name=args.instance_name,
                role=args.role,
                host=args.host,
                snowflake_connection=args.snowflake_connection,
                authenticator=args.authenticator,
                use_role=args.use_role,
                database=args.database,
            )
            if result["success"]:
                cert_line = ""
                if result.get("cert_upgraded"):
                    cert_line = "✅ CA certificate saved, upgraded to sslmode=verify-ca\n"
                output["message"] = (
                    f"Reset credentials for {result['instance_name']} ({result['role']})\n"
                    f"✅ Password updated in ~/.pgpass\n"
                    f"{cert_line}"
                    f"   Connect with: psql \"service={result['connection_name']}\""
                )
            else:
                output["success"] = False
                output["message"] = (
                    f"{result['message']}\n"
                    f"Response saved to: {result['tmp_path']}\n"
                    f"Run: pg_connect.py --from-reset-response {result['tmp_path']} --connection-name {args.instance_name.lower()}"
                )
        
        # Handle --fetch-cert: Fetch CA cert and upgrade service entry to verify-ca
        elif args.fetch_cert:
            if not args.instance_name:
                print("❌ --instance-name is required for --fetch-cert", file=sys.stderr)
                sys.exit(1)
            
            connection_name = args.connection_name if args.connection_name != "default" else args.instance_name.lower()
            cert_path = ensure_cert(
                instance_name=args.instance_name,
                connection_name=connection_name,
                snowflake_connection=args.snowflake_connection,
                authenticator=args.authenticator,
                role=args.use_role,
            )
            if cert_path:
                # Update service entry with cert if it exists
                service = get_service_entry(connection_name)
                if service:
                    save_service_entry(connection_name, service, sslrootcert=str(cert_path))
                    output["message"] = (
                        f"Certificate saved to {cert_path}\n"
                        f"✅ Service entry '{connection_name}' updated: sslmode=verify-ca\n"
                        f"   Connect with: psql \"service={connection_name}\""
                    )
                else:
                    output["message"] = (
                        f"Certificate saved to {cert_path}\n"
                        f"⚠️  No service entry '{connection_name}' found to update.\n"
                        f"   Add sslrootcert={cert_path} and sslmode=verify-ca to your connection."
                    )
                output["data"] = {"cert_path": str(cert_path)}
            else:
                output["success"] = False
                output["message"] = (
                    f"No certificate found in DESCRIBE output for {args.instance_name}.\n"
                    "The certificate field may not be available for this instance."
                )
        
        # Handle --upgrade-ssl: Batch upgrade all connections without cert verification
        elif args.upgrade_ssl:
            names = list_connections()
            upgraded = []
            skipped = []
            failed = []
            for name in names:
                entry = get_service_entry(name)
                if not entry:
                    continue
                if entry.get("sslrootcert"):
                    skipped.append(name)
                    continue
                # Use the connection name as both instance and cert identifier
                try:
                    cert_path = ensure_cert(
                        name.upper(), name,
                        args.snowflake_connection, args.authenticator,
                        args.use_role,
                    )
                    if cert_path:
                        save_service_entry(name, entry, sslrootcert=str(cert_path))
                        upgraded.append(name)
                    else:
                        failed.append(name)
                except Exception:
                    failed.append(name)

            lines = []
            if upgraded:
                lines.append(f"✅ Upgraded {len(upgraded)}: {', '.join(upgraded)}")
            if skipped:
                lines.append(f"⏭️  Already verified {len(skipped)}: {', '.join(skipped)}")
            if failed:
                lines.append(f"⚠️  Could not fetch cert for {len(failed)}: {', '.join(failed)}")
            if not names:
                lines.append("No saved connections found in ~/.pg_service.conf")
            output["message"] = "\n".join(lines)
            output["data"] = {"upgraded": upgraded, "skipped": skipped, "failed": failed}
        
        # Handle password update from reset response file
        elif hasattr(args, '_update_password_from_file'):
            if update_password(args.connection_name, args._update_password_from_file):
                output["message"] = (
                    f"Password for '{args.connection_name}' updated in ~/.pgpass\n"
                    f"Connect with: psql \"service={args.connection_name}\""
                )
            else:
                output["success"] = False
                output["message"] = f"Connection '{args.connection_name}' not found in ~/.pg_service.conf"
                
        elif args.list:
            names = list_connections()
            output["data"] = names
            output["message"] = f"Found {len(names)} saved connections in ~/.pg_service.conf"
            
        elif args.delete:
            if delete_connection(args.delete):
                output["message"] = f"Deleted connection '{args.delete}' from service file and pgpass"
            else:
                output["success"] = False
                output["message"] = f"Connection '{args.delete}' not found"

        elif args.test and not args.connection and not hasattr(args, '_params_from_args'):
            # --test against a saved connection name (no connection string supplied).
            # Works with any Postgres — Snowflake PG, Neon, Supabase, self-hosted, etc.
            lookup_name = args.connection_name
            params = get_connection(lookup_name)
            if not params:
                output["success"] = False
                if lookup_name == "default":
                    output["message"] = (
                        "--test needs either --connection <postgres://...> or "
                        "--connection-name <saved_name>. "
                        "Run --list to see saved connections."
                    )
                else:
                    output["message"] = (
                        f"No saved connection named '{lookup_name}'. "
                        "Run --list to see saved connections."
                    )
            else:
                success, msg = validate_connection(params)
                output["success"] = success
                output["message"] = msg
                if success:
                    secret_keys = {"password", "access_roles"}
                    display_params = {k: v for k, v in params.items() if k not in secret_keys}
                    display_params["has_password"] = bool(params.get("password"))
                    output["data"] = display_params

        elif args.connection or hasattr(args, '_params_from_args'):
            if hasattr(args, '_params_from_args'):
                params = args._params_from_args
            else:
                params = parse_connection_string(args.connection)

            # An explicit --database wins over the response/URL database so the
            # saved service entry + pgpass row point at the database the user's
            # tables actually live in. Left untouched when --database is omitted:
            # --from-response defaults to postgres, a URL keeps its own dbname.
            if args.database:
                params["database"] = args.database

            if args.test:
                success, msg = validate_connection(params)
                output["success"] = success
                output["message"] = msg
                
            if args.save and output["success"]:
                # Derive connection name from instance name when not explicitly set
                conn_name = args.connection_name
                if conn_name == "default" and args.instance_name:
                    conn_name = args.instance_name.lower()

                # If instance name is available (e.g. --from-response --instance-name),
                # fetch CA cert and save with verify-ca
                cert_path = None
                if args.instance_name:
                    try:
                        cert_path = ensure_cert(
                            args.instance_name, conn_name,
                            args.snowflake_connection, args.authenticator,
                            args.use_role,
                        )
                    except Exception:
                        pass

                save_result = save_connection(conn_name, params)

                # Upgrade the service entry with cert if fetched
                if cert_path:
                    entry = get_service_entry(conn_name)
                    if entry:
                        save_service_entry(conn_name, entry, sslrootcert=str(cert_path))

                if output["success"]:
                    cert_line = ""
                    if cert_path:
                        cert_line = "  CA cert: sslmode=verify-ca\n"
                    if save_result["connection_existed"]:
                        output["message"] = (
                            f"Connection '{conn_name}' updated\n"
                            f"  Service file: ~/.pg_service.conf\n"
                            f"  Password: ~/.pgpass\n"
                            f"{cert_line}"
                            f"Connect with: psql \"service={conn_name}\""
                        )
                    else:
                        output["message"] = (
                            f"Connection '{conn_name}' saved\n"
                            f"  Service file: ~/.pg_service.conf\n"
                            f"  Password: ~/.pgpass\n"
                            f"{cert_line}"
                            f"Connect with: psql \"service={conn_name}\""
                        )
                
            if output["success"]:
                # Filter out secrets from display output
                secret_keys = {"password", "access_roles"}
                display_params = {k: v for k, v in params.items() if k not in secret_keys}
                display_params["has_password"] = bool(params.get("password"))
                output["data"] = display_params
            
        else:
            names = list_connections()
            if names:
                output["data"] = {"saved_connections": names}
                output["message"] = (
                    "Connections stored in:\n"
                    "  ~/.pg_service.conf (connection profiles)\n"
                    "  ~/.pgpass (passwords)\n"
                    "Use --connection to add or --list to see saved"
                )
            else:
                output["message"] = (
                    "No saved connections.\n"
                    "Use --connection to add one, or manually edit:\n"
                    "  ~/.pg_service.conf (connection profiles)\n"
                    "  ~/.pgpass (passwords, chmod 600)"
                )
                
    except ValueError as e:
        output["success"] = False
        output["message"] = sanitize_error(str(e), vars(args) if hasattr(args, "__dict__") else {})
    except Exception as e:
        output["success"] = False
        hint = translate_snowflake_error(e, current_role=args.use_role)
        error_msg = sanitize_error(str(e), vars(args) if hasattr(args, '__dict__') else {})
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        if hint:
            output["message"] = f"Error: {type(e).__name__}: {error_msg}\n\n{hint}"
        else:
            output["message"] = f"Error: {type(e).__name__}: {error_msg}"
    
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        if output["message"]:
            prefix = "✅" if output["success"] else "❌"
            print(f"{prefix} {output['message']}")
        if output["data"]:
            if isinstance(output["data"], list):
                for item in output["data"]:
                    print(f"  - {item}")
            elif isinstance(output["data"], dict):
                # Never print secret fields even if they somehow got into output
                secret_fields = {"password", "access_roles"}
                for k, v in output["data"].items():
                    if k not in secret_fields:
                        print(f"  {k}: {v}")
    
    sys.exit(0 if output["success"] else 1)


if __name__ == "__main__":
    main()
