## Confluence Page Content Structure

Use the following hierarchy to organize content. For a live page, hand the content and
target-page context to `confluence-html-editor`; it owns fetching, macro/attachment
preservation, publishing, and verification.

```text
{Confluence Space} /
  System Design /
    {System Name} Architecture Overview     <- Landing page with links to all levels
    +-- System Context (L1)                 <- L1 diagram + description + changelog
    +-- Container Diagram (L2)              <- L2 diagram + description + changelog
    +-- Component: API Service (L3)         <- L3 per container (only if valuable)
    +-- Deployment: Production (Supp.)      <- Deployment diagram per environment
    +-- Dynamic: Order Processing (Supp.)   <- Dynamic diagrams (sparingly)
    +-- Architecture Change Log             <- Master changelog across all levels
```
