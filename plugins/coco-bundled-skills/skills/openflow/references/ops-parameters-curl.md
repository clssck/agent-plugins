---
name: openflow-ops-parameters-curl
description: Curl alternatives for parameter operations when nipyapi is not available.
---

# Parameter Operations with Curl

Curl alternatives for parameter operations.

**Scope:** Use this reference only when nipyapi is unavailable. Prefer nipyapi commands in `references/ops-parameters-inspect.md` and `references/ops-parameters-configure.md` as they handle complexity automatically.

**Prerequisite:** Understand parameter context concepts in `references/ops-parameters-main.md`.

**Setup:** Ensure `$BASE_URL` and `$AUTH_HEADER` are set from your nipyapi profile (see `references/core-guidelines.md`).

**Note:** Add `-k` to curl commands if you encounter certificate verification errors.

## List All Parameter Contexts

```bash
curl -sk -H "$AUTH_HEADER" "$BASE_URL/flow/parameter-contexts" | jq '.parameterContexts[].component | {id, name}'
```

## Get Parameter Context Details

```bash
CONTEXT_ID="<context-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID" | jq '{
  name: .component.name,
  inherited_parameter_contexts: .component.inherited_parameter_contexts,
  parameters: [.component.parameters[].parameter | {name: .name, value: .value, sensitive: .sensitive}]
}'
```

## Get Parameters Only

```bash
CONTEXT_ID="<context-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID" | jq '.component.parameters[].parameter | {name, value, sensitive}'
```

## Check Context Bindings

See which process groups use a parameter context:

```bash
CONTEXT_ID="<context-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID" | jq '{
  name: .component.name,
  bound_process_groups: [.component.bound_process_groups[]? | {name: .component.name, id: .id}]
}'
```

## Find Parameter Ownership

Before updating a parameter, identify which context owns it:

```bash
# Get the process group's bound parameter context
PG_ID="<process-group-id>"
CTX_ID=$(curl -sk -H "$AUTH_HEADER" "$BASE_URL/process-groups/$PG_ID" | jq -r '.component.parameterContext.id')

# Get the context with its inherited contexts
curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CTX_ID" | jq '{
  name: .component.name,
  id: .component.id,
  parameters: [.component.parameters[].parameter.name],
  inherited_from: [.component.inheritedParameterContexts[]? | {name: .component.name, id: .component.id}]
}'
```

Then check each inherited context to find where the target parameter is defined:

```bash
INHERITED_CTX_ID="<inherited-context-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$INHERITED_CTX_ID" | jq '.component.parameters[].parameter.name'
```

## Update Parameter Value

**Critical:** Always update parameters in their owning context, not a parent context. Adding a parameter to the wrong context creates shadowing.

```bash
CONTEXT_ID="<context-id>"

# Get current revision
REVISION=$(curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID" | jq '.revision')

# Update parameter
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  "$BASE_URL/parameter-contexts/$CONTEXT_ID" \
  -d '{
    "revision": '"$REVISION"',
    "component": {
      "id": "'"$CONTEXT_ID"'",
      "parameters": [
        {
          "parameter": {
            "name": "Database Host",
            "value": "new-host.example.com"
          }
        }
      ]
    }
  }'
```

## Update Multiple Parameters

```bash
CONTEXT_ID="<context-id>"
REVISION=$(curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID" | jq '.revision')

curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  "$BASE_URL/parameter-contexts/$CONTEXT_ID" \
  -d '{
    "revision": '"$REVISION"',
    "component": {
      "id": "'"$CONTEXT_ID"'",
      "parameters": [
        {"parameter": {"name": "Database Host", "value": "new-host.example.com"}},
        {"parameter": {"name": "Database Port", "value": "5432"}}
      ]
    }
  }'
```

## List Assets

```bash
CONTEXT_ID="<parameter-context-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID/assets" | jq '.assets[] | {id, name}'
```

## Upload Asset from File

**Important:** Assets must be uploaded with `Content-Type: application/octet-stream` and the file contents directly as the body (not multipart/form-data). Include a `filename` header.

```bash
CONTEXT_ID="<parameter-context-id>"
FILE_PATH="/path/to/driver.jar"
FILENAME=$(basename "$FILE_PATH")

ASSET_ID=$(curl -sk -X POST -H "$AUTH_HEADER" \
  -H "Content-Type: application/octet-stream" \
  -H "filename: $FILENAME" \
  --data-binary "@$FILE_PATH" \
  "$BASE_URL/parameter-contexts/$CONTEXT_ID/assets" | jq -r '.asset.id')

echo "Uploaded asset ID: $ASSET_ID"
```

## Link Asset to Parameter

After uploading, link the asset to a parameter:

```bash
CONTEXT_ID="<context-id>"
ASSET_ID="<asset-id>"
FILENAME="driver.jar"

# Get current revision
REVISION=$(curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID" | jq '.revision')

# Update parameter with asset reference
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  "$BASE_URL/parameter-contexts/$CONTEXT_ID" \
  -d '{
    "revision": '"$REVISION"',
    "component": {
      "id": "'"$CONTEXT_ID"'",
      "parameters": [
        {
          "parameter": {
            "name": "JDBC Driver",
            "sensitive": false,
            "description": "The path to the JDBC Driver",
            "value": null,
            "referencedAssets": [{"id": "'"$ASSET_ID"'", "name": "'"$FILENAME"'"}]
          }
        }
      ]
    }
  }'
```

---

## Limitations

Curl is suitable for basic operations but has limitations:

| Operation | Curl | nipyapi |
|-----------|------|---------|
| Simple parameter update | Yes | Yes |
| Inheritance-aware update | Manual | Automatic |
| Ownership detection | Manual | Automatic |
| Dry run | No | Yes |
| File-based import | Manual | Yes |
| Export to file | Manual | Yes |

For complex parameter hierarchies, consider installing nipyapi.

---

## Next Step

Return to `references/ops-parameters-main.md` for routing to other parameter operations.
