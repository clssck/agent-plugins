---
name: openflow-core-guidelines-cli
description: CLI/terminal-surface tooling for Openflow — the nipyapi and curl NiFi-API layers and Authorship (custom flow) mode. Load on the CLI surface when work resolves to Gen1/canvas/custom (NiFi API required). Not applicable on the Snowsight (SQL-only) surface.
---

# Openflow Guidelines — CLI / terminal surface

Terminal-surface tooling that requires the NiFi API. Load this **only** on the CLI/Desktop surface, and only once the work has resolved to Gen1 connectors, canvas operations, or custom flow authoring (the "CLI + Gen1/canvas" cell of the capability x intent matrix in `SKILL.md`).

On the **Snowsight (SQL-only)** surface these tools do not exist (no Secret, no egress to the Runtime API endpoint) — do not attempt them; decline canvas/Gen1 work and direct the user to the Openflow UI in Snowsight, or Cortex Code CLI/Desktop. The shared SQL tool layer and safety principles live in `references/core-guidelines.md`.

## Tool Hierarchy — Runtime level (NiFi API)

### nipyapi (Runtime Level)

**Everything within a Runtime** is accessible via nipyapi. Use the simplest level that works:

**Preference order:**

1. **CLI commands** — For operations with simple inputs/outputs. Returns structured JSON.
2. **CI functions** — Common workflows with error handling (`nipyapi ci ...` or `nipyapi.ci.*`)
3. **Module functions** — Granular control (`nipyapi canvas ...` or `nipyapi.canvas.*`)

**Common operations (CLI preferred):**

| Operation | CLI Command |
|-----------|-------------|
| Deploy flow | `nipyapi ci deploy_flow --bucket X --flow Y` |
| Start/Stop flow | `nipyapi ci start_flow --pg_id <id>` |
| Get status | `nipyapi ci get_status --pg_id <id>` |
| Configure params | `nipyapi ci configure_inherited_params --pg_id <id> --parameters '{...}'` |
| Get bulletins | `nipyapi bulletins get_bulletin_board` |
| List processors | `nipyapi canvas list_all_processors --pg_id <id>` |
| Cleanup | `nipyapi ci cleanup --pg_id <id>` |

**When to use Python instead of CLI:**
- Complex logic across multiple API calls
- Need to inspect/manipulate response objects
- Looping or conditional operations
- Operations not exposed in CLI (e.g., `nipyapi.canvas.create_processor()`)

For unfamiliar commands, check `--help` first.

**CLI Error Output:** nipyapi CLI returns structured JSON even on failure:

```json
{
  "success": false,
  "error": "(503)\nReason: Service Unavailable\nHTTP response headers: ...",
  "error_type": "ApiException",
  "logs": ["HTTP response body..."]
}
```

Use `success` to check outcome, `error` for HTTP status/reason, `error_type` to categorize.

### Curl (Alternative for Runtime Level)

If the user prefers curl or Python/nipyapi is unavailable, basic operations can be performed via curl against the NiFi REST API.

**Setup:** Extract URL and PAT from the nipyapi profile. If no profile exists, run `references/bootstrap-cli.md` first to create one.

Run this once per session:

```bash
PROFILE="<profile-name>"
BASE_URL=$(awk -v profile="$PROFILE:" '$0 ~ profile {found=1} found && /nifi_url:/ {gsub(/.*nifi_url: *"?|"?$/, ""); print; exit}' ~/.nipyapi/profiles.yml)
PAT=$(awk -v profile="$PROFILE:" '$0 ~ profile {found=1} found && /nifi_bearer_token:/ {gsub(/.*nifi_bearer_token: *"?|"?$/, ""); print; exit}' ~/.nipyapi/profiles.yml)
AUTH_HEADER="Authorization: Bearer $PAT"
```

**Usage:** All curl commands use `$BASE_URL` and `$AUTH_HEADER`. Use the profile that matches the runtime you're working with. Add `-k` if you encounter certificate verification errors.

**Coverage:** Curl provides basic operations only. These references include curl alternatives:

| Reference | Curl Operations Available |
|-----------|---------------------------|
| `ops-flow-deploy.md` | List registries, list flows, deploy |
| `ops-flow-lifecycle.md` | Start, stop, bulletins, terminate |
| `ops-parameters-main.md` | List contexts, get context details, update parameters, find ownership |
| `ops-parameters-assets.md` | Asset upload |
| `ops-config-verification.md` | Full verification workflow |
| `connector-cdc.md` | Table state queries |

**Not available via curl (require nipyapi):**
- Layout management (`ops-layout.md`)
- Version control helpers (`ops-version-control.md`)
- Tracked modifications (`ops-tracked-modifications.md`)
- Extension management (`ops-extensions.md`)
- Automatic parameter ownership resolution (curl requires manual context identification)

## Operational Pattern: Check-Act-Check (NiFi async operations)

Many NiFi operations are **asynchronous** — the command returns before the action completes. Verify before and after:

```bash
# Check: Confirm flow is stopped
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
# Expect: stopped_processors > 0

# Act: Start the flow
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"

# Check: Confirm flow is running
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
# Expect: running_processors > 0, bulletin_errors = 0
```

- Default to `get_status` for the Check step when unsure.
- If post-Check shows unexpected state, investigate and discuss corrective action with the user.

(The general Check-Act-Check principle — and its SQL/SOM form — is in `references/core-guidelines.md`.)

## Authorship Mode (custom flow structural changes)

Structural changes to flow design — adding/removing/modifying processors, connections, or process groups. Requires the NiFi API (nipyapi), so it is CLI-surface only.

**Critical distinction:** The Snowflake connector registry (`Snowflake Openflow Connector Registry`) is **read-only**. It provides pre-built connectors but cannot save custom edits. For Authorship work, the user needs their own Git registry client or to author flows without version control.

**Agent behavior:**
- **Prompt about version control** if the target flow is not already versioned to a user-owned registry:
  > "You're about to make structural changes to this flow. Would you like to set up version control first? This requires connecting your own Git repository (the Snowflake connector registry is read-only). This provides undo capability and change management. (Skip if you're just experimenting.)"
- If flow is versioned to `main` branch, suggest a feature branch.
- See `references/ops-version-control.md` for Git registry client setup.

**Mode transition into Authorship** (from Deployment): make clear that customizations cannot be saved back to Snowflake's registry — the user needs their own Git registry client.
