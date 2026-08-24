# CLI Version Check

Confirm the Snowflake Apps command surface is available and the Snowflake CLI is current.

## Goal

Use `snow app` for all Snowflake Apps commands. Verify it works and warn the user if their CLI is outdated.

## Check command surface (required)

Use exactly these two commands: `snow app setup --help` to check the command surface, and `snow --version` to check the version. Do not combine them into other variations.

```bash
snow app setup --help
```

If it succeeds, use `snow app` for all Snowflake Apps commands.

If it fails, the Snowflake CLI is missing or too old to expose the `snow app` command surface. Stop and ask the user to install or upgrade Snowflake CLI (see the upgrade commands below) before continuing.

## Version check (informational)

Compare the installed CLI version against the latest released version instead of a hard-coded floor. Prefer the CLI's built-in `snow helpers check-version` command; only fall back to the manual GitHub comparison if that command isn't available.

### Preferred: built-in check

Newer Snowflake CLI versions ship a `snow helpers check-version` command that reports the installed version, the latest published version, and whether an upgrade is available:

```bash
snow helpers check-version --format JSON
```

If it succeeds, it returns JSON like:

```json
{
  "current_version": "3.24.0",
  "latest_version": "3.24.0",
  "update_available": false
}
```

If `update_available` is `true`, warn the user that their CLI is outdated (mention both `current_version` and `latest_version`) and offer the matching upgrade command below. If it's `false`, the CLI is current — say nothing. If the output can't be parsed as JSON or is missing the `update_available` field, treat it as a failure and use the manual-comparison fallback below.

### Fallback: manual comparison

If `snow helpers check-version` fails (e.g. it's not recognized on an older CLI, or there's no network), fall back to comparing versions manually.

1. Get the installed version:

```bash
snow --version
```

2. Get the latest released version from GitHub (strip the leading `v`):

```bash
curl -fsSL https://api.github.com/repos/snowflakedb/snowflake-cli/releases/latest | grep -o '"tag_name": *"[^"]*"' | head -1 | grep -o '[0-9][0-9.]*'
```

The command above is written for a POSIX shell (macOS/Linux). This runs on the user's host machine, so if you're on a different platform (e.g. Windows PowerShell), convert it to the equivalent command for that shell.

Compare the two version strings. If the installed version is behind the latest release, warn the user that their CLI is outdated (mention both the installed and latest versions) and offer the matching upgrade command below. If the latest version can't be fetched (e.g. no network), skip the warning silently — the command-surface check above is the required gate, this is only informational.

## Upgrade commands by install method

Detect the install method and use the first match:

| Detection | Update Command |
|-----------|----------------|
| `brew list snowflake-cli 2>/dev/null` | `brew update && brew upgrade snowflake-cli` |
| `pipx list 2>/dev/null \| grep snowflake-cli` | `pipx upgrade snowflake-cli` |
| `pip show snowflake-cli 2>/dev/null` | `pip install --upgrade snowflake-cli` |
| `snow --info` reports `"installation_source": "binary"` | Download the new installer from the [GitHub releases page](https://github.com/snowflakedb/snowflake-cli/releases) and run it |
| None of the above | `pip install --upgrade snowflake-cli` |
