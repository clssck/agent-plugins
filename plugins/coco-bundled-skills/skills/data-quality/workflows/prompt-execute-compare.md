---
parent_skill: data-quality
---

# Workflow: Prompt Execute & Compare

Execute both the original and improved prompts through Cortex Complete and present the LLM outputs side by side for comparison.

## Trigger Phrases

- "Execute both prompts"
- "Run both prompts"
- "Compare prompt outputs"
- "Test my prompt"
- "Show me the difference in outputs"

## Prerequisites

Requires both an original prompt and an improved prompt. If the improved prompt has not been generated yet, run `workflows/prompt-improve.md` first.

## Execution Steps

### Step 1: Confirm with User

**Stopping point.** Present what will be executed:

> "I'll run both prompts through Cortex Complete (default model: `claude-sonnet-4-6`) and show you the outputs side by side. This will use LLM credits for two calls. Would you like to proceed, or use a different model?"

If the user specifies a different model, use their preference.

### Step 2: Execute Original Prompt

Read and execute `templates/prompt-cortex-complete.sql`, replacing `<model>` and `<prompt>` with the original prompt:

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE('<model>', $$<original_prompt>$$);
```

Execute via `snowflake_sql_execute`. Store the result.

### Step 3: Execute Improved Prompt

Execute the same template with the improved prompt:

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE('<model>', $$<improved_prompt>$$);
```

Store the result.

### Step 4: Present Side-by-Side Comparison

```
**Model:** <model name>

---

**Original Prompt Output:**

<output from original prompt>

---

**Improved Prompt Output:**

<output from improved prompt>

---

**Score Recap:**
- Original: X / 10
- Improved: Y / 10
- Delta: +Z points
```

### Step 5: Wrap Up

Summarize the key differences observed in the outputs. Note whether the improved prompt produced a more structured, detailed, or focused response.

## Error Handling

| Error | Action |
|---|---|
| Cortex Complete fails on one prompt | Show the successful output and report the error for the failed one |
| Both fail | Report errors; suggest checking warehouse availability or trying a different model |
| Outputs are identical | Note this and explain that structural prompt improvements don't always change output for simple tasks |
