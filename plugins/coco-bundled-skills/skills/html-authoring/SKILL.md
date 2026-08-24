---
name: html-authoring
description: "**[REQUIRED]** for ALL creation, updating, or editing of `.html` files, regardless of complexity. Snowflake renders report HTML in a strict, sandboxed environment: no inline event handlers, no `eval`, no runtime network calls, no remote images or CDN scripts — only a fixed set of vendored libraries served from `/libs/`. Author every report to these rules so it renders correctly and is safe to share. Must use whenever generating, creating, updating, or modifying an `.html` file (e.g. 'update the HTML report at …')."
---

# HTML Authoring

When report sharing is enabled, Snowflake renders your report HTML in a **locked-down sandbox**: a strict Content-Security-Policy applies and the page has **no network access**. Author to the rules below so the report renders correctly and is safe to share — plain, self-contained HTML with inline JavaScript and all data embedded is ideal.

---

## Where to save the file

**Never leave the file in transient storage** — a temporary or scratch location (e.g. `/tmp`) is wiped when the session ends, leaving nothing to publish or refresh later. The file must land somewhere durable.

**Creating a new report:** save it to the **current workspace** by default. This skill can also run outside a workspace (e.g. from the Cowork page), and the user may name a destination of their own — use it when it's durable, otherwise ask. If no durable destination is clear, ask before writing.

**Updating an existing report:** write it back to the same location.

---

## Marker meta tag

Include this in `<head>` so downstream tooling knows the file is agent-authored:

```html
<meta name="snowflake-source" content="cortex-agent-authored">
```

---

## Report metadata — for later refresh

Embed one provenance block in `<head>` so a future run (yours or another agent's) can **refresh or iterate** on the report — its equivalent of a header doc-comment in code. Record where the data came from and how each part was produced. It's a `<script type="application/json">` data block: never rendered, never executed (wrong type), and read by **parsing, not position** — so it stays intact if the pipeline lifts it into a manifest.

```html
<script type="application/json" id="snowflake-report-metadata">
{
  "generated": "2026-06-23",
  "intent": "Q4 revenue analysis by region",
  "dataSources": [
    { "type": "query", "warehouse": "{WAREHOUSE}",
      "sql": "SELECT region, SUM(revenue) AS revenue FROM {DATABASE}.{SCHEMA}.{TABLE} WHERE quarter = 'Q4' GROUP BY region" }
  ],
  "sections": [
    { "id": "revenue-by-region", "title": "Revenue by region",
      "dataSources": [{ "type": "query", "sql": "SELECT region, SUM(revenue) … GROUP BY region" }],
      "producerNotes": "Chart values are inlined from the query above — re-run it to refresh." }
  ]
}
</script>
```

- **Key each `sections[]` entry to the section's anchor id** (`<h2 id="revenue-by-region">` or `<section id="…">`). The id — not the block's position — is the link, so "refresh section X" is a lookup on `sections[].id`, and the pipeline can extract the whole block without losing which entry maps to which section.
- Scope each source: put it in a section's `dataSources` if it feeds only that section, or in the top-level `dataSources` if it's shared across sections — use either or both. (The template below is section-level only because each source is section-specific.)
- Keep it machine-readable: list every query / table / file each part draws on, plus any parameters or assumptions a future update needs.
- Update it whenever you change what the report shows.
- Tokens in `{…}` (e.g. `{WAREHOUSE}`, `{DATABASE}.{SCHEMA}.{TABLE}`) are placeholders — replace them with the report's real warehouse and fully-qualified sources.

---

## What you can and can't use

**Use freely:**
- ✅ Inline `<script>` — put all your JavaScript here.
- ✅ Inline `<style>` and `style="…"` attributes.
- ✅ `<canvas>`, inline `<svg>`, and the vendored `/libs/` libraries (below).
- ✅ Images as `data:` or `blob:` URIs.

**Don't use** (silently dropped or blocked):
- ❌ Inline event handlers (`onclick=`, `onload=`, …) — attach handlers with `addEventListener` inside a `<script>`.
- ❌ `eval`, `new Function`, or `setTimeout("…code…")`.
- ❌ External / CDN scripts, stylesheets, or web fonts — load only from `/libs/`.
- ❌ Remote images (`<img src="https://…">`) — inline the bytes as a `data:` URI.
- ❌ Runtime network calls — `fetch`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`. Embed all data directly in the HTML.
- ❌ Cookies, `localStorage`, `sessionStorage` — unavailable in the sandbox.
- ❌ `<iframe>`, `<object>`/`<embed>`, `<video>`/`<audio>`, Web Workers, `<form>` submission, `<base>`.

---

## Available libraries

Reference a vendored library by its **pinned path** — nothing else loads:

```html
<script src="/libs/chart.js@4.4.4/chart.umd.js"></script>
<link rel="stylesheet" href="/libs/katex@0.16.21/katex.min.css">
```

| Library | Reference path | Use / limits |
|---|---|---|
| chart.js | `/libs/chart.js@4.4.4/chart.umd.js` | Charts (renders to `<canvas>`) |
| plotly (cartesian) | `/libs/plotly.js-cartesian-dist-min@2.35.2/plotly-cartesian.min.js` | Cartesian charts only |
| d3 | `/libs/d3@7.9.0/d3.min.js` | Low-level data viz |
| vega | `/libs/vega@6.2.0/vega.min.js` | Base for vega-lite / vega-embed |
| vega-lite | `/libs/vega-lite@6.4.3/vega-lite.min.js` | Declarative charts |
| vega-embed | `/libs/vega-embed@7.1.0/vega-embed.min.js` | Embeds a spec — **must** pass `{ ast: true }` |
| mermaid | `/libs/mermaid@10.9.6/mermaid.min.js` | Diagrams (flowchart, sequence, class, state, ER, gantt, pie, gitGraph, journey, …) — **must init with `securityLevel: 'strict'`** |
| katex | `/libs/katex@0.16.21/katex.min.js` + `/libs/katex@0.16.21/katex.min.css` | Math typesetting |
| highlight.js | `/libs/highlight.js@11.10.0/highlight.min.js` + `/libs/highlight.js@11.10.0/github.min.css` | Code highlighting |
| marked | `/libs/marked@14.1.3/marked.min.js` | Markdown → HTML |
| three | `/libs/three@0.169.0/three.module.min.js` | 3D (WebGL); ES module |

Notes:
- **Mermaid:** initialize with `securityLevel: 'strict'` (required — it sanitizes diagram labels; never use `'loose'`). Images in labels must be `data:` URIs or inline `<svg>` — remote image URLs are blocked and won't load.
- **Vega:** always pass `{ ast: true }` to `vegaEmbed` (required — without it the chart won't render). Give the spec an explicit numeric `width` (e.g. `width: 700`) — `width: 'container'` renders a zero-width, blank chart in the sandbox.
- **KaTeX:** include both the JS and the CSS.
- **three.js** is an ES module — load it with `<script type="module">`.

---

## Theming (light & dark)

Reports adapt to the viewer's light or dark color scheme, so **make your CSS adapt too** — don't hard-code a light background with dark text (or vice-versa).

- Use the `light-dark()` function for colors, e.g. `color: light-dark(#1f2937, #e5e7eb);`, and declare `:root { color-scheme: light dark; }`.
- Or provide `@media (prefers-color-scheme: dark) { … }` overrides.

---

## Responsive layout

Reports are opened on phones and in narrow side-panels as often as full-width, so the layout must **reflow, not overflow** — nothing should force horizontal page scrolling or spill past the viewport edge on a ~360px-wide screen. The `<meta name="viewport" content="width=device-width, initial-scale=1">` tag (in the template) is what makes this possible — always keep it.

- **Fluid container:** cap the width but let it shrink — `max-width: 880px; width: 100%; box-sizing: border-box;` — and use fluid padding like `padding: clamp(16px, 4vw, 24px);` so narrow screens aren't cramped and wide ones aren't sparse.
- **Wide tables:** wrap every table in a horizontally scrollable container so the table scrolls on its own instead of stretching the whole page:
  ```html
  <div style="overflow-x: auto;"><table>…</table></div>
  ```
- **Images & SVG:** add `img, svg { max-width: 100%; height: auto; }` so they never exceed the viewport width.
- **Charts (chart.js):** wrap the `<canvas>` in a **fixed-height box** and let the chart fill it — put the height in CSS, never let the chart's own aspect ratio decide it. A ratio that looks right on desktop (e.g. a `1040×360` canvas, or `aspectRatio`/`height:auto` derived from it) collapses to a short unreadable sliver at phone width. See the pattern below (`.chart-box` + `responsive: true, maintainAspectRatio: false`). For Vega-Lite, `width: 'container'` renders blank in the sandbox, so keep a numeric `width` and wrap the chart in `<div style="overflow-x: auto;">` so it scrolls when the screen is narrower than the chart.
- **Charts (Plotly):** Plotly renders to a `<div>`, so the `.chart-box`/canvas pattern doesn't apply. Wrap it in a `width: 100%` container, set `layout: { autosize: true }` (no fixed `width`), and pass `{ responsive: true }` as the config to `Plotly.newPlot(...)` so it re-fits when the viewport changes.
- **Avoid fixed pixel widths** on layout elements — prefer `%`, `max-width`, and `min()`/`clamp()`. For multi-column layouts use a grid/flex that collapses on narrow screens, e.g. `display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));` or `display: flex; flex-wrap: wrap;`.
- **Test narrow:** picture the report at ~360px wide — if anything is cut off or triggers horizontal scrolling of the whole page, constrain or wrap it.

---

## External links

Write normal links with real URLs:

```html
<a href="https://docs.snowflake.com/">Docs</a>
```

- Links to untrusted hosts are automatically made inert (the text stays, but they aren't clickable).
- `mailto:` and `tel:` links are kept as-is — use them for contact links.
- Don't use `javascript:` or `data:` hrefs (they're stripped), and don't rely on JavaScript (`window.open`, `location = …`) to navigate.

---

## Charts & interactivity — the pattern

Put all logic in an inline `<script>` and load the library from `/libs/`.

**chart.js** — wrap the `<canvas>` in a fixed-height box and let the chart fill it. The box's CSS height controls the chart height at every screen width; `maintainAspectRatio: false` lets it span the full width:

```html
<style>
  .chart-box { position: relative; width: 100%; height: 320px; }   /* height lives here */
  .chart-box > canvas { width: 100% !important; height: 100% !important; }
</style>
<div class="chart-box"><canvas id="rev"></canvas></div>    <!-- no width/height attrs on the canvas -->
<script src="/libs/chart.js@4.4.4/chart.umd.js"></script>
<script>
  new Chart(document.getElementById('rev'), {
    type: 'bar',
    data: {
      labels: ['North America', 'EMEA', 'APAC'],
      datasets: [{ label: 'Revenue ($M)', data: [1.2, 0.5, 0.4] }],
    },
    options: { responsive: true, maintainAspectRatio: false },   // fill the box
  });
</script>
```

> This is the sizing that survives a narrow screen. **Don't** size a chart by its canvas `width`/`height` attributes or by `aspectRatio`/`height: auto` — a wide desktop ratio (e.g. `1040×360`) collapses to a ~100px-tall sliver at phone width. Pinning the height on `.chart-box` and filling it (`maintainAspectRatio: false`) gives a full-width, controlled-height chart on every device; the `.chart-box > canvas` rule keeps it filling the box even if the runtime strips chart.js's inline sizing. For a taller/shorter chart, change the one `height` value (use `clamp()`, e.g. `height: clamp(240px, 45vw, 360px)`, if you want it to grow a little on wider screens).

**Vega-Lite** (always pass `{ ast: true }`):

```html
<div id="vis"></div>
<script src="/libs/vega@6.2.0/vega.min.js"></script>
<script src="/libs/vega-lite@6.4.3/vega-lite.min.js"></script>
<script src="/libs/vega-embed@7.1.0/vega-embed.min.js"></script>
<script>
  const spec = {
    width: 700, height: 300,                 // numeric width — 'container' renders blank in the sandbox
    data: { values: [{ r: 'NA', v: 1.2 }, { r: 'EMEA', v: 0.5 }, { r: 'APAC', v: 0.4 }] },
    mark: 'bar',
    encoding: { x: { field: 'r', type: 'nominal' }, y: { field: 'v', type: 'quantitative' } },
  };
  vegaEmbed('#vis', spec, { ast: true });
</script>
```

**Mermaid** (always set `securityLevel: 'strict'`):

```html
<pre class="mermaid">
flowchart TD
  A[Start] --> B{OK?}
  B -->|yes| C[Done]
</pre>
<script src="/libs/mermaid@10.9.6/mermaid.min.js"></script>
<script>
  mermaid.initialize({ startOnLoad: true, securityLevel: 'strict' });
</script>
```

---

## File structure template

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="snowflake-source" content="cortex-agent-authored" />
  <title>Q4 Revenue Analysis</title>
  <script type="application/json" id="snowflake-report-metadata">
  {
    "generated": "2026-06-23",
    "intent": "Q4 revenue analysis by region",
    "sections": [
      { "id": "revenue-by-region", "title": "Revenue by region",
        "dataSources": [{ "type": "query", "sql": "SELECT region, SUM(revenue) FROM {DATABASE}.{SCHEMA}.{TABLE} WHERE quarter = 'Q4' GROUP BY region" }],
        "producerNotes": "Chart values inlined from the query above; re-run it to refresh." }
    ]
  }
  </script>
  <style>
    :root { color-scheme: light dark; }                 /* adapt to light/dark */
    body {
      font-family: -apple-system, system-ui, sans-serif;
      max-width: 880px; width: 100%; box-sizing: border-box;
      margin: 0 auto; padding: clamp(16px, 4vw, 24px);   /* fluid — comfortable on narrow screens */
      color: light-dark(#1f2937, #e5e7eb);
    }
    h1, h2, h3 { color: light-dark(#0f172a, #f1f5f9); }
    a { color: light-dark(#2563eb, #60a5fa); }
    img, svg { max-width: 100%; height: auto; }          /* never exceed the viewport */
    .chart-box { position: relative; width: 100%; height: 320px; }   /* charts: height set here, not by aspect ratio */
    .chart-box > canvas { width: 100% !important; height: 100% !important; }
    .table-wrap { overflow-x: auto; margin: 16px 0; }    /* wide tables scroll, page doesn't */
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid light-dark(#d1d5db, #374151); padding: 6px 10px; text-align: left; }
    th { background: light-dark(#f3f4f6, #1f2937); font-weight: 600; }
  </style>
</head>
<body>

  <h1>Q4 Revenue Analysis</h1>
  <p>Summary of Q4 results by region.</p>

  <h2 id="revenue-by-region">Revenue by region</h2>
  <div class="chart-box"><canvas id="rev"></canvas></div>   <!-- fixed-height box; chart fills it -->
  <script src="/libs/chart.js@4.4.4/chart.umd.js"></script>
  <script>
    new Chart(document.getElementById('rev'), {
      type: 'bar',
      data: {
        labels: ['North America', 'EMEA', 'APAC'],
        datasets: [{ label: 'Revenue ($M)', data: [1.2, 0.5, 0.4] }],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  </script>

  <h2>Detail</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Region</th><th>Revenue</th><th>YoY</th></tr></thead>
      <tbody>
        <tr><td>North America</td><td>$1.2M</td><td>+9%</td></tr>
        <tr><td>EMEA</td><td>$0.5M</td><td>+6%</td></tr>
        <tr><td>APAC</td><td>$0.4M</td><td>+28%</td></tr>
      </tbody>
    </table>
  </div>

  <p>Source: <a href="https://docs.snowflake.com/">Snowflake docs</a>.</p>

</body>
</html>
```
