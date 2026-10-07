# Presentation — a no-SQL app over the published outputs (Streamlit in Snowflake)

A small **user-facing app** over the pipeline's published contract: a reading/exploration surface for a corpus
profile, or a search box that returns grounded cited answers. It reads only the published objects
(`<prefix>_*` views and the `<prefix>_SEARCH` service), so it generalizes — you retarget a few constants/labels,
not the structure. **Not** a copy-paste monolith: one render function per published output, wired into tabs;
compose only the tabs whose blocks were built.

> Read [`../conventions.md`](../conventions.md) first. This is **not SQL** — it's a Streamlit app that runs all
> AI/search server-side via a Snowpark session.

## Principles

- **Read only the published contract** (`<prefix>_*` views, `<prefix>_SEARCH`), never intermediate DTs.
- **One render function per surface → one tab.** Compose only the tabs whose blocks exist.
- **Parameterize, don't hardcode** — a handful of constants + labels are the only per-pipeline edits.
- **Bind the user's input** as a `?` parameter — never f-string it into SQL.

## Contract → tab map

| Published object | Tab | Surface |
|------------------|-----|---------|
| `<prefix>_SEARCH` (Cortex Search) | Ask | grounded RAG answer + source chunks (title/page) |
| `<prefix>_SEARCH` | Search | raw retrieval preview (no LLM) |
| `DT_<prefix>_CHUNKS` *(optional)* | Browse | filter by document/facet, page through chunks |
| `DT_<prefix>_SYNTHESIS` | Overview | generated narrative + headline metrics |
| `<prefix>_PROFILE` | Themes | bar chart + table (count, cohesion) |
| `DT_<prefix>_TIMELINE` *(if built)* | Evolution | stacked-area of dimension × time |
| `<prefix>_ITEMS` (`IS_OUTLIER`, `THEME_SIM`) | Outliers | similarity-vs-time scatter + cards |
| `<prefix>_HIGHLIGHTS` | Where to start | exemplar / outlier per theme |
| `<prefix>_ITEMS` | Explore | filters + table + per-item detail |
| `<prefix>_INSIGHTS` | Insights | ranked observations + recommended actions |

## Shared setup (declare once)

```python
import json, streamlit as st
try:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()                       # works in SiS
except Exception:
    import os
    from snowflake.snowpark import Session                # local `streamlit run`
    session = Session.builder.config(
        "connection_name", os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME") or "default").create()

@st.cache_data(ttl=600, show_spinner=False)
def q(sql: str):                          # cache keyed on the SQL string; session stays global (unhashable)
    return session.sql(sql).to_pandas()   # ⚠ columns come back UPPERCASE

DB, SCHEMA, PREFIX = "ACME", "KB", "ESR"             # pointers
SERVICE   = f"{DB}.{SCHEMA}.{PREFIX}_SEARCH"
RAG_MODEL = "claude-sonnet-4-6"
ITEM, ITEMS = "document", "documents"                # domain labels
FACET = None                                          # e.g. "DOC_TYPE"/"THEME" if indexed as an ATTRIBUTE; else None
```

## Retrieval + answer helpers (search apps)

```python
def loc(h):                                   # page when paginated, else chunk position
    return f"p.{h['PAGE']}" if h.get("PAGE") is not None else f"#{h.get('CHUNK_NO')}"

def search(question, facet_value=None, limit=8):
    cols = ["CHUNK", "TITLE", "PAGE", "CHUNK_NO", "RELATIVE_PATH"]   # corpus svc: ["TITLE","THEME","CHUNK_TEXT"]
    req = {"query": question, "columns": cols, "limit": limit}
    if FACET and facet_value and facet_value != "All":
        req["filter"] = {"@eq": {FACET: facet_value}}
    row = session.sql("SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?) AS R",   # ⚠ bind (?) — never f-string the question
                      params=[SERVICE, json.dumps(req)]).collect()
    return json.loads(row[0]["R"]).get("results", []) if row and row[0]["R"] else []

def answer(question, hits):
    if not hits:
        return f"Nothing relevant in the {ITEMS} for that."
    ctx = "\n---\n".join(f"{h['TITLE']} ({loc(h)}): {h['CHUNK']}" for h in hits)
    prompt = ("Answer using ONLY the context; cite (Title, p.N) — or (Title, #chunk) when no page — for every "
              f"claim; say so if not covered.\n\nQuestion: {question}\n\nContext:\n{ctx}")
    return session.sql("SELECT AI_COMPLETE(?, ?)::STRING AS A",   # ⚠ ::STRING — VARIANT else renders JSON-quoted
                      params=[RAG_MODEL, prompt]).collect()[0]["A"]
```

## Per-tab render functions (catalogue — include only what you built)

```python
def render_ask():                                   # ← Cortex Search (RAG)
    scope = st.selectbox("Scope", ["All"] + sorted(
        q(f"SELECT DISTINCT {FACET} AS F FROM {DB}.{SCHEMA}.DT_{PREFIX}_CHUNKS WHERE {FACET} IS NOT NULL")["F"].tolist())) if FACET else None
    if question := st.chat_input(f"Ask about the {ITEMS}…"):
        hits = search(question, scope)
        st.markdown(answer(question, hits))
        for h in hits:
            with st.expander(f"📄 {h['TITLE']} · {loc(h)}"): st.write(h["CHUNK"])
    # Persist st.session_state.messages to keep chat history across reruns.

def render_overview(items):                         # ← Corpus synthesis
    n = q(f"SELECT CORPUS_NARRATIVE::STRING AS N FROM {DB}.{SCHEMA}.DT_{PREFIX}_SYNTHESIS").iloc[0]["N"]
    c1, c2, c3 = st.columns(3)
    c1.metric(ITEMS.capitalize(), len(items)); c2.metric("Themes", items["THEME"].nunique())
    c3.metric("Outliers", int(items["IS_OUTLIER"].sum()))
    st.markdown(n)

def render_themes():                                # ← profile
    df = q(f"SELECT THEME, N_ITEMS, AVG_COHESION FROM {DB}.{SCHEMA}.{PREFIX}_PROFILE").sort_values("N_ITEMS", ascending=False)
    st.bar_chart(df.set_index("THEME")["N_ITEMS"]); st.dataframe(df, hide_index=True, width="stretch")

def render_outliers(items):                         # ← items; bound the year axis explicitly (see gotchas)
    import altair as alt
    lo, hi = int(items["TIME_KEY"].min()), int(items["TIME_KEY"].max())
    chart = (alt.Chart(items).mark_circle(size=80, opacity=0.8).encode(
        x=alt.X("TIME_KEY:Q", title="Year", axis=alt.Axis(format="d"), scale=alt.Scale(zero=False, domain=[lo-0.5, hi+0.5])),
        y=alt.Y("THEME_SIM:Q", title="Similarity to theme", scale=alt.Scale(zero=False)),
        color=alt.Color("IS_OUTLIER:N"), tooltip=["TITLE","THEME","TIME_KEY","THEME_SIM"]))
    st.altair_chart(chart, width="stretch")

def render_insights():                              # ← insights
    st.dataframe(q(f"SELECT PRIORITY, OBSERVATION, RECOMMENDED_ACTION FROM {DB}.{SCHEMA}.{PREFIX}_INSIGHTS"),
                 hide_index=True, width="stretch")
```

`render_search`, `render_browse`, `render_evolution`, `render_highlights`, `render_explore` follow the same
shape — one published object each. The **Explore** render is the one pipeline-specific surface: it mirrors the
extract/summary schema (`st.markdown(f"**Problem.** {r.get('S_PROBLEM') or '—'}")`).

## Wiring (include only the tabs whose blocks exist)

```python
items = q(f"SELECT * FROM {DB}.{SCHEMA}.{PREFIX}_ITEMS")   # if a corpus pipeline; backs several tabs
tabs = st.tabs(["Ask", "Overview", "Themes", "Outliers", "Insights"])
with tabs[0]: render_ask()
with tabs[1]: render_overview(items)
# … etc
```

## Per-pipeline tweaks (the only things that change)

1. **Pointers** — `DB` / `SCHEMA` / `PREFIX` / `RAG_MODEL`.
2. **Labels** — `ITEM` / `ITEMS` + the domain framing in the `answer()` prompt.
3. **Facet** — set `FACET` to an indexed `ATTRIBUTE` to enable scoped search; else `None`.
4. **Conditional tabs** — drop tabs whose blocks weren't built; the **Explore** detail fields mirror your schema.

## Gotchas (Streamlit-in-Snowflake — all verified)

- **VARIANT → `::STRING`.** `AI_COMPLETE` output is VARIANT; without the cast the client renders it JSON-quoted
  (surrounding quotes + literal `\n`) and `st.markdown` prints that verbatim. Cast at read time or in the DT.
- **Bind parameters.** Pass the question and search request via `?` params, never string-interpolated SQL.
- **UPPERCASE columns.** Snowpark `to_pandas()` uppercases names — index with `df["TITLE"]`.
- **Cache keys.** `@st.cache_data` hashes args — key on the SQL string; keep `session` module-global (unhashable).
- **Bound axes.** Quantitative axes default to a zero baseline (a year axis spans 0–~2200). Use Altair
  `scale(zero=False, domain=[lo, hi])`; `st.*_chart` can't set a domain.
- **SiS Streamlit version.** A SQL-deployed app defaults to an old runtime lacking `st.chat_input` (1.24),
  `st.container(border=…)` (1.29), `hide_index` (1.23), `width="stretch"` (1.49). Pin a modern version with an
  `environment.yml` (`streamlit=1.49.1`) in the app's `ROOT_LOCATION`, or fall back to `use_container_width=True`.
- **Run it.** Local: `SNOWFLAKE_DEFAULT_CONNECTION_NAME=<conn> streamlit run app.py` (all AI/search runs
  server-side). Deploy to SiS only to share.
