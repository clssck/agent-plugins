---
name: openflow-ops-flow-deploy
description: Sub-reference for deploying flows from registries. Called from connector-main.md or author-main.md workflows. Not a direct entry point.
---

# Flow Deployment

Deploy flows from registries to the canvas. This is a sub-reference called from `connector-main.md` (step 5-6) or custom flow workflows.

**Note:** For connector deployment, start with `references/connector-main.md` which orchestrates the full workflow including this reference.

## First: Check Deployment Source

| User has... | Go to |
|-------------|-------|
| Registry name (e.g., `MyGithubRegistryClient`) | Continue with this reference |
| Flow name from Snowflake connector catalog | Continue with this reference |
| Local JSON/YAML file on their machine | `references/ops-flow-export.md` (Import section) |

Most users deploy from the Snowflake-provided connector registry. If the user wants to deploy from a local file, redirect to the import workflow.

---

**Note:** Deploy is a state-modifying operation. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

**Discovery:** Run `nipyapi ci deploy_flow --help` to see all available arguments.

## Scope

- Deploying flows from registries (connectors or custom)
- Registry discovery and flow listing
- For authoring flows, see `references/ops-version-control.md`

## Discover Available Registries

```bash
nipyapi --profile <profile> versioning list_registry_clients | jq '.registries[].component | {id, name, type}'
```

| Registry Type | Typical Name | Purpose |
|---------------|--------------|---------|
| Snowflake Connector Registry | `ConnectorFlowRegistryClient` | Pre-built Snowflake connectors (read-only) |
| Git Registry (GitHub/GitLab) | User-defined | Custom flows, forked connectors |

**Note:** The Snowflake Connector Registry (`ConnectorFlowRegistryClient`) is a GitHub-compatible registry. Use the same `list_git_registry_*` commands for both Snowflake connectors and custom Git registries. Snowflake has wrapped this registry type but the underlying API is identical.

## List Available Flows

Note that the list_registry_flows function accepts a name or UUID:

```bash
nipyapi --profile <profile> ci list_registry_flows \
  --registry_client ConnectorFlowRegistryClient \
  --bucket connectors
```

Output includes `flows` array with name and flow_id for each available flow.

For detailed info (descriptions, comments), add `--detailed`:

```bash
nipyapi --profile <profile> ci list_registry_flows \
  --registry_client ConnectorFlowRegistryClient \
  --bucket connectors \
  --detailed
```

List buckets (folders) in a registry:

```bash
nipyapi --profile <profile> versioning list_git_registry_buckets <registry-client-id>
```

## Check for Existing Deployments

Before deploying, check if the flow already exists on the canvas:

```bash
nipyapi --profile <profile> ci list_flows | jq -r '.process_groups[].name'
```

**Important:** Deploying the same connector type twice may share parameter contexts. See `references/ops-parameters-main.md` for implications.

## Deploy a Flow

**Check:** Confirm the flow doesn't already exist on the canvas:

```bash
nipyapi --profile <profile> ci list_flows | jq -r '.process_groups[].name'
```

**Act:** Deploy from registry:

```bash
# Deploy latest version
nipyapi --profile <profile> ci deploy_flow \
  --registry_client ConnectorFlowRegistryClient \
  --bucket connectors \
  --flow postgresql

# Or deploy specific version
nipyapi --profile <profile> ci deploy_flow \
  --registry_client ConnectorFlowRegistryClient \
  --bucket connectors \
  --flow postgresql \
  --version 5
```

**Exact argument names (do not substitute):**
- `--registry_client` - registry client name or ID (exact match)
- `--bucket` - bucket/folder name
- `--flow` - flow name
- `--version` - optional, for specific version
- `--parameter_context_handling` - optional, `KEEP_EXISTING` (default) or `REPLACE`

**Parameter Context Handling (Git registries only):**
- `KEEP_EXISTING` (default): Reuse parameter contexts that already exist by name
- `REPLACE`: Create new contexts with numbered suffix for isolation

```bash
# Deploy with independent parameter contexts (not shared with existing flows)
nipyapi --profile <profile> ci deploy_flow \
  --registry_client ConnectorFlowRegistryClient \
  --bucket connectors \
  --flow postgresql \
  --parameter_context_handling REPLACE
```

See `references/ops-parameters-main.md` for details on parameter context behavior.

**Check:** Confirm deployment succeeded and flow is present:

```bash
nipyapi --profile <profile> ci list_flows | jq '.process_groups[] | select(.name == "postgresql")'
```

Expect: Flow appears in list with `versioned: true`.

### Deploy Output

```json
{
  "process_group_id": "abc-123-def",
  "process_group_name": "postgresql",
  "version": 7,
  "status": "deployed"
}
```

Record the `process_group_id` for subsequent operations.

## Common Patterns

### Find and Deploy a Connector

```bash
# 1. List available connectors (use registry name directly)
nipyapi --profile <profile> ci list_registry_flows \
  --registry_client ConnectorFlowRegistryClient \
  --bucket connectors

# 2. Deploy (use registry name directly)
nipyapi --profile <profile> ci deploy_flow \
  --registry_client ConnectorFlowRegistryClient \
  --bucket connectors \
  --flow <connector-name>
```

**Note:** Both commands accept registry client by name (exact match). No ID lookup required.

## Available Functions

| Function | Purpose |
|----------|---------|
| `nipyapi ci deploy_flow` | Deploy a flow from registry to canvas |
| `nipyapi ci list_flows` | List deployed flows on canvas (check before deploying) |
| `nipyapi ci list_registry_flows` | List flows available in a registry bucket |
| `nipyapi versioning list_registry_clients` | List available registries |
| `nipyapi versioning list_git_registry_buckets` | List buckets in a registry |
| `nipyapi versioning list_git_registry_flow_versions` | List versions of a specific flow |

## Curl Alternatives

For environments using curl instead of nipyapi. Ensure `$BASE_URL` and `$AUTH_HEADER` are set from your nipyapi profile (see `references/core-guidelines.md` section 4).

### List Registries (curl)

```bash
curl -sk -H "$AUTH_HEADER" "$BASE_URL/flow/registries" | jq '.registries[].component | {id, name, type}'
```

### List Buckets (curl)

```bash
REGISTRY_ID="<registry-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/flow/registries/$REGISTRY_ID/buckets" | jq '.buckets[].id'
```

### List Flows in Bucket (curl)

```bash
REGISTRY_ID="<registry-id>"
BUCKET="connectors"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/flow/registries/$REGISTRY_ID/buckets/$BUCKET/flows" | jq '.versionedFlows[].versionedFlow.flowName'
```

### List Flow Versions (curl)

```bash
FLOW_ID="<flow-name>"
curl -s -H "$AUTH_HEADER" "$BASE_URL/flow/registries/$REGISTRY_ID/buckets/$BUCKET/flows/$FLOW_ID/versions" | jq '.'
```

### Deploy Flow (curl)

```bash
# Get the latest version
VERSION=$(curl -sk -H "$AUTH_HEADER" "$BASE_URL/flow/registries/$REGISTRY_ID/buckets/$BUCKET/flows/$FLOW_ID/versions" | jq -r '.versionedFlowSnapshotMetadataSet[-1].versionedFlowSnapshotMetadata.version')

# Deploy to canvas
curl -s -X POST -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  "$BASE_URL/process-groups/root/process-groups?parameterContextHandlingStrategy=KEEP_EXISTING" \
  -d '{
    "revision": {
      "clientId": "cortex-agent",
      "version": 0
    },
    "disconnectedNodeAcknowledged": false,
    "component": {
      "position": {"x": 100, "y": 100},
      "versionControlInformation": {
        "registryId": "'"$REGISTRY_ID"'",
        "bucketId": "'"$BUCKET"'",
        "flowId": "'"$FLOW_ID"'",
        "version": "'"$VERSION"'"
      }
    }
  }'
```

### List Deployed Flows (curl)

```bash
curl -s -H "$AUTH_HEADER" "$BASE_URL/flow/process-groups/root" | jq '.processGroupFlow.flow.processGroups[] | {id, name: .component.name, versioned: (.component.versionControlInformation != null)}'
```

---

## Next Step

After deployment completes, **return to the calling workflow** to continue with the next step.

## See Also

- `references/ops-parameters-main.md` - Parameter configuration
- `references/platform-eai.md` - Network access (SPCS)
- `references/ops-flow-lifecycle.md` - Start/stop flows
- `references/ops-flow-export.md` - Export or Import flows from user files (when VCS not in use)
- `references/ops-version-control.md` - Git-based version control for authoring
