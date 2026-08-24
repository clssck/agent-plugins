# Cortex Sense

> **⚠ Private Preview — Enablement required**
>
> Cortex Sense is a **Private Preview (PrPr)** product. It will not work without explicit enablement from the Snowflake team.
> **Contact your Snowflake account team or Snowflake SE before attempting to use this skill.** Do not share this skill with customers who have not been through the enablement process.

---

## What is Cortex Sense?

Cortex Sense is a context layer for Cortex Code (CoCo) and Snowflake Intelligence. It learns how *your* business works — the schemas, tables, views, dashboards, metrics, and definitions that matter for a specific domain — and grounds agents in that context so they stop guessing.

```
your data estate today        with Cortex Sense
····················          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
·····█··············          ▒▒▒▒▒█▒▒▒▒▒▒▒▒▒▒▒▒▒▒
····················          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
··············█··█··    ──▶   ▒▒▒▒▒▒▒▒▒▒▒▒▒▒█▒▒█▒▒
··················█·          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒█▒
····················          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
mostly uncovered              every table grounded

█ hand-curated context   · no context, agent guesses   ▒ grounded by Sense
```

One Cortex Sense context = one domain (e.g. "sales pipeline", "finance reporting", "product analytics"). You can have as many as you need.

---

## Prerequisites (enablement required)

Before this skill will function, the following must be completed by the Snowflake team:

1. **Feature flag enabled** on your Snowflake account.
2. **`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER`** system function made available.
3. **Snowflake CLI (`snow`)** installed and configured with a connection to your account.
4. **CoCo** (Cursor + Snowflake skill pack) configured and pointing at this skill directory.

None of these can be self-served during Private Preview. Reach out to your Snowflake account team or SE to start the onboarding process.

---

## How it works

1. **Scope it** — Name a domain. CoCo scans your account (tables, dashboards, semantic views, dbt, and more) and proposes a scope. You review and adjust in plain English. Takes ~10 minutes.
2. **Build it** — CoCo kicks off a background build. It typically completes within a few hours. You don't have to wait.
3. **Use it** — Once built, CoCo and Snowflake Intelligence automatically use the context when answering questions in that domain.
4. **Iterate** — Refine the scope, add definitions, fix wrong answers, or generate an eval set to measure quality — all through conversation.

---

## Skill structure

```
cortex-sense/
├── SKILL.md                    # router — seven intents (list / setup / test / query / refine / eval / agent)
├── setup/SKILL.md              # name → scan → draft → confirm → save
├── test/SKILL.md               # spot-check the active context
├── query/SKILL.md              # cross-context search
├── refine/SKILL.md             # corrections, expansions, updates
├── eval/SKILL.md               # generate / run / diff eval sets
├── agent/SKILL.md              # built context → CoWork agent (or add Cortex Sense to an existing agent)
├── reference/                  # contracts loaded on demand by sub-skills
│                               #   incl. AGENT_SPEC.md, AGENT_INSTRUCTIONS.md
└── scripts/                    # Python helpers (validation, usage discovery, ontology)
```

---

## Trigger phrases (inside CoCo)

| What you want | What to type |
|---|---|
| Start a new domain | `set up cortex sense for <domain>` |
| Resume an existing one | `@cortex-sense resume <domain>` |
| Check the build | `@cortex-sense resume <domain>` → "check build" |
| Fix a wrong answer | `@cortex-sense resume <domain>` → describe the issue |
| Run an eval | `@cortex-sense resume <domain>` → "run eval" |
| Turn it into an agent | `create an agent for <domain>` |
| Add Cortex Sense to an existing agent | `add cortex sense to <agent>` |

---

## Status & limitations

Cortex Sense is in **Private Preview**. Known limitations during this phase:

- Build status is inferred (no true running/done/failed state field yet).
- Horizon Context connectors (Tableau, Power BI, Databricks, etc.) require separate connector setup.
- Native use-case object is not yet available — context is stored as YAML on a Snowflake stage.
- Content search inside BI objects and external tables is not yet supported (discovery is, reading internal queries/fields is not).

See `reference/NOT_YET_IMPLEMENTED.md` for the full list.
