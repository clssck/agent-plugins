---
name: ref-spcs-service-spec
description: "Service specification file templates for SPCS in Native Apps: static spec, template spec with consumer variables, and multi-container patterns."
parent_skill: native-app-provider
---

# SPCS Service Spec Reference

## Service Specification File Template

Place in the project directory (e.g., `containers/service_spec.yaml`). Paths are relative to the app root when referenced via `FROM SPECIFICATION_FILE`.

```yaml
spec:
  containers:
  - name: <container_name>
    image: /<db>/<schema>/<repo>/<image_name>:<tag>
    env:
      PORT: "8080"
    resources:
      requests:
        memory: 1Gi
        cpu: 500m
      limits:
        memory: 2Gi
        cpu: 1000m
    readinessProbe:
      port: 8080
      path: /healthcheck
  endpoints:
  - name: <endpoint_name>
    port: 8080
    public: true
serviceRoles:
- name: <service_role_name>
  endpoints:
  - <endpoint_name>
```

**Create service from this file** (in the setup script, after the preamble):
```sql
CREATE SERVICE IF NOT EXISTS <schema>.<service_name>
  IN COMPUTE POOL IDENTIFIER(:pool_name)
  FROM SPECIFICATION_FILE = '/containers/service_spec.yaml'
  MIN_INSTANCES = 1
  MAX_INSTANCES = 1;
```

The path is relative to the app root and must start with `/`. No stage prefix — native apps resolve the path from the app package automatically.

**Key rules:**
- `image` uses `/<db>/<schema>/<repo>/<image>` format (no registry URL)
- Endpoints with `public: true` require the `BIND SERVICE ENDPOINT` privilege
- Align `readinessProbe.port`, container env `PORT`, and `endpoints.port`
- `serviceRoles` is a **top-level key** (sibling of `spec:`), NOT nested under `spec:`
- **Container names** (`containers[].name`): lowercase alphanumeric and hyphens only, must start with a letter, end with alphanumeric, max 63 chars. **No underscores.** (e.g., `hello-service` not `hello_container`)
- **Endpoint names** allow only lowercase alphanumeric + hyphens (e.g. `my-endpoint` ✅, `my_endpoint` ❌)
- **Service role names** must be valid SQL identifiers (no hyphens) for use after `!` in GRANT statements — derive from endpoint name by replacing hyphens with underscores (e.g. endpoint `my-endpoint` → role `my_endpoint_role`)

## Specification Template File

Use templates when the service needs consumer-provided arguments (e.g., configuration values). Arguments are stored in the app instance for use during upgrades.

```yaml
spec:
  containers:
  - name: <container_name>
    image: /<db>/<schema>/<repo>/<image_name>:<tag>
    env:
      CUSTOM_CONFIG: "{{consumer_config_value}}"
  endpoints:
  - name: <endpoint_name>
    port: 8080
    public: true
```

**Create with template** (standalone or inside `grant_callback`):
```sql
CREATE SERVICE IF NOT EXISTS <schema>.<service_name>
  IN COMPUTE POOL <pool_name>
  FROM SPECIFICATION_TEMPLATE_FILE = '/containers/<spec_template>.yaml'
  USING (consumer_config_value => '<value>');
```

**Inside `grant_callback`** — use placeholder values at install time; consumer configures later via the Configure Procedure:
```sql
-- Inside the BIND SERVICE ENDPOINT branch of grant_callback:
CREATE SERVICE IF NOT EXISTS services.<service_name>
  IN COMPUTE POOL IDENTIFIER(:pool_name)
  FROM SPECIFICATION_TEMPLATE_FILE = '/containers/service_spec.yaml'
  USING (api_url => 'https://placeholder.example.com', model_name => 'default')
  MIN_INSTANCES = 1
  MAX_INSTANCES = 1;
```

## Mounting Secrets for External API Authentication

When an SPCS service needs to call an external API that requires OAuth (or any credential), the service reads the credential from a **file mounted into the container** by SPCS — not from an env var. The credential is a Snowflake `SECRET` object that you attach to the container via the spec YAML.

This pattern is used alongside:
- A `SECURITY INTEGRATION` that owns the OAuth client credentials (see `request-security-integration/SKILL.md`)
- A `SECRET` of `TYPE = OAUTH2` bound to that security integration
- An `EXTERNAL ACCESS INTEGRATION` with `ALLOWED_AUTHENTICATION_SECRETS = ALL` and the outbound host (see `request-external-access-integration/SKILL.md` Approach A and `app-spec-eai.md`). Using `ALL` avoids listing specific secrets and works for both app-owned and consumer-owned secrets.
- An app specification of `TYPE = SECURITY_INTEGRATION` (OAuth) and `TYPE = EXTERNAL_ACCESS`

### YAML pattern

Add a `secrets:` block to the container. Each entry mounts one Snowflake secret as files under `directoryPath`:

```yaml
spec:
  containers:
  - name: <container_name>
    image: /<db>/<schema>/<repo>/<image_name>:<tag>
    env:
      PORT: "8080"
    secrets:
    - snowflakeSecret: <schema>.<secret_name>
      directoryPath: '/usr/local/creds'
    resources:
      requests:
        memory: 512Mi
        cpu: 250m
    readinessProbe:
      port: 8080
      path: /healthcheck
  endpoints:
  - name: <endpoint_name>
    port: 8080
    public: true
```

**Key rules:**
- `snowflakeSecret` must be the fully qualified name of a schema-level `SECRET`. Account-level objects (SI, EAI) are **not** referenced here.
- `directoryPath` is the container filesystem path where SPCS writes the credential files.
- **Do NOT** put `EXTERNAL_ACCESS_INTEGRATIONS` in this YAML. EAI is attached at `CREATE SERVICE` time in SQL — see `ref-spcs-setup-script.md` § Attaching EAI to a Service.
- **Approach A (app-created secret)**: `snowflakeSecret` is the secret your setup script creates (e.g., `core.ms_graph_oauth_secret`).
- **Approach B (consumer-owned secret reference)**: Use `objectReference` to mount the consumer-bound secret. Instead of resolving the secret name at runtime, set `snowflakeSecret` to an object with key `objectReference` whose value is the **manifest reference name** (lowercase, matching the `references:` entry in `manifest.yml`). SPCS resolves the consumer-bound secret automatically via the manifest reference binding — no `SPECIFICATION_TEMPLATE_FILE` or runtime name lookup is needed. Use `SPECIFICATION_FILE` (static YAML, not template). The service is created by the reconciler in `register_callback` (see `ref-spcs-setup-script.md` § Deferred Service Creation Pattern → Reconciler — Approach B).

  ```yaml
  # Approach B: consumer-owned secret via objectReference
  secrets:
  - snowflakeSecret:
      objectReference: consumer_secret   # ← manifest reference name, NOT a resolved FQN
      directoryPath: '/usr/local/creds'
  ```

  > **WARNING**: Do NOT attempt to resolve the consumer secret name at bind-time via `SYSTEM$GET_ALL_REFERENCES()` or `SHOW REFERENCES` and substitute it into a `SPECIFICATION_TEMPLATE_FILE`. `SYSTEM$GET_ALL_REFERENCES` returns internal UUIDs (not FQNs), FQNs with dots are rejected by the template engine, and `SHOW REFERENCES` cannot run inside app SQL procedures. The `objectReference` pattern is the only supported approach for consumer-owned secrets in SPCS service specs.

### Files produced per secret type

| Secret `TYPE` | Files written to `directoryPath` | Container reads |
|---------------|-----------------------------------|-----------------|
| `OAUTH2` (API_AUTHENTICATION) | `access_token` | `open('/usr/local/creds/access_token').read()` |
| `GENERIC_STRING` | `secret_string` | `open('/usr/local/creds/secret_string').read()` |
| `PASSWORD` | `username`, `password` | read each file |

**Python example (OAUTH2):**
```python
with open('/usr/local/creds/access_token') as f:
    access_token = f.read().strip()
headers = {'Authorization': f'Bearer {access_token}'}
```

### Install-time behavior (CRITICAL)

**For Approach B, always defer `CREATE SERVICE` until all references are bound.** For Approach A with `manifest_version: 2`, app specs are auto-granted and the service can be created directly in the setup script. With deferred creation (Approach B) or direct creation after auto-grant (Approach A), `access_token` is populated on the first container start and the install-time 0-byte window does not exist.

The trigger differs by manifest version:

- **`manifest_version: 2`** — Approach A: app specs are auto-granted at install time, so the service can be created directly in the setup script (no deferred pattern needed). Approach B: automatic via `register_callback` on each reference.
- **`manifest_version: 1`** — manual via a consumer-invoked `start_service()` procedure that delegates to the same reconciler. Consumer calls it once after approving both specs.

See `ref-spcs-setup-script.md` § Deferred Service Creation Pattern (manifest_version: 2) and § Deferred Service Creation — manifest_version: 1 (manual trigger).

**Anti-pattern (do NOT ship):** Creating the service at install with specs still `PENDING` and documenting "consumer must suspend + resume after approval" as the supported workflow. SPCS writes a **zero-byte** `access_token` and does **not** auto-rotate the mount when the SI is later approved. Suspend/resume is a workaround for that broken state; deferred creation prevents it from occurring.

## Multi-Container Apps

Multi-container service specs (frontend + backend sharing `localhost`) are a general SPCS pattern. The only native-app-specific requirement: **every image** used across all containers must be listed in `manifest.yml` → `artifacts.container_services.images`. Missing images will fail at version registration.

Containers within the same service share a network namespace — they communicate via `localhost`. The public endpoint is on the frontend; the backend is internal-only.

```yaml
spec:
  containers:
  - name: backend
    image: /<db>/<schema>/<repo>/backend:1.0
    env:
      PORT: "8000"
    resources:
      requests:
        memory: 2Gi
        cpu: 500m
      limits:
        memory: 4Gi
        cpu: 1000m
    readinessProbe:
      port: 8000
      path: /health
  - name: frontend
    image: /<db>/<schema>/<repo>/frontend:1.0
    env:
      PORT: "8080"
      BACKEND_URL: "http://localhost:8000"   # reach backend via localhost
    resources:
      requests:
        memory: 512Mi
        cpu: 250m
      limits:
        memory: 1Gi
        cpu: 500m
    readinessProbe:
      port: 8080
      path: /health
  endpoints:
  - name: ui
    port: 8080
    public: true          # only the frontend is exposed publicly
serviceRoles:
- name: ui_role
  endpoints:
  - ui
```

**manifest.yml** must list both images:
```yaml
artifacts:
  container_services:
    images:
    - /<db>/<schema>/<repo>/backend:1.0
    - /<db>/<schema>/<repo>/frontend:1.0
```
