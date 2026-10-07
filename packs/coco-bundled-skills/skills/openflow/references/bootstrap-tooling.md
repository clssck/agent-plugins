---
name: openflow-bootstrap-tooling
description: Install required tooling for Openflow CLI access. Load when tools are missing.
---

# Tooling Setup

Required tools: `snow` (Snowflake CLI), `python3`, `nipyapi`

Optional fallback: `curl` (for environments without Python)

## Check What's Available

```bash
which snow && which python3 && which nipyapi && which curl
```

Handle each missing tool in order below. Skip sections for tools already installed.

## Tooling Preference

If both `nipyapi` and `curl` are available, ask the user:

> Both Python (nipyapi) and curl are available. Which do you prefer?
>
> - **nipyapi** (recommended): Full functionality including layout management, version control, parameter inheritance automation, and advanced operations
> - **curl**: Basic operations only (deploy, start, stop, status, bulletins). Limited coverage - some workflows will require Python.

Store preference in cache (see "Update Cache" section below).

**Note:** If only curl is available and nipyapi cannot be installed, warn the user that functionality will be limited to basic operations.

---

## Install Python 3 (if missing)

Recommend uv for Python management:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python via uv
uv python install 3.12
```

Verify:

```bash
which python3 && python3 --version
```

---

## Install Snowflake CLI (if missing)

```bash
uv tool install snowflake-cli
```

Verify:

```bash
which snow && snow --version
```

After install, configure a connection:

```bash
snow connection add
```

---

## Install nipyapi (if missing)

```bash
uv tool install "nipyapi[cli]>=1.2.0"
```

Verify:

```bash
which nipyapi && nipyapi -V
```

Expected output: `nipyapi X.Y.Z` (version number confirms CLI is working)

### Verify --profile Flag

```bash
nipyapi --profile nonexistent 2>&1 | head -1
```

| Result | Status |
|--------|--------|
| "Profile 'nonexistent' not found" or similar | Working |
| "Cannot find key: --profile" | Outdated - see Upgrade nipyapi below |

---

## Upgrade nipyapi

If nipyapi is installed but outdated (version < 1.2.0), upgrade to get full functionality.

**Check current version:**

```bash
nipyapi --version
```

**Upgrade using uv (recommended):**

```bash
uv tool install --force "nipyapi[cli]>=1.2.0"
```

**Upgrade using pip:**

```bash
pip install --upgrade "nipyapi[cli]>=1.2.0"
```

**Verify upgrade:**

```bash
nipyapi --version
```

Expected: `nipyapi 1.5.0` or higher.

**Why upgrade matters:** Version 1.5.0+ includes:
- `nipyapi bulletins` module for error diagnostics
- Enhanced CI commands with better error handling
- Profile-based authentication improvements

---

## Update Cache

Write the `tooling` section to the cache with the commands you verified above.

**Tooling schema:**

```json
{
  "tooling": {
    "preferred": "nipyapi | curl",
    "nipyapi_available": true,
    "curl_available": true,
    "python_command": "python3",
    "pip_command": "pip3",
    "updated_at": "<ISO_TIMESTAMP>"
  }
}
```

**If cache file exists:**

```bash
jq '.tooling = {preferred: "<PREFERENCE>", nipyapi_available: <true|false>, curl_available: <true|false>, python_command: "<PYTHON_CMD>", pip_command: "<PIP_CMD>", updated_at: "<TIMESTAMP>"}' \
  ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json > tmp && mv tmp ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json
```

**If no cache file exists yet:**

```bash
mkdir -p ~/.snowflake/cortex/memory
cat > ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json << 'EOF'
{
  "connection": "<CONNECTION>",
  "tooling": {
    "preferred": "<PREFERENCE>",
    "nipyapi_available": <true|false>,
    "curl_available": <true|false>,
    "python_command": "<PYTHON_CMD>",
    "pip_command": "<PIP_CMD>",
    "updated_at": "<TIMESTAMP>"
  }
}
EOF
```

Replace placeholders with actual values from your verification steps.

---

## Next Step

**Continue** to `references/bootstrap-cli.md` Step 1b to ensure the cache has a tooling section, then proceed through the remaining setup steps.
