---
name: trust-center
description: "Use for ALL Snowflake Trust Center requests: security findings, scanner analysis, scanner management, finding remediation, severity distribution, CIS benchmarks, Security Essentials, Threat Intelligence, AI Security, enable/disable scanners, scanner schedules, notifications, webhook, notification integration, at-risk entities, security posture, vulnerability analysis, detection analysis, remediation guidance."
---

# Trust Center

Helps users analyze, manage, and remediate security findings from Snowflake Trust Center.

## When to Use

- User asks about Trust Center findings, scanners, or security posture
- User wants to enable/disable scanners or change schedules/notifications
- User wants to fix or remediate a specific security finding
- User asks about CIS Benchmarks, Security Essentials, Threat Intelligence, or AI Security

## Workflow

```
Start
  ↓
Intent Detection
  ├─→ ANALYZE FINDINGS  → Load findings-analysis/SKILL.md
  ├─→ ANALYZE SCANNERS  → Load scanner-analysis/SKILL.md
  ├─→ MANAGE SCANNERS   → Load api-management/SKILL.md
  └─→ REMEDIATE FINDING → Load finding-remediation/SKILL.md
```

### Step 1: Detect Intent

| User Intent | Keywords | Route |
|-------------|----------|-------|
| Analyze findings | findings, severity, new findings, resolved, trend, security posture, categories | [findings-analysis/SKILL.md](findings-analysis/SKILL.md) |
| Analyze scanner inventory and coverage | what scanners exist, scanner packages, coverage, disabled scanners, CIS, scanner health | [scanner-analysis/SKILL.md](scanner-analysis/SKILL.md) |
| Manage or inspect scanner configuration | enable, disable, schedule, notification, webhook, threshold, tune, parameter, sensitivity, custom configuration, check if default, inspect settings | [api-management/SKILL.md](api-management/SKILL.md) |
| Remediate findings | fix, remediate, at-risk entities, suggested action, how to fix | [finding-remediation/SKILL.md](finding-remediation/SKILL.md) |

If intent is unclear, ask:
```
What would you like to do with Trust Center?
1. Analyze findings (severity, trends, categories)
2. Review scanners (inventory, coverage, health)
3. Manage scanners (enable/disable, schedules, notifications)
4. Remediate a finding (fix a specific security issue)
```

### Step 2: Load Reference and Sub-Skill

**MANDATORY: Load** [references/trust-center-api.md](references/trust-center-api.md) — this contains all Trust Center views, columns, stored procedures, and scanner mappings. Then route to the appropriate sub-skill based on detected intent.

## Response Style

All Trust Center sub-skills must follow these rules:

- **Be concise.** Lead with the answer or action. Omit filler sentences, preamble, and restatements of what the user already knows.
- **Do not speculate.** Never list possible causes, troubleshooting checklists, or "common issues" unless the user asks. If a remediation didn't work, say "wait for data refresh and re-run" — do not enumerate hypothetical reasons.
- **Show data, not prose.** Prefer tables and SQL results over narrative paragraphs. Skip formatting boilerplate (e.g., section headers for a single sentence).
- **One action at a time.** Present the next concrete step. Do not dump an entire multi-step plan when the user only needs the current step.
- **Skip the menu when intent is clear.** Only present option lists when the user's intent is genuinely ambiguous.

## Stopping Points

- ✋ Step 1: If user intent is unclear, ask for clarification

## Output

This skill routes to sub-skills, each of which produces its own output:

| Sub-Skill | Output |
|-----------|--------|
| findings-analysis | Findings counts, severity distribution, trends, categories |
| scanner-analysis | Scanner inventory, coverage gaps, health checks |
| api-management | Confirmation of scanner configuration changes |
| finding-remediation | Remediation steps, SQL, verification |
