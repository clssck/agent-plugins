---
description: Keep viewport meta settings from locking page zoom
condition: '(?i)\b(?:user-?scalable|maximum-?scale)\b'
scope: "tool:edit(**/*.{html,htm,css,scss,sass,less,js,jsx,mjs,cjs,ts,tsx,mts,cts,vue,svelte,astro}), tool:write(**/*.{html,htm,css,scss,sass,less,js,jsx,mjs,cjs,ts,tsx,mts,cts,vue,svelte,astro})"
interruptMode: never
---

Preserve ordinary page zoom. Remove viewport settings that disable user scaling or cap it below 200%; do not use them to suppress input-focus zoom. Prefer leaving zoom caps unset.

This applies to HTML `user-scalable` / `maximum-scale` and framework forms such as `userScalable` / `maximumScale`. A browser ignoring a restriction is not a reason to add it.

## Exceptions

- Settings already allowing zoom (`yes` / `true`, or a maximum scale of at least 2) need no change.
- Non-viewport data and inert examples or test fixtures need no change.
- An alternative text-resizing mechanism needs verification; a token match alone is not a WCAG verdict.

The trigger marks relevance, including compliant values. Check the actual viewport and resizing behavior before changing it. Source: [W3C viewport-zoom check and its assumptions](https://www.w3.org/WAI/standards-guidelines/act/rules/b4f0c3/).
