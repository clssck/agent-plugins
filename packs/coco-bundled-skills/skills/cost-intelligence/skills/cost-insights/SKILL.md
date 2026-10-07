# Cost Insights Skill

Surface proactive cost optimization insights from the `SNOWFLAKE.LOCAL.COST_INSIGHTS` class. These insights identify waste reduction opportunities — unused tables, idle warehouses, underutilized features — and quantify their credit impact.

---

## Step 1: Determine Intent

| Intent | Keywords |
|--------|----------|
| **Overview** (list all insight types with counts and impact) | "insights", "recommendations", "optimization", "waste", "cost insights", "what can I save", "savings", "overview", "all insights" |
| **Drill-down** (specific objects for one insight type) | "warehouse gaps", "idle warehouses", "unused tables", "never queried", "only written", "auto-clustering", "materialized view unused", "search optimization", "short lifespan", "same min max", "cold file storage" |

If the user asks for a general overview first and then wants to drill into a specific type, handle both sequentially (overview → drill-down).

---

## Step 2: Determine Access

The `COST_INSIGHTS` class procedures require the `APP_USAGE_VIEWER` or `APP_USAGE_ADMIN` application role (or `ACCOUNTADMIN`, which has implicit access).

Run:

```sql
SHOW GRANTS OF APPLICATION ROLE SNOWFLAKE.APP_USAGE_VIEWER;
```

Check whether `CURRENT_ROLE()` appears in the `grantee_name` column **and** `granted_to = 'ROLE'`. If so, the current role has access.

If **not**, also check:

```sql
SELECT CURRENT_ROLE();
```

If the current role is `ACCOUNTADMIN`, access is granted implicitly — proceed.

If the role is neither `ACCOUNTADMIN` nor has `APP_USAGE_VIEWER` granted → inform the user:
> "Your current role lacks the `APP_USAGE_VIEWER` application role required to access cost insights. Ask your account administrator to grant it, or switch to `ACCOUNTADMIN`."

Stop here — do not proceed to sub-skills.

---

## Step 3: Route to Sub-Skill

| Intent | Load |
|--------|------|
| Overview | `overview/SKILL.md` |
| Drill-down (specific insight type) | `drill-down/SKILL.md` |

**Do NOT execute any SQL until you have loaded the appropriate sub-skill.**
