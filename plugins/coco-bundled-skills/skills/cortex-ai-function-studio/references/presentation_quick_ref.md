<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Inline Cost Table — Quick Reference

**When the user provides model/score results as a table in chat** (not from a Snowflake experiment), run `presentation.py` with `--json`.

> **⚠️ Do NOT compute costs manually, use Python REPL, or read from `models.json` by hand.** The script applies the correct formula: `cost = input_cost × prompt_chars + output_cost × avg_output_chars`. Manual calculations produce wrong units (dollars instead of relative multipliers) and will produce incorrect results.

```bash
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
SKILL_DIR=$(find /custom-skills /workspace /home -name "presentation.py" -path "*/cortex-ai-function-studio/*" 2>/dev/null | head -1 | xargs dirname | xargs dirname)

uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/presentation.py" \
    --json '[{"model": "model-name", "score": 0.XX}, {"model": "model-name-2", "score": 0.YY}]' \
    --prompt-chars {system_prompt_chars} --avg-output-chars {avg_output_chars} \
    --seed-score {original_score} --format table
```

**`--prompt-chars`**: System prompt template character count **ONLY** — do NOT add user input characters. User input is variable data passed separately to the function.
- Example: user says "system prompt: 300 chars, user input: 700 chars, output: 100 chars" → `--prompt-chars 300 --avg-output-chars 100`

**`--avg-output-chars`**: Average expected output character count.

**`--seed-score`**: Original function score before optimization (optional, shows improvement delta).
