#!/usr/bin/env python3
"""
Snowflake storage integration management for pg_lake (AWS/S3).

Handles CREATE/DESCRIBE/ATTACH/DETACH/DROP of Snowflake storage integrations
used by pg_lake for S3 access. Sensitive output (IAM ARN, external ID) is
written to secure temp files — never printed to stdout.

Scope: this script is AWS/S3-specific (IAM role ARN trust policy, s3:// locations,
check-aws/update-aws subcommands). Azure pg_lake instances use a different
storage integration shape (Azure tenant + consent URL instead of an IAM role).
For Azure instances, see
https://docs.snowflake.com/en/user-guide/data-load-azure-config and run the
Azure CREATE STORAGE INTEGRATION / ALTER SQL directly via snowflake-connector
or SnowSQL.

Connection: Uses ~/.snowflake/connections.toml (same as pg_connect.py).
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    import snowflake.connector
except ImportError:
    snowflake = None

# Make ./shared/ importable when this script is run directly (pytest already
# injects it via pythonpath). Mirrors the bootstrap in pg_lake_catalog.py /
# pg_connect.py. Without this, the lazy `from sf_session import ...` calls
# below raise ModuleNotFoundError when the CLI fallback path fires for a
# direct invocation (Windows ARM64 testing).
_SHARED_DIR = Path(__file__).resolve().parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))


# Portable Snowflake-query exception tuple. Both backends surface DDL
# rejection ("already exists", "does not exist", privilege errors, etc.)
# with the same message text — call sites just need a tuple they can
# `except` against without caring which backend ran the query.
def _snowflake_query_errors() -> tuple:
    from sf_session import SnowflakeError
    if snowflake is not None:
        return (snowflake.connector.errors.ProgrammingError, SnowflakeError)
    return (SnowflakeError,)

# Valid unquoted Snowflake identifier: starts with letter/underscore
_UNQUOTED_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

_ARN_RE = re.compile(r"^arn:aws:iam::\d+:role/[\w+=,.@/-]+$")
_S3_LOCATION_RE = re.compile(r"^s3://[a-z0-9][\w.\-]{1,61}[a-z0-9](/[\w.\-/]*)?$")


def _validate_arn(arn: str) -> str:
    """Validate an AWS IAM role ARN to prevent SQL injection in DDL."""
    if not _ARN_RE.match(arn):
        raise ValueError(
            f"Invalid IAM role ARN format: {arn!r}. "
            f"Expected: arn:aws:iam::<account-id>:role/<role-name>. "
            f"This command is AWS-specific; for Azure pg_lake instances, see "
            f"https://docs.snowflake.com/en/user-guide/data-load-azure-config "
            f"and run the Azure CREATE STORAGE INTEGRATION SQL directly."
        )
    return arn


def _validate_s3_location(loc: str) -> str:
    """Validate an S3 location to prevent SQL injection in DDL."""
    if not _S3_LOCATION_RE.match(loc):
        raise ValueError(
            f"Invalid S3 location format: {loc!r}. "
            f"Expected: s3://<bucket>/<optional-prefix>/. "
            f"This command accepts S3 (AWS) locations only; for Azure "
            f"(azure://) or GCS locations, see the Snowflake storage "
            f"integration docs for the current cross-cloud support matrix."
        )
    return loc


def _quote_identifier(name: str) -> str:
    """Safely quote a Snowflake identifier to prevent SQL injection."""
    if not name:
        raise ValueError("Identifier cannot be empty")
    if any(c in name for c in [";", "--", "/*", "*/"]):
        raise ValueError("Invalid identifier: contains prohibited characters")
    if _UNQUOTED_IDENTIFIER_RE.match(name):
        return name
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _write_secure_json(data: dict) -> str:
    """Write JSON to a temp file with 0600 permissions. Returns file path."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="pg_lake_", dir="/tmp")
    fd_owned = False
    try:
        with os.fdopen(fd, "w") as f:
            fd_owned = True
            json.dump(data, f, indent=2)
        os.chmod(path, 0o600)
    except Exception:
        if not fd_owned:
            os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


# ---------------------------------------------------------------------------
# Snowflake connection
# ---------------------------------------------------------------------------

def get_snowflake_connection(
    connection_name: str | None = None,
):
    """
    Get a Snowflake connection. Returns a `connector.SnowflakeConnection`
    on the connector backend, or a `sf_session._SessionConnAdapter` on the
    `snow` CLI backend — both expose the `.cursor()` / `.fetchall()` /
    `.description` / `.close()` surface this module relies on.

    Priority:
    1. Environment variables (SNOWFLAKE_ACCOUNT + SNOWFLAKE_USER)
       — connector backend only; gated by `check_snowflake_connector`.
    2. Named connection from ~/.snowflake/connections.toml
       — works on both backends via `sf_session.open_snowflake_connection`.

    For key-pair (private_key_path) or OAuth (token_file_path) auth on the
    connector backend, `pg_connect.get_snowflake_connection` (called
    transitively by `open_snowflake_connection`) loads the key / token
    before passing to `snowflake.connector.connect` — the Python
    connector's SNOWFLAKE_JWT auth does not accept paths directly. On the
    CLI backend snow handles those auth flows natively via the
    connections.toml entry, so no extra wiring is needed here.
    """
    env_account = os.environ.get("SNOWFLAKE_ACCOUNT")
    env_user = os.environ.get("SNOWFLAKE_USER")
    if env_account and env_user:
        from pg_common import check_snowflake_connector
        check_snowflake_connector()
        connect_args = {"account": env_account, "user": env_user}
        if os.environ.get("SNOWFLAKE_AUTHENTICATOR"):
            connect_args["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
        elif os.environ.get("SNOWFLAKE_PASSWORD"):
            connect_args["password"] = os.environ["SNOWFLAKE_PASSWORD"]
        return snowflake.connector.connect(**connect_args)

    from sf_session import open_snowflake_connection
    return open_snowflake_connection(connection=connection_name)


# ---------------------------------------------------------------------------
# Storage integration operations
# ---------------------------------------------------------------------------

def create_storage_integration(
    sf_conn,
    name: str,
    role_arn: str,
    locations: list[str],
) -> dict:
    """
    Create a Snowflake storage integration for pg_lake (POSTGRES_EXTERNAL_STORAGE).

    The integration type POSTGRES_EXTERNAL_STORAGE is specific to Snowflake Postgres
    pg_lake — it is NOT the same as EXTERNAL_STAGE used for regular Snowflake stages.
    """
    safe_name = _quote_identifier(name)
    _validate_arn(role_arn)
    for loc in locations:
        _validate_s3_location(loc)
    locations_str = ",".join(f"'{loc}'" for loc in locations)

    sql = f"""
        CREATE STORAGE INTEGRATION {safe_name}
            TYPE = POSTGRES_EXTERNAL_STORAGE
            STORAGE_PROVIDER = 'S3'
            ENABLED = TRUE
            STORAGE_AWS_ROLE_ARN = '{role_arn}'
            STORAGE_ALLOWED_LOCATIONS = ({locations_str})
    """

    try:
        with sf_conn.cursor() as cur:
            cur.execute(sql)
    except _snowflake_query_errors() as e:
        if "already exists" in str(e):
            return {
                "success": False,
                "action": "create",
                "name": name,
                "already_exists": True,
                "error": f"Integration '{name}' already exists.",
                "hint": "Use 'describe' to get its IAM values, or 'drop' first to recreate it.",
            }
        raise

    return {
        "success": True,
        "action": "create",
        "name": name,
        "type": "POSTGRES_EXTERNAL_STORAGE",
        "role_arn": role_arn,
        "locations": locations,
        "trust_policy_note": (
            "This integration has a fresh STORAGE_AWS_IAM_USER_ARN and "
            "STORAGE_AWS_EXTERNAL_ID. If you recreated an existing integration, the "
            "old IAM trust-policy entries are now stale and S3 access will fail "
            "silently. Run 'describe --name %s' and (re)apply the trust policy with "
            "the new values before using pg_lake." % name
        ),
    }


def describe_integration(sf_conn, name: str) -> dict:
    """
    Describe a storage integration and extract IAM values.

    SENSITIVE: The returned IAM_USER_ARN and EXTERNAL_ID are written to a
    secure temp file (0600 permissions) — never printed to stdout. The user
    needs these values to update the AWS IAM trust policy.
    """
    safe_name = _quote_identifier(name)

    with sf_conn.cursor() as cur:
        cur.execute(f"DESCRIBE INTEGRATION {safe_name}")
        rows = cur.fetchall()

    properties = {}
    for row in rows:
        prop_name = row[0] if row[0] else ""
        prop_type = row[1] if len(row) > 1 else ""
        prop_value = row[2] if len(row) > 2 else ""
        prop_default = row[3] if len(row) > 3 else ""
        properties[prop_name] = {
            "type": prop_type,
            "value": prop_value,
            "default": prop_default,
        }

    # Extract the IAM values the user needs for the trust policy
    iam_user_arn = properties.get("STORAGE_AWS_IAM_USER_ARN", {}).get("value", "")
    external_id = properties.get("STORAGE_AWS_EXTERNAL_ID", {}).get("value", "")

    # Write sensitive values to secure temp file
    sensitive_data = {
        "integration_name": name,
        "STORAGE_AWS_IAM_USER_ARN": iam_user_arn,
        "STORAGE_AWS_EXTERNAL_ID": external_id,
        "instructions": (
            "Update your IAM role trust policy with these values. "
            "Set the Principal AWS ARN to STORAGE_AWS_IAM_USER_ARN "
            "and the sts:ExternalId to STORAGE_AWS_EXTERNAL_ID. "
            "Also ensure the IAM role has a Maximum session duration of 12 hours."
        ),
    }
    secure_path = _write_secure_json(sensitive_data)

    return {
        "success": True,
        "action": "describe",
        "name": name,
        "properties_count": len(properties),
        "sensitive_values_file": secure_path,
        "has_iam_values": bool(iam_user_arn and external_id),
    }


def attach_to_instance(sf_conn, instance: str, integration: str) -> dict:
    """
    Attach a storage integration to a Postgres instance.

    After attaching, pg_lake on the Postgres instance can access S3
    through the storage integration's IAM role.
    """
    safe_instance = _quote_identifier(instance)
    safe_integration = _quote_identifier(integration)

    sql = (
        f"ALTER POSTGRES INSTANCE {safe_instance} "
        f"SET STORAGE_INTEGRATION = {safe_integration}"
    )

    with sf_conn.cursor() as cur:
        cur.execute(sql)

    return {
        "success": True,
        "action": "attach",
        "instance": instance,
        "integration": integration,
    }


def verify_attachment(sf_conn, instance: str) -> dict:
    """
    Verify a storage integration is attached to a Postgres instance.

    Runs DESCRIBE POSTGRES INSTANCE and checks the storage_integration field.
    DESCRIBE returns key-value rows (property, value), not columnar data.
    """
    safe_instance = _quote_identifier(instance)

    with sf_conn.cursor() as cur:
        cur.execute(f"DESCRIBE POSTGRES INSTANCE {safe_instance}")
        rows = cur.fetchall()
        columns = [c[0].lower() for c in cur.description] if cur.description else []

    # DESCRIBE returns rows as (property, value) pairs
    # Build a dict from all property/value rows
    if columns == ["property", "value"]:
        result_dict = {row[0].lower(): row[1] for row in rows if row[0]}
    else:
        # Fallback for unexpected formats
        result_dict = dict(zip(columns, rows[0])) if rows else {}

    storage_integration = result_dict.get("storage_integration", "")
    # Allowlist — only return known-safe fields. DESCRIBE output can change
    # across releases and may include credentials in new fields.
    safe_keys = {
        "name", "owner", "owner_role_type", "created_on", "updated_on",
        "type", "host", "compute_family", "storage_size_gb",
        "postgres_version", "postgres_settings", "high_availability",
        "authentication_authority", "maintenance_window_start",
        "state", "comment", "origin", "replicas", "operations",
        "network_policy", "storage_integration",
    }
    safe_fields = {
        k: v for k, v in result_dict.items()
        if k in safe_keys
    }

    return {
        "success": True,
        "action": "verify",
        "instance": instance,
        "storage_integration": storage_integration or None,
        "is_attached": bool(storage_integration),
        "instance_info": safe_fields,
    }


def detach_from_instance(sf_conn, instance: str) -> dict:
    """Remove storage integration from a Postgres instance."""
    safe_instance = _quote_identifier(instance)

    sql = (
        f"ALTER POSTGRES INSTANCE {safe_instance} "
        f"UNSET STORAGE_INTEGRATION"
    )

    with sf_conn.cursor() as cur:
        cur.execute(sql)

    return {
        "success": True,
        "action": "detach",
        "instance": instance,
    }


def drop_integration(sf_conn, name: str) -> dict:
    """Drop a storage integration (cleanup)."""
    safe_name = _quote_identifier(name)

    with sf_conn.cursor() as cur:
        cur.execute(f"DROP STORAGE INTEGRATION IF EXISTS {safe_name}")

    return {
        "success": True,
        "action": "drop",
        "name": name,
    }


# ---------------------------------------------------------------------------
# AWS Trust Policy Check (boto3 preferred, AWS CLI fallback)
# ---------------------------------------------------------------------------

def _extract_role_name_from_arn(arn: str) -> str:
    """Extract role name from ARN like arn:aws:iam::123456:role/my-role."""
    match = re.match(r"^arn:aws:iam::\d+:role/(.+)$", arn)
    if not match:
        raise ValueError(f"Cannot extract role name from ARN: {arn}")
    return match.group(1)


def _check_trust_policy_boto3(
    role_name: str,
    expected_principal: str,
    expected_external_id: str,
    aws_profile: str | None = None,
) -> dict | None:
    """
    Check trust policy using boto3. Returns None if boto3 unavailable.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        return None

    try:
        session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
        iam = session.client("iam")
        response = iam.get_role(RoleName=role_name)
        role_info = response.get("Role", {})
    except NoCredentialsError:
        return {
            "success": False,
            "method": "boto3",
            "error": "No AWS credentials configured",
            "can_skip": True,
            "auth_error": True,
            "hint": "Try --aws-profile <PROFILE> or run: aws configure list-profiles",
        }
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        auth_codes = {"ExpiredToken", "ExpiredTokenException", "AccessDenied",
                      "InvalidClientTokenId", "UnrecognizedClientException"}
        is_auth = error_code in auth_codes
        result = {
            "success": False,
            "method": "boto3",
            "error": f"{error_code}: {error_msg}",
            "can_skip": True,
        }
        if is_auth:
            result["auth_error"] = True
            result["hint"] = (
                "AWS credentials expired or invalid. "
                "Try --aws-profile <PROFILE> or re-authenticate: "
                "aws sso login --profile <PROFILE>"
            )
        return result
    except Exception as e:
        return {
            "success": False,
            "method": "boto3",
            "error": str(e),
            "can_skip": True,
        }

    return _parse_role_info(role_info, expected_principal, expected_external_id, "boto3")


def _check_trust_policy_cli(
    role_name: str,
    expected_principal: str,
    expected_external_id: str,
    aws_profile: str | None = None,
) -> dict | None:
    """
    Check trust policy using AWS CLI. Returns None if CLI unavailable.
    """
    import shutil
    import subprocess

    if not shutil.which("aws"):
        return None

    cmd = ["aws", "iam", "get-role", "--role-name", role_name, "--output", "json"]
    if aws_profile:
        cmd.extend(["--profile", aws_profile])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "method": "aws-cli",
            "error": "AWS CLI timed out",
            "can_skip": True,
        }
    except Exception as e:
        return {
            "success": False,
            "method": "aws-cli",
            "error": str(e),
            "can_skip": True,
        }

    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        auth_keywords = ["ExpiredToken", "expired", "InvalidClientTokenId",
                         "NoCredentialProviders", "UnrecognizedClientException"]
        is_auth = any(kw.lower() in error_msg.lower() for kw in auth_keywords)
        resp = {
            "success": False,
            "method": "aws-cli",
            "error": error_msg,
            "can_skip": True,
        }
        if is_auth:
            resp["auth_error"] = True
            resp["hint"] = (
                "AWS credentials expired or invalid. "
                "Try --aws-profile <PROFILE> or re-authenticate: "
                "aws sso login --profile <PROFILE>"
            )
        return resp

    try:
        role_data = json.loads(result.stdout)
        role_info = role_data.get("Role", {})
    except json.JSONDecodeError:
        return {
            "success": False,
            "method": "aws-cli",
            "error": "Failed to parse AWS CLI output",
            "can_skip": True,
        }

    return _parse_role_info(role_info, expected_principal, expected_external_id, "aws-cli")


def _parse_role_info(
    role_info: dict,
    expected_principal: str,
    expected_external_id: str,
    method: str,
) -> dict:
    """Parse AWS role info and check trust policy configuration."""
    # Check max session duration (should be 43200 = 12 hours)
    max_session = role_info.get("MaxSessionDuration", 3600)
    max_session_ok = max_session >= 43200

    # Check trust policy for Snowflake principal and external ID
    trust_policy = role_info.get("AssumeRolePolicyDocument", {})
    statements = trust_policy.get("Statement", [])

    principal_found = False
    external_id_found = False
    external_id_matches = False

    for stmt in statements:
        if stmt.get("Effect") != "Allow":
            continue
        action = stmt.get("Action")
        if action != "sts:AssumeRole" and action != ["sts:AssumeRole"]:
            continue

        # Check principal
        principal = stmt.get("Principal", {})
        if isinstance(principal, dict):
            aws_principal = principal.get("AWS", "")
            if isinstance(aws_principal, list):
                principal_found = expected_principal in aws_principal
            else:
                principal_found = aws_principal == expected_principal
        elif isinstance(principal, str):
            principal_found = principal == expected_principal

        if not principal_found:
            continue

        # Check external ID in condition
        condition = stmt.get("Condition", {})
        string_equals = condition.get("StringEquals", {})
        ext_id_value = string_equals.get("sts:ExternalId", "")
        if ext_id_value:
            external_id_found = True
            external_id_matches = ext_id_value == expected_external_id

        break

    all_ok = principal_found and external_id_matches and max_session_ok

    return {
        "success": True,
        "method": method,
        "checks": {
            "principal_in_trust_policy": principal_found,
            "external_id_in_trust_policy": external_id_found,
            "external_id_matches": external_id_matches,
            "max_session_duration_seconds": max_session,
            "max_session_12_hours": max_session_ok,
        },
        "all_configured": all_ok,
        "needs_update": not all_ok,
    }


def check_aws_trust_policy(
    role_arn: str,
    expected_principal: str,
    expected_external_id: str,
    aws_profile: str | None = None,
) -> dict:
    """
    Check if AWS IAM role trust policy is already configured for Snowflake.

    Tries boto3 first, then AWS CLI. If boto3 is installed but fails (e.g.
    expired creds), still falls back to CLI. Returns cli_available so the
    agent knows whether it can offer to run update commands for the user.

    Checks:
    - Whether Snowflake's IAM user is in the trust policy
    - Whether the external ID matches
    - Whether max session duration is 12 hours (43200 seconds)
    """
    import shutil

    cli_available = bool(shutil.which("aws"))

    try:
        role_name = _extract_role_name_from_arn(role_arn)
    except ValueError as e:
        return {
            "success": False,
            "action": "check-aws",
            "error": str(e),
            "can_skip": True,
            "cli_available": cli_available,
        }

    def _enrich(result: dict) -> dict:
        result["action"] = "check-aws"
        result["role_arn"] = role_arn
        result["role_name"] = role_name
        result["cli_available"] = cli_available
        return result

    # Try boto3 first
    boto3_result = _check_trust_policy_boto3(
        role_name, expected_principal, expected_external_id, aws_profile
    )
    if boto3_result is not None and boto3_result.get("success"):
        return _enrich(boto3_result)

    # Fall back to CLI (even if boto3 was available but had auth issues)
    cli_result = _check_trust_policy_cli(
        role_name, expected_principal, expected_external_id, aws_profile
    )
    if cli_result is not None:
        return _enrich(cli_result)

    # Return boto3 failure if we got one (e.g. expired creds)
    if boto3_result is not None:
        return _enrich(boto3_result)

    # Neither available
    return {
        "success": False,
        "action": "check-aws",
        "role_arn": role_arn,
        "role_name": role_name,
        "error": "Neither boto3 nor AWS CLI available",
        "can_skip": True,
        "cli_available": False,
        "message": (
            "Cannot auto-check AWS trust policy. "
            "Install boto3 (`pip install boto3`) or AWS CLI to enable this check, "
            "or verify the trust policy manually in AWS Console."
        ),
    }


def _is_snowflake_trust_statement(statement: dict, principal_arn: str) -> bool:
    """Check if a trust policy statement is for a specific Snowflake principal."""
    if statement.get("Effect") != "Allow":
        return False
    action = statement.get("Action")
    if action != "sts:AssumeRole" and action != ["sts:AssumeRole"]:
        return False
    stmt_principal = statement.get("Principal", {})
    if isinstance(stmt_principal, dict):
        aws_val = stmt_principal.get("AWS", "")
        if isinstance(aws_val, list):
            return principal_arn in aws_val
        return aws_val == principal_arn
    return stmt_principal == principal_arn


def update_aws_trust_policy(
    role_arn: str,
    sensitive_file: str,
    aws_profile: str | None = None,
) -> dict:
    """
    Update AWS IAM role trust policy and session duration via AWS CLI.

    Reads STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID from the
    secure temp file created by `describe` — sensitive values never appear
    in shell commands or chat output.
    """
    import shutil
    import subprocess

    if not shutil.which("aws"):
        return {
            "success": False,
            "action": "update-aws",
            "error": "AWS CLI not installed",
        }

    try:
        with open(sensitive_file) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {
            "success": False,
            "action": "update-aws",
            "error": f"Cannot read sensitive file: {e}",
        }

    principal = data.get("STORAGE_AWS_IAM_USER_ARN")
    external_id = data.get("STORAGE_AWS_EXTERNAL_ID")
    if not principal or not external_id:
        return {
            "success": False,
            "action": "update-aws",
            "error": "Missing STORAGE_AWS_IAM_USER_ARN or STORAGE_AWS_EXTERNAL_ID in file",
        }

    try:
        role_name = _extract_role_name_from_arn(role_arn)
    except ValueError as e:
        return {"success": False, "action": "update-aws", "error": str(e)}

    snowflake_statement = {
        "Effect": "Allow",
        "Principal": {"AWS": principal},
        "Action": "sts:AssumeRole",
        "Condition": {
            "StringEquals": {"sts:ExternalId": external_id}
        },
    }

    profile_args = ["--profile", aws_profile] if aws_profile else []

    # Fetch existing trust policy so we merge, not replace
    get_result = subprocess.run(
        ["aws", "iam", "get-role", "--role-name", role_name,
         "--output", "json"] + profile_args,
        capture_output=True, text=True, timeout=30,
    )
    if get_result.returncode != 0:
        return {
            "success": False,
            "action": "update-aws",
            "step": "get_existing_policy",
            "error": get_result.stderr.strip(),
            "role_name": role_name,
        }

    try:
        existing_role = json.loads(get_result.stdout).get("Role", {})
        existing_policy = existing_role.get("AssumeRolePolicyDocument", {})
        existing_statements = existing_policy.get("Statement", [])
    except (json.JSONDecodeError, AttributeError):
        existing_statements = []

    # Remove any existing Snowflake statement for this principal to avoid duplicates
    merged_statements = [
        s for s in existing_statements
        if not _is_snowflake_trust_statement(s, principal)
    ]
    merged_statements.append(snowflake_statement)

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": merged_statements,
    }
    policy_path = _write_secure_json(trust_policy)

    try:
        # Part A: update trust policy (merged with existing statements)
        result = subprocess.run(
            ["aws", "iam", "update-assume-role-policy",
             "--role-name", role_name,
             "--policy-document", f"file://{policy_path}"] + profile_args,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "action": "update-aws",
                "step": "trust_policy",
                "error": result.stderr.strip(),
                "role_name": role_name,
            }

        # Part B: set max session duration to 12 hours
        result = subprocess.run(
            ["aws", "iam", "update-role",
             "--role-name", role_name,
             "--max-session-duration", "43200"] + profile_args,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "action": "update-aws",
                "step": "session_duration",
                "error": result.stderr.strip(),
                "role_name": role_name,
                "trust_policy_updated": True,
            }
    finally:
        try:
            os.unlink(policy_path)
        except OSError:
            pass

    return {
        "success": True,
        "action": "update-aws",
        "role_name": role_name,
        "trust_policy_updated": True,
        "max_session_duration_set": 43200,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Snowflake storage integration management for pg_lake",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  create     Create a POSTGRES_EXTERNAL_STORAGE integration
  describe   Get integration details (IAM values written to secure file)
  check-aws  Check if AWS trust policy is already configured (no Snowflake needed)
  update-aws Update trust policy and session duration via AWS CLI (no Snowflake needed)
  attach     Attach integration to a Postgres instance
  verify     Check if integration is attached to an instance
  detach     Remove integration from an instance
  drop       Drop a storage integration

Examples:
  %(prog)s create --name my_s3 --role-arn arn:aws:iam::123:role/myrole \\
    --locations s3://my-bucket/ --snowflake-connection my_conn --json

  %(prog)s describe --name my_s3 --snowflake-connection my_conn

  %(prog)s check-aws --role-arn arn:aws:iam::123:role/myrole \\
    --expected-principal arn:aws:iam::981625497706:user/snowflake-user \\
    --expected-external-id "ABC123_SFCRole=1_xyz" --json

  %(prog)s update-aws --role-arn arn:aws:iam::123:role/myrole \\
    --sensitive-file /tmp/pg_lake_abc123.json --json

  %(prog)s attach --instance my_pg --integration my_s3 \\
    --snowflake-connection my_conn

  %(prog)s verify --instance my_pg --snowflake-connection my_conn --json
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Shared connection argument
    def add_connection_arg(p):
        p.add_argument(
            "--snowflake-connection",
            help="Named connection from ~/.snowflake/connections.toml",
        )
        p.add_argument(
            "--json",
            action="store_true",
            help="Output as JSON",
        )

    # create
    p_create = subparsers.add_parser(
        "create",
        help="Create storage integration (AWS/S3)",
        description=(
            "Create a Snowflake storage integration for pg_lake S3 access. "
            "AWS/S3 only — Azure pg_lake instances use a different shape "
            "(tenant + consent URL). For Azure setup, see "
            "https://docs.snowflake.com/en/user-guide/data-load-azure-config"
        ),
    )
    p_create.add_argument("--name", required=True, help="Integration name")
    p_create.add_argument("--role-arn", required=True, help="AWS IAM role ARN")
    p_create.add_argument(
        "--locations",
        required=True,
        nargs="+",
        help="Allowed S3 locations (e.g., s3://bucket/path/)",
    )
    add_connection_arg(p_create)

    # describe
    p_describe = subparsers.add_parser(
        "describe", help="Describe integration (sensitive values to file)"
    )
    p_describe.add_argument("--name", required=True, help="Integration name")
    add_connection_arg(p_describe)

    # check-aws (no Snowflake connection needed)
    p_check_aws = subparsers.add_parser(
        "check-aws",
        help=(
            "Check AWS IAM trust policy is configured (uses boto3 or AWS CLI). "
            "AWS-only — Azure uses a different consent flow (no direct parallel in this script)."
        ),
    )
    p_check_aws.add_argument(
        "--role-arn", required=True, help="AWS IAM role ARN to check"
    )
    p_check_aws.add_argument(
        "--expected-principal",
        required=True,
        help="Expected Snowflake IAM user ARN (STORAGE_AWS_IAM_USER_ARN)",
    )
    p_check_aws.add_argument(
        "--expected-external-id",
        required=True,
        help="Expected external ID (STORAGE_AWS_EXTERNAL_ID)",
    )
    p_check_aws.add_argument(
        "--aws-profile", help="AWS CLI/SDK profile name (from ~/.aws/config)"
    )
    p_check_aws.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    # update-aws (no Snowflake connection needed)
    p_update_aws = subparsers.add_parser(
        "update-aws",
        help=(
            "Update AWS IAM trust policy and session duration via CLI. "
            "AWS-only — Azure uses a different consent flow (no direct parallel in this script)."
        ),
    )
    p_update_aws.add_argument(
        "--role-arn", required=True, help="AWS IAM role ARN to update"
    )
    p_update_aws.add_argument(
        "--sensitive-file",
        required=True,
        help="Path to describe output file containing IAM values",
    )
    p_update_aws.add_argument(
        "--aws-profile", help="AWS CLI/SDK profile name (from ~/.aws/config)"
    )
    p_update_aws.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    # attach
    p_attach = subparsers.add_parser(
        "attach", help="Attach integration to Postgres instance"
    )
    p_attach.add_argument("--instance", required=True, help="Postgres instance name")
    p_attach.add_argument(
        "--integration", required=True, help="Storage integration name"
    )
    add_connection_arg(p_attach)

    # verify
    p_verify = subparsers.add_parser(
        "verify", help="Verify integration attachment"
    )
    p_verify.add_argument("--instance", required=True, help="Postgres instance name")
    add_connection_arg(p_verify)

    # detach
    p_detach = subparsers.add_parser(
        "detach", help="Remove integration from instance"
    )
    p_detach.add_argument("--instance", required=True, help="Postgres instance name")
    add_connection_arg(p_detach)

    # drop
    p_drop = subparsers.add_parser("drop", help="Drop storage integration")
    p_drop.add_argument("--name", required=True, help="Integration name")
    add_connection_arg(p_drop)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle check-aws and update-aws separately (no Snowflake connection needed)
    if args.command in ("check-aws", "update-aws"):
        try:
            if args.command == "check-aws":
                result = check_aws_trust_policy(
                    args.role_arn,
                    args.expected_principal,
                    args.expected_external_id,
                    aws_profile=args.aws_profile,
                )
            else:
                result = update_aws_trust_policy(
                    args.role_arn,
                    args.sensitive_file,
                    aws_profile=args.aws_profile,
                )
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                _print_result(result)
            sys.exit(0 if result.get("success") else 1)
        except Exception as e:
            error = {"success": False, "error": str(e)}
            if args.json:
                print(json.dumps(error, indent=2))
            else:
                print(f"Error: {e}")
            sys.exit(1)

    # All other commands need Snowflake connection
    try:
        sf_conn = get_snowflake_connection(
            getattr(args, "snowflake_connection", None)
        )
    except Exception as e:
        error = {"success": False, "error": f"Snowflake connection failed: {e}"}
        if getattr(args, "json", False):
            print(json.dumps(error, indent=2))
        else:
            print(f"Snowflake connection failed: {e}")
        sys.exit(1)

    try:
        result = _dispatch(args, sf_conn)
        use_json = getattr(args, "json", False)

        if use_json:
            print(json.dumps(result, indent=2))
        else:
            _print_result(result)

        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        error = {"success": False, "error": str(e)}
        if getattr(args, "json", False):
            print(json.dumps(error, indent=2))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    finally:
        sf_conn.close()


def _dispatch(args, sf_conn) -> dict:
    """Route to the correct operation based on subcommand."""
    if args.command == "create":
        return create_storage_integration(
            sf_conn, args.name, args.role_arn, args.locations
        )
    elif args.command == "describe":
        return describe_integration(sf_conn, args.name)
    elif args.command == "attach":
        return attach_to_instance(sf_conn, args.instance, args.integration)
    elif args.command == "verify":
        return verify_attachment(sf_conn, args.instance)
    elif args.command == "detach":
        return detach_from_instance(sf_conn, args.instance)
    elif args.command == "drop":
        return drop_integration(sf_conn, args.name)
    else:
        raise ValueError(f"Unknown command: {args.command}")


def _print_result(result: dict) -> None:
    """Human-readable output for each action."""
    action = result.get("action", "unknown")

    if action == "create":
        print(f"Storage integration created: {result['name']}")
        print(f"  Type: {result['type']}")
        print(f"  Role ARN: {result['role_arn']}")
        print(f"  Locations: {', '.join(result['locations'])}")
        print(f"\nNext: Run 'describe --name {result['name']}' to get IAM values")

    elif action == "describe":
        print(f"Integration: {result['name']}")
        if result["has_iam_values"]:
            print(f"\nIAM values written to: {result['sensitive_values_file']}")
            print("  (file has 0600 permissions — only you can read it)")
            print("\nNext steps:")
            print("  1. Read the file to get STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID")
            print("  2. Update your IAM role trust policy with these values")
            print("  3. Set IAM role Maximum session duration to 12 hours")
        else:
            print("  No IAM values found — integration may not be configured correctly")

    elif action == "attach":
        print(f"Storage integration '{result['integration']}' attached to '{result['instance']}'")
        print(f"\nNext: Run 'verify --instance {result['instance']}' to confirm")

    elif action == "verify":
        if result["is_attached"]:
            print(f"Instance '{result['instance']}' has storage integration: {result['storage_integration']}")
        else:
            print(f"Instance '{result['instance']}' has no storage integration attached")

    elif action == "detach":
        print(f"Storage integration removed from '{result['instance']}'")

    elif action == "drop":
        print(f"Storage integration '{result['name']}' dropped")

    elif action == "check-aws":
        role_name = result.get("role_name", "unknown")
        cli_avail = result.get("cli_available", False)
        if not result.get("success"):
            error = result.get("error", "Unknown error")
            print(f"AWS check failed: {error}")
            if result.get("can_skip"):
                print("Check skipped — manual verification required")
        else:
            checks = result.get("checks", {})
            all_ok = result.get("all_configured", False)
            method = result.get("method", "unknown")
            print(f"AWS Trust Policy Check ({method})")
            print(f"  Role: {role_name}")
            print(f"  Principal configured: {checks.get('principal_in_trust_policy', False)}")
            print(f"  External ID matches: {checks.get('external_id_matches', False)}")
            print(f"  Max session duration: {checks.get('max_session_duration_seconds', 0)}s (need 43200)")
            print(f"  All configured: {all_ok}")
        print(f"  AWS CLI available: {cli_avail}")

    elif action == "update-aws":
        role_name = result.get("role_name", "unknown")
        if result.get("success"):
            print(f"AWS trust policy updated for {role_name}")
            print("  Trust policy: updated")
            print("  Max session duration: 12 hours (43200s)")
        else:
            step = result.get("step", "unknown")
            error = result.get("error", "Unknown error")
            print(f"AWS update failed at {step}: {error}")
            if result.get("trust_policy_updated"):
                print("  Note: trust policy was updated before failure")

    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
