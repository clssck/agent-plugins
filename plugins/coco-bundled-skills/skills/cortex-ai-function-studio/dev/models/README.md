<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Model Registry Tools

Scripts for maintaining `src/models.json` — the model name/cost registry used at runtime.

- **`validate_models.py`** — Fetch prices from Snowhouse, validate each model with `AI_COMPLETE`, write survivors to `src/models.json`.
- **`diff_models.py`** — Compare two `models.json` files and produce a human-readable diff (plain text or Slack mrkdwn).

## Usage

```bash
# From the cortex-ai-function-studio root:
make update-models                  # fetch + validate + write
make validate-models                # validate existing models.json without re-fetching
python dev/models/diff_models.py old.json new.json
```
