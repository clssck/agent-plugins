---
name: openflow-ops-extensions
description: Manage custom NAR extensions in Openflow runtimes. Use for uploading NARs, Python processor initialization, and version management.
---

# Extension Operations

This reference covers managing custom NAR (NiFi Archive) extensions in Openflow runtimes. A custom NAR may contain Java or Python components.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

## Scope

This reference covers:
- Uploading and managing custom NAR files
- Python processor initialization
- NAR version management
- Troubleshooting missing or ghosted components

## Key Concepts

| Term | Meaning |
|------|---------|
| **NAR** | NiFi Archive - a bundle containing processors, controller services, or other components |
| **Extension** | A custom component type provided by a NAR |
| **Python Processor** | A processor written in Python that requires virtual environment setup |
| **Orphaned Component** | A processor/controller whose NAR has been removed |
| **Ghosted Processor** | A processor with multiple possible versions or missing versions |

## Prerequisites

- nipyapi CLI installed and profile configured (see `references/bootstrap-cli.md`)
- NAR file built and accessible locally
- For Python processors: runtime may need EAI access for PyPI (see `references/platform-eai.md`)

## CLI Commands Reference

| Command | Purpose |
|---------|---------|
| `nipyapi ci list_nars` | List all installed NARs |
| `nipyapi ci upload_nar` | Upload and install a NAR |
| `nipyapi ci delete_nar` | Delete a NAR (with optional force) |

---

## 1. Upload and Verify

This workflow uploads a NAR and confirms the components are available.

### Step 1: Check Existing NARs

```bash
nipyapi ci list_nars
```

Example output:

```json
{
  "nars": [
    {
      "identifier": "0af6f178-2d1d-31af-b3e6-6ec38a01c82c",
      "coordinate": "prepare-regulatory-file:prepare-regulatory-file-nar:0.0.1",
      "state": "Installed"
    }
  ],
  "count": 1
}
```

### Step 2: Act - Upload NAR

```bash
nipyapi ci upload_nar --file_path /path/to/my-processor.nar
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--file_path` | Yes | Path to the NAR file |
| `--timeout` | No | Max seconds to wait for installation (default: 120) |

### Step 3: Check - Verify Installation

```python
import nipyapi
nipyapi.profiles.switch()

# Get NAR details
nar = nipyapi.extensions.get_nar('<nar_identifier>')
details = nipyapi.extensions.get_nar_details(nar.identifier)

# List processor types
for proc_type in details.processor_types:
    print(f"Processor: {proc_type.type}")

# List controller service types
for cs_type in details.controller_service_types:
    print(f"Controller: {cs_type.type}")
```

**End of upload workflow.** Report the uploaded NAR and available component types to the user. Do not automatically create processors - wait for the user to request that.

---

## 2. Component Creation and Initialization

This section covers what happens when a user requests creation of a component from an uploaded NAR.

### Creating a Processor (On User Request)

If the user asks to create a processor from an uploaded NAR:

```python
import nipyapi
nipyapi.profiles.switch()

# Get the processor type
proc_type = nipyapi.canvas.get_processor_type('NameOfCustomProcessor')

# Get parent process group
pg = nipyapi.canvas.get_process_group('<pg_id>', 'id')

# Use layout module for proper positioning - see references/ops-layout.md

# Create the processor
proc = nipyapi.canvas.create_processor(
    parent_pg=pg,
    processor=proc_type,
    location=position,
    name='My Custom Processor'
)
print(f"Created: {proc.id}")
```

**Note:** For proper canvas positioning, use the layout module functions. See `references/ops-layout.md` for positioning guidance.

### Python Processor Initialization

Python Processors have their declared dependenices downloaded from PyPi during initialization, if the Runtime cannot connect to PyPi it may fail to initialize.

Python processors go through specific states during initialization. Understanding these states helps diagnose issues.

| State | Validation Status | Meaning |
|-------|-------------------|---------|
| `initializing` | INVALID | Setting up virtual environment |
| `downloading_dependencies` | INVALID | Downloading packages from PyPI |
| `dependency_failed` | INVALID | Failed to download dependencies (check EAI) |
| `ready` | INVALID/VALID | Ready for configuration |
| `missing_nar` | INVALID | NAR was removed |

### Initialization Timeline

Typical initialization for a Python processor:

1. **0-5 seconds:** "Initializing runtime environment" - venv setup
2. **5-30 seconds:** "Downloading third-party dependencies" - if external packages needed
3. **After download:** Properties loaded, processor ready for configuration

### Virtual Environment Caching

Python Virtual Environments are cached by NAR coordinate (group:artifact:version):

| Scenario | Behavior |
|----------|----------|
| Same coordinate | Reuses cached venv, instant initialization |
| New version | Creates fresh venv, triggers full dependency download |
| Delete and re-upload same version | May clear cache and trigger fresh initialization |

---

## 3. Version Management

When multiple versions of the same processor type are installed (via multiple NAR files), you can manage which version an existing processor uses.

### Check Available Versions

```python
import nipyapi
nipyapi.profiles.switch()

# List all available versions for a processor type
versions = nipyapi.extensions.get_processor_bundle_versions('PrepareRegulatoryFile')
for v in versions:
    print(f"Version: {v['bundle'].version}")
```

### Change Processor Version

```python
import nipyapi
nipyapi.profiles.switch()

# Get the processor
proc = nipyapi.canvas.get_processor('<processor_id>', 'id')
print(f"Current version: {proc.component.bundle.version}")

# Change to a different version
updated = nipyapi.extensions.change_processor_bundle_version(proc, '0.0.2-SNAPSHOT')
print(f"New version: {updated.component.bundle.version}")
```

**Requirements:**
- The processor must be stopped before changing versions
- Properties and configuration should be captured before change and validated afterwards

### Create Processor with Specific Version

When multiple versions exist, specify the version during creation:

```python
import nipyapi
nipyapi.profiles.switch()

# Get type with specific bundle version
proc_type = nipyapi.extensions.get_processor_type_version(
    'PrepareRegulatoryFile',
    '0.0.2-SNAPSHOT'
)

# Create - bundle is included automatically
proc = nipyapi.canvas.create_processor(pg, proc_type, (300, 300), 'MyProc')
```

---

## 4. Deletion

**Check:** Attempt deletion - this will fail if components are in use:

```bash
nipyapi ci delete_nar --identifier <nar_id>
```

**If deletion fails** with "components are instantiated from this NAR":

1. Identify which components use the NAR
2. Stop and delete those components first
3. Retry the delete

**Only if clean removal is not possible**, discuss force delete with the user:

```bash
nipyapi ci delete_nar --identifier <nar_id> --force
```

**Warning:** Force deletion orphans components. They will show "Missing Processor" errors and require manual cleanup or NAR re-upload to recover.

### Delete by Coordinate

You can also delete by coordinate instead of identifier:

```bash
nipyapi ci delete_nar \
  --group_id prepare-regulatory-file \
  --artifact_id prepare-regulatory-file-nar \
  --version 0.0.1
```

### NAR Lifecycle with Active Components

| Action | Result | Component State |
|--------|--------|-----------------|
| Delete NAR (no force) | **Blocked** | Unchanged |
| Delete NAR (force) | NAR removed | STOPPED, INVALID with "Missing Processor" |
| Re-upload same NAR | NAR installed | Recovers to VALID (properties preserved) |

### Recovering Orphaned Components

If a NAR was force-deleted and you need to recover:

1. Re-upload the same NAR version
2. Components automatically recover
3. Properties and configuration are preserved
4. Components can be restarted

---

## 5. Troubleshooting

### "Initializing runtime environment" persists

The Python processor is still setting up its virtual environment. This can take longer if:
- Dependencies need to be downloaded from PyPI
- The runtime doesn't have cached environments
- Network access to PyPI is slow or blocked

**Check EAI configuration:** Python processors may need external access to PyPI. See `references/platform-eai.md`.

### "Missing Processor" error

The NAR containing this processor type has been removed.

**Solutions:**
1. Re-upload the NAR to recover the component
2. Delete the orphaned processor if no longer needed

### NAR installation times out

The NAR is taking too long to install.

**Possible causes:**
- Large NAR file
- Runtime under heavy load
- Installation failed silently

**Check NAR state:**

```python
nar = nipyapi.extensions.get_nar('<identifier>')
print(f"State: {nar.state}")
print(f"Complete: {nar.install_complete}")
print(f"Failure: {nar.failure_message}")
```

### NAR uploads but has no processor types

The NAR installs successfully but shows no processor types.

**Cause:** Python processors may not be valid code, such as missing a `class Java` declaration for NiFi to recognize them:

```python
from nifiapi.flowfiletransform import FlowFileTransform, FlowFileTransformResult

class MyProcessor(FlowFileTransform):
    # THIS IS REQUIRED for NiFi to discover the processor
    class Java:
        implements = ['org.apache.nifi.python.processor.FlowFileTransform']

    class ProcessorDetails:
        version = '1.0.0-SNAPSHOT'
        description = 'My processor'
        tags = ['example']
        dependencies = []

    # ... rest of processor
```

### Cannot delete NAR

Components are using the NAR.

**Options:**
1. Delete/stop all components using the NAR first
2. Use `--force` to orphan the components (not recommended for production)

### Dependency installation failed (Python processors)

If the runtime cannot access PyPI, Python processors with external dependencies will fail to initialize.

**Symptoms:**
- Processor cycles between downloading and failed states
- Properties never load

**Solutions:**
1. Configure EAI for PyPI access (see `references/platform-eai.md`)
2. Bundle all dependencies in the NAR

---

## Next Step

After completing extension operations, **return to the calling workflow** to continue.

If you arrived here directly from the main router, return there for further routing.
