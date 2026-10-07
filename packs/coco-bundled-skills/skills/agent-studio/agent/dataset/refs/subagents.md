# Methodology + parallel-invocation playbook (reference)

Two concerns owned by this reference file:

1. **`<METHODOLOGY>`** — invoke the user's agent for ground truth, or build it manually (hand-authored locally).
2. **Bounded parallel invocation** — when `<METHODOLOGY> = 2`, fan out to ≤ 8 concurrent agent calls via a single Python script using `concurrent.futures.ThreadPoolExecutor(max_workers=8)`. The main agent executes the script via `bash` (heredoc), waits for it to finish, then proceeds to Step 3 / Step 4.

It is **not** a skill. `dataset-scratch` (and transitively `dataset-expand`'s `build-only` sub-call) link here when they reach the methodology choice or the agent-invocation batch. Does NOT apply to `dataset-production` (its data is observed, not invoked).

**Speed-first defaults the calling skill auto-applies (no user ASK / STOP):** `<METHODOLOGY> = 2`, ≤ 8 workers, 300 s per-question hard timeout, one consolidated retry pass, drop residual misses, print the miss-rate report.

## When to read this

| You're at… | …read |
|---|---|
| methodology choice (auto-default = 1) | [Step 1](#step-1-methodology-decision-matrix) |
| spawning the batch | [Step 2](#step-2-bounded-parallel-agent-invocation-python-threadpoolexecutor) |
| post-batch verification + miss-rate report | [Step 3](#step-3-verification--miss-rate-report) |
| per-track projection / trace-window rules | [Step 4](#step-4-projection--trace-window-invariants) |

---

## Step 1: Methodology decision matrix

Auto-default to `<METHODOLOGY> = 2` — no STOP. Use the matrix when the user overrides in-turn or when an individual row needs a fallback to #2 mid-batch.

| `<METHODOLOGY>` | What it does | When to pick |
|---|---|---|
| **1 — build manually** | No agent invocation, no observability traffic. You hand-author `ground_truth_output` and write SQL / search queries / `CALL`s against real data (see [`ac_details.md` § AC drafting by methodology](./ac_details.md#ac-drafting-by-methodology) and [`tea_details.md` § TEA drafting by methodology](./tea_details.md#tea-drafting-by-methodology)). | Agent not yet built, or the user wants a clean reference independent of current behaviour. |
| **2 — invoke the user's agent** | Spawns Step 2 against `<ALL_QUESTIONS>`. AC-track rows capture `record_root.output`; TEA-track rows capture the full trace. Higher fidelity, some bias toward current agent behaviour. | Default. Agent is wired up and the user wants ground truth that reflects what it does today. |

**Per-row fallback** — under `<METHODOLOGY> = 1` you may escalate individual rows to #2 (or vice versa). Track which path produced each row so the user can audit later.

---

## Step 2: Bounded-parallel agent invocation (Python ThreadPoolExecutor)

When `<METHODOLOGY> = 2`, the calling skill needs `<N>` agent invocations executed against the user's agent with **≤ 8 concurrent in-flight calls** and a 300 s per-call hard timeout. Since the coding agent runs one main session (no `Task` subagent spawning), the canonical pattern is a **single Python script** that uses `concurrent.futures.ThreadPoolExecutor(max_workers=8)` against the agent's REST `:run` endpoint.

Properties:

- **One auth / one Snowflake session token** (`conn.rest.token`) — the REST endpoint is stateless per request, so 8 concurrent calls share one token cleanly.
- **8 workers in flight** with slot reuse via `as_completed` — when any one finishes, the next question is dispatched immediately. **Strictly faster** than fixed-round dispatch (8-at-once / wait-all / next-round) because stragglers don't block the round.
- **300 s per-call hard timeout** on each request.
- **Ground truth extraction** happens AFTER the batch via `GET_AI_OBSERVABILITY_EVENTS(...)` — the script only triggers runs and confirms OK/FAIL/TIMEOUT. Do NOT parse SSE traces for ground truth.

**Run-trigger contract** — execute the script below via bash heredoc (`python3 << 'PYEOF' ... PYEOF`). Do NOT use `python_repl`, skills, subagents, or any other tools. Wait for it to finish, then proceed to Step 3.

> Print to user: `"Testing authorization..."`

**Auth resolution (run silently — do NOT print any of this to the user):**

1. Run `cortex secret list` to check for a stored PAT (e.g. `SNOWFLAKE_PAT`).
2. If a PAT exists: inject via `SNOWFLAKE_PAT="<SNOWFLAKE_PAT>" python3 << 'PYEOF'` and read from `os.environ["SNOWFLAKE_PAT"]` inside the script. Use `Authorization: Snowflake Token="<pat>"`.
3. If no PAT: use `snowflake.connector.connect(connection_name=CONNECTION)` and `conn.rest.token`. Use `Authorization: Snowflake Token="<token>"`. Set `CONNECTION` to the connection the user names (default: `"default"`).
4. Test auth with a single `python3 -c` one-liner to confirm the host + token work before running the full batch.

> Print to user: `"Authorization Confirmed."`

The script writes `batch_meta.json` with `batch_start`, `batch_end`, succeeded/failed/timed_out. Ground truth is projected from observability afterward — the script produces no ground-truth artifacts.

**Script template** (substitute `<AGENT_FQN>`, `<CONNECTION>`, `<ALL_QUESTIONS>`, wrap in `python3 << 'PYEOF' ... PYEOF`):

```python
"""dataset-scratch Step 2 — bounded-parallel agent invocation via ThreadPoolExecutor.
Runs end-to-end inside one coding-agent Python execution (bash heredoc); ≤ 8 in-flight
requests to the agent's REST :run endpoint, 300 s per-call hard timeout.
NOTE: This script only TRIGGERS runs and records OK/FAIL/TIMEOUT.
Ground truth is extracted AFTER via GET_AI_OBSERVABILITY_EVENTS — never from SSE."""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
import snowflake.connector

# ---- Inputs the calling skill substitutes ----
AGENT_FQN     = "<DATABASE>.<SCHEMA>.<AGENT_NAME>"      # e.g. SNOWFLAKE_INTELLIGENCE.AGENTS.PDS_AGENT
CONNECTION    = "<CONNECTION>"                           # snowflake-cli connection name with USAGE on the agent (e.g. "default")
ALL_QUESTIONS = [                                        # union of AC + TEA INPUT_QUERY strings (de-duplicated)
    {"id": "<qid_1>", "q": "<INPUT_QUERY_1>", "track": "ac"},
    {"id": "<qid_2>", "q": "<INPUT_QUERY_2>", "track": "tea"},
    # ...
]
WORK_DIR      = Path("/tmp/dataset_scratch_invoke")
MAX_WORKERS   = 8
PER_CALL_TIMEOUT_SEC = 300

# ---- 1. Capture <batch_start> exactly once before any HTTP call ----
batch_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- 2. Connect once; reuse one Snowflake session token across 8 threads ----
db, schema, agent_name = AGENT_FQN.split(".")
conn = snowflake.connector.connect(connection_name=CONNECTION)
URL = f"https://{conn.host}/api/v2/databases/{db}/schemas/{schema}/agents/{agent_name}:run"
HEADERS = {
    "Authorization": f'Snowflake Token="{conn.rest.token}"',
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}

WORK_DIR.mkdir(parents=True, exist_ok=True)
(WORK_DIR / "traces").mkdir(parents=True, exist_ok=True)

def invoke_one(item):
    qid, q = item["id"], item["q"]
    body = {"messages": [{"role": "user", "content": [{"type": "text", "text": q}]}]}
    out = WORK_DIR / "traces" / f"{qid}.jsonl"
    try:
        r = requests.post(URL, headers=HEADERS, json=body, stream=True,
                          timeout=PER_CALL_TIMEOUT_SEC, verify=False)
        if r.status_code != 200:
            return (qid, "FAIL", f"http_{r.status_code}: {r.text[:200]}")
        with open(out, "w") as f:
            for line in r.iter_lines(decode_unicode=True):
                if line:
                    f.write(line + "\n")
        return (qid, "OK", str(out))
    except Exception as e:
        return (qid, "TIMEOUT" if "timeout" in str(e).lower() else "FAIL", str(e)[:200])

# ---- 3. Bounded parallel: 8 in flight at all times via slot reuse ----
results = []
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = {ex.submit(invoke_one, item): item for item in ALL_QUESTIONS}
    for fut in as_completed(futures):
        qid, status, info = fut.result()
        results.append({"id": qid, "status": status, "info": info})
        print(f"  {qid}: {status}")

batch_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- 4. Persist metadata for the main agent to read in Step 3 ----
meta = {
    "batch_start": batch_start,
    "batch_end":   batch_end,
    "total":       len(ALL_QUESTIONS),
    "questions":   ALL_QUESTIONS,
    "succeeded":   [r["id"] for r in results if r["status"] == "OK"],
    "failed":      [{"id": r["id"], "reason": r["info"]} for r in results if r["status"] == "FAIL"],
    "timed_out":   [{"id": r["id"], "reason": r["info"]} for r in results if r["status"] == "TIMEOUT"],
}
(WORK_DIR / "batch_meta.json").write_text(json.dumps(meta, indent=2))

print(f"batch_start={batch_start}  batch_end={batch_end}")
print(f"OK={len(meta['succeeded'])}  FAIL={len(meta['failed'])}  TIMEOUT={len(meta['timed_out'])}  /  TOTAL={meta['total']}")

conn.close()
```

**What the main agent does after the script exits:**

1. Read `batch_meta.json` to get `<batch_start>`, `<batch_end>`, `succeeded`, `failed`, `timed_out`.
2. Build `<MISS_LIST>` from failed + timed_out. Proceed to Step 3 (verification).
3. **DO NOT** read, parse, or open any `.jsonl` trace files. Proceed directly to Step 3 → Step 4 using `snowflake_sql_execute` against `GET_AI_OBSERVABILITY_EVENTS(...)` for all ground-truth extraction.

**Why `ThreadPoolExecutor` slot reuse, not fixed N/8 rounds?**

| Pattern | Wall-time bound | Tail-latency behavior |
|---|---|---|
| Fully sequential (1 worker) | `Σ latency` | Linear in `N` — slowest path |
| **`ThreadPoolExecutor(max_workers=8)` (slot reuse)** ✅ | `≈ Σ latency / 8` | A slow call frees its slot only when it finishes; other 7 keep moving |
| 8-at-once + wait-all + next-round | `Σ max(per-round latency)` | A 90 s straggler in any round blocks the next round for 90 s |

Slot reuse (`as_completed`) **strictly dominates** rounded dispatch at the same concurrency cap.

**Forbidden inside the Python script:**

- Do NOT project per-tool traces (no `agent.tool.*` SQL) — the main agent does that in Step 4.
- Do NOT write to `EVAL_DATASET_*` / `EVAL_ANNOTATIONS_*` tables — that's Step 4 / Step 5 of the calling skill.
- Do NOT call `SYSTEM$CREATE_EVALUATION_DATASET` — the calling skill's Step 5 owns registration.

---

## Step 3: Verification + miss-rate report

Run **once** after Step 2 completes, before any per-track projection:

> Use `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'))` to read observability events scoped to the agent.

```sql
SELECT COUNT(DISTINCT RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING) AS distinct_questions
FROM TABLE(
  SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>',
    '<SCHEMA>',
    '<AGENT_NAME>',
    'CORTEX AGENT'
  )
)
WHERE TIMESTAMP >= '<batch_start>'
  AND RECORD_ATTRIBUTES:"ai.observability.span_type"::STRING = 'record_root'
  AND RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING IN (<ALL_QUESTIONS>);
-- expected = N - len(<MISS_LIST>)
```

If `distinct_questions` is short of `N - len(<MISS_LIST>)`, append the silently-missing `INPUT_QUERY` values to `<MISS_LIST>` (`reason = "silent_missing_span"`) — do not re-invoke.

**`<MISS_LIST>`** = union of timeouts, HTTP/wrapper errors, and silent missing spans (per question, with a reason tag). Reduce `<ALL_QUESTIONS>` by `<MISS_LIST>`. For each missed `INPUT_QUERY`, look up its track label (`ac` / `tea`) from the Step 2 question design (the same label attached when the question was authored) and decrement `<AC_COUNT>` or `<TEA_COUNT>` accordingly.

> Print to user:
> ```
> Done! Captured <N - MISS_COUNT> of <N> questions:
>   - <AC_COUNT - ac_misses> for answer correctness and logical consistency
>   - <TEA_COUNT - tea_misses> for tool execution accuracy and tool selection accuracy
> [If MISS_COUNT > 0:]  Dropped <MISS_COUNT> questions (timed out or errored): <list of dropped question texts>
> ```

If `<MISS_RATE> > 25 %`, append a one-line warning but still proceed — the user can re-run dataset-curation later.

---

## Step 4: Projection + trace-window invariants

> **MANDATORY:** All ground-truth data (agent answers for AC, SQL/search/generic invocations for TEA) MUST be extracted by executing the projection SQL from `tea_details.md` / `ac_details.md` against `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(...))` via `snowflake_sql_execute`. Do NOT read or parse any local trace files, SSE payloads, `.jsonl` files, or Python script output for ground truth. The invocation script exists only to trigger runs — it produces no usable ground-truth artifacts.

After Step 3, the AC-track and TEA-track per-track subsections in the calling skill each run their own projection against the same `<batch_start>` window:

- **AC-track** — pulls `record_root.input` + `record_root.output` for the AC-track subset. SQL: [`ac_details.md` § AC drafting by methodology](./ac_details.md#ac-drafting-by-methodology).
- **TEA-track** — pulls the per-family `agent.tool.<sql_execution|cortex_search|web_search>.*` payloads (plus `agent.planning.tool_execution.*` as the fallback for custom / generic tools) for the TEA-track subset. SQL: [`tea_details.md` § TEA drafting by methodology](./tea_details.md#tea-drafting-by-methodology).

**Trace-window invariants** (must hold across the whole batch):

1. `<batch_start>` is fixed **once**, immediately before Step 2 spawns its first invoker. Never re-capture later.
2. Both per-track projections read the **same** `<batch_start>`. Mixing windows lets non-deterministic tool routing drift the two tracks apart.
3. Never invoke the agent inside a per-track subsection — the shared Step 2 batch is the only window.
4. Under `<METHODOLOGY> = 1`, there is no `<batch_start>` and no batch — `ac_details.md` / `tea_details.md` handle the local-only path.
