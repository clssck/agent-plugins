#!/usr/bin/env python3
"""
Check current IP against a Snowflake network policy.

Uses snowflake-connector-python to query policy details and compares against
the current public IP address or a specified IP.

Connection options (in priority order):
1. CLI args: --account, --user, --password (or --authenticator for SSO)
2. Environment variables: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
3. Connection name from ~/.snowflake/connections.toml
"""

import argparse
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import urlopen

try:
    import snowflake.connector
except ImportError:
    snowflake = None

# Make ./shared/ importable when this script is run directly (pytest already
# injects it via pythonpath). Without this, the lazy `from sf_session import
# open_snowflake_connection` in get_connection() raises ModuleNotFoundError
# when the CLI fallback path fires for a direct invocation.
_SHARED_DIR = Path(__file__).resolve().parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))


SNOWFLAKE_CONFIG_DIR = Path.home() / ".snowflake"
CONNECTIONS_TOML = SNOWFLAKE_CONFIG_DIR / "connections.toml"

# Valid unquoted Snowflake identifier pattern
_UNQUOTED_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')


def quote_identifier(name: str) -> str:
    """
    Safely quote a Snowflake identifier to prevent SQL injection.
    
    - Valid unquoted identifiers are returned as-is
    - Others are double-quoted with internal quotes escaped
    """
    if not name:
        raise ValueError("Identifier cannot be empty")
    
    # Check for obviously malicious content
    if any(c in name for c in [';', '--', '/*', '*/']):
        raise ValueError("Invalid identifier: contains prohibited characters")
    
    # If it's a valid unquoted identifier, return as-is
    if _UNQUOTED_IDENTIFIER_RE.match(name):
        return name
    
    # Otherwise, quote it (escape internal double quotes by doubling them)
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def get_public_ip() -> str:
    """Fetch current public IP. Tries ifconfig.me first, falls back to ipify."""
    # Try ifconfig.me first
    try:
        with urlopen("https://ifconfig.me", timeout=5) as response:
            return response.read().decode("utf-8").strip()
    except Exception:
        pass
    
    # Fall back to ipify
    try:
        with urlopen("https://api.ipify.org", timeout=5) as response:
            return response.read().decode("utf-8").strip()
    except Exception as e:
        raise RuntimeError(f"Failed to get public IP: {e}")


def ip_in_cidr_list(ip: str, cidr_list: list[str]) -> bool:
    """Check if an IP address falls within any CIDR range in the list."""
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for cidr in cidr_list:
        cidr = cidr.strip().strip("'\"")
        if not cidr:
            continue
        try:
            if "/" not in cidr:
                cidr = f"{cidr}/32"
            network = ipaddress.ip_network(cidr, strict=False)
            if ip_obj in network:
                return True
        except ValueError:
            continue
    return False


def check_connection_config() -> dict:
    """
    Check what Snowflake connection options are available.
    
    Returns dict with: has_toml, has_env, toml_path, connections
    """
    result = {
        "has_toml": False,
        "has_env": False,
        "toml_path": str(CONNECTIONS_TOML),
        "connections": [],
        "env_vars": {},
    }
    
    # Check for connections.toml
    if CONNECTIONS_TOML.exists():
        result["has_toml"] = True
        try:
            # Parse toml to list connection names
            import tomllib
            with open(CONNECTIONS_TOML, "rb") as f:
                config = tomllib.load(f)
                result["connections"] = list(config.keys())
        except Exception:
            # If we can't parse, just note it exists
            pass
    
    # Check for environment variables
    env_vars = {
        "SNOWFLAKE_ACCOUNT": os.environ.get("SNOWFLAKE_ACCOUNT"),
        "SNOWFLAKE_USER": os.environ.get("SNOWFLAKE_USER"),
        "SNOWFLAKE_PASSWORD": os.environ.get("SNOWFLAKE_PASSWORD"),
        "SNOWFLAKE_AUTHENTICATOR": os.environ.get("SNOWFLAKE_AUTHENTICATOR"),
        "SNOWFLAKE_DEFAULT_CONNECTION_NAME": os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME"),
        "SNOWFLAKE_CONNECTION_NAME": os.environ.get("SNOWFLAKE_CONNECTION_NAME"),
    }
    result["env_vars"] = {k: v for k, v in env_vars.items() if v}
    result["has_env"] = bool(result["env_vars"].get("SNOWFLAKE_ACCOUNT"))
    
    return result


def print_connection_help(config: dict) -> None:
    """Print helpful guidance on setting up Snowflake connection."""
    print("\n❌ No Snowflake connection configuration found.\n")
    print("Options to connect:\n")
    
    print("1. **CLI Arguments** (one-time use):")
    print("   --account <account> --user <user> --password <password>")
    print("   Or for SSO: --account <account> --user <user> --authenticator externalbrowser\n")
    
    print("2. **Environment Variables**:")
    print("   export SNOWFLAKE_ACCOUNT=<org>-<account>")
    print("   export SNOWFLAKE_USER=<username>")
    print("   export SNOWFLAKE_PASSWORD=<password>")
    print("   # Or for SSO:")
    print("   export SNOWFLAKE_AUTHENTICATOR=externalbrowser\n")
    
    print("3. **Snowflake CLI** (recommended - creates ~/.snowflake/connections.toml):")
    print("   # Install: brew install snowflake-cli  OR  pip install snowflake-cli")
    print("   snow connection add\n")
    
    print("4. **Create config manually** (~/.snowflake/connections.toml):")
    print("   [default]")
    print("   account = \"<org>-<account>\"")
    print("   user = \"<username>\"")
    print("   password = \"<password>\"  # or use authenticator = \"externalbrowser\"\n")
    
    if config["connections"]:
        print(f"Found connections in {config['toml_path']}: {', '.join(config['connections'])}")
        print("Use --connection <name> to specify which one.\n")


def get_connection(
    connection_name: str | None = None,
    account: str | None = None,
    user: str | None = None,
    password: str | None = None,
    authenticator: str | None = None,
):
    """
    Get a Snowflake connection using available configuration.

    Priority:
    1. Direct args (account, user, password/authenticator) — connector backend only
    2. Environment variables                                — connector backend only
    3. Connection name from ~/.snowflake/connections.toml
       — works on both connector and `snow` CLI backends via sf_session

    Direct-args / env-var auth requires the Python connector — they have
    no `snow sql` equivalent. On Windows ARM64 (where the connector wheel
    is unavailable), use the saved-connection path instead.
    """
    # Direct args + env-var paths are connector-only auth flows. Keep
    # check_snowflake_connector here so WoA users get a clear "use a
    # saved connection" message instead of a NameError.
    if account and user:
        from pg_common import check_snowflake_connector
        check_snowflake_connector()
        connect_args = {
            "account": account,
            "user": user,
        }
        if authenticator:
            connect_args["authenticator"] = authenticator
        elif password:
            connect_args["password"] = password
        else:
            connect_args["password"] = os.environ.get("SNOWFLAKE_PASSWORD", "")
        return snowflake.connector.connect(**connect_args)

    env_account = os.environ.get("SNOWFLAKE_ACCOUNT")
    env_user = os.environ.get("SNOWFLAKE_USER")
    if env_account and env_user:
        from pg_common import check_snowflake_connector
        check_snowflake_connector()
        connect_args = {
            "account": env_account,
            "user": env_user,
        }
        if os.environ.get("SNOWFLAKE_AUTHENTICATOR"):
            connect_args["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
        elif os.environ.get("SNOWFLAKE_PASSWORD"):
            connect_args["password"] = os.environ["SNOWFLAKE_PASSWORD"]
        return snowflake.connector.connect(**connect_args)

    name = (
        connection_name
        or os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME")
        or os.environ.get("SNOWFLAKE_CONNECTION_NAME")
        or "default"
    )

    if not CONNECTIONS_TOML.exists():
        config = check_connection_config()
        print_connection_help(config)
        raise RuntimeError("No Snowflake connection configuration found")

    from sf_session import open_snowflake_connection
    return open_snowflake_connection(connection=name)


def parse_ip_list(value: str) -> list[str]:
    """Parse an IP list from Snowflake DESCRIBE output."""
    if not value or value.lower() in ("null", "none", ""):
        return []
    
    value = value.strip("[]")
    pattern = r"['\"]?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?)['\"]?"
    matches = re.findall(pattern, value)
    return matches


def get_network_policy(conn, policy_name: str) -> dict:
    """Fetch network policy details from Snowflake."""
    safe_name = quote_identifier(policy_name)
    query = f"DESCRIBE NETWORK POLICY {safe_name}"
    
    policy = {}
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur:
            name = row[0].lower() if row[0] else ""
            value = row[1] if len(row) > 1 else ""
            
            if name == "allowed_ip_list":
                policy["allowed_ip_list"] = parse_ip_list(str(value))
            elif name == "blocked_ip_list":
                policy["blocked_ip_list"] = parse_ip_list(str(value))
            elif name == "name":
                policy["name"] = value
    
    return policy


def check_ip_against_policy(
    ip: str, 
    policy_name: str, 
    connection_name: str | None = None,
    account: str | None = None,
    user: str | None = None,
    password: str | None = None,
    authenticator: str | None = None,
) -> dict:
    """Check if an IP address is allowed by a network policy."""
    conn = get_connection(connection_name, account, user, password, authenticator)
    try:
        policy = get_network_policy(conn, policy_name)
    finally:
        conn.close()
    
    allowed_list = policy.get("allowed_ip_list", [])
    blocked_list = policy.get("blocked_ip_list", [])
    
    is_in_allowed = ip_in_cidr_list(ip, allowed_list)
    is_in_blocked = ip_in_cidr_list(ip, blocked_list)
    
    result = {
        "ip": ip,
        "policy_name": policy_name,
        "in_allowed_list": is_in_allowed,
        "in_blocked_list": is_in_blocked,
        "allowed_ip_list": allowed_list,
        "blocked_ip_list": blocked_list,
    }
    
    if is_in_blocked:
        result["status"] = "BLOCKED"
        result["message"] = f"IP {ip} is explicitly blocked by the network policy"
        result["allowed"] = False
    elif is_in_allowed:
        result["status"] = "ALLOWED"
        result["message"] = f"IP {ip} is allowed by the network policy"
        result["allowed"] = True
    else:
        result["status"] = "NOT_ALLOWED"
        result["message"] = f"IP {ip} is not in the allowed list of the network policy"
        result["allowed"] = False
    
    return result


def main():
    from pg_common import configure_stdio_utf8
    configure_stdio_utf8()
    parser = argparse.ArgumentParser(
        description="Check if your IP is allowed by a Snowflake network policy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Connection options (in priority order):
  1. CLI args: --account, --user, --password (or --authenticator for SSO)
  2. Environment: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
  3. Config file: ~/.snowflake/connections.toml (--connection to specify name)

Examples:
  # Using connection from ~/.snowflake/connections.toml
  %(prog)s -p my_policy

  # Using specific connection name
  %(prog)s -p my_policy --connection prod

  # Using direct credentials
  %(prog)s -p my_policy --account myorg-myaccount --user myuser --password mypass

  # Using SSO
  %(prog)s -p my_policy --account myorg-myaccount --user myuser --authenticator externalbrowser
"""
    )
    parser.add_argument(
        "--policy-name", "-p",
        required=True,
        help="Name of the network policy to check against"
    )
    
    # Connection options
    conn_group = parser.add_argument_group("connection options")
    conn_group.add_argument(
        "--connection", "-c",
        help="Connection name from ~/.snowflake/connections.toml"
    )
    conn_group.add_argument(
        "--account",
        help="Snowflake account identifier (org-account)"
    )
    conn_group.add_argument(
        "--user",
        help="Snowflake username"
    )
    conn_group.add_argument(
        "--password",
        help="Snowflake password (or use SNOWFLAKE_PASSWORD env var)"
    )
    conn_group.add_argument(
        "--authenticator",
        help="Authentication method (e.g., 'externalbrowser' for SSO)"
    )
    
    # Other options
    parser.add_argument(
        "--ip",
        help="Specific IP to check (default: current public IP)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Check available connection options and exit"
    )
    
    args = parser.parse_args()
    
    # Check config mode
    if args.check_config:
        config = check_connection_config()
        print("Snowflake Connection Configuration\n")
        print(f"Config file: {config['toml_path']}")
        print(f"  Exists: {'✅' if config['has_toml'] else '❌'}")
        if config['connections']:
            print(f"  Connections: {', '.join(config['connections'])}")
        print("\nEnvironment variables:")
        if config['env_vars']:
            for k, v in config['env_vars'].items():
                # Mask password
                display = "****" if "PASSWORD" in k else v
                print(f"  {k}={display}")
        else:
            print("  (none set)")
        print(f"\nReady to connect: {'✅' if config['has_toml'] or config['has_env'] else '❌'}")
        if not config['has_toml'] and not config['has_env']:
            print_connection_help(config)
        sys.exit(0)
    
    try:
        # Get IP to check
        ip = args.ip if args.ip else get_public_ip()
        
        # Check against policy
        result = check_ip_against_policy(
            ip, 
            args.policy_name, 
            args.connection,
            args.account,
            args.user,
            args.password,
            args.authenticator,
        )
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            status_icon = {
                "ALLOWED": "✅",
                "BLOCKED": "❌",
                "NOT_ALLOWED": "⚠️"
            }.get(result["status"], "❓")
            
            print(f"{status_icon} {result['message']}")
            print(f"\n  Policy: {result['policy_name']}")
            print(f"  Your IP: {result['ip']}")
            print(f"  Allowed IPs: {', '.join(result['allowed_ip_list']) or 'none'}")
            if result["blocked_ip_list"]:
                print(f"  Blocked IPs: {', '.join(result['blocked_ip_list'])}")
            
            if not result["allowed"]:
                print("\n  💡 To add your IP, run:")
                print(f"     ALTER NETWORK POLICY {args.policy_name}")
                existing_ips = ", ".join(f"'{x}'" for x in result["allowed_ip_list"])
                new_ip = f"'{ip}/32'"
                all_ips = f"{existing_ips}, {new_ip}" if existing_ips else new_ip
                print(f"       SET ALLOWED_IP_LIST = ({all_ips});")
        
        sys.exit(0 if result["allowed"] else 1)
        
    except Exception as e:
        error = {"success": False, "error": str(e)}
        if args.json:
            print(json.dumps(error, indent=2))
        else:
            print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
