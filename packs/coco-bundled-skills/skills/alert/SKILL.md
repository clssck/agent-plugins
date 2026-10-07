---
name: alert
description: "Snowflake alert management - create, alter, suspend, resume, and troubleshoot alerts. Use when: user wants to create a new alert, modify an existing alert, set up monitoring, suspend or resume alerts, or investigate why an alert is firing/failing/not delivering. Triggers: create alert, new alert, add alert, alter alert, modify alert, change alert, suspend alert, resume alert, monitor with alert, set up alert, alert condition, troubleshoot alert, debug alert, investigate alert, alert firing, alert failed, alert not firing, why did my alert trigger, CONDITION_FAILED, ACTION_FAILED, notification not delivered."
---

# Alert

**MANDATORY DELEGATION:** This skill does NOT contain alert logic. You MUST load the appropriate sub-skill from the table below. Do NOT attempt to handle any alert-related request on your own — always delegate to a sub-skill first.

Do NOT:
- Generate any alert SQL without first loading the matching sub-skill
- Guess at syntax, condition queries, or notification content
- Skip loading the sub-skill because you think you already know the answer
- Partially follow the sub-skill — follow its complete workflow end-to-end

## Route to Sub-Skill

| Intent | Triggers | Action |
|--------|----------|--------|
| Create, alter, or delete alerts | "create alert", "new alert", "alter alert", "modify alert", "drop alert", "suspend alert", "resume alert", "set up alert", "monitor with alert" | **Load** `./alert-create-alter/SKILL.md` |
| Troubleshoot an alert that is firing, failing, or not delivering | "alert firing", "alert failed", "why did my alert trigger", "alert not firing", "CONDITION_FAILED", "ACTION_FAILED", "ACTION_SKIPPED", "notification not delivered", "debug alert", "investigate alert", "alert misfiring", "alert noisy", "alert silent" | **Load** `./alert-troubleshoot/SKILL.md` |

-**Runtime fallback (required):**
-If `skill alert-troubleshoot` is unavailable in this runtime, load `./alert-troubleshoot/SKILL.md` directly and execute it end-to-end. Do not switch to ad-hoc troubleshooting.

For the broader troubleshooting landscape (which products have dedicated troubleshoot skills, where the gaps are, how the uber skill routes between them), see [`TROUBLESHOOTING_LANDSCAPE.md`](TROUBLESHOOTING_LANDSCAPE.md).
