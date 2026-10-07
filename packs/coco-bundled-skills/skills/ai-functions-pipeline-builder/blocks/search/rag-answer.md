# RAG answer — grounded, cited answers (`SEARCH_PREVIEW` → `AI_COMPLETE`)

The "ask a question, get a cited answer" surface over a Cortex Search service. Answers are per-question, so this
is a **query pattern, not a DT** — with an optional stored-procedure wrapper for a one-call surface.

> Read [`../conventions.md`](../conventions.md) first. Requires a `<prefix>_SEARCH` service from
> [`chunk-index.md`](chunk-index.md).

- **Reads** — `<prefix>_SEARCH` (Cortex Search service).
- **Produces** — an answer (and optionally an `ask_<prefix>(question)` Python stored procedure).

Retrieve the top chunks → `LISTAGG` them into context → `AI_COMPLETE` with explicit citation instructions and a
"say so if context is insufficient" guard. Cite `(Title, p.N)` when a page exists, else `(Title, #chunk)` —
`COALESCE('p.' || PAGE, '#' || CHUNK_NO)` picks the right form, since `PAGE` is `NULL` for non-paginating formats.

**Raw retrieval preview (no LLM) — confirm the index serves relevant chunks:**

```sql
SELECT v.value:TITLE::STRING AS TITLE,
       COALESCE('p.' || v.value:PAGE::STRING, '#' || v.value:CHUNK_NO::STRING) AS LOC,
       LEFT(v.value:CHUNK::STRING, 240) AS CHUNK_PREVIEW
FROM TABLE(FLATTEN(input => PARSE_JSON(
  SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
    '<db>.<schema>.<prefix>_SEARCH',
    '{"query": "<question>", "columns": ["CHUNK","TITLE","PAGE","CHUNK_NO","RELATIVE_PATH"], "limit": 8}'
  ))['results'])) v;
```

**Grounded, cited answer:**

```sql
WITH hits AS (
  SELECT v.value:CHUNK::STRING AS CHUNK, v.value:TITLE::STRING AS TITLE,
         v.value:PAGE::INT AS PAGE, v.value:CHUNK_NO::INT AS CHUNK_NO
  FROM TABLE(FLATTEN(input => PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
      '<db>.<schema>.<prefix>_SEARCH',
      '{"query": "<question>", "columns": ["CHUNK","TITLE","PAGE","CHUNK_NO","RELATIVE_PATH"], "limit": 10}'
      -- add a facet filter, e.g.  ,"filter": {"@eq": {"DOC_TYPE": "<type>"}}
    ))['results'])) v
)
SELECT AI_COMPLETE('<reasoning_model>',
  'Answer the question using ONLY the provided context. Cite the source for every claim as (Title, p.N) '
  || 'when a page is given, otherwise (Title, #chunk). If the context is insufficient, say so.\n\n'
  || 'Question: <question>\n\nContext:\n'
  || LISTAGG(TITLE || ' (' || COALESCE('p.' || PAGE::STRING, '#' || CHUNK_NO::STRING) || '): ' || CHUNK, '\n---\n')
       WITHIN GROUP (ORDER BY TITLE, PAGE, CHUNK_NO)
) AS ANSWER
FROM hits;
```

For a simpler corpus where page citation isn't needed, the same pattern works with just `["TITLE","THEME","CHUNK_TEXT"]`
columns and a `{"@eq": {"THEME": "<theme>"}}` facet filter.

---

## Optional convenience wrapper — `ask_<prefix>(question)`

> **⚠ It must be a Python stored procedure, not a scalar SQL UDF.** `SEARCH_PREVIEW` requires its **query
> argument to be a constant** (`argument 2 … needs to be constant`). A literal or a **bound (`?`) parameter**
> satisfies that; a scalar SQL UDF's argument does not — so a `CREATE FUNCTION … SEARCH_PREVIEW('…' || QUESTION
> || '…')` wrapper fails for every question. A Python proc gets a session, **binds** the question (constant ⇒
> allowed), and `json.dumps` handles escaping.

```sql
CREATE OR REPLACE PROCEDURE <db>.<schema>.ask_<prefix>(QUESTION STRING)
RETURNS STRING LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python') HANDLER = 'ask'
AS
$$
import json
def ask(session, question):
    req = {"query": question, "columns": ["CHUNK","TITLE","PAGE","CHUNK_NO"], "limit": 10}
    row = session.sql("SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?) AS R",
                      params=["<db>.<schema>.<prefix>_SEARCH", json.dumps(req)]).collect()
    hits = json.loads(row[0]["R"]).get("results", []) if row and row[0]["R"] else []
    if not hits:
        return "Nothing relevant in the library for that."
    def loc(h):
        return f"p.{h['PAGE']}" if h.get("PAGE") is not None else f"#{h.get('CHUNK_NO')}"
    ctx = "\n---\n".join(f"{h['TITLE']} ({loc(h)}): {h['CHUNK']}" for h in hits)
    prompt = ("Answer using ONLY the context. Cite (Title, p.N) — or (Title, #chunk) when no page — "
              "for every claim; say so if insufficient.\n\n"
              f"Question: {question}\n\nContext:\n{ctx}")
    return session.sql("SELECT AI_COMPLETE(?, ?)::STRING AS A",
                      params=["<reasoning_model>", prompt]).collect()[0]["A"]
$$;
-- Then:  CALL <db>.<schema>.ask_<prefix>('Which documents mention …?');
```

> Off by default — offer it only if the user wants a one-call surface. For an interactive search/answer app, see
> [`../serve/presentation.md`](../serve/presentation.md) (same bind-the-question approach, with tabs and history).
