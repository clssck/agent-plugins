---
parent_skill: data-quality
---

# Workflow: Prompt Improve (Score + Rewrite + Re-Score)

Score an LLM prompt via Cortex Complete using the 9-dimension heuristic rubric, generate an improved version that addresses detected quality gaps, then re-score and show the before-vs-after comparison.

## Trigger Phrases

- "Improve my prompt"
- "Rewrite this prompt"
- "Make my prompt better"
- "Fix my prompt"
- "Prompt engineering help"

## Prerequisites

If the user's prompt has not been scored yet, run `workflows/prompt-quality.md` (Steps 1-4) first to get the scoring data.

## Execution Steps

### Step 1: Identify Gaps

From the scoring result, collect:
- **Gaps**: dimensions with score < 0.5
- **Suggestions**: the `suggestions` array from the scoring response

### Step 2: Confirm with User

**Stopping point.** Present the detected gaps and ask:

> "I found gaps in: <gap list>. I can generate an improved version using Cortex Complete that addresses these issues. This will use LLM credits. Proceed?"

Upon approval, continue.

### Step 3: Build the Rewrite Meta-Prompt

Construct a meta-prompt with two parts:

**System message:**
```
You are an expert prompt engineer. Rewrite the given prompt to address the listed quality gaps. Preserve the original intent exactly — do NOT change what the prompt is asking for. Only output the improved prompt text, nothing else.
```

**User message:**
```
ORIGINAL PROMPT:
<original prompt text>

QUALITY GAPS TO FIX: <comma-separated gap dimension names>

SPECIFIC SUGGESTIONS:
- <suggestion 1>
- <suggestion 2>
- ...

Return ONLY the improved prompt.
```

### Step 4: Generate Improved Prompt

Read and execute `templates/prompt-cortex-complete.sql`, replacing `<model>` (default: `claude-sonnet-4-6`) and `<prompt>` with the constructed meta-prompt.

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE('<model>', $$<meta_prompt>$$);
```

Execute via `snowflake_sql_execute`. The result is the improved prompt text.

### Step 5: Re-Score the Improved Prompt

Score the improved prompt using the same Cortex Complete scoring approach from `workflows/prompt-quality.md` (Steps 2-3). Build the scoring meta-prompt with the improved prompt text and execute via `templates/prompt-cortex-complete.sql`:

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE('<model>', $$<scoring_meta_prompt_with_improved_prompt>$$);
```

### Step 6: Present Before-vs-After

**Score comparison:**
```
**Original Score: X / 10** — <band>
**Improved Score: Y / 10** — <band>
**Delta: +/-Z points**
```

**Per-dimension comparison table:**

| Dimension | Original | Improved | Delta |
|---|---|---|---|
| Structure | X/10 | Y/10 | +/-Z |
| Role Clarity | X/10 | Y/10 | +/-Z |
| ... | ... | ... | ... |

**Improved prompt text:** Show the full improved prompt.

### Step 7: Offer Next Steps

1. **Execute both** — "Want to run both the original and improved prompts through Cortex Complete and compare the outputs?" → Load `workflows/prompt-execute-compare.md`
2. **Score another prompt** — Loop back to `workflows/prompt-quality.md`
3. **Stop** — Done.

## Error Handling

| Error | Action |
|---|---|
| Cortex Complete fails | Report error; suggest retrying with a different model |
| Improved prompt scores lower | Warn user; show what regressed and offer to try again |
| No gaps found (score >= 8) | Inform user the prompt is already well-crafted; offer minor polish suggestions |
