#!/usr/bin/env python3
"""Shared PostgreSQL driver + connection helpers for snowflake-postgres scripts.

Provides dual-driver detection (psycopg2 preferred, pg8000 fallback), connection
builders that accept parsed argparse Namespaces, and argparse wiring for the
source/target host/port/db/user/password/sslmode flag families.

Ported verbatim from the upstream pg-to-spg-migration skill (scripts/pg_common.py).
Behavior is locked in by the test suite in tests/test_pg_common.py — including
the port-type asymmetry between psycopg2 and pg8000, the PGPASSWORD-shadows-
SOURCE_PGPASSWORD fallback, and the eager int cast of SOURCE_PGPORT/TARGET_PGPORT
at add_*_args() call time. Do not alter those behaviors without updating the
contract tests in lockstep.

Two helpers are additions for this repo:
  - check_psql(): surface a clear hint when the psql CLI is missing
  - add_use_role_arg(): shared --use-role plumbing for Snowflake session role
    overrides (mirrors the pattern already in pg_connect.py)

Module-level aliases for portable exception handling across drivers:
  - PgError: psycopg2.Error or pg8000.dbapi.Error (or Exception as fallback)
  - PgOperationalError: psycopg2.OperationalError or pg8000.dbapi.InterfaceError
"""
import argparse
import configparser
import os
import shutil
import sys
from pathlib import Path

try:
    import psycopg2
    DB_DRIVER = 'psycopg2'
    PgError = psycopg2.Error
    PgOperationalError = psycopg2.OperationalError
except ImportError:
    psycopg2 = None
    try:
        import pg8000
        import pg8000.dbapi
        DB_DRIVER = 'pg8000'
        PgError = pg8000.dbapi.Error
        PgOperationalError = pg8000.dbapi.InterfaceError
    except ImportError:
        pg8000 = None
        DB_DRIVER = None
        PgError = Exception
        PgOperationalError = Exception


def check_driver():
    if DB_DRIVER is None:
        print("ERROR: No PostgreSQL driver found.", file=sys.stderr)
        print("Install one of:", file=sys.stderr)
        print("  pip install psycopg2-binary", file=sys.stderr)
        print("  pip install pg8000", file=sys.stderr)
        if _is_managed_python():
            print("", file=sys.stderr)
            print("NOTE: Your Python appears to be managed by Homebrew or a system package manager.", file=sys.stderr)
            print("You may need to create a virtual environment first:", file=sys.stderr)
            print("  python3 -m venv ~/.pg_migration_venv", file=sys.stderr)
            print("  source ~/.pg_migration_venv/bin/activate", file=sys.stderr)
            print("  pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)


def _is_managed_python():
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--dry-run', 'pip'],
            capture_output=True, text=True, timeout=5
        )
        return 'externally-managed' in result.stderr.lower()
    except Exception:
        return False


def configure_stdio_utf8():
    """Reconfigure stdout/stderr to UTF-8 on native Windows.

    Windows consoles default to cp1252 which can't encode emoji (used in
    human-readable output from pg_connect, pg_doctor, network_policy_check).
    POSIX hosts (macOS, Linux, WSL) already use UTF-8 — early-return so the
    `errors="replace"` policy doesn't silently mask UnicodeEncodeErrors on
    those platforms.
    """
    if os.name != "nt":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def check_snowflake_connector():
    """Verify snowflake-connector-python is importable.

    Gates the connector-only auth flows — direct account/user/password args
    and `SNOWFLAKE_*` env vars — which have no `snow sql` equivalent. On
    Windows ARM64 the connector has no pre-built wheel and is skipped at
    install time, so this gives an actionable message instead of a confusing
    AttributeError. Saved-connection paths route through
    `sf_session.SnowflakeSession` and need no connector — they fall back to
    the `snow` CLI. See `references/windows.md`.
    """
    try:
        import snowflake.connector  # noqa: F401
    except ImportError:
        print("ERROR: snowflake-connector-python is not installed.", file=sys.stderr)
        print("This package has no pre-built wheel for Windows ARM64.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Direct-args and SNOWFLAKE_* env-var auth require the connector;", file=sys.stderr)
        print("they have no `snow sql` equivalent. Use a saved connection instead,", file=sys.stderr)
        print("which works without the connector via the snow CLI fallback:", file=sys.stderr)
        print("  1. Save it once with `snow connection add` (or via Snowsight),", file=sys.stderr)
        print("     so it lands in ~/.snowflake/connections.toml", file=sys.stderr)
        print("  2. Re-run with --snowflake-connection NAME", file=sys.stderr)
        print("", file=sys.stderr)
        print("See references/windows.md for details.", file=sys.stderr)
        sys.exit(1)


def check_psql():
    """Verify the psql CLI is on PATH.

    Scripts that shell out to psql (dump/restore, connectivity probes) should
    call this at entry to fail fast with an actionable message rather than
    letting subprocess bubble up a cryptic FileNotFoundError.
    """
    if shutil.which("psql") is None:
        print("ERROR: psql CLI not found on PATH.", file=sys.stderr)
        print("Install PostgreSQL client tools:", file=sys.stderr)
        print("  macOS:  brew install libpq && brew link --force libpq", file=sys.stderr)
        print("  Debian: apt-get install postgresql-client", file=sys.stderr)
        print("  RHEL:   dnf install postgresql", file=sys.stderr)
        sys.exit(1)


def connect(host, port, dbname, user, password, sslmode=None, sslrootcert=None,
            hostaddr=None, connect_timeout=None, options=None):
    """Driver-agnostic connect.

    sslrootcert: filesystem path to a CA certificate. Required for
    sslmode=verify-ca / verify-full when connecting to Snowflake Postgres
    (which fetches the per-instance CA on first connection and stores the
    path in the ~/.pg_service.conf entry). The argument is honored on both
    drivers:
      - psycopg2: passed through as the libpq sslrootcert kwarg.
      - pg8000:   loaded into the ssl.SSLContext via cafile=. For
                  sslmode=verify-ca the hostname check is disabled (verify
                  the cert chain only); for verify-full it is left enabled
                  (the libpq default behavior we are mirroring).

    hostaddr: optional literal IP for libpq DNS-bypass flows. This is
    forwarded only on the psycopg2/libpq path. pg8000 does not expose an
    equivalent parameter, so the fallback driver continues to use `host`.

    connect_timeout: seconds before connect attempt gives up. Translated
    per driver: psycopg2 receives `connect_timeout=`, pg8000 receives
    `timeout=` (available since pg8000 1.30).

    options: libpq GUC-setting string (e.g. "-c statement_timeout=5000").
    Forwarded on psycopg2 only. pg8000 has no equivalent — callers needing
    post-connect parity should issue SET SQL directly.
    """
    check_driver()
    if DB_DRIVER == 'psycopg2':
        kw = dict(host=host, port=port, database=dbname, user=user, password=password)
        if hostaddr:
            kw['hostaddr'] = hostaddr
        if sslmode:
            kw['sslmode'] = sslmode
        if sslrootcert:
            kw['sslrootcert'] = sslrootcert
        if connect_timeout is not None:
            kw['connect_timeout'] = connect_timeout
        if options is not None:
            kw['options'] = options
        return psycopg2.connect(**kw)
    else:
        kw = dict(host=host, port=int(port), database=dbname, user=user, password=password)
        if sslmode and sslmode != 'disable':
            import ssl
            ctx = ssl.create_default_context(cafile=sslrootcert) if sslrootcert else ssl.create_default_context()
            if sslmode in ('require', 'prefer', 'allow'):
                # libpq require = encrypt only, no cert verification
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            elif sslmode == 'verify-ca':
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_REQUIRED
            # verify-full: leave defaults (check_hostname=True, CERT_REQUIRED)
            kw['ssl_context'] = ctx
        if connect_timeout is not None:
            kw['timeout'] = connect_timeout
        return pg8000.connect(**kw)


def query(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    if cur.description:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    return []


def scalar(conn, sql, params=None):
    rows = query(conn, sql, params)
    if rows:
        vals = list(rows[0].values())
        return vals[0] if vals else None
    return None


def detect_pg_version(conn):
    ver = scalar(conn, "SELECT current_setting('server_version_num')::int")
    return int(ver) if ver else 0


def quote_ident(name):
    """Standard PostgreSQL identifier quoting: wrap in `"`, double any embedded `"`.

    Use for schema/table/column names interpolated into f-strings (where %s
    placeholders won't work because Postgres rejects parameterised identifiers).
    Names that come from `pg_catalog` are still trusted, but quoting protects
    against mixed-case identifiers, reserved words, and embedded quotes.
    """
    return '"' + str(name).replace('"', '""') + '"'


def quote_qualified(name):
    """Quote a qualified identifier `schema.table` (or just `table`).

    Splits on the FIRST `.` only. Does not handle pathological names with `.`
    inside an unquoted segment — caller should pass `(schema, table)` tuples
    via `quote_ident` for those.
    """
    parts = str(name).split('.', 1)
    return '.'.join(quote_ident(p) for p in parts)


def quote_literal(value):
    """Standard PostgreSQL string-literal quoting.

    Use ONLY for SQL contexts that don't accept %s parameters (notably
    `pg_drop_replication_slot('name')` whose argument is a literal name, and
    SQL string-templated tools). Prefer %s + params for everything else.
    """
    return "'" + str(value).replace("'", "''") + "'"


# Single source of truth for the Snowflake Postgres supported-extension
# allowlist. Imported by run_assessment, validate_schema_compatibility, and
# prepare_target so the three never drift. All comparisons are case-insensitive
# (callers should `.lower()` their inputs before checking membership).
SUPPORTED_EXTENSIONS = frozenset({
    'plpgsql', 'pgvector', 'vector', 'postgis', 'postgis_topology', 'postgis_raster',
    'postgis_sfcgal', 'postgis_tiger_geocoder', 'pgrouting', 'h3',
    'pg_cron', 'pg_partman', 'pglogical', 'hstore', 'uuid-ossp', 'pg_uuidv7',
    'pg_trgm', 'btree_gin', 'btree_gist', 'pg_stat_statements', 'pgcrypto',
    'citext', 'cube', 'isn', 'lo', 'ltree', 'seg', 'semver',
    'fuzzystrmatch', 'earthdistance', 'tablefunc', 'unaccent',
    'pg_buffercache', 'pgstattuple', 'pageinspect', 'pg_repack', 'pg_squeeze',
    'pg_hint_plan', 'dict_int', 'dict_xsyn', 'postgres_fdw', 'pgaudit',
    'http', 'hypopg', 'pg_ivm', 'orafce', 'xml2', 'pgx_ulid', 'bloom',
    'pg_lake', 'pg_incremental', 'dblink', 'file_fdw', 'pg_prewarm',
    'pg_visibility', 'adminpack', 'intarray', 'address_standardizer',
    'address_standardizer_data_us', 'amcheck', 'intagg', 'pg_freespacemap',
    'pgrowlocks', 'sslinfo', 'tsm_system_rows', 'tsm_system_time',
    'pg_similarity',
})

SUPPORTED_LANGUAGES = frozenset({'plpgsql', 'sql', 'internal', 'c'})


def add_source_args(parser):
    parser.add_argument('--source-service', dest='source_service',
                        default=os.environ.get('SOURCE_PG_SERVICE', ''),
                        help='Load host/hostaddr/port/dbname/user from ~/.pg_service.conf[NAME]; '
                             'password from ~/.pgpass. Use this in chat-safe invocations '
                             'instead of --password.')
    parser.add_argument('--host', '-H', '--source-host', dest='host',
                        default=os.environ.get('SOURCE_PGHOST', ''),
                        help='Source PostgreSQL host (aliases: -H, --source-host)')
    parser.add_argument('--hostaddr', dest='hostaddr',
                        default=os.environ.get('SOURCE_PGHOSTADDR', None),
                        help='Optional source PostgreSQL IP address for DNS-bypass '
                             'flows. Keep --host set for TLS/pgpass identity.')
    parser.add_argument('--port', '-p', '--source-port', dest='port', type=int,
                        default=int(os.environ.get('SOURCE_PGPORT', '5432')),
                        help='Source PostgreSQL port (default: 5432)')
    parser.add_argument('--dbname', '-d', '--source-dbname', dest='dbname',
                        default=os.environ.get('SOURCE_PGDATABASE', ''),
                        help='Source database name')
    parser.add_argument('--user', '-U', '--source-user', dest='user',
                        default=os.environ.get('SOURCE_PGUSER', ''),
                        help='Source username')
    parser.add_argument('--password', '-W', default='',
                        help='Source password (fallback — prefer --source-service + ~/.pgpass '
                             'in chat since CLI passwords land in the transcript)')
    parser.add_argument('--sslmode', default=None,
                        help='SSL mode (disable, require, verify-ca, verify-full)')
    parser.add_argument('--sslrootcert', dest='sslrootcert',
                        default=os.environ.get('SOURCE_PGSSLROOTCERT', None),
                        help='Path to source CA certificate file (required for '
                             'sslmode=verify-ca / verify-full). Auto-populated '
                             'from --source-service when the profile has it.')


def add_target_args(parser):
    parser.add_argument('--target-service', dest='target_service',
                        default=os.environ.get('TARGET_PG_SERVICE', ''),
                        help='Load target host/hostaddr/port/dbname/user from ~/.pg_service.conf[NAME]; '
                             'password from ~/.pgpass. Preferred in chat-safe invocations.')
    parser.add_argument('--target-host',
                        default=os.environ.get('TARGET_PGHOST', ''),
                        help='Target Snowflake Postgres host')
    parser.add_argument('--target-hostaddr', dest='target_hostaddr',
                        default=os.environ.get('TARGET_PGHOSTADDR', None),
                        help='Optional target IP address for DNS-bypass flows. '
                             'Keep --target-host set for TLS/pgpass identity.')
    parser.add_argument('--target-port', type=int,
                        default=int(os.environ.get('TARGET_PGPORT', '5432')),
                        help='Target port (default: 5432)')
    parser.add_argument('--target-dbname',
                        default=os.environ.get('TARGET_PGDATABASE', ''),
                        help='Target database name')
    parser.add_argument('--target-user',
                        default=os.environ.get('TARGET_PGUSER', ''),
                        help='Target username')
    parser.add_argument('--target-password', default='',
                        help='Target password (fallback — prefer --target-service + ~/.pgpass)')
    parser.add_argument('--target-sslmode', default=None,
                        help='Target SSL mode')
    parser.add_argument('--target-sslrootcert', dest='target_sslrootcert',
                        default=os.environ.get('TARGET_PGSSLROOTCERT', None),
                        help='Path to target CA certificate file (required for '
                             'sslmode=verify-ca / verify-full). Auto-populated '
                             'from --target-service when the profile has it.')


def add_use_role_arg(parser):
    """Add a --use-role flag for Snowflake session role overrides.

    Mirrors the pattern in pg_connect.py: session-scoped override for the
    script invocation, does not mutate ~/.snowflake/connections.toml or
    ~/.snowflake/config.toml. Callers read args.use_role.
    """
    parser.add_argument('--use-role',
                        default=None,
                        help='Snowflake session role override (e.g., ACCOUNTADMIN). '
                             'Passed to the connector for this invocation only — does not mutate config files. '
                             'Use when the default role lacks privileges required by the operation.')


def _apply_source_service(args):
    """If args.source_service is set, fill host/port/dbname/user from the
    service file. Service values are authoritative for host/port/user
    (overrides argparse defaults and env fallbacks) — the operator opted
    into the profile. Mutates args.

    Explicit non-empty `--dbname` wins over the service profile so callers
    can target a specific database without rewriting ~/.pg_service.conf
    (mirrors sslmode/sslrootcert CLI-wins behavior).

    sslmode and sslrootcert use precedence-respecting copy: if the operator
    passed --sslmode / --sslrootcert explicitly, those win; otherwise the
    service-file values fill in. This keeps verify-ca profiles working
    end-to-end (sslrootcert from `pg_connect --create` flows to migrate
    scripts) without preventing one-off CLI overrides.
    """
    name = getattr(args, 'source_service', '') or ''
    if not name:
        return
    entry = get_service_entry(name)
    if entry is None:
        raise ValueError(
            f"Source service '{name}' not found in ~/.pg_service.conf. "
            f"Register it via: python <SKILL_DIR>/scripts/shared/pg_common.py "
            f"--add-source-service {name} --host ... --user ..."
        )
    args.host = entry['host']
    if getattr(args, 'hostaddr', None) is None and entry.get('hostaddr'):
        args.hostaddr = entry['hostaddr']
    args.port = entry['port']
    if not (getattr(args, 'dbname', None) or ''):
        args.dbname = entry['database']
    args.user = entry['user']
    if getattr(args, 'sslmode', None) is None:
        args.sslmode = entry.get('sslmode')
    if getattr(args, 'sslrootcert', None) is None and entry.get('sslrootcert'):
        args.sslrootcert = entry['sslrootcert']


def _apply_target_service(args):
    """Target-side sibling of _apply_source_service. Mutates args.

    sslrootcert from the target service profile flows through here so
    Snowflake Postgres targets registered via `pg_connect --create` (which
    fetches the per-instance CA and writes the path into the service entry)
    work end-to-end with verify-ca from migrate scripts.
    """
    name = getattr(args, 'target_service', '') or ''
    if not name:
        return
    entry = get_service_entry(name)
    if entry is None:
        raise ValueError(
            f"Target service '{name}' not found in ~/.pg_service.conf. "
            f"Register it via `pg_connect --create --name {name} ...` (Snowflake targets) or "
            f"`python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service {name} ...` (non-SF)."
        )
    args.target_host = entry['host']
    if getattr(args, 'target_hostaddr', None) is None and entry.get('hostaddr'):
        args.target_hostaddr = entry['hostaddr']
    args.target_port = entry['port']
    args.target_dbname = entry['database']
    args.target_user = entry['user']
    if getattr(args, 'target_sslmode', None) is None:
        args.target_sslmode = entry.get('sslmode')
    if getattr(args, 'target_sslrootcert', None) is None and entry.get('sslrootcert'):
        args.target_sslrootcert = entry['sslrootcert']


def resolve_source_password(args):
    """Resolve source password.

    When --source-service is set, precedence is:
      CLI --password > PGPASSWORD/SOURCE_PGPASSWORD env > ~/.pgpass
    The pgpass branch fires only when service is set (we have a trustworthy
    host/port/dbname/user to match on).

    Without --source-service, preserves the upstream legacy single-line semantics
    including the PGPASSWORD='' shadow quirk — contract tests pin this.
    """
    if getattr(args, 'source_service', '') or '':
        if args.password:
            return args.password
        env_pw = os.environ.get('PGPASSWORD') or os.environ.get('SOURCE_PGPASSWORD')
        if env_pw:
            return env_pw
        entry = find_pgpass_entry(args.host, args.port, args.dbname, args.user)
        if entry:
            return entry['password']
        return ''
    return args.password or os.environ.get('PGPASSWORD', os.environ.get('SOURCE_PGPASSWORD', ''))


def resolve_target_password(args):
    """Target-side sibling of resolve_source_password.

    Without --target-service, preserves the upstream legacy behavior.
    """
    if getattr(args, 'target_service', '') or '':
        if args.target_password:
            return args.target_password
        env_pw = os.environ.get('TARGET_PGPASSWORD')
        if env_pw:
            return env_pw
        entry = find_pgpass_entry(args.target_host, args.target_port, args.target_dbname, args.target_user)
        if entry:
            return entry['password']
        return ''
    return args.target_password or os.environ.get('TARGET_PGPASSWORD', '')


def connect_source(args):
    _apply_source_service(args)
    pw = resolve_source_password(args)
    return connect(args.host, args.port, args.dbname, args.user, pw,
                   args.sslmode, sslrootcert=getattr(args, 'sslrootcert', None),
                   hostaddr=getattr(args, 'hostaddr', None))


def connect_target(args):
    _apply_target_service(args)
    pw = resolve_target_password(args)
    return connect(args.target_host, args.target_port, args.target_dbname,
                   args.target_user, pw, args.target_sslmode,
                   sslrootcert=getattr(args, 'target_sslrootcert', None),
                   hostaddr=getattr(args, 'target_hostaddr', None))


# --- PostgreSQL service file + pgpass management (generic PG; shared by pg_connect
# and migration scripts). Moved from pg_connect.py in T014 to place generic-PG
# credential plumbing in the generic-PG module. Tests that previously patched
# pg_connect.PG_SERVICE_FILE / pg_connect.PGPASS_FILE now patch pg_common.* since
# the functions look up these constants in this module's namespace. ---


def _pg_config_dir(os_name: str = os.name, environ: dict | None = None) -> Path:
    """Return the directory libpq looks in for pg_service.conf / pgpass.

    Native Windows: %APPDATA%\\postgresql\\ (fallback to
    %USERPROFILE%\\AppData\\Roaming\\postgresql\\, matching libpq's own
    fallback chain). Raises RuntimeError if neither env var is set.

    WSL processes report os.name == 'posix' and get the Linux/macOS branch
    deliberately — they have a Linux filesystem view and must use
    ~/.pg_service.conf / ~/.pgpass, not %APPDATA%.

    os_name and environ are parameterized so tests on a POSIX host can pin
    the Windows branch without monkeypatching os.name (which would trigger
    pathlib's PosixPath / WindowsPath factory switch and fail).
    """
    if environ is None:
        environ = os.environ
    if os_name == "nt":
        appdata = environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "postgresql"
        userprofile = environ.get("USERPROFILE")
        if userprofile:
            return Path(userprofile) / "AppData" / "Roaming" / "postgresql"
        raise RuntimeError(
            "Expected APPDATA or USERPROFILE to be set on Windows; "
            "cannot resolve pg_service.conf / pgpass location."
        )
    return Path.home()


def _pg_service_filename(os_name: str = os.name) -> str:
    return "pg_service.conf" if os_name == "nt" else ".pg_service.conf"


def _pgpass_filename(os_name: str = os.name) -> str:
    return "pgpass.conf" if os_name == "nt" else ".pgpass"


PG_SERVICE_FILE = _pg_config_dir() / _pg_service_filename()
PGPASS_FILE = _pg_config_dir() / _pgpass_filename()


def load_service_file() -> configparser.ConfigParser:
    """Load ~/.pg_service.conf as a ConfigParser object."""
    config = configparser.ConfigParser()
    if PG_SERVICE_FILE.exists():
        config.read(PG_SERVICE_FILE)
    return config


def save_service_file(config: configparser.ConfigParser) -> None:
    """Save the service file in pg_service.conf format (no spaces around =)."""
    PG_SERVICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PG_SERVICE_FILE, "w") as f:
        for section in config.sections():
            f.write(f"[{section}]\n")
            for key, value in config.items(section):
                f.write(f"{key}={value}\n")
            f.write("\n")


def get_service_entry(name: str) -> dict | None:
    """Get a service entry by name (without password).

    Returns None if the entry doesn't exist or is missing required 'host' field.
    Includes optional hostaddr / sslrootcert paths if present in the service file.
    """
    config = load_service_file()
    if name not in config.sections():
        return None

    host = config.get(name, "host", fallback=None)
    if not host:
        return None

    entry = {
        "host": host,
        "port": config.getint(name, "port", fallback=5432),
        "database": config.get(name, "dbname", fallback="postgres"),
        "user": config.get(name, "user", fallback="snowflake_admin"),
        "sslmode": config.get(name, "sslmode", fallback="require"),
    }

    hostaddr = config.get(name, "hostaddr", fallback=None)
    if hostaddr:
        entry["hostaddr"] = hostaddr

    sslrootcert = config.get(name, "sslrootcert", fallback=None)
    if sslrootcert:
        entry["sslrootcert"] = sslrootcert

    return entry


def validate_pg_field(
    value: str,
    field_name: str,
    *,
    allow_star: bool = False,
    max_length: int | None = None,
) -> str:
    """Reject values that would corrupt ~/.pgpass or ~/.pg_service.conf.

    libpq config files are line-oriented. Newlines/control characters in
    host/database/user fields can inject extra entries or shift which
    credentials match. Raises ValueError on bad input; returns the value
    unchanged when valid.
    """
    if value is None:
        raise ValueError(f"{field_name} cannot be None")
    s = str(value)
    if allow_star and s == "*":
        return s
    if not s:
        raise ValueError(f"{field_name} cannot be empty")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in s):
        raise ValueError(
            f"Invalid {field_name}: control characters "
            f"(including newlines) are not allowed"
        )
    if s != s.strip():
        raise ValueError(
            f"Invalid {field_name}: leading/trailing whitespace is not allowed"
        )
    if max_length is not None and len(s) > max_length:
        raise ValueError(
            f"Invalid {field_name}: exceeds maximum length of {max_length} characters"
        )
    return s


def validate_pg_database_name(database: str) -> str:
    """Validate a Postgres database name before persisting it to config files."""
    # Postgres NAMEDATALEN default is 64 (63 usable chars for identifiers).
    return validate_pg_field(database, "database", max_length=63)


def save_service_entry(name: str, params: dict, sslrootcert: str | None = None) -> None:
    """Save a service entry (without password).

    When sslrootcert is provided, the entry is written with sslmode=verify-ca
    and sslrootcert pointing to the CA certificate file. This upgrades the
    connection from encrypted-only (require) to verified server identity. When
    params includes hostaddr, it is written as an optional libpq DNS-bypass
    companion to host.
    """
    validate_pg_field(params["host"], "host")
    validate_pg_field(params.get("database", "postgres"), "database")
    validate_pg_field(params.get("user", "snowflake_admin"), "user")

    config = load_service_file()

    if name not in config.sections():
        config.add_section(name)

    config.set(name, "host", params["host"])
    if params.get("hostaddr"):
        config.set(name, "hostaddr", params["hostaddr"])
    else:
        config.remove_option(name, "hostaddr")
    config.set(name, "port", str(params.get("port", 5432)))
    config.set(name, "dbname", params.get("database", "postgres"))
    config.set(name, "user", params.get("user", "snowflake_admin"))

    if sslrootcert:
        config.set(name, "sslmode", "verify-ca")
        config.set(name, "sslrootcert", sslrootcert)
    else:
        config.set(name, "sslmode", params.get("sslmode", "require"))
        config.remove_option(name, "sslrootcert")

    save_service_file(config)


def delete_service_entry(name: str) -> bool:
    """Delete a service entry."""
    config = load_service_file()
    if name not in config.sections():
        return False

    config.remove_section(name)
    save_service_file(config)
    return True


def list_service_entries() -> list[str]:
    """List all service entry names."""
    config = load_service_file()
    return config.sections()


# --- PostgreSQL Password File Management ---

def load_pgpass() -> list[dict]:
    """
    Load ~/.pgpass entries.

    Format: hostname:port:database:username:password
    Lines starting with # are comments.
    """
    entries = []
    if not PGPASS_FILE.exists():
        return entries

    with open(PGPASS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = []
            current = ""
            i = 0
            while i < len(line):
                if line[i] == "\\" and i + 1 < len(line) and line[i + 1] == ":":
                    current += ":"
                    i += 2
                elif line[i] == ":":
                    parts.append(current)
                    current = ""
                    i += 1
                else:
                    current += line[i]
                    i += 1
            parts.append(current)

            if len(parts) == 5:
                entries.append({
                    "host": parts[0],
                    "port": parts[1],
                    "database": parts[2],
                    "user": parts[3],
                    "password": parts[4],
                })

    return entries


def save_pgpass(entries: list[dict]) -> None:
    """Save entries to ~/.pgpass with secure permissions."""
    lines = []
    for entry in entries:
        validate_pg_field(entry["host"], "host", allow_star=True)
        validate_pg_field(entry.get("database", "*"), "database", allow_star=True)
        validate_pg_field(entry.get("user", "*"), "user", allow_star=True)

        def escape(s):
            return str(s).replace("\\", "\\\\").replace(":", "\\:")

        def escape_password(s):
            return str(s).replace("\\", "\\\\").replace(":", "\\:").replace("\n", "").replace("\r", "")

        line = ":".join([
            escape(entry["host"]),
            str(entry.get("port", "*")),
            escape(entry.get("database", "*")),
            escape(entry.get("user", "*")),
            escape_password(entry["password"]),
        ])
        lines.append(line)

    PGPASS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PGPASS_FILE, "w") as f:
        f.write("# PostgreSQL password file - managed by pg_connect.py\n")
        f.write("# Format: hostname:port:database:username:password\n")
        f.write("\n".join(lines))
        if lines:
            f.write("\n")

    os.chmod(PGPASS_FILE, 0o600)


def find_pgpass_entry(host: str, port: int, database: str, user: str) -> dict | None:
    """Find a matching pgpass entry."""
    entries = load_pgpass()
    for entry in entries:
        if (
            (entry["host"] == "*" or entry["host"] == host) and
            (entry["port"] == "*" or str(entry["port"]) == str(port)) and
            (entry["database"] == "*" or entry["database"] == database) and
            (entry["user"] == "*" or entry["user"] == user)
        ):
            return entry
    return None


def upsert_pgpass_entry(host: str, port: int, database: str, user: str, password: str) -> None:
    """Add or update a pgpass entry."""
    entries = load_pgpass()

    for entry in entries:
        if (
            entry["host"] == host and
            str(entry["port"]) == str(port) and
            entry["database"] == database and
            entry["user"] == user
        ):
            entry["password"] = password
            save_pgpass(entries)
            return

    entries.append({
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
    })
    save_pgpass(entries)


def delete_pgpass_entry(host: str, port: int, database: str, user: str) -> bool:
    """Delete a pgpass entry."""
    entries = load_pgpass()
    original_len = len(entries)

    entries = [
        e for e in entries
        if not (
            e["host"] == host and
            str(e["port"]) == str(port) and
            e["database"] == database and
            e["user"] == user
        )
    ]

    if len(entries) < original_len:
        save_pgpass(entries)
        return True
    return False


# --- Generic-PG CLI (T014c) -------------------------------------------------
#
# Thin wrapper over save_service_entry / list_service_entries / delete_service_entry
# so non-Snowflake sources get the same "register once, reference by name" UX
# as Snowflake targets (which register via `pg_connect --create`). Kept in
# pg_common to preserve the generic-PG / Snowflake-PG boundary — pg_connect
# stays Snowflake-specific.
#
# Usage (file-path invocation; pg_common is not exposed as an importable
# top-level module so `python -m pg_common` will not find it):
#   python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service NAME \
#       --host H --port P --dbname D --user U [--password PW]
#   # Or set PGPASSWORD / SOURCE_PGPASSWORD for the same command to populate
#   # ~/.pgpass without passing the password on argv.
#   python <SKILL_DIR>/scripts/shared/pg_common.py --list-services
#   python <SKILL_DIR>/scripts/shared/pg_common.py --remove-source-service NAME [--keep-pgpass]

def _cli_add_source_service(args) -> int:
    save_service_entry(args.name, {
        "host": args.host,
        "hostaddr": args.hostaddr,
        "port": args.port,
        "database": args.dbname,
        "user": args.user,
        "sslmode": args.sslmode,
    })
    password = args.password or os.environ.get("PGPASSWORD") or os.environ.get("SOURCE_PGPASSWORD")
    wrote_pgpass = False
    if password:
        upsert_pgpass_entry(args.host, args.port, args.dbname, args.user, password)
        wrote_pgpass = True
    print(f"Registered service '{args.name}' in {PG_SERVICE_FILE}")
    if wrote_pgpass:
        print(f"Password stored in {PGPASS_FILE} (mode 0600)")
    else:
        print(f"No password stored. Add one later via: "
              f"python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service {args.name} "
              f"--host {args.host} --port {args.port} --dbname {args.dbname} "
              f"--user {args.user} --password <pw> "
              f"(or rerun with PGPASSWORD / SOURCE_PGPASSWORD set)")
    return 0


def _cli_list_services() -> int:
    names = list_service_entries()
    if not names:
        print(f"No services registered in {PG_SERVICE_FILE}")
        return 0
    for name in names:
        entry = get_service_entry(name)
        if entry is None:
            print(f"{name}\t(invalid entry)")
            continue
        has_pgpass = find_pgpass_entry(entry["host"], entry["port"], entry["database"], entry["user"]) is not None
        pgpass_flag = "pgpass" if has_pgpass else "no-pgpass"
        print(f"{name}\t{entry['user']}@{entry['host']}:{entry['port']}/{entry['database']}\tsslmode={entry['sslmode']}\t{pgpass_flag}")
    return 0


def _cli_remove_source_service(args) -> int:
    entry = get_service_entry(args.name)
    deleted = delete_service_entry(args.name)
    if not deleted:
        print(f"Service '{args.name}' not found in {PG_SERVICE_FILE}", file=sys.stderr)
        return 1
    print(f"Removed service '{args.name}' from {PG_SERVICE_FILE}")
    if entry and not args.keep_pgpass:
        if delete_pgpass_entry(entry["host"], entry["port"], entry["database"], entry["user"]):
            print(f"Removed matching entry from {PGPASS_FILE}")
    return 0


def _build_cli_parser():
    parser = argparse.ArgumentParser(
        prog="pg_common",
        description="Generic-PG credential helpers. Register non-Snowflake source "
                    "profiles in ~/.pg_service.conf + ~/.pgpass. For Snowflake Postgres "
                    "targets, use `pg_connect --create` instead.",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--add-source-service", dest="add_name", metavar="NAME",
                        help="Register a source service profile")
    action.add_argument("--list-services", action="store_true",
                        help="List all registered service profiles")
    action.add_argument("--remove-source-service", dest="remove_name", metavar="NAME",
                        help="Remove a source service profile (and its pgpass entry)")

    parser.add_argument("--host", help="PostgreSQL host (required with --add-source-service)")
    parser.add_argument("--hostaddr",
                        help="Optional PostgreSQL IP address for libpq DNS-bypass flows")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port (default: 5432)")
    parser.add_argument("--dbname", default="postgres", help="Database name (default: postgres)")
    parser.add_argument("--user", help="Username (required with --add-source-service)")
    parser.add_argument(
        "--password",
        default="",
        help="Password to store in ~/.pgpass (optional; env fallback: PGPASSWORD or SOURCE_PGPASSWORD)",
    )
    parser.add_argument("--sslmode", default="require",
                        help="SSL mode (default: require)")
    parser.add_argument("--keep-pgpass", action="store_true",
                        help="With --remove-source-service: do not delete the matching pgpass entry")
    return parser


def _main(argv=None):
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    if args.add_name:
        if not args.host or not args.user:
            parser.error("--add-source-service requires --host and --user")
        args.name = args.add_name
        return _cli_add_source_service(args)
    if args.list_services:
        return _cli_list_services()
    if args.remove_name:
        args.name = args.remove_name
        return _cli_remove_source_service(args)
    parser.error("no action specified")
    return 2


if __name__ == "__main__":
    sys.exit(_main())
