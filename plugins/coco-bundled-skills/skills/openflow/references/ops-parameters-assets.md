---
name: openflow-ops-parameters-assets
description: Manage parameter assets (JARs, certificates, drivers). Use for uploading, listing, and linking binary files to parameters. Supports multiple assets per parameter.
---

# Parameter Asset Operations

Manage assets (binary files like JARs, certificates, or drivers) attached to parameter contexts. A single parameter can reference **multiple assets** (useful for JMS, complex JDBC drivers, etc.).

**Scope:** Use this reference for uploading, listing, and managing binary assets. Assets can be used with any parameter context, whether using inheritance or a simple single-context setup.

**Load First:** For parameter inspection or configuration (not just asset upload), load `references/ops-parameters-main.md` before this reference.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern (see `references/core-guidelines.md`).

**Discovery:** Run `nipyapi ci upload_asset --help` to see all available arguments.

## List Existing Assets

```bash
nipyapi parameters list_assets "<context-id>"
```

Or with Python for formatted output:

```python
import nipyapi
nipyapi.profiles.switch()

assets = nipyapi.parameters.list_assets('<context-id>')
for a in assets:
    print(f"{a['name']} (ID: {a['id']})")
```

## Upload Asset from URL

**Check:** List existing assets first. **Act:** Upload. **Check:** Verify asset appears and parameter updated.

```bash
nipyapi ci upload_asset \
  --url "https://example.com/myfile.jar" \
  --context_id "<parameter-context-id>" \
  --param_name "My Asset Parameter"
```

**Exact argument names (do not substitute):**
- `--url` (not --file_path for remote files; use URL when possible)
- `--context_id` (not --parameter_context_id, --ctx_id, etc.)
- `--param_name` (not --parameter_name, --name, etc.)

Output:

```json
{
  "asset_id": "8af31588-3118-3c71-b2ea-121a78572076",
  "asset_name": "myfile.jar",
  "asset_digest": "f2a1cc0352dd5e5c6f65dbadff27bee00c32e432c6ad030d07447f8a5983c42a",
  "context_id": "<context-id>",
  "context_name": "Source Parameters",
  "parameter_updated": "true",
  "parameter_name": "My Asset Parameter"
}
```

## Upload Without Linking (Just Store)

```bash
nipyapi ci upload_asset \
  --url "https://example.com/another-file.jar" \
  --context_id "<parameter-context-id>"
```

This stores the asset in the context but does not link it to any parameter. Useful for staging assets before configuring parameters.

## Multiple Assets per Parameter

A single parameter can reference **multiple assets**. This is common for:
- **JMS/ActiveMQ:** Requires multiple JARs (activemq-client, jakarta.jms-api, etc.)
- **JDBC drivers:** Some databases need multiple JARs
- **Custom libraries:** When dependencies span multiple files

### Upload Multiple Assets, Then Link Together

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

context_id = "<parameter-context-id>"

# Upload all required JARs (without linking yet)
jar_urls = [
    "https://repo1.maven.org/maven2/.../activemq-client-6.1.4.jar",
    "https://repo1.maven.org/maven2/.../jakarta.jms-api-3.1.0.jar",
    "https://repo1.maven.org/maven2/.../activemq-openwire-legacy-6.1.4.jar",
]

uploaded_assets = []
for url in jar_urls:
    result = nipyapi.parameters.upload_asset_from_url(context_id, url)
    uploaded_assets.append({"id": result["id"], "name": result["name"]})
    print(f"Uploaded: {result['name']}")

# Link all assets to a single parameter using the assets parameter
ctx = nipyapi.parameters.get_parameter_context(context_id, identifier_type='id')
param = nipyapi.parameters.prepare_parameter_with_asset(
    name="JMS Client Libraries",
    assets=uploaded_assets,  # List of dicts with 'id' and 'name' keys
    description="ActiveMQ client JARs"
)
nipyapi.parameters.upsert_parameter_to_context(ctx, param)
print(f"Linked {len(uploaded_assets)} assets to parameter")
```

### Curl: Link Multiple Assets

```bash
# After uploading assets, link multiple to one parameter
curl -sk -X PUT -H "$AUTH_HEADER" -H "Content-Type: application/json" \
  "$BASE_URL/parameter-contexts/$CONTEXT_ID" \
  -d '{
    "revision": '"$REVISION"',
    "component": {
      "id": "'"$CONTEXT_ID"'",
      "parameters": [
        {
          "parameter": {
            "name": "JMS Client Libraries",
            "sensitive": false,
            "value": null,
            "referencedAssets": [
              {"id": "asset-id-1", "name": "activemq-client-6.1.4.jar"},
              {"id": "asset-id-2", "name": "jakarta.jms-api-3.1.0.jar"},
              {"id": "asset-id-3", "name": "activemq-openwire-legacy-6.1.4.jar"}
            ]
          }
        }
      ]
    }
  }'
```

**Note:** When a parameter references assets, its `value` must be `null`. The processor reads the asset files directly.

## Switch Between Asset Versions

If you've uploaded multiple versions of an asset:

```python
import nipyapi
nipyapi.profiles.switch()

context_id = "<parameter-context-id>"
target_version = "2.0"  # Part of filename to match

# Find the asset
assets = nipyapi.parameters.list_assets(context_id)
target_asset = next(a for a in assets if target_version in a['name'])
print(f"Switching to: {target_asset['name']}")

# Update parameter
ctx = nipyapi.parameters.get_parameter_context(context_id, identifier_type='id')
param = nipyapi.parameters.prepare_parameter_with_asset(
    name="My Asset Parameter",  # Adjust for your parameter
    asset_id=target_asset['id'],
    asset_name=target_asset['name']
)
nipyapi.parameters.upsert_parameter_to_context(ctx, param)
print("Done!")
```

## Environment Variables for Automation

| Variable | Description |
|----------|-------------|
| `NIFI_PARAMETER_CONTEXT_ID` | Direct context ID for asset uploads |
| `NIFI_ASSET_URL` | URL to download asset from |
| `NIFI_ASSET_PARAM_NAME` | Parameter to link asset to |

## Troubleshooting

### "Setting a value will replace the asset reference"

This warning appears when using `configure_inherited_params` on a parameter that currently references an asset. If you want to replace the asset with a text value, proceed. If you want to update the asset itself, use `upload_asset` instead.

### Asset not appearing after upload

Verify the upload succeeded by listing assets:

```bash
nipyapi parameters list_assets "<context-id>"
```

If the asset appears but isn't linked to a parameter, use the `--param_name` option when uploading, or manually link it using the Python API.

## Curl Alternative

For environments using curl instead of nipyapi. Ensure `$BASE_URL` and `$AUTH_HEADER` are set from your nipyapi profile (see `references/core-guidelines.md` section 4).

### List Assets (curl)

```bash
CONTEXT_ID="<parameter-context-id>"
curl -sk -H "$AUTH_HEADER" "$BASE_URL/parameter-contexts/$CONTEXT_ID/assets" | jq '.assets[] | {id, name}'
```

### Upload Asset from File (curl)

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

### Link Asset to Parameter (curl)

After uploading, link the asset to a parameter:

```bash
# Get current context to retrieve revision
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

## Next Step

After asset operations:
- To configure parameter values, load `references/ops-parameters-configure.md`
- To verify flow, load `references/ops-flow-lifecycle.md`
- Return to `references/ops-parameters-main.md` for routing
