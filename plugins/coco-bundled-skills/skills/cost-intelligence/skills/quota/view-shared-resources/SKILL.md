# View Quota Shared Resources

View which resource domains and targets are configured on a quota.

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/shared-resources.md`

---

## How to View Shared Resources

### GET_QUOTA_SCOPE

Returns the full scope JSON including shared resources.

```sql
CALL {quota_fqn}!GET_QUOTA_SCOPE();
```

**Returns** a VARIANT with structure:
```json
{
  "user_tags": { ... },
  "shared_resources": [
    {
      "domain": "AI FUNCTION",
      "target": null
    },
    {
      "domain": "WAREHOUSE",
      "target": "MY_WAREHOUSE"
    }
  ]
}
```

- `domain`: The resource domain (e.g., `'AI FUNCTION'`, `'WAREHOUSE'`, `'CORTEX AGENT'`, `'SNOWFLAKE INTELLIGENCE'`, `'CORTEX_CODE'`)
- `target`: The specific target within the domain, or `null` if all targets in the domain are included

> **Domain names come back normalized.** Spaces are returned as underscores, so a domain added as
> `'AI FUNCTION'` reads back as `AI_FUNCTION`, and `'CORTEX AGENT'` as `CORTEX_AGENT`. Match
> case-insensitively and treat `_` and space as equivalent when comparing to what the user asked for.

> **An all-targets entry may report an id of `-1` and a synthetic name** such as
> `[ALL-WAREHOUSES]`, `[ALL-CORTEX AI FUNCTIONS]`, `[ALL-AGENTS]`, or `[ALL-CORTEX CODES]`. Present
> these as "all targets in the domain", not as a resource name.

> **An empty `shared_resources` array means the quota measures 0 credits.** Warn the user
> explicitly in that case — it is almost always unintended.

---

## Presenting Results

Show the user a table of configured shared resources:

```
| Domain              | Target         |
|---------------------|----------------|
| AI FUNCTION         | (all)          |
| WAREHOUSE           | MY_WAREHOUSE   |
```
