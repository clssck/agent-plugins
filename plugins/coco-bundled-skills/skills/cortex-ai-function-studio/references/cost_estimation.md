<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Pre-flight Cost Estimation (AI_COUNT_TOKENS)

> **Focus: a fast, best-effort token/cost estimate run *before* a large or fan-out AI-function query.** Surface it as a heads-up so the user can decide whether to proceed, narrow scope, or sample first. It is **advisory, never a hard blocker** — if the estimate can't run, say so briefly and let the user proceed.

`AI_COUNT_TOKENS` returns the token count of an input **without invoking the model** (it incurs only small compute, not per-token model billing), so it's cheap to run over a sample. Multiply the per-row token count by the row count to project the full run before you spend real credits on it.

**CRITICAL: Use `AI_COUNT_TOKENS(...)` — NOT `SNOWFLAKE.CORTEX.COUNT_TOKENS(...)`.** The `SNOWFLAKE.CORTEX.COUNT_TOKENS` form is deprecated with no exceptions. The correct function is `AI_COUNT_TOKENS`.

Source of truth: [AI_COUNT_TOKENS](https://docs.snowflake.com/en/sql-reference/functions/ai_count_tokens). Always confirm the current per-function signature via `snowflake_product_docs` before drafting the estimate query — do not rely on the snippets below verbatim.

## When to estimate (and when to skip)

Run the estimate only when a run is **potentially large or fans out**. Otherwise skip it — a token pass on a trivial query is just noise.

**Estimate first when:**
- The AI function is applied to a **table column** (batch over many rows), not just string literals, **and** the table isn't already narrowed to a small sample/`LIMIT`.
- A single statement has **multiple AI calls** (several AI functions, or the same one chained across CTEs) — cost is roughly the **sum** across calls, so fan-out multiplies it.

**Skip the estimate (just run it) when:**
- You're only compiling/validating (`only_compile: true`) — no rows are processed.
- It's a **trial / single-literal call** (e.g. `AI_SENTIMENT('some text')`) or a demo on a handful of rows.
- The user already scoped it small — an explicit `SAMPLE`, `LIMIT`, or a tiny table.

When unsure whether a table is "large," a quick `SELECT COUNT(*)` is enough to decide.

## The estimate

Two cheap reads: average tokens per row over a small sample, and the full row count. Multiply.

```sql
-- Example: AI_SENTIMENT over reviews.review_text
WITH sample_est AS (
  SELECT AVG(AI_COUNT_TOKENS('ai_sentiment', review_text)) AS avg_tokens_per_row
  FROM reviews SAMPLE (200 ROWS)   -- sample keeps the estimate cheap
)
SELECT
  (SELECT COUNT(*) FROM reviews)                        AS n_rows,
  s.avg_tokens_per_row,
  (SELECT COUNT(*) FROM reviews) * s.avg_tokens_per_row  AS est_total_input_tokens
FROM sample_est s;
```

`est_total_input_tokens ≈ avg_tokens_per_row × n_rows`. For a statement with multiple AI calls, estimate each call and **sum** them.

### Per-function signatures

`AI_COUNT_TOKENS` keys off the **lowercase** function name and mirrors that function's inputs. Common shapes (verify against docs):

| Function | Estimate call |
|----------|---------------|
| `AI_COMPLETE` | `AI_COUNT_TOKENS('ai_complete', '<model>', prompt_col)` — **model required** (see caveat below) |
| `AI_SENTIMENT` | `AI_COUNT_TOKENS('ai_sentiment', text_col)` |
| `AI_CLASSIFY` | `AI_COUNT_TOKENS('ai_classify', text_col, [{'label':'a'},{'label':'b'}])` — categories count toward tokens |
| `AI_TRANSLATE` | `AI_COUNT_TOKENS('ai_translate', text_col, 'en', 'de')` |
| `AI_SIMILARITY` | `AI_COUNT_TOKENS('ai_similarity', text_a, text_b)` |
| `AI_EMBED` | `AI_COUNT_TOKENS('ai_embed', '<model>', text_col)` — model required |
| `AI_REDACT` | `AI_COUNT_TOKENS('ai_redact', text_col)` |

## Caveats — read these before trusting the number

- **Input tokens only.** `AI_COUNT_TOKENS` counts the **input** prompt. Generative functions (`AI_COMPLETE`, `AI_SUMMARIZE_AGG`, `AI_AGG`, and text-emitting calls) also bill **output** tokens, which this does **not** predict. Treat the estimate as a **floor** for those, and say so.
- **Newer `AI_COMPLETE` models aren't supported for counting.** `AI_COUNT_TOKENS` rejects the current default families (claude-4-*, openai-gpt-5-*, gemini-2.5/3.x, etc.). If the target model is unsupported, count with a **supported proxy** (e.g. `'llama3.3-70b'` or `'llama3.1-8b'`) purely to size the input, and flag that the number is an **approximation** — tokenizers differ across models.
- **Text only.** It does **not** accept image, audio, or video inputs, so it can't size `AI_PARSE_DOCUMENT`, `AI_TRANSCRIBE`, or image inputs to `AI_COMPLETE`. For those, skip the token pass and give a **row/file-count** heads-up instead.
- **`AI_*` namespace only.** Not supported for the deprecated `SNOWFLAKE.CORTEX.*` functions or fine-tuned models (a non-issue if you follow `ai-function-rules.md`).
- **The estimate itself costs a little compute.** Keep it on a `SAMPLE`, not the full table.

## Presenting the estimate

Report the projection, then hand the decision to the user — this is a stopping point, not a gate you decide.

- Lead with the concrete size: `~<n_rows> rows × ~<avg> input tokens/row ≈ <total> input tokens`.
- Add the floor caveat for generative functions ("output tokens bill on top of this") and the proxy-model caveat if you used one.
- **Answer "how much will this cost?" with token counts — not dollars.** Even when the user asks about "cost", always express it as token counts. Do NOT look up Snowflake pricing, do NOT consult the Service Consumption Table, do NOT convert tokens to USD. **Dollar amounts (`$0.15`, `$2.00`, etc.) are explicitly prohibited.** Use token counts only — the user can check the current pricing page themselves.
- If you compare models, use the `input_cost`/`output_cost` relative multipliers from `models.json` (see `model_selection.md`) — these are relative units, not USD.
- Offer choices: **proceed**, **run on a `LIMIT`/`SAMPLE` first**, or **narrow the filter**. Only continue once the user picks.

```
Heads-up before I run this: ~4.2M rows × ~180 input tokens/row ≈ ~760M input tokens.
AI_SENTIMENT is input-only so that's the full picture here (no output-token billing).

Want me to (1) run it as-is, (2) try a LIMIT 1000 sample first, or (3) narrow the rows?
```

## Pitfalls

- **Don't block.** If `AI_COUNT_TOKENS` errors or the sample fails, note it in one line and let the user decide — never refuse to run their query over a failed estimate.
- **Don't estimate trivial calls.** A token pass before a single-literal or already-sampled query wastes a round-trip and clutters the reply.
- **NEVER quote dollars.** Token counts and `models.json` costs are relative units, not USD. Writing `$0.15` or any dollar figure in your response is a hard violation — use token counts only.
- **Don't forget output tokens.** For generative functions, always label the estimate a floor.
- **Don't count with an unsupported model and then present it as exact.** If you fell back to a proxy model, say the number is approximate.
