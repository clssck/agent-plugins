---
name: databricks-cli-install
description: "Install, update, and configure the Databricks CLI. Use when the user wants to install databricks cli, set up databricks cli, update databricks cli, configure databricks authentication, databricks auth login, brew install databricks, troubleshoot databricks cli installation issues, connect to a new databricks workspace, new workspace onboarding, getting started with databricks, or first time databricks setup. NOTE: If the user wants to install Databricks SKILLS or MCP tools for Cortex Code (AI Dev Kit), route to the databricks-setup skill instead."
---

# Databricks CLI Installation

## When to Use

- User wants to install or update the Databricks CLI (v0.205+)
- User wants to configure authentication for the Databricks CLI
- User is troubleshooting a broken or outdated Databricks CLI installation
- User wants to connect to a new Databricks workspace for the first time

**Routing note:** If the user wants to install Databricks *skills* or *MCP tools* for Cortex Code (the AI Dev Kit), use the `databricks-setup` skill instead. This skill is for the CLI binary and authentication only.

## Workflow

> **Convention:** All placeholders in `<angle-brackets>` must be replaced with actual values from the user. Always ask the user for the value before running the command.

### Step 1: Detect OS and Existing Installation

**Goal:** Determine the user's platform and whether the CLI is already installed.

**Actions:**

1. **Run** the following commands to detect the environment:
   ```bash
   uname -s 2>/dev/null || echo "Windows"
   databricks -v 2>/dev/null || echo "NOT_INSTALLED"
   ```

2. **If already installed** at version 0.205.0+:

   **⚠️ MANDATORY STOPPING POINT**: Ask the user what they want to do before proceeding.

   - Update to the latest version (go to **Updating the CLI** section, then Step 3)
   - Reconfigure authentication (go to Step 4)
   - Reinstall from scratch (continue to Step 2)

3. **If not installed or below 0.205.0**, continue to Step 2.

### Step 2: Install the Databricks CLI

**Goal:** Install the CLI using the best method for the user's OS.

**Route by platform:**

#### Linux / macOS -- Homebrew (recommended)

First check if Homebrew is available:
```bash
brew -v 2>/dev/null || echo "HOMEBREW_NOT_INSTALLED"
```

If Homebrew is available:
```bash
brew tap databricks/tap
brew install databricks
```

If Homebrew is not installed, either install it or fall back to the curl method below:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Linux / macOS / WSL -- curl

```bash
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
```

- Installs to `/usr/local/bin/databricks`
- If permission denied, re-run with `sudo`

#### Windows -- WinGet

```bash
winget search databricks
winget install Databricks.DatabricksCLI
```

Restart the terminal after install.

#### Windows -- Chocolatey (experimental)

```bash
choco install databricks-cli
```

#### Any OS -- Source zip

1. Download the correct `.zip` from GitHub releases: `https://github.com/databricks/cli/releases`
2. Match the file to the OS and architecture:
   - `databricks_cli_X.Y.Z_darwin_amd64.zip` -- macOS Intel
   - `databricks_cli_X.Y.Z_darwin_arm64.zip` -- macOS Apple Silicon
   - `databricks_cli_X.Y.Z_linux_amd64.zip` -- Linux x86_64
   - `databricks_cli_X.Y.Z_linux_arm64.zip` -- Linux ARM64
   - `databricks_cli_X.Y.Z_windows_amd64.zip` -- Windows x64
3. Extract and place the `databricks` binary on the system PATH.

**After installation, continue to Step 3.**

### Step 3: Verify Installation

**Goal:** Confirm the CLI is installed and functional.

**Actions:**

1. **Run:**
   ```bash
   databricks -v
   ```

2. **Expected:** Version 0.205.0 or above.

3. **If verification fails**, see Troubleshooting below.

**After verification succeeds, continue to Step 4.**

### Step 4: Configure Authentication

**⚠️ MANDATORY STOPPING POINT**: Ask the user which authentication method they want to use before proceeding.

**Present options:**

1. **OAuth U2M (user-to-machine)** -- Interactive browser login. Best for individual users.
2. **OAuth M2M (machine-to-machine)** -- Service principal credentials. Best for automation/CI.
3. **Personal Access Token** -- Legacy/deprecated. Only if required by existing setup.
4. **Environment variables** -- Set `DATABRICKS_HOST` and `DATABRICKS_TOKEN` (or `DATABRICKS_CLIENT_ID` + `DATABRICKS_CLIENT_SECRET`). Useful for CI/CD pipelines.
5. **Skip** -- User will configure auth later.

**Note:** The CLI resolves credentials in this order: bundle settings → environment variables → `~/.databrickscfg` profiles.

#### Option 1: OAuth U2M

Ask the user for their workspace URL (e.g., `https://dbc-a1b2345c-d6e7.cloud.databricks.com`).

For workspace-level access:
```bash
databricks auth login --host <workspace-url>
```

For account-level access (also ask for account ID):
```bash
databricks auth login --host https://accounts.cloud.databricks.com --account-id <account-id>
```

The CLI opens a browser for login and saves a configuration profile to `~/.databrickscfg`.

**Post-login verification (critical):** The OAuth flow can exit 0 without actually writing the config file. Always verify immediately:

```bash
cat ~/.databrickscfg
databricks auth token
```

If `~/.databrickscfg` does not exist or is empty after `auth login` succeeded:
- The browser OAuth flow may have silently failed (window closed early, SSO redirect issue)
- Retry: `databricks auth login --host <workspace-url>` and complete the full browser flow
- If it still fails, fall back to **Option 3 (Personal Access Token)** as a workaround

#### Option 2: OAuth M2M

Ask the user for: workspace URL, client ID, and client secret.

**Append** the profile to `~/.databrickscfg` (check if the file exists first; do not overwrite existing profiles):
```ini
[<profile-name>]
host = <workspace-url>
client_id = <service-principal-client-id>
client_secret = <service-principal-oauth-secret>
```

#### Option 3: Personal Access Token (deprecated)

Ask the user for: workspace URL and token.

**Append** the profile to `~/.databrickscfg` (check if the file exists first; do not overwrite existing profiles):
```ini
[<profile-name>]
host = <workspace-url>
token = <personal-access-token>
```

#### Option 4: Environment Variables

Ask the user which env vars they want to set. Common patterns:

For PAT-based:
```bash
export DATABRICKS_HOST="<workspace-url>"
export DATABRICKS_TOKEN="<personal-access-token>"
```

For M2M OAuth:
```bash
export DATABRICKS_HOST="<workspace-url>"
export DATABRICKS_CLIENT_ID="<service-principal-client-id>"
export DATABRICKS_CLIENT_SECRET="<service-principal-oauth-secret>"
```

Recommend the user adds these to their shell profile (`~/.bashrc`, `~/.zshrc`, etc.) for persistence.

#### Option 5: Skip

Inform the user they can configure auth later with `databricks auth login`.

### Step 5: Verify Authentication

**Goal:** Confirm the CLI can reach the Databricks workspace.

**Actions:**

1. **Run** to verify the token is valid:
   ```bash
   databricks auth token -p <profile-name>
   ```
   **Expected:** A valid token and expiration timestamp. No errors.

2. **Optionally**, run a deeper connectivity check:
   ```bash
   databricks clusters list -p <profile-name>
   ```
   Or without a profile (if env vars or default profile):
   ```bash
   databricks clusters list
   ```
   **Expected:** A list of clusters (or empty list if none exist). No auth errors.
   **Note:** This requires workspace-level permissions. If the user only has account-level auth, skip this check.

3. **If auth fails**, check:
   - Profile name is correct: `databricks auth profiles`
   - Token is valid: `databricks auth token -p <profile-name>`
   - Host URL is correct and reachable

## Updating the CLI

### Homebrew
```bash
brew upgrade databricks
```

### curl (remove old binary first)
```bash
rm /usr/local/bin/databricks
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
```

### WinGet
```bash
winget upgrade Databricks.DatabricksCLI
```

### Chocolatey
```bash
choco upgrade databricks-cli
```

## Stopping Points

- After Step 1 if CLI is already installed (ask user intent)
- Before Step 4 (ask which auth method)
- After Step 5 if auth fails (diagnose before retrying)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `command not found: databricks` | Binary not on PATH. Check install location and add to PATH. |
| `/usr/local/bin is not writable` | Re-run the curl install with `sudo`. |
| `Target path already exists` | Remove existing binary first: `rm /usr/local/bin/databricks`, then reinstall. |
| Version below 0.205.0 | You have the legacy CLI. Uninstall it (`pip uninstall databricks-cli`) and install the new one. |
| `brew: command not found` | Install Homebrew first or use the curl method instead. |
| Auth token expired | Re-run `databricks auth login --host <url>` to refresh. |
| `Error: invalid token` | Token may be revoked. Generate a new one or re-authenticate with OAuth. |
| `auth login` exits 0 but `~/.databrickscfg` missing | OAuth browser flow silently failed. Retry with explicit `--host`, or fall back to PAT auth. |

## Output

- Databricks CLI installed and on PATH at version 0.205.0+
- Authentication configured with a named profile in `~/.databrickscfg`
- Verified connectivity to the Databricks workspace
