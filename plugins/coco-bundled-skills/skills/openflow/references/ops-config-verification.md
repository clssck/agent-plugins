---
name: openflow-ops-config-verification
description: Verify configuration of processors and controller services before starting flows. Validates that properties meet constraints.
---

# Configuration Verification

Verify that processors and controller services are correctly configured before starting a flow. This validates that required properties are set and values meet defined constraints.

**Note:** Verification is a read-only diagnostic that checks property validity, NOT actual connectivity or credentials. A component can pass verification but still fail at runtime if external services are unreachable.

## Scope

- Validating controller service configuration (required properties set, valid values)
- Validating processor configuration (property constraints met)
- Pre-start verification to catch configuration errors early
- Does NOT cover runtime errors (see `references/ops-flow-lifecycle.md` for bulletins)

## When to Verify

Verify configuration:
- Before first start of a newly deployed connector
- After changing connection parameters
- When troubleshooting "Invalid" component states
- Before starting after parameter changes

## Prerequisites

- Component must be stopped (processor) or disabled (controller service)
- Cannot verify while component is running

## Choosing the Right Approach

| Scenario | Function | Use Case |
|----------|----------|----------|
| Verify entire flow before start | `nipyapi.ci.verify_config()` | Most efficient for deployed flows |
| Verify single modified component | `nipyapi.canvas.verify_controller/processor()` | After changing one component |

**Recommendation:** When verifying a deployed flow or process group, use batch verification - it handles all components efficiently with proper result aggregation.

## Batch Verification (Recommended)

Verify all stopped/disabled components in a process group at once:

```python
import nipyapi
nipyapi.profiles.switch()

# Verify all stopped/disabled components in PG
result = nipyapi.ci.verify_config(process_group_id="<pg-id>")

print(f"Verified: {result['verified']}")
print(f"Failed: {result['failed_count']}")
print(result['summary'])
```

Or via CLI:

```bash
nipyapi ci verify_config --process-group-id "<pg-id>"
```

### Batch Verification Options

```python
# Verify only controllers (skip processors)
result = nipyapi.ci.verify_config(
    process_group_id="<pg-id>",
    verify_processors=False
)

# Continue on failure (don't raise exception)
result = nipyapi.ci.verify_config(
    process_group_id="<pg-id>",
    fail_on_error=False
)
# Check result['failed_count'] to see if any failed
```

## Single Component Verification

Use these when you've modified a single component and want to verify just that one:

### Verify a Controller Service

```python
import nipyapi
nipyapi.profiles.switch()

# Get the controller service
controller = nipyapi.canvas.get_controller("<controller-id>", "id")

# Verify configuration (controller must be DISABLED)
results = nipyapi.canvas.verify_controller(controller)

# Check results
for r in results:
    print(f"{r.verification_step_name}: {r.outcome}")
    if r.outcome == "FAILED":
        print(f"  Reason: {r.explanation}")
```

### Verify a Processor

```python
import nipyapi
nipyapi.profiles.switch()

# Get the processor
processor = nipyapi.canvas.get_processor("<processor-id>", "id")

# Verify configuration (processor must be STOPPED)
results = nipyapi.canvas.verify_processor(processor)

# Check results
all_passed = all(r.outcome == "SUCCESSFUL" for r in results)
print(f"Verification {'passed' if all_passed else 'FAILED'}")
```

## Verification Results

Each verification returns a list of `ConfigVerificationResultDTO` objects:

| Field | Description |
|-------|-------------|
| `verification_step_name` | What was checked (e.g., "Perform Validation") |
| `outcome` | `SUCCESSFUL`, `FAILED`, or `SKIPPED` |
| `explanation` | Details about why it passed or failed |

### Common Outcomes

| Outcome | Meaning |
|---------|---------|
| `SUCCESSFUL` | Property validation passed |
| `FAILED` | Required property missing or value invalid |
| `SKIPPED` | Check not applicable for this component |

## Failure Pattern Interpretation

When verification fails, examine the error message to determine the cause and appropriate resolution.

### Blocking Failures

These failures indicate structural problems that **must be resolved before attempting any configuration**. Do not attempt to set properties or parameters on components with blocking failures.

| Error Pattern | Cause | Resolution |
|---------------|-------|------------|
| "not a valid Processor type" | **Missing extension** - processor requires a NAR or Python extension that is not uploaded | Upload the required extension (see `ops-extensions.md`) |
| "is not a valid Controller Service Identifier" | Controller service reference points to non-existent service | Re-create the controller service or fix the reference |

#### Missing Extension Warning

When a processor has a missing extension (NAR or Python processor not uploaded), NiFi exhibits defensive behavior:

- **All properties appear as `sensitive: true`** in the descriptors
- **All property values show as `********`** (masked)
- **The processor type shows as a short name** (e.g., `PrepareRegulatoryFile`) instead of fully-qualified (e.g., `org.apache.nifi.processors.standard.ExecuteSQL`)
- **`extension_missing: true`** in the processor component

**Do not attempt to configure properties on processors with missing extensions.** The sensitive property indicators are misleading - they are NiFi's defensive response to an unknown component, not actual sensitive values. Configuration attempts will appear to succeed but have no effect.

**Detection in verify_config output:**
```json
{
  "name": "MyCustomProcessor",
  "type": "MyCustomProcessor",
  "success": false,
  "failures": [{
    "step": "Perform Validation",
    "explanation": "... Processor is of type MyCustomProcessor, but this is not a valid Processor type"
  }]
}
```

### Resolvable Failures

These failures indicate configuration issues that can be fixed by setting properties or parameters:

| Error Pattern | Cause | Resolution |
|---------------|-------|------------|
| "Property X is required" | Missing required property | Set the property value (`ops-component-config.md`) |
| "Invalid value" | Value doesn't match expected format | Check property documentation |
| "Parameter not found" | References undefined parameter | Create the parameter (`ops-parameters-contexts.md`) |
| "Asset not found" | Asset reference broken | Re-upload or re-link asset (`ops-parameters-assets.md`) |
| "Controller Service ... is disabled" | Processor references a disabled controller | Enable the controller service first |

### Verification Before Configuration

**Always run verification before configuring properties or parameters:**

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --only_failures
```

**Decision tree:**
1. If no failures → proceed with configuration
2. If failures include "not a valid Processor type" → **stop**, resolve missing extension first
3. If failures include "is not a valid Controller Service Identifier" → **stop**, fix controller references first
4. If failures are resolvable (missing parameters, disabled controllers) → proceed with configuration to fix them

---

## Verification vs Validation vs Runtime

| Concept | What it Checks | When |
|---------|----------------|------|
| **Validation** | Syntax and required fields | Always (NiFi internal) |
| **Verification** | Property constraints | On-demand (this workflow) |
| **Runtime** | Actual connectivity | When component runs |

A component can:
- Be "valid" (all required fields set) ✓
- Pass verification (property values acceptable) ✓
- Still fail at runtime (wrong password, host unreachable) ✗

---

## Curl Alternative

For environments using curl instead of nipyapi. Ensure `$BASE_URL` and `$AUTH_HEADER` are set from your nipyapi profile (see `references/core-guidelines.md` section 4).

### Start Verification (curl)

```bash
COMPONENT_ID="<controller-service-id>"

# Start verification
RESPONSE=$(curl -sk -X POST -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  "$BASE_URL/controller-services/$COMPONENT_ID/config/verification-requests" \
  -d '{"request": {"properties": {}, "componentId": "'"$COMPONENT_ID"'", "attributes": {}}}')

REQUEST_ID=$(echo "$RESPONSE" | jq -r '.request.requestId')
REQUEST_URI=$(echo "$RESPONSE" | jq -r '.request.uri')
```

For processors, use `/processors/$PROCESSOR_ID/config/verification-requests` instead.

### Poll and Get Results (curl)

```bash
# Poll until complete
while true; do
  STATUS=$(curl -sk -H "$AUTH_HEADER" "$REQUEST_URI")
  COMPLETE=$(echo "$STATUS" | jq -r '.request.complete')
  [ "$COMPLETE" = "true" ] && break
  sleep 2
done

# Show results
curl -sk -H "$AUTH_HEADER" "$REQUEST_URI" | jq '.request.results[] | {step: .verificationStepName, outcome, explanation}'
```

### Cleanup (curl) - MANDATORY

```bash
curl -sk -X DELETE -H "$AUTH_HEADER" "$REQUEST_URI"
```

**Warning:** Failing to cleanup verification requests may cause issues with subsequent verifications.

---

## Next Step

After verification completes:
- If passed: Proceed to start the flow (see `references/ops-flow-lifecycle.md`)
- If failed: Fix the configuration and re-verify

Return to the calling workflow to continue.
