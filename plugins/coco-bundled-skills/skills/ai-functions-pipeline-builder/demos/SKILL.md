---
name: demos
description: "Interactive, turnkey demos of the pipeline-builder use-case templates. Use when the user wants a demo, example, walkthrough, or to 'show me / try it / see it work' for a Snowflake document pipeline: enterprise search, structured extraction, corpus intelligence (research analytics), or customer 360. Each demo sources a small public sample corpus into the user's account, builds a live incremental pipeline, and showcases the hero result."
parent_skill: ai-functions-pipeline-builder
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Pipeline Builder Demos

Turnkey walkthroughs of the pipeline-builder templates. Each demo sources a small public sample corpus into your account, stands up the same incremental, Snowflake-native pipeline the matching template teaches, and showcases the hero result end to end.

## When to load

Load when intent is DEMO: "demo", "example", "walkthrough", "show me", "try it", "how does this work", "see it work" for a document pipeline. Not yet wired into the parent skill's routing table — reach this router by naming it or opening `demos/SKILL.md`.

## Read first

The shared scaffold lives in [`conventions.md`](conventions.md): location, cost gate, consent, build/verify, cleanup, and stopping points every demo reuses. Each demo `SKILL.md` carries only its domain specifics and points here — do not restate the scaffold.

## Workflow

### Step 1: Select the demo

Ask the user:

```
Which pipeline demo would you like to run?

1. Enterprise Search (~10-15 min)
   Turn a shelf of consumer-goods annual reports into a searchable,
   chart-aware knowledge base with grounded, cited RAG answers -- including
   answers read off charts that live only as images.
   Pipeline: parse -> chart vision -> chunk -> Cortex Search -> cited RAG.

2. Structured Extraction (~15 min)
   Route a stream of mixed auto-insurance claim documents: classify each,
   extract by its own schema, assess damage photos with vision, assemble
   one record per claim, then decide and triage into
   auto-settle / needs-review / reject lanes.

3. Corpus Intelligence / Research Analytics (~15 min)
   Read across a collection of research papers: parse, read numbers off
   figures with vision, extract trial fields, and synthesize a competitive
   landscape briefing per drug.

4. Customer 360 (~15 min)
   Fuse pre-loaded warehouse tables with staged customer documents into a
   per-customer 360 record: risk/route, searchable knowledge, and
   product-health insight in one pipeline.
```

**STOP**: wait for the user's selection.

### Step 2: Route

- **Enterprise Search** -> load [`enterprise-search/SKILL.md`](enterprise-search/SKILL.md)
- **Structured Extraction** -> load [`structured-extraction/SKILL.md`](structured-extraction/SKILL.md)
- **Corpus Intelligence** -> load [`corpus-intelligence/SKILL.md`](corpus-intelligence/SKILL.md)
- **Customer 360** -> load [`customer360/SKILL.md`](customer360/SKILL.md)

## What to expect

See [`conventions.md`](conventions.md) for the naming scheme (`DEMO_<tag>_` / `DT_DEMO_<tag>_`), cost gate, consent, teardown, and stopping points every demo enforces. Each demo then:

1. Sources a small sample corpus into a stage in your account.
2. Builds a live incremental pipeline (stream + task + dynamic tables) from shipped, compile-checked SQL.
3. Showcases the hero result via deliverable SQL and a Snowflake notebook.
4. Offers to tear everything down at the end.

## Stopping points

- ✋ Step 1: wait for the demo selection.
