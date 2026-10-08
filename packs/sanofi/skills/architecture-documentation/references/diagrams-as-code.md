# Diagrams as Code

Edit C4 sources that already live in the repository (Structurizr DSL, C4-PlantUML, Mermaid C4) without breaking their renderer. The model narrative stays primary. A diagram tool is NEVER a prerequisite.

## Detect the Existing Format

Detect with `glob`/`grep` BEFORE drafting anything new. Edit the format the repository already uses. NEVER convert it unasked.

| Format | Detect | Notes |
|---|---|---|
| Structurizr DSL | `glob` `**/workspace.dsl`, `**/*.dsl`; sibling `workspace.json` | One model, many views |
| C4-PlantUML | `glob` `**/*.{puml,plantuml,iuml}`; `grep` `C4_(Context\|Container\|Component\|Dynamic\|Deployment\|Sequence)` | Legend and tags supported |
| Mermaid C4 | `grep` `C4(Context\|Container\|Component\|Dynamic\|Deployment)` in `**/*.{md,mmd,mermaid}` | Experimental, limited |
| Draw.io | `glob` `**/*.drawio` | [drawio-c4-templates.md](drawio-c4-templates.md) |

## Choosing a Format (only when asked to create one)

| Need | Prefer | Why |
|---|---|---|
| Several views that must stay consistent; renames in one place | Structurizr DSL | Modelling tool: one model, many views. The C4 site recommends modelling over diagramming |
| Text source with legend, dashed async lines, landscape view | C4-PlantUML | `SHOW_LEGEND()`, `AddRelTag(... DashedLine())`, `C4_Context` covers landscape |
| A small view rendered inline in Markdown | Mermaid C4 | Native rendering; accept the limits below |

## Mermaid C4 Limits

Mermaid marks C4 as **experimental**: syntax and properties may change between releases.

- Supported types: `C4Context`, `C4Container`, `C4Component`, `C4Dynamic`, `C4Deployment`. There is no landscape type. A landscape is a context diagram without a focus system, so use `C4Context` with an `Enterprise_Boundary`.
- NOT supported: `Legend`, tags, sprites, links, `AddElementTag`/`AddRelTag`, `DashedLine()`. The Sanofi legend and dashed-async convention cannot be drawn. MUST place the legend as adjacent text or a table, and MUST mark async relationships in the technology label (e.g. `"SQS/HTTPS, async"`).
- Layout follows statement order. `Lay_U/D/L/R` are not supported. Tune with `UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")`.
- `RelIndex` ignores its index. Numbering follows the order of the `Rel` statements, so write `C4Dynamic` relationships in interaction order.
- `BiRel` exists, but C4 relationships are unidirectional. NEVER use it; write two `Rel` lines.
- Text wraps by default since Mermaid v11.17.1. A renderer pinned to an earlier version does not wrap, so check the rendered output where it will be published.

Bad: `BiRel(api, db, "Reads/writes")`, and a legend line inside a `C4Container` block.
Good: `Rel(api, db, "Reads orders from", "SQL/TCP")`, plus a legend table directly under the diagram.

## C4-PlantUML

- Preserve the repository's include style:
  - `!include <C4/C4_Container>` uses the stdlib copy bundled with PlantUML. It works offline but may lag the latest release.
  - A raw GitHub `master` URL fetches on every render.
  - Vendored files need `-DRELATIVE_INCLUDE="."`.
- Use `SHOW_LEGEND()` or `LAYOUT_WITH_LEGEND()` for the legend.
- For the Sanofi dashed-async convention, use `AddRelTag("async", $lineStyle = DashedLine())` with `Rel(..., $tags="async")`.
- `C4_Context` covers both context and landscape. `C4_Sequence` gives the sequence style of a dynamic diagram.

## Structurizr

The tooling consolidated in 2025-2026. Structurizr Lite, Structurizr CLI, on-premises and the cloud service are end of life. All commands now ship in one `structurizr/structurizr` image (or `structurizr.war`, Java 21): `local` replaces Lite, `server` replaces on-premises, and `export`/`push`/`pull`/`validate`/`inspect` replace the CLI.

Bad: `docker run structurizr/cli export ...` or `docker run structurizr/lite`.
Good: `docker run --rm -v "$PWD:/usr/local/structurizr" structurizr/structurizr validate -workspace workspace.dsl`.

| Task | POSIX shell | PowerShell |
|---|---|---|
| Validate | `docker run --rm -v "$PWD:/usr/local/structurizr" structurizr/structurizr validate -workspace workspace.dsl` | `docker run --rm -v "${PWD}:/usr/local/structurizr" structurizr/structurizr validate -workspace workspace.dsl` |
| Inspect | `docker run --rm -v "$PWD:/usr/local/structurizr" structurizr/structurizr inspect -workspace workspace.dsl -severity error,warning` | same with `"${PWD}:/usr/local/structurizr"` |
| Export | `docker run --rm -v "$PWD:/usr/local/structurizr" structurizr/structurizr export -workspace workspace.dsl -format mermaid -output diagrams` | same with `"${PWD}:/usr/local/structurizr"` |

- Drop the documented `-it` flag in non-interactive `bash` runs. Docker rejects `-t` without a TTY.
- `inspect` exits with the violation count. A nonzero exit is findings, not a crash.
- Export formats: `plantuml`, `plantuml/c4plantuml`, `mermaid`, `static`, `json`. `png`/`svg` need the `-playwright` image tag. Exports do not support every shape or feature.
- Mermaid exports need `securityLevel: "loose"` in the Mermaid config.
- `local` writes manual layout to `workspace.json` next to `workspace.dsl`. NEVER delete or regenerate `workspace.json` when editing the DSL, or the layout is lost. NEVER rename `workspace.dsl`, because `local` looks for that name. Apply the [versioning-guide.md](versioning-guide.md) identifier to exports and the changelog.
- Implied relationships are on by default. A container-level relationship implies the system-level one, so NEVER add duplicate explicit L1 relationships. Respect any `!impliedRelationships` setting already in the file.
- Keep one software system per workspace and `workspace.json` under about 1-2 MB. Model a landscape across workspaces, not in one large workspace.

## Hosted Renderers

`playground.structurizr.com`, the PlantUML web server, and `mermaid.live`/`mermaid.ai` are hosted services. AVOID pasting internal architecture into them unless approved. Render locally with the image, the PlantUML jar, or the repository's own pipeline.

## Sources

- C4 model, Tooling (diagramming vs modelling): https://c4model.com/tooling
- C4 model, System landscape diagram: https://c4model.com/diagrams/system-landscape
- Mermaid, C4 Diagrams: https://mermaid.js.org/syntax/c4.html
- C4-PlantUML README: https://github.com/plantuml-stdlib/C4-PlantUML/blob/master/README.md
- Structurizr, End of life: https://docs.structurizr.com/eol
- Structurizr, Commands: https://docs.structurizr.com/commands
- Structurizr, Binaries: https://docs.structurizr.com/binaries
- Structurizr, export: https://docs.structurizr.com/export
- Structurizr, Mermaid export: https://docs.structurizr.com/export/mermaid
- Structurizr, inspect: https://docs.structurizr.com/inspect
- Structurizr, local workflow: https://docs.structurizr.com/local/workflow
- Structurizr, Implied relationships: https://docs.structurizr.com/dsl/implied-relationships
- Structurizr, Workspace recommendations: https://docs.structurizr.com/workspaces/recommendations
