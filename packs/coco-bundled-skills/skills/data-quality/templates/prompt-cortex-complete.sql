-- ── CORTEX COMPLETE FOR PROMPT WORKFLOWS ─────────────────────────────────────
-- Shared template for all prompt-quality Cortex Complete calls:
--   • Scoring a prompt (pass a scoring meta-prompt with the 9-dimension rubric)
--   • Rewriting a prompt (pass a meta-prompt with gaps + suggestions)
--   • Executing a prompt to compare original vs improved output
--
-- Replace <model> with the LLM model name (default: claude-sonnet-4-6).
-- Replace <prompt> with:
--   • For scoring: the constructed scoring meta-prompt (system instructions
--     with 9-dimension rubric + user's prompt). See workflows/prompt-quality.md.
--   • For rewrite: the constructed meta-prompt (system instructions + original
--     prompt + quality gaps + suggestions). See workflows/prompt-improve.md.
--   • For execution: the prompt text to run through the LLM.
--
-- ⚠️ Uses LLM credits. Confirm with user before executing.

SELECT SNOWFLAKE.CORTEX.COMPLETE('<model>', $$<prompt>$$);
