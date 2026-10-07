---
name: snowflake-yml-reference
description: "Reference for snowflake.yml project definition file used by Snow CLI native app commands"
parent_skill: native-app-provider
---

# Snowflake Project Definition Reference (`snowflake.yml`)

The `snowflake.yml` file declares a directory as a Snowflake Native App project. It is required when using Snow CLI commands (`snow app run`, `snow app deploy`, etc.). Place it at the project root.

## Minimal Template

```yaml
definition_version: 2

entities:
  <app_pkg_name>:
    type: application package
    manifest: manifest.yml
    stage: stage_content.app_code
    artifacts:
      - src: .
        dest: ./

  <app_name>:
    type: application
    from:
      target: <app_pkg_name>
    debug: true
```

Replace `<app_pkg_name>` and `<app_name>` with the user's chosen names.

## Key Fields

### Application Package Entity

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `application package` |
| `identifier` | No | Snowflake object name; defaults to entity key |
| `manifest` | No | Path to `manifest.yml` (auto-detected if at root) |
| `stage` | No | Stage for artifacts; format `schema.stage_name`, defaults to `app_src.stage` |
| `deploy_root` | No | Build output directory; defaults to `output/deploy` |
| `artifacts` | Yes | List of src/dest file mappings (see below) |
| `distribution` | No | `internal` (default) or `external` |
| `meta.role` | No | Role for creating the package |
| `meta.warehouse` | No | Warehouse for post-deploy scripts |
| `meta.post_deploy` | No | List of SQL scripts to run after creation |

### Artifacts

Artifacts map local files to stage paths. Each entry has:

```yaml
artifacts:
  - src: app/*        # local source (supports globs)
    dest: ./           # stage destination
  - src: src/lib.jar
    dest: lib/lib.jar
```

**Processors** can transform files during bundling:

```yaml
artifacts:
  - src: app/*
    dest: ./
    processors:
      - snowpark        # process Snowpark annotations
      - templates        # expand template variables
```

### Application Entity

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `application` |
| `from.target` | Yes | References the package entity key |
| `identifier` | No | Snowflake object name; defaults to entity key |
| `debug` | No | Enable debug mode (default: false) |
| `meta.role` | No | Role for creating the application |
| `meta.warehouse` | No | Warehouse for the application |

### Telemetry (Optional)

```yaml
  <app_name>:
    type: application
    from:
      target: <app_pkg_name>
    telemetry:
      share_mandatory_events: true
      optional_shared_events:
        - DEBUG_LOGS
```

## Local Overrides

Create `snowflake.local.yml` alongside the base file for developer-specific settings (add to `.gitignore`). All required fields from the base become optional in the override.

```yaml
definition_version: 2

entities:
  my_pkg:
    type: application package
    meta:
      role: MY_DEV_ROLE
```

## Common Patterns

**Internal app (simplest):**
```yaml
definition_version: 2
entities:
  hello_pkg:
    type: application package
    artifacts:
      - src: .
        dest: ./
  hello_app:
    type: application
    from:
      target: hello_pkg
    debug: true
```

**External app with specific role:**
```yaml
definition_version: 2
entities:
  analytics_pkg:
    type: application package
    distribution: external
    artifacts:
      - src: app/*
        dest: ./
      - src: streamlit/*
        dest: streamlit/
    meta:
      role: APP_PROVIDER
  analytics_app:
    type: application
    from:
      target: analytics_pkg
    meta:
      role: APP_TESTER
```
