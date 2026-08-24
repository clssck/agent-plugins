# Snowflake-wired Dashboard Scaffolds

Copyable starting points for Streamlit dashboards that read from Snowflake. Each directory is self-contained: copy it into the user's project, adapt the data layer, and deploy.

## Templates

| Template | Purpose | Key patterns |
|---|---|---|
| `dashboard-metrics-snowflake` | KPI cards with time-series | `st.connection("snowflake")`, TIME_RANGES filter (1M/6M/1Y/QTD/YTD/All), chart/table toggle, `st.popover` filters |
| `dashboard-compute-snowflake` | Resource / credit monitoring | `@st.fragment` independent widgets, popover filters, line/bar toggle |
| `dashboard-stock-peers-snowflake` | Peer analysis with normalized charts | `st.multiselect`, normalized chart comparisons, synthetic stock data in Snowflake SQL |

## Shape of each template

```
dashboard-<name>-snowflake/
├── streamlit_app.py        # Entry point with Snowflake connection + layout
├── pyproject.toml          # Python dependencies
├── snowflake.yml           # Snowflake CLI manifest (definition_version 2)
├── .gitignore
└── .streamlit/
    └── config.toml         # Theme + Snowflake connection settings
```

Use `snowflake.yml` + `streamlit_app.py` artifacts when deploying via `snow streamlit deploy`.

Before `snow streamlit deploy`, resolve placeholders in `snowflake.yml`:

| Placeholder | How to resolve |
|---|---|
| `<FROM_CONNECTION>` | `snow connection list` — database, schema, `query_warehouse` |
| `<FROM_ACCOUNT_DEFAULT>` | `SHOW PARAMETERS LIKE 'DEFAULT_STREAMLIT_COMPUTE_POOL' IN ACCOUNT` for the account default, then `SHOW COMPUTE POOLS` to confirm the role can use it (or prompt the user to pick from that list) |
| `<YOUR_PYPI_INTEGRATION>` | `SHOW EXTERNAL ACCESS INTEGRATIONS` — required because templates ship `pyproject.toml` in `artifacts` |

See `<SKILL_DIR>/references/snowflake-deployment.md` Step 3 for the full `compute_pool` and `external_access_integrations` flows.

## Dependencies

All templates require Python >=3.11:

- `snowflake-connector-python>=3.3.0` (required — `streamlit[snowflake]` silently skips this on Python 3.12+)
- `streamlit[snowflake]>=1.54.0`
- `altair>=5.5.0`
- `pandas>=2.2.3`
- `numpy>=1.26.0`

## Canonical patterns

The patterns below are shared across all three scaffolds. Preserve them when adapting, and borrow them when building new Snowflake-wired apps from scratch.

### Page configuration

Always set page config as the first Streamlit call:

```python
st.set_page_config(
    page_title="My Dashboard",
    page_icon=":material/monitoring:",
    layout="wide",
)
```

### Standard constants

```python
TIME_RANGES = ["1M", "6M", "1Y", "QTD", "YTD", "All"]
CHART_HEIGHT = 300  # pixels
```

### Time-range filtering

```python
def filter_by_time_range(df: pd.DataFrame, x_col: str, time_range: str) -> pd.DataFrame:
    if time_range == "All" or df.empty:
        return df
    df = df.copy()
    df[x_col] = pd.to_datetime(df[x_col])
    max_date = df[x_col].max()
    if time_range == "1M":
        min_date = max_date - timedelta(days=30)
    elif time_range == "6M":
        min_date = max_date - timedelta(days=180)
    elif time_range == "1Y":
        min_date = max_date - timedelta(days=365)
    elif time_range == "QTD":
        quarter_month = ((max_date.month - 1) // 3) * 3 + 1
        min_date = pd.Timestamp(date(max_date.year, quarter_month, 1))
    elif time_range == "YTD":
        min_date = pd.Timestamp(date(max_date.year, 1, 1))
    else:
        return df
    return df[df[x_col] >= min_date]
```

### Popover filters

```python
with st.popover("Filters", type="tertiary"):
    line_options = st.pills("Lines", ["Daily", "7-day MA"], selection_mode="multi")
    time_range = st.segmented_control("Time range", TIME_RANGES, default="All")
```

### Page header with reset

```python
def render_page_header(title: str):
    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"
    ):
        st.markdown(title)
        if st.button(":material/restart_alt: Reset", type="tertiary"):
            st.session_state.clear()
            st.rerun()
```

### Independent widget updates with @st.fragment

```python
@st.fragment
def metric_card():
    with st.container(border=True):
        # Rerenders independently of the rest of the page
        ...
```

### Snowflake column normalization

Snowflake returns uppercase column names. Normalize after every query, and pass **bind parameters** as the second argument — never interpolate user input into SQL strings:

```python
df = conn.query(query, params=params)
df.columns = df.columns.str.lower()
```

### Local-vs-deploy gotcha: `NotSupportedError` from `conn.query()`

`conn.query()` calls `fetch_pandas_all()`, which requires Arrow-formatted results. SiS-deployed apps get Arrow by default. Some local accounts (OAuth / internal / legacy, e.g. `snowhouse`) default to JSON and raise `snowflake.connector.errors.NotSupportedError: Unknown error`. pyarrow being installed does NOT fix this — the result format is set server-side.

If you hit this locally, swap the template's data layer to raw cursor + `pd.DataFrame`:

```python
import snowflake.connector, os

@st.cache_resource
def get_conn():
    return snowflake.connector.connect(
        connection_name=os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME") or "default"
    )

@st.cache_data(ttl=3600)
def load(sql, params=None):
    with get_conn().cursor() as cur:
        cur.execute(sql, params or [])
        rows = cur.fetchall()
        cols = [c[0].lower() for c in cur.description]
    return pd.DataFrame(rows, columns=cols)
```

The fallback `"default"` is intentional — the SiS container runtime only exposes a connection named `default`. For local runs, set the env var to your actual connection name (e.g. `SNOWFLAKE_DEFAULT_CONNECTION_NAME=snowhouse`).

See `<SKILL_DIR>/references/local-preview-troubleshooting.md` for the full symptom/cause table.

### Snowflake connection error handling

```python
try:
    get_snowflake_connection()
except Exception as e:
    st.error(f"Failed to connect to Snowflake: {e}")
    st.info(
        "Make sure you have configured your Snowflake connection in "
        "`.streamlit/secrets.toml` or via environment variables."
    )
    st.stop()
```

### Data loading with caching

```python
@st.cache_data(ttl=3600)
def load_metric_data() -> pd.DataFrame:
    # Replace with:
    # - Snowflake query via st.connection("snowflake")
    # - API call
    # - Database query
    return generate_synthetic_data()
```
