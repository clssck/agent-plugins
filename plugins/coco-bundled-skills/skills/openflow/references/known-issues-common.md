---
name: openflow-known-issues-common
description: Known issues shared across multiple Openflow connectors, kept in one place so per-connector references link here instead of duplicating them. Currently covers the StandardPrivateKeyService INVALID controller seen on managed-token (SPCS / BYOC SNOWFLAKE_MANAGED) deployments.
---

# Common Connector Known Issues

Known issues that apply across multiple Openflow connectors. Per-connector references link here instead of repeating the text; each connector keeps its own scope note (e.g. some connectors hit this only on SPCS, others on SPCS and BYOC managed token).

## StandardPrivateKeyService INVALID

The `Snowflake Private Key Service` (`StandardPrivateKeyService`) controller is used **only** for `KEY_PAIR` Snowflake authentication. On any deployment that uses a managed token instead — **SPCS** (always), and **BYOC** when configured with `SNOWFLAKE_MANAGED` — the controller is unused and shows **INVALID**.

**Impact:** None. The connector works correctly.

**Workaround:** Ignore (recommended), or delete the controller (causes local modifications).

**Note:** This one invalid controller inflates `verify_config --verify_processors=false`'s `failed_count` (often into the 20s) because every processor that references the disabled service contributes a validation error. Inspect `controller_results[]` and confirm `Snowflake Private Key Service` is the only `success: false` entry — the number itself is not actionable.
