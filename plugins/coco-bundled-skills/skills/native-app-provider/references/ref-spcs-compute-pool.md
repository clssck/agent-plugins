---
name: ref-spcs-compute-pool
description: "Compute pool patterns for SPCS in Native Apps: multi-cloud instance family selection and compute pool constraints."
parent_skill: native-app-provider
---

# SPCS Compute Pool Reference

## Instance Families

**CPU families are identical across AWS, Azure, and GCP** — no branching needed:

| Family | vCPU | Memory |
|--------|------|--------|
| `CPU_X64_XS` | 1 | 6 GiB |
| `CPU_X64_S` | 3 | 13 GiB |
| `CPU_X64_M` | 6 | 28 GiB |
| `CPU_X64_SL` | 14 | 54 GiB |
| `CPU_X64_L` | 28 | 116 GiB |
| `HIGHMEM_X64_S` | 6 | 58 GiB |
| `HIGHMEM_X64_M` | 28 | ~230 GiB |

**GPU families are cloud-specific** — use `CURRENT_REGION()` to branch:

| Cloud | GPU Families |
|-------|-------------|
| AWS | `GPU_NV_S`, `GPU_NV_M`, `GPU_NV_L` |
| Azure | `GPU_NV_XS`, `GPU_NV_SM`, `GPU_NV_2M`, `GPU_NV_3M`, `GPU_NV_SL` |
| GCP | `GPU_GCP_NV_L4_1_24G`, `GPU_GCP_NV_L4_4_24G`, `GPU_GCP_NV_A100_8_40G` |

**GPU multi-cloud procedure:**
```sql
CREATE OR REPLACE PROCEDURE <schema>.create_compute_pool()
  RETURNS VARCHAR
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  LET pool_name := (SELECT CURRENT_DATABASE()) || '_compute_pool';
  LET instance_family VARCHAR;

  IF (CONTAINS(CURRENT_REGION(), 'AWS')) THEN
    instance_family := 'GPU_NV_S';
  ELSEIF (CONTAINS(CURRENT_REGION(), 'AZURE')) THEN
    instance_family := 'GPU_NV_XS';
  ELSEIF (CONTAINS(CURRENT_REGION(), 'GCP')) THEN
    instance_family := 'GPU_GCP_NV_L4_1_24G';
  END IF;

  CREATE COMPUTE POOL IF NOT EXISTS IDENTIFIER(:pool_name)
    MIN_NODES = 1
    MAX_NODES = 1
    INSTANCE_FAMILY = :instance_family
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 300;

  RETURN 'Compute pool created: ' || :pool_name;
END;
$$;
```

## Compute Pool Constraints

| Constraint | Value |
|-----------|-------|
| Max compute pools per app | 5 |
| Name scope | Account-level — must be unique across ALL apps and users |
| Naming strategy | Prefix with `CURRENT_DATABASE()` for uniqueness |
| Ownership | Exclusively owned by the app — cannot be shared with other apps |
| Before app uninstall | Consumer MUST drop or transfer ownership of compute pools |
| Communication | Containers in different pools within the same app can communicate directly |
| Cost control | Set `AUTO_SUSPEND_SECS` to suspend idle pools |
| Consumer visibility | Consumer can only see app-created pools with MANAGE GRANTS privilege |
