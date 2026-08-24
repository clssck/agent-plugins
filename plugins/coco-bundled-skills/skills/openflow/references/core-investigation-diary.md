---
name: openflow-core-investigation-diary
description: Investigation diary methodology for complex troubleshooting and customer issues. Use when diagnosing problems, researching solutions, or working through multi-step investigations that may span extended sessions.
---

# Investigation Diary

Structured approach for complex troubleshooting that maintains context and produces useful artifacts.

## When to Apply

### Quick Check (No Diary)
- Single API call or query to verify state
- Looking up a specific value or configuration
- Answering a factual question about the system
- Expected resolution in < 5 minutes

### Investigation (Use Diary)
- Problem requires multiple exploration steps
- Root cause is not immediately obvious
- Solution may require experimentation
- Session likely to exceed 5-10 exchanges
- User indicates this is a complex or ongoing issue

**Trigger phrase from user**: "investigate", "debug", "figure out why", "troubleshoot", "not working as expected", "customer issue"

## Starting an Investigation

When the investigation threshold is met, inform the user:

> "This looks like it may require some exploration. I'll create an investigation diary in memory to track our progress - this helps maintain context and could produce useful documentation at the end. Is that okay?"

If user agrees, create the diary file.

## Diary Location

```
~/.snowflake/cortex/memory/investigations/
```

**Filename format**: `<YYYY-MM-DD>-<brief-topic>.md`

Example: `2024-12-28-timestamp-to-date-type.md`

## Diary Structure

```markdown
# Investigation: [Brief Title]

**Started**: YYYY-MM-DD HH:MM
**Status**: In Progress | Resolved | Blocked
**Connection**: [connection name from session]

## Problem Statement

### Initial Understanding
[What the user first described]

### Refined Understanding
[Updated as investigation reveals more context]

### Constraints Discovered
- [Constraint 1]
- [Constraint 2]

---

## Tooling Log

| Step | Tool/Function | Purpose | Outcome |
|------|---------------|---------|---------|
| 1 | nipyapi.canvas.get_processor | Get config | Found UpdateRecord using format() |
| 2 | snow sql -c az1 -q "DESCRIBE..." | Check table schema | EVENT_DATE is DATE type |

---

## Key Lessons

<!-- Add as discovered, these become the knowledge artifacts -->

1. [Lesson with brief explanation]
2. [Lesson with brief explanation]

---

## Solution Steps

### Step 1: [Action]
**What**: [What was done]
**Result**: [What was observed]
**Decision**: [What was decided based on result]

### Step 2: [Action]
...

---

## Resolution

**Solution**: [Brief description]

**Verification**: [How it was verified working]

**Artifacts Created**:
- [File 1 - purpose]
- [File 2 - purpose]

---

## Follow-up Actions

- [ ] [Action item if any]
```

## During Investigation

### Update Frequency
- Add to "Tooling Log" after each significant tool use
- Add to "Key Lessons" when discovering something reusable
- Update "Problem Statement" when understanding evolves
- Add "Solution Steps" as you work through the problem

### Context Management
If conversation is getting long or chat is summarised due to context over-run:
1. Read the diary file to refresh context
2. Summarize completed steps
3. Focus on current step and next actions

### If Blocked
Update status to "Blocked" and document:
- What was attempted
- Where it failed
- What information is needed to proceed

## Completing Investigation

### Success Path
1. Document the resolution in the diary
2. Ask user if they need:
   - Customer-facing summary (extracted from diary)
   - Internal learnings document
   - Exported artifacts (configs, flows, etc.)
3. Update status to "Resolved"

### Handoff Path
If investigation needs to continue later or with someone else:
1. Ensure diary is complete through current point
2. Clearly document next steps
3. Note any credentials or access needed

## Benefits

| Benefit | How Diary Helps |
|---------|-----------------|
| Context resilience | Survives conversation summarization |
| Knowledge capture | Lessons learned are documented as found |
| Audit trail | Shows decision reasoning |
| Deliverable generation | Easy to split into customer vs internal docs |
| Session continuity | Can resume investigation after break |

## Example Transition Points

### "Should I start a diary?"

When you notice:
- Third exploration step without resolution
- User says "this is strange" or "not what I expected"
- Problem involves multiple systems (NiFi + Snowflake)
- You're forming hypotheses to test

Ask: "This is taking some exploration. Want me to keep an investigation diary so we maintain context and capture what we learn?"

### "Let me update the diary"

After significant discoveries:
- "I'll note that in our investigation diary - the Schema Write Strategy was the issue"
- "Adding this to our tooling log - the versioning module has export functions"

Keep it lightweight - don't narrate every update, just acknowledge when capturing important points.

## Related References

- `core-session-cli.md` - Session setup and connection management (CLI/terminal surface)
- `core-guidelines.md` - General operating principles
- `ops-flow-export.md` - Backing up flows before changes
