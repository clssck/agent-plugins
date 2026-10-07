---
name: openflow-ops-version-control
description: Version control for flows. Setup Git registry clients (GitHub/GitLab), save versions, commit changes, and rollback mistakes.
---

# Version Control

Version control operations for flows built in Openflow.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

## Scope

- Git registry client setup (GitHub/GitLab)
- Committing and rolling back flow versions
- For read-only deployment from registries, see `references/ops-flow-deploy.md`

## Prerequisites

- nipyapi CLI installed and profile configured (see `references/bootstrap-cli.md`)
- A Git repository for storing flows (GitHub or GitLab)
- Access token for the Git provider

## Key Concepts

| Term | Meaning |
|------|---------|
| **Registry Client** | Connection from NiFi to a Git repository |
| **Bucket** | A folder in the Git repository that contains flows |
| **Flow** | A versioned process group stored in the registry |
| **Version** | A specific commit/snapshot of a flow |

---

## Workflow: First-Time Setup

### Step 1: Identify the Target Process Group

```bash
nipyapi --profile <profile> ci list_flows
```

Look for process groups with `versioned: false`.

### Step 2: Check Existing Registry Clients

```bash
nipyapi --profile <profile> versioning list_registry_clients
```

If a client for your repository exists, skip to Step 4.

### Step 3: Create a Registry Client

#### Parameter Reference

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| `--repo` | Yes | Repository in `owner/repo` format | - |
| `--token` | Yes | Personal Access Token | - |
| `--provider` | No | `github` or `gitlab` | `github` |
| `--client_name` | No | Name for the registry client | `{Provider}-FlowRegistry` |
| `--api_url` | No | API URL (Enterprise/self-hosted only) | Standard API |
| `--default_branch` | No | Default branch | `main` |
| `--repository_path` | No | Subfolder path for storing flows | (root) |

#### GitHub Example

```bash
nipyapi --profile <profile> ci ensure_registry \
  --repo Chaffelson/flowregtest \
  --token ghp_xxxxxxxxxxxxxxxxxxxx \
  --client_name flowregtest \
  --provider github
```

#### GitLab Example

```bash
nipyapi --profile <profile> ci ensure_registry \
  --repo mygroup/myproject \
  --token glpat-xxxxxxxxxxxxxxxxxxxx \
  --client_name my-gitlab-flows \
  --provider gitlab
```

#### Self-Hosted GitLab

```bash
nipyapi --profile <profile> ci ensure_registry \
  --repo mygroup/myproject \
  --token glpat-xxxxxxxxxxxxxxxxxxxx \
  --provider gitlab \
  --api_url https://gitlab.mycompany.com/
```

### Step 4: List Available Buckets

```bash
nipyapi --profile <profile> versioning list_git_registry_buckets <registry_client_id>
```

**Ask the user:** "Which folder would you like to save your flow to?"

### Step 5: Save Initial Version

**Before committing:** The process group name becomes the flow name in the registry. Verify the name is production-ready (e.g., `octopus-products-ingestion` not `test-flow`). Renaming later requires detaching and re-committing as a new flow.

```bash
nipyapi --profile <profile> ci commit_flow \
  --process_group_id <pg_id> \
  --registry_client <registry_name> \
  --bucket <bucket_name> \
  --comment "Initial commit"
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--process_group_id` | Yes | ID of the process group |
| `--registry_client` | Yes | Name of the registry client |
| `--bucket` | Yes | Bucket/folder name |
| `--comment` | No | Commit message |
| `--flow_name` | No | Name in registry (defaults to PG name) |

---

## Workflow: Ongoing Version Control

### Check Version Status

```bash
nipyapi --profile <profile> ci list_flows
```

| State | Meaning |
|-------|---------|
| `LOCALLY_MODIFIED` | Uncommitted changes exist |
| `UP_TO_DATE` | Flow matches committed version |
| `STALE` | Newer version available in registry |

### Save Changes (Commit)

```bash
nipyapi --profile <profile> ci commit_flow \
  --process_group_id <pg_id> \
  --comment "Description of changes"
```

For subsequent commits, `--registry_client` and `--bucket` are not needed.

### Rollback Changes (Revert)

Discard local modifications and restore to last committed version:

```bash
nipyapi --profile <profile> ci revert_flow --process_group_id <pg_id>
```

### View Version History

```bash
nipyapi --profile <profile> ci get_flow_versions --process_group_id <pg_id>
```

### Switch to a Specific Version

```bash
nipyapi --profile <profile> ci change_flow_version \
  --process_group_id <pg_id> \
  --target_version <commit_sha>
```

Omit `--target_version` to update to the latest version.

### Fork a Flow (Detach and Re-version)

To make modifications to a read-only flow:

```bash
# Step 1: Detach from the current registry
nipyapi --profile <profile> ci detach_flow --process_group_id <pg_id>

# Step 2: Save to your own registry
nipyapi --profile <profile> ci commit_flow \
  --process_group_id <pg_id> \
  --registry_client <your_registry> \
  --bucket <your_bucket> \
  --comment "Forked for customization"
```

**Important:** After forking, you will not receive updates from the original registry.

---

## Parameter Context Handling

The registry client defaults to `Parameter Context Values: IGNORE_CHANGES`:

| Setting | Behavior |
|---------|----------|
| `IGNORE_CHANGES` | Preserve local parameter values (default) |
| `RETAIN` | Keep parameter values from the registry |
| `REMOVE` | Clear parameter values on version change |

---

## Troubleshooting

### Registry Client Creation Fails

- **Missing token:** Pass `--token` or set `GH_REGISTRY_TOKEN` / `GL_REGISTRY_TOKEN`
- **Invalid repo format:** Must be `owner/repo` format
- **Repository not accessible:** Verify token has `repo` scope

### Bucket Not Found

- Buckets are folders in the Git repository root
- Create the folder in the repository if it doesn't exist
- Folders starting with `.` are excluded

### Version Control Operations Fail

- Stop the process group before version operations
- Check for validation errors on processors/controllers

---

## Available CI Functions

### Authorship Operations (This Reference)

| Function | Purpose |
|----------|---------|
| `nipyapi ci list_flows` | List flows with version status |
| `nipyapi ci get_flow_versions` | List all versions of a flow |
| `nipyapi ci commit_flow` | Save initial or subsequent versions |
| `nipyapi ci change_flow_version` | Switch to a specific version |
| `nipyapi ci revert_flow` | Discard local changes |
| `nipyapi ci detach_flow` | Remove version control (for forking) |
| `nipyapi ci get_flow_diff` | Get local (uncommitted) modifications |

### Deployment Operations (See ops-flow-deploy.md)

| Function | Purpose |
|----------|---------|
| `nipyapi ci list_flows` | List deployed flows on canvas |
| `nipyapi ci list_registry_flows` | List flows available in a registry bucket |
| `nipyapi ci deploy_flow` | Deploy a flow from registry to canvas |
| `nipyapi versioning list_registry_clients` | List available registries |
| `nipyapi versioning list_git_registry_buckets` | List buckets in a registry |

### Lifecycle Operations (See ops-flow-lifecycle.md)

| Function | Purpose |
|----------|---------|
| `nipyapi ci start_flow` | Enable controllers and start processors |
| `nipyapi ci stop_flow` | Stop processors (optionally disable controllers) |
| `nipyapi ci get_status` | Get flow status and health metrics |
| `nipyapi ci cleanup` | Delete a flow from the canvas |

---

## Alternative: Export Without VCS

If Git-based version control is not available or appropriate, you can export flow definitions directly to JSON files for backup or migration:

```bash
nipyapi --profile <profile> ci export_flow_definition \
  --process_group_id "<pg-id>" \
  --file_path backup.json
```

See `references/ops-flow-export.md` for complete export/import workflows.

**Key difference:** VCS saves include full parameter context definitions, handles diffs, and offers intelligent version migration. Direct export only includes the parameter context **name** - export parameter contexts separately for a complete backup.

---

## Related References

- `references/ops-flow-deploy.md` - Deploy flows from registries
- `references/ops-flow-lifecycle.md` - Start, stop, monitor, delete flows
- `references/ops-tracked-modifications.md` - Version change with preserved local modifications
- `references/ops-flow-export.md` - Export/import flows without VCS
