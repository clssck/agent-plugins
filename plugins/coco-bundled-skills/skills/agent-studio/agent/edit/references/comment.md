# Agent Comment Guidelines

The agent `COMMENT` field is the primary routing signal: a routing LLM reads it to decide which agent best matches an incoming query. Every word must earn its place.

## Format rules

- **≤ 1000 characters recommended** — longer comments dilute the routing signal; aim to stay under this threshold
- **Plain prose only** — no bullet points, no headers, no markdown formatting

## Content Rules

**Lead with named systems.** Within the first 200 characters, name at least one specific system, tool, database, schema, product, or proper noun that uniquely identifies this agent's domain. These named tokens are the strongest routing signal — a query mentioning <PRODUCT> routes to the agent whose comment says <PRODUCT>.

**Enumerate all named technical artifacts.** Include every specific named system visible in the agent spec: database names, schema names, table names, semantic view names, search service names, MCP server names, internal service codenames, third-party integrations, and tool names. If the spec names it, the comment should too.

**State technical capabilities explicitly and prominently.** Capabilities are the most actionable routing signal. Cover every distinct thing the agent can do: answer questions about specific metrics, search documentation, analyze profiling data, look up CRM records, generate forecasts, interpret dashboards, etc. Use the same vocabulary a user would use in a query. Do not assume the router infers capability from tool names or system names alone — state the capability directly. The more specific the capability, the stronger the signal ("query revenue by product line in the SALES_METRICS semantic view" outperforms "analyze data").

**Add discriminative cues from the agent's own scope.** Derive when-to-use and when-not-to-use guidance purely from this agent's spec. Identify the agent's precise domain boundaries (which systems, schemas, question types, or workflows it handles) and state them explicitly. What does this agent handle that a generic assistant would not? What questions fall outside its tools or instructions? Stating the boundary clearly ("this agent handles X but not Y") is more useful than a positive-only description.

**Be exhaustive about capabilities, compact in expression.** Cover all tools, MCPs, and skills the agent has access to. Combine related capabilities into single dense sentences rather than listing them.


## Self-Check Before Proposing

- Does the comment name at least one specific system in the first 200 characters?
- Does it enumerate every tool, semantic view, search service, MCP, and skill in the agent spec?
- Does it state what the agent can *do* (not just what it *knows about*)?
- Is it under 1000 characters (or as close as possible without dropping important signals)?
- Is it plain prose with no markdown?
