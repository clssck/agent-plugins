# Confluence Page Content Outlines

Use these outlines to prepare architecture-page content, not as a publishable HTML or
storage-format payload. For live Confluence work, hand the target-page context and
prepared content to `confluence-html-editor`. It fetches the current page, preserves
macros and attachments, publishes a complete HTML body, and verifies the result.

Do not construct raw macro markup from this reference. Describe a required diagram,
attachment, panel, or internal link in the content, then let the publishing workflow
preserve or create the native Confluence representation.

For an existing page, set or preserve its title through the publishing workflow rather
than adding a durable `<h1>` to the replacement body. The title comments below are for a
new-page title or content-planning context.

## Table of Contents

- [Architecture Overview Landing Page](#architecture-overview-landing-page)
- [L1 System Context Page](#l1-system-context-page)
- [L2 Container Page](#l2-container-page)
- [L3 Component Page](#l3-component-page)
- [Deployment Diagram Page](#deployment-diagram-page)
- [Master Architecture Change Log Page](#master-architecture-change-log-page)
- [Diagram Artifact Placement](#diagram-artifact-placement)
- [Callout Content](#callout-content)

---

## Architecture Overview Landing Page

```html
<!-- Page title: {System Name} Architecture -->

<blockquote>
  <p><strong>Architecture Documentation</strong></p>
  <p>This page is the entry point for all architecture documentation for the
  <strong>{System Name}</strong> system. Each level of the C4 model has its own
  child page with diagrams, descriptions, and change history.</p>
  <p><strong>Last updated:</strong> {YYYY-MM-DD} | <strong>Current version:</strong> v{X.Y.Z}</p>
</blockquote>

<h2>System Metadata</h2>
<table>
  <tbody>
    <tr><td><strong>System ID</strong></td><td>{APM ID or CMDB identifier}</td></tr>
    <tr><td><strong>Business Owner</strong></td><td>{Responsible business stakeholder}</td></tr>
    <tr><td><strong>Technical Owner</strong></td><td>{Responsible technical lead}</td></tr>
    <tr><td><strong>Classification</strong></td><td>{Data sensitivity level}</td></tr>
    <tr><td><strong>Status</strong></td><td>{Current | Planned | Deprecated}</td></tr>
    <tr><td><strong>Compliance Status</strong></td><td>{GxP / SOX / GDPR status}</td></tr>
    <tr><td><strong>Technology Stack</strong></td><td>{Key technologies}</td></tr>
    <tr><td><strong>SLA</strong></td><td>{Service level agreements if applicable}</td></tr>
    <tr><td><strong>Disaster Recovery</strong></td><td>{DR classification}</td></tr>
  </tbody>
</table>

<h2>Architecture Levels</h2>
<table>
  <thead>
    <tr><th>Level</th><th>Page</th><th>Audience</th><th>Status</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>L1 - System Context</td>
      <td>{Link to System Context (L1) page}</td>
      <td>Everyone</td>
      <td>Current (v{X.Y.Z})</td>
    </tr>
    <tr>
      <td>L2 - Container</td>
      <td>{Link to Container Diagram (L2) page}</td>
      <td>Technical</td>
      <td>Current (v{X.Y.Z})</td>
    </tr>
    <tr>
      <td>L3 - Component: {Service}</td>
      <td>{Link to Component: {Service Name} (L3) page}</td>
      <td>Architects, Developers</td>
      <td>Current (v{X.Y.Z})</td>
    </tr>
    <tr>
      <td>Deployment: Production</td>
      <td>{Link to Deployment: Production (Supplementary) page}</td>
      <td>Technical, Ops</td>
      <td>Current (v{X.Y.Z})</td>
    </tr>
    <tr>
      <td>Change Log</td>
      <td>{Link to Architecture Change Log page}</td>
      <td>Everyone</td>
      <td>--</td>
    </tr>
  </tbody>
</table>

<h2>Quick Links</h2>
<ul>
  <li>{Link to full change history}</li>
  <li><a href="https://github.com/{owner}/{repo}">Source Repository</a></li>
  <li><a href="https://sanofi.atlassian.net/browse/{PROJ}">Jira Project</a></li>
</ul>

<p><em>Drafted with AI assistance (architecture-documentation). Review and approve before finalizing.</em></p>
```

---

## L1 System Context Page

```html
<!-- Page title: {System Name} - System Context (L1) -->

<h2>Metadata</h2>
<table>
  <tbody>
    <tr><td><strong>Current Version</strong></td><td>v{X.Y.Z} ({YYYY-MM-DD})</td></tr>
    <tr><td><strong>Triggered By</strong></td><td><a href="https://sanofi.atlassian.net/browse/{PROJ-123}">{PROJ-123}</a></td></tr>
    <tr><td><strong>System ID</strong></td><td>{APM ID}</td></tr>
    <tr><td><strong>Business Owner</strong></td><td>{Name}</td></tr>
    <tr><td><strong>Technical Owner</strong></td><td>{Name}</td></tr>
    <tr><td><strong>Classification</strong></td><td>{Data sensitivity}</td></tr>
    <tr><td><strong>Status</strong></td><td>{Current | Planned | Deprecated}</td></tr>
    <tr><td><strong>Compliance Status</strong></td><td>{GxP / SOX / GDPR}</td></tr>
    <tr><td><strong>Review Date</strong></td><td>{YYYY-MM-DD}</td></tr>
    <tr><td><strong>SLA</strong></td><td>{SLA details}</td></tr>
  </tbody>
</table>

<h2>Diagram</h2>
<p><em>Diagram artifact: {system-name}-L1-v{X.Y.Z}. Preserve an existing embed or
attachment, or add the approved native artifact through the publishing workflow.</em></p>

<h2>Description</h2>
<p>{System Name} provides {primary capability} to {primary users} by {key functionality}.
It supports {business process} and integrates with {key systems}. The system is classified
as {criticality level} and handles {data classification} data.</p>

<p>This System Context diagram shows how {System Name} fits into the broader organizational
landscape, highlighting the key users and external systems it interacts with.</p>

<h2>Key Elements</h2>
<table>
  <thead>
    <tr><th>Element</th><th>Type</th><th>Description</th></tr>
  </thead>
  <tbody>
    <tr><td>{User Role}</td><td>Person</td><td>{How they use the system}</td></tr>
    <tr><td>{System Name}</td><td>Software System</td><td>{System purpose}</td></tr>
    <tr><td>{External System}</td><td>External System</td><td>{Integration purpose}</td></tr>
  </tbody>
</table>

<h2>Key Decisions</h2>
<ul>
  <li><strong>{Decision}</strong>: {Rationale} (ref: {ADR or Jira ticket})</li>
</ul>

<h2>Change History</h2>
<table>
  <thead>
    <tr><th>Version</th><th>Date</th><th>Ticket</th><th>Level</th><th>Summary</th><th>Author</th></tr>
  </thead>
  <tbody>
    <tr><td>v{X.Y.Z}</td><td>{YYYY-MM-DD}</td><td>{PROJ-123}</td><td>L1</td><td>{Summary}</td><td>{Author}</td></tr>
  </tbody>
</table>

<p><em>Drafted with AI assistance (architecture-documentation). Review and approve before finalizing.</em></p>
```

---

## L2 Container Page

```html
<!-- Page title: {System Name} - Container Diagram (L2) -->

<h2>Metadata</h2>
<table>
  <tbody>
    <tr><td><strong>Current Version</strong></td><td>v{X.Y.Z} ({YYYY-MM-DD})</td></tr>
    <tr><td><strong>Triggered By</strong></td><td><a href="https://sanofi.atlassian.net/browse/{PROJ-123}">{PROJ-123}</a></td></tr>
    <tr><td><strong>System ID</strong></td><td>{APM ID}</td></tr>
    <tr><td><strong>Business Owner</strong></td><td>{Name}</td></tr>
    <tr><td><strong>Technical Owner</strong></td><td>{Name}</td></tr>
    <tr><td><strong>Classification</strong></td><td>{Data sensitivity}</td></tr>
    <tr><td><strong>Status</strong></td><td>{Current | Planned | Deprecated}</td></tr>
    <tr><td><strong>Compliance Status</strong></td><td>{GxP / SOX / GDPR}</td></tr>
    <tr><td><strong>Review Date</strong></td><td>{YYYY-MM-DD}</td></tr>
    <tr><td><strong>Technology Stack</strong></td><td>{React, Fastify, PostgreSQL, SQS, etc.}</td></tr>
    <tr><td><strong>SLA</strong></td><td>{SLA details}</td></tr>
    <tr><td><strong>Disaster Recovery</strong></td><td>{DR classification}</td></tr>
  </tbody>
</table>

<h2>Diagram</h2>
<p><em>Diagram artifact: {system-name}-L2-v{X.Y.Z}. Preserve an existing embed or
attachment, or add the approved native artifact through the publishing workflow.</em></p>

<h2>Description</h2>
<p>The Container diagram shows the high-level shape of the {System Name} architecture
and how responsibilities are distributed across containers. Each container is a
separately runnable/deployable unit.</p>

<p>{Describe the major containers, their roles, and how they communicate. Mention key
technology choices and their justifications.}</p>

<blockquote>
  <p><strong>Browser SPA scope</strong></p>
  <p>Model the client-side SPA as a container. Add an API, asset host, or other
  server-side runtime only when it is a distinct in-scope responsibility; show an
  external API as an external system.</p>
</blockquote>

<h2>Key Elements</h2>
<table>
  <thead>
    <tr><th>Element</th><th>Type</th><th>Technology</th><th>Description</th></tr>
  </thead>
  <tbody>
    <tr><td>{Web App}</td><td>Container</td><td>React / TypeScript</td><td>{Purpose}</td></tr>
    <tr><td>{API Service}</td><td>Container</td><td>Fastify / TypeScript</td><td>{Purpose}</td></tr>
    <tr><td>{Database}</td><td>Container</td><td>PostgreSQL</td><td>{Data stored}</td></tr>
    <tr><td>{Queue}</td><td>Container</td><td>SQS</td><td>{Async purpose}</td></tr>
  </tbody>
</table>

<h2>Key Decisions</h2>
<ul>
  <li><strong>{Decision}</strong>: {Rationale} (ref: {ADR or Jira ticket})</li>
</ul>

<h2>Change History</h2>
<table>
  <thead>
    <tr><th>Version</th><th>Date</th><th>Ticket</th><th>Level</th><th>Summary</th><th>Author</th></tr>
  </thead>
  <tbody>
    <tr><td>v{X.Y.Z}</td><td>{YYYY-MM-DD}</td><td>{PROJ-123}</td><td>L2</td><td>{Summary}</td><td>{Author}</td></tr>
  </tbody>
</table>

<p><em>Drafted with AI assistance (architecture-documentation). Review and approve before finalizing.</em></p>
```

---

## L3 Component Page

```html
<!-- Page title: {System Name} - Component: {Container Name} (L3) -->

<h2>Metadata</h2>
<table>
  <tbody>
    <tr><td><strong>Current Version</strong></td><td>v{X.Y.Z} ({YYYY-MM-DD})</td></tr>
    <tr><td><strong>Triggered By</strong></td><td><a href="https://sanofi.atlassian.net/browse/{PROJ-123}">{PROJ-123}</a></td></tr>
    <tr><td><strong>Parent Container</strong></td><td>{Container Name} [Technology]</td></tr>
    <tr><td><strong>Status</strong></td><td>{Current | Planned | Deprecated}</td></tr>
    <tr><td><strong>Technology Stack</strong></td><td>{Detailed technology}</td></tr>
  </tbody>
</table>

<blockquote>
  <p><strong>Component diagrams are optional</strong></p>
  <p>Create an L3 view only when it adds genuine value for an architecturally complex
  container. Simple CRUD services typically do not need one.</p>
</blockquote>

<h2>Diagram</h2>
<p><em>Diagram artifact: {system-name}-L3-{container}-v{X.Y.Z}. Preserve an existing
embed or attachment, or add the approved native artifact through the publishing workflow.</em></p>

<h2>Description</h2>
<p>{Container Name} is a {container type} that provides {primary capability} using
{technology/platform}. It is responsible for {key responsibilities} and stores
{data types}. {Security/compliance considerations} apply to this container.</p>

<h2>Key Elements</h2>
<table>
  <thead>
    <tr><th>Component</th><th>Technology</th><th>Responsibility</th></tr>
  </thead>
  <tbody>
    <tr><td>{Route Handler}</td><td>Fastify Routes</td><td>{HTTP request handling}</td></tr>
    <tr><td>{Service Layer}</td><td>TypeScript</td><td>{Business logic}</td></tr>
    <tr><td>{Repository}</td><td>Drizzle ORM</td><td>{Data access}</td></tr>
    <tr><td>{Auth Middleware}</td><td>JWT / OIDC</td><td>{Authentication}</td></tr>
  </tbody>
</table>

<h2>Change History</h2>
<table>
  <thead>
    <tr><th>Version</th><th>Date</th><th>Ticket</th><th>Level</th><th>Summary</th><th>Author</th></tr>
  </thead>
  <tbody>
    <tr><td>v{X.Y.Z}</td><td>{YYYY-MM-DD}</td><td>{PROJ-123}</td><td>L3</td><td>{Summary}</td><td>{Author}</td></tr>
  </tbody>
</table>
```

---

## Deployment Diagram Page

```html
<!-- Page title: {System Name} - Deployment: {Environment} (Supplementary) -->

<h2>Metadata</h2>
<table>
  <tbody>
    <tr><td><strong>Current Version</strong></td><td>v{X.Y.Z} ({YYYY-MM-DD})</td></tr>
    <tr><td><strong>Environment</strong></td><td>{Production | Staging | Dev}</td></tr>
    <tr><td><strong>Cloud Provider</strong></td><td>AWS</td></tr>
    <tr><td><strong>Region</strong></td><td>{eu-west-1}</td></tr>
    <tr><td><strong>Disaster Recovery</strong></td><td>{DR classification}</td></tr>
  </tbody>
</table>

<h2>Diagram</h2>
<p><em>Diagram artifact: {system-name}-deploy-{env}-v{X.Y.Z}. Preserve an existing
embed or attachment, or add the approved native artifact through the publishing workflow.</em></p>

<h2>Description</h2>
<p>This deployment diagram shows how the containers of {System Name} are mapped to
infrastructure in the {environment} environment. Key infrastructure decisions and
deployment topology are documented below.</p>

<h2>Infrastructure Summary</h2>
<table>
  <thead>
    <tr><th>Container</th><th>Deployed As</th><th>Scaling</th><th>Notes</th></tr>
  </thead>
  <tbody>
    <tr><td>{API Service}</td><td>ECS Fargate</td><td>2-6 tasks</td><td>Behind ALB</td></tr>
    <tr><td>{Database}</td><td>RDS PostgreSQL</td><td>Multi-AZ</td><td>Encrypted at rest</td></tr>
    <tr><td>{Queue}</td><td>SQS</td><td>Managed</td><td>Standard queue</td></tr>
  </tbody>
</table>

<h2>Change History</h2>
<table>
  <thead>
    <tr><th>Version</th><th>Date</th><th>Ticket</th><th>Level</th><th>Summary</th><th>Author</th></tr>
  </thead>
  <tbody>
    <tr><td>v{X.Y.Z}</td><td>{YYYY-MM-DD}</td><td>{PROJ-123}</td><td>Deploy</td><td>{Summary}</td><td>{Author}</td></tr>
  </tbody>
</table>
```

---

## Master Architecture Change Log Page

```html
<!-- Page title: {System Name} - Architecture Change Log -->

<blockquote>
  <p><strong>Change Log</strong></p>
  <p>This page tracks all architecture documentation changes across all C4 levels.
  Each entry links to the Jira ticket that triggered the change and the affected
  diagram level.</p>
</blockquote>

<table>
  <thead>
    <tr>
      <th>Version</th>
      <th>Date</th>
      <th>Jira Ticket</th>
      <th>C4 Level</th>
      <th>Summary</th>
      <th>Author</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>v3.1.0</td>
      <td>2026-02-11</td>
      <td><a href="https://sanofi.atlassian.net/browse/PROJ-456">PROJ-456</a></td>
      <td>L2 Container</td>
      <td>Added Redis cache for session management</td>
      <td>AI-assisted (architecture-documentation)</td>
    </tr>
    <tr>
      <td>v3.0.0</td>
      <td>2026-01-28</td>
      <td><a href="https://sanofi.atlassian.net/browse/PROJ-412">PROJ-412</a></td>
      <td>L1 Context, L2 Container</td>
      <td>Added payment service integration</td>
      <td>J. Smith</td>
    </tr>
    <tr>
      <td>v1.0.0</td>
      <td>2025-11-01</td>
      <td>--</td>
      <td>L1, L2, L3</td>
      <td>Initial architecture documentation</td>
      <td>AI-assisted (architecture-documentation)</td>
    </tr>
  </tbody>
</table>

<p><em>Drafted with AI assistance (architecture-documentation). Review and approve before finalizing.</em></p>
```

---

## Diagram Artifact Placement

For a live page, provide the logical artifact identifier, current attachment or embed
context, and intended placement to `confluence-html-editor`. Do not construct a macro
payload or reference a local file path in the page body. The publisher fetches the page,
preserves compatible existing embeds, uploads new attachments only through an available
attachment path, and verifies the resulting page.

---

## Callout Content

Supply the intended meaning and text; let `confluence-html-editor` select or preserve
the native callout representation.

- **Current**: This diagram reflects the current production architecture as of
  `{YYYY-MM-DD}`.
- **Planned Changes**: `{Description of upcoming changes and expected timeline.}`
- **Deprecated**: This component or service is deprecated as of `{date}`. See
  `{PROJ-XXX}` for the migration plan.
- **GxP Compliance**: This system is classified as GxP-relevant. All changes must
  follow validated change-control procedures per 21 CFR Part 11.
