# Large-System Workflow

## Scaling Large Systems

Many containers or components → split into focused diagrams, never one crammed view. Split by:

- **Business area**: one diagram per domain (e.g., "Order Processing", "User Management")
- **Bounded context**: one diagram per DDD bounded context
- **Service group**: one diagram per related cluster of microservices

Keep a single logical model; AVOID duplicating relationship facts across unrelated views. Use the repository's established source-of-truth format when it has one; otherwise keep model narrative, labels, and change history sufficient to recreate a visual artifact consistently.

## Cross-Repository Documentation

Question spans several repositories (e.g., separate backend and frontend repos) → first decide whether they form one software system. Repository layout is evidence, not the system boundary.

### Unified Diagrams
- **L1 (System Context)**: one system box only when the repositories together form the documented system; otherwise show the other system(s) as external or model a broader landscape.
- **L2 (Container)**: include containers from each repository only within the determined system boundary; annotate source repositories where that aids follow-up.
- **L3 (Component)**: scoped to one container. Title names the container; list every implementing source repository as traceability metadata.
- **Deployment**: may span repos (all containers deploy to shared infrastructure).

### Repo Annotation Convention
In the container description line, include the source repo:
```text
Line 1: **User API**
Line 2: [Container: Fastify / TypeScript]
Line 3: Handles user CRUD operations (repo: user-api)
```

Tells engineers which repo to consult for L3 deep-dives or code changes.

## Troubleshooting

### Codebase too large to analyze

**Cause**: repository has thousands of files; analysis is slow or incomplete.
**Solution**: start with Level 1, then scope the search explicitly instead of using an unsupported flag:

1. Discover likely application and infrastructure roots with the `glob` tool, for example
   `**/{package.json,pyproject.toml,go.mod,pom.xml,Dockerfile,*.tf}`.
2. Select the smallest relevant directories (for example `apps/api` and
   `infrastructure`) and list only their files with `glob` (`apps/api/**`, `infrastructure/**`).
3. Search runtime and integration evidence only inside those directories with the `grep`
   tool, using `path: "apps/api;infrastructure"` and pattern
   `listen\(|createServer|queue|publish|subscribe|database|redis|s3` (case-insensitive).
4. Widen the path set one directory at a time only when an unresolved relationship or
   dependency requires more evidence.

   Several independent roots (separate repositories, or services under `apps/`) → spawn one `scout` per root in a single `task` batch; each returns runtime, data-store, and integration evidence as `path:line`. Scouts gather evidence only. Classify containers and draw the boundary yourself from the combined reports. Spawning unavailable → search root by root as above.

### No Docker or infrastructure files found

**Cause**: serverless or platform-managed deployment not visible in the repo.
**Solution**: ask the engineer about deployment targets; add them manually to the Container diagram.

### Confluence page creation fails

**Cause**: Atlassian/Confluence connection unavailable, or user lacks write permission on the target space.
**Solution**: save a tool-neutral page outline, model narrative, and artifact references locally. When publishing access returns, use the `atl` skill (`atl page update <page> --file <path> --plan` first) so the page is fetched, its macros are preserved, and the update is safe.
