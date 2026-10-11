# Blameless Language: Do / Don't

Blameless ≠ "omit details" or "pretend no one made a decision". Blameless = every cause framed as a **systems or process** property, not a **personal failing**.

Humans under pressure, with incomplete information, on systems they did not design, make choices that look wrong in retrospect. The question: _why did the system make that choice look reasonable at the time?_

## The core reframes

### Name systems and processes, not individuals

| Don't write | Write instead |
|---|---|
| "Alice deployed without checking the canary." | "The deploy process did not require verifying canary health before rollout." |
| "Bob approved the PR too quickly." | "The review checklist did not include verifying schema compatibility for legacy records." |
| "The on-call engineer missed the page." | "The paging system did not escalate when the first responder failed to acknowledge within 5 minutes." |
| "Carol wrote buggy code." | "The code path hit a null dereference that was not covered by existing tests." |

### Describe decisions in context

| Don't write | Write instead |
|---|---|
| "They made the wrong call." | "Given the information available at the time (dashboard X looked normal, no alerts firing), rollback was not prioritized." |
| "They should have known this would happen." | "The failure mode was not represented in any existing runbook, test fixture, or monitoring dashboard." |
| "Obvious mistake." | "This was the first time this code path had been exercised with legacy-schema data in production." |

### Replace shame words with system words

| Shame word | System word |
|---|---|
| "carelessly" | "following standard procedure, which did not include…" |
| "failed to" | "the process did not require…" |
| "should have" | "a future safeguard could…" |
| "sloppy" | "under-specified" |
| "stupid mistake" | "easy-to-make error given the current design" |
| "forgot to" | "no reminder exists in the workflow for…" |

### Tense

System property, still true → present. Event → past. Present tense for a gap shows it persists until the action item closes it.

| Framing | Kind |
|---|---|
| "The deploy pipeline **does not** block rollouts on canary errors." | Property of the system, now |
| "The responder **acknowledged** the page at 14:21 UTC." | Event |

## Near-misses and luck

Name luck explicitly. Luck is not a safeguard; naming it pushes the team to build real ones.

| Don't write | Write instead |
|---|---|
| "Luckily, it didn't affect the other region." | "The incident did not propagate to region B because the deploy had not yet reached it — this was timing, not a safeguard, and could have been worse had the rollout been 20 minutes faster." |

## Action-item language

| Don't write | Write instead |
|---|---|
| "Be more careful with deploys." | "Add a canary health gate that blocks rollout when 5xx > baseline + 2σ." |
| "Review code more thoroughly." | "Add checklist item: verify all DB field accesses are null-safe for records created before schema-migration YYYY-MM." |
| "Train the team on X." | "Add integration test covering X; failure becomes a CI signal rather than a human memory item." |

"Be more careful" actions are invisible on the next incident — nothing to verify. Concrete artefact changes produce durable safeguards.

## When the report must mention a person

Naming is fine to credit the IC, record who holds an action item, or preserve the timeline (who did what). The principle forbids assigning **causal fault**, not acknowledging presence.

| Acceptable | Not acceptable |
|---|---|
| "IC: @bob." | "@bob should have declared the incident sooner." |
| "@alice identified the null dereference at 14:26 UTC." | "@alice caused the bug by not null-checking." |
| "Action item owner: @carol." | "@carol needs to stop making this kind of mistake." |

## Anti-pattern: the "passive voice trick"

Blameless ≠ active voice rewritten as passive. Blameless = responsibility moved from a person to a system. Left column: human failing with the actor hidden. Right: fixable system property.

| Don't (passive but still blaming) | Do (genuinely blameless) |
|---|---|
| "A mistake was made in the PR review." | "The review checklist did not include schema-compatibility verification, so the regression was not caught." |
| "The deploy was done without checking the canary." | "The deploy workflow does not require canary health verification before full rollout." |

## Self-check

Run before publishing:

1. **Names.** Search every human name; each is a cause or a participant? Cause → rewrite.
2. **Phrases.** Search "should have", "failed to", "forgot to", "didn't check"; each hit is almost always a blameless rewrite.
3. **Root causes.** Each answer names a system/process/artefact gap, not a person? Person → keep asking "why was that reasonable to do?" until a system-level cause surfaces.
4. **Action items.** Verifiable by looking at a file, config, or test? Or dependent on a person "being more careful"?
