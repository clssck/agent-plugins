---
name: ref-spcs-image-registry
description: "Image path rules, registry authentication (CLI and PAT), and docker buildx build+push workflow for SPCS in Native Apps."
parent_skill: native-app-provider
---

# SPCS Image Registry Reference

## Image Path Rules

Container images in Native App service specs use **fully-qualified provider-side paths**:

```
/<database>/<schema>/<image_repository>/<image_name>:<tag>
```

**Rules:**
- NO registry URL prefix (e.g., `org-account.registry.snowflakecomputing.com/...` is **invalid**)
- Path must match the provider's image repository location exactly
- Images listed in `manifest.yml` → `artifacts.container_services.images` are the **only** images accessible to the app
- Images become **immutable** once a version is added to the application package — changes require a new version
- External image repositories are not supported — images must be in a Snowflake image repository

**Step 1 — Get the registry hostname:**
```sql
SHOW IMAGE REPOSITORIES IN SCHEMA <db>.<schema>;
-- Use the repository_url column value as <registry_hostname>
```

**Step 2 — Authenticate:**

Detect whether Snowflake CLI is installed:
```bash
snow --version
```

**Path A — Snowflake CLI installed** (agent executes this directly):
```bash
snow spcs image-registry login --connection <conn>
```

**Path B — No Snowflake CLI** (agent provides the command; user must run it themselves — do NOT execute, PAT must not appear in the conversation):

Ask the user to generate a PAT in Snowsight: **your username (top-right) → Programmatic Access Tokens → Generate token**. Then provide this template for the user to run:
```bash
echo "<PAT>" | docker login <registry_hostname> --username USER --password-stdin
```
Source: https://docs.snowflake.com/en/developer-guide/snowpark-container-services/working-with-registry-repository#image-registry-authentication

**Step 3 — Build and push:**

Always use `docker buildx build --platform linux/amd64 --push` — this builds an amd64 image and pushes it directly to the registry in one step. SPCS only runs amd64 containers.

**Do NOT use any of these — they all produce ARM images on ARM64 hosts:**
- `docker build` (even with `--platform linux/amd64` — silently ignored on ARM)
- `docker buildx build --load` then `docker push` (`--load` imports into the local daemon as the **host** architecture, not the target platform — the subsequent push sends an ARM image)
- `docker build` then `docker push`

**Only `--push` works** — it builds inside the buildx builder container (which respects `--platform`) and pushes the correct amd64 image directly to the registry without going through the local Docker daemon.

**CRITICAL ordering: authenticate BEFORE creating the builder.** The `docker-container` buildx driver copies `~/.docker/config.json` into the builder container at creation time. If you create the builder first and login later, the builder never gets the credentials and every `--push` will fail with `UNAUTHORIZED`.

```bash
# 1. Authenticate FIRST — credentials must exist before builder creation
snow spcs image-registry login --connection <conn>

# 2. THEN create the builder (skip if multiplatform-builder already exists)
docker buildx create --name multiplatform-builder --driver docker-container --use || true
docker buildx inspect --bootstrap

# 3. Build and push in one step — MUST use --push, NOT --load
docker buildx build \
  --platform linux/amd64 \
  --push \
  -t <registry_hostname>/<db>/<schema>/<repo>/<image_name>:<tag> .
```

If the builder was already created before login, **remove and recreate it** after logging in:
```bash
docker buildx rm multiplatform-builder 2>/dev/null || true
docker buildx create --name multiplatform-builder --driver docker-container --use
docker buildx inspect --bootstrap
```

If buildx fails on an ARM64 host with a platform error, install QEMU first (one-time):
```bash
docker run --privileged --rm tonistiigi/binfmt --install amd64
```
