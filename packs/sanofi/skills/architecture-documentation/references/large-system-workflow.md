## Scaling Large Systems

For systems with many containers or components, split into multiple focused diagrams rather
than cramming everything into one. Split strategies:

- **By business area**: One diagram per domain (e.g., "Order Processing", "User Management")
- **By bounded context**: One diagram per DDD bounded context
- **By service group**: One diagram per related cluster of microservices

Keep a single logical model and avoid duplicating the same relationship facts across
unrelated views. Use the repository's established source-of-truth format when it has one;
otherwise keep the model narrative, labels, and change history sufficient to recreate a
visual artifact consistently.

## Cross-Repository Documentation

When an architecture question spans multiple repositories (for example, separate backend
and frontend repos), first decide whether they form one software system. Repository layout
is evidence, not the system boundary.

### Unified Diagrams
- **L1 (System Context)**: Use one system box only when the repositories together form
  the documented system. Otherwise show the other system(s) as external or model a
  broader landscape.
- **L2 (Container)**: Include containers from each repository only when they are within
  the determined system boundary. Annotate source repositories where that aids follow-up.
- **L3 (Component)**: Scoped to a single container. The diagram title names the container;
  list every source repository that implements it as traceability metadata.
- **Deployment**: May span repos (all containers deploy to shared infrastructure).

### Repo Annotation Convention
In the container description line, include the source repo:
```text
Line 1: **User API**
Line 2: [Container: Fastify / TypeScript]
Line 3: Handles user CRUD operations (repo: user-api)
```

This tells engineers which repo to consult for L3 deep-dives or code changes.

## Troubleshooting

### Codebase too large to analyze

**Cause**: Repository has thousands of files; analysis step is slow or incomplete.
**Solution**: Start with Level 1, then scope the search explicitly instead of using an
unsupported flag:

1. Discover likely application and infrastructure roots with the `glob` tool, for example
   `**/{package.json,pyproject.toml,go.mod,pom.xml,Dockerfile,*.tf}`.
2. Select the smallest relevant directories (for example `apps/api` and
   `infrastructure`) and list only their files with `glob` (`apps/api/**`, `infrastructure/**`).
3. Search runtime and integration evidence only inside those directories with the `grep`
   tool, using `path: "apps/api;infrastructure"` and pattern
   `listen\(|createServer|queue|publish|subscribe|database|redis|s3` (case-insensitive).
4. Widen the path set one directory at a time only when an unresolved relationship or
   dependency requires more evidence.

### No Docker or infrastructure files found

**Cause**: Project uses serverless or platform-managed deployment not visible in the repo.
**Solution**: Ask the engineer about deployment targets. Add them manually to the Container diagram.

### Confluence page creation fails

**Cause**: Atlassian/Confluence connection is unavailable or the user lacks write permissions to the target space.
**Solution**: Save a tool-neutral page outline, model narrative, and artifact references
locally. When publishing access is available, use `confluence-html-editor` so it can
fetch the target page, preserve its macros and attachments, and publish safely.
