---
description: Keep touch-action from taking over native scrolling and pinch zoom
condition: '(?i)\btouch-?action\b|\btouch-(?:none\b|pan-)'
scope: "tool:edit(**/*.{html,htm,css,scss,sass,less,js,jsx,mjs,cjs,ts,tsx,mts,cts,vue,svelte,astro}), tool:write(**/*.{html,htm,css,scss,sass,less,js,jsx,mjs,cjs,ts,tsx,mts,cts,vue,svelte,astro})"
interruptMode: never
---

Preserve native scrolling and pinch zoom. `touch-action` controls what the browser handles, not the direction your JavaScript should drag. Inspect the element and relevant ancestors: the browser intersects their restrictions before a gesture starts.

## Use

- Native horizontal scrolling, including scroll-snap: retain browser panning, normally with `auto`. Do not restrict the track to `pan-y`.
- Custom JavaScript horizontal dragging: `pan-y pinch-zoom` leaves vertical scrolling and pinch zoom to the browser. Tailwind's equivalent is `touch-pan-y touch-pinch-zoom`.
- Faster tap handling on controls: `manipulation` retains panning and pinch zoom.
- `none`: only on a bounded custom gesture surface with accessible alternatives, not on the page or as a blanket tap-lag fix.

## Exceptions

Already-compliant declarations, verified custom surfaces, and inert examples or test fixtures need no change. A matched property or utility is a relevance reminder, not proof of a violation. Source: [MDN touch-action semantics and accessibility](https://developer.mozilla.org/en-US/docs/Web/CSS/touch-action).
