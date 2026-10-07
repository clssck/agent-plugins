---
name: streamlit-templates
description: "Templates for adding Streamlit to a Native App: environment.yml, app .py, CREATE STREAMLIT SQL, and manifest artifacts. Referenced from add-streamlit-warehouse/SKILL.md."
parent_skill: native-app-provider
---

# Reference: Streamlit Native App Templates

## environment.yml Template

```yaml
name: sf_env
channels:
  - snowflake        # Required. External Anaconda/PyPI channels are not supported.
dependencies:
  - streamlit=1.35.0   # Always pin explicitly — omitting defaults to 1.22.0
  # - scikit-learn      # Add user-requested packages here
  # - pandas
```

## Streamlit App File Template

Generate the main `.py` file using the `get_active_session()` pattern:

```python
import streamlit as st
from snowflake.snowpark.context import get_active_session

# IMPORTANT: use get_active_session() — NOT Session.builder.create()
# The Native App runtime injects the session automatically.
session = get_active_session()

st.title("My Native App")

# Example: call a stored procedure defined in the setup script
if st.button("Run"):
    result = session.sql("CALL core.my_proc()").collect()
    st.dataframe(result)
```

**Never** use `Session.builder.create()`:

```python
# ❌ WRONG — .create() always opens a new connection and requires credentials,
# which are not available in the Native App runtime.
from snowflake.snowpark import Session
session = Session.builder.configs({...}).create()

# ✅ Also acceptable (returns the existing injected session, same as get_active_session())
# but get_active_session() is the idiomatic choice and makes intent explicit.
session = Session.builder.getOrCreate()
```

## CREATE STREAMLIT SQL Template

```sql
-- Ensure the schema exists (skip if already created elsewhere in the script)
CREATE SCHEMA IF NOT EXISTS <schema>;
GRANT USAGE ON SCHEMA <schema> TO APPLICATION ROLE <app_role>;

-- FROM: stage path relative to app root, must start with /
-- MAIN_FILE: path relative to the FROM directory, must start with /
CREATE OR REPLACE STREAMLIT <schema>.<streamlit_name>
  FROM '/<stage_subdir>'
  MAIN_FILE = '/<main_file>.py';

GRANT USAGE ON STREAMLIT <schema>.<streamlit_name> TO APPLICATION ROLE <app_role>;
```

## manifest.yml Artifacts Template

```yaml
artifacts:
  setup_script: scripts/setup.sql
  readme: README.md
  default_streamlit: <schema>.<streamlit_name>
```

