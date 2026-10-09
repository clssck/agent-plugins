---
description: Raw strings written into HTML sinks (dangerouslySetInnerHTML, v-html, {@html}, innerHTML) or JSON-LD scripts without escaping
condition:
- 'dangerouslySetInnerHTML=\{\{\s*__html\s*:\s*(?!\s*(?:DOMPurify\.sanitize|sanitize\w*|purify\w*|serialize\w*|escape\w*|safe\w*)\s*\()(?![^}]*\.replace\(\s*/<)|\bv-html=|\{@html\s|\.(?:inner|outer)HTML\s*(?:\+?=)(?!\s*(?:[\"''`]{2}|DOMPurify|sanitize))|\bhref=\{?[\"''`]\s*javascript:'
scope:
- tool:edit(**/*.{js,jsx,ts,tsx,vue,svelte,astro,html})
- tool:write(**/*.{js,jsx,ts,tsx,vue,svelte,astro,html})
interruptMode: never
---

**An HTML sink renders whatever string it gets, so content from a CMS, the database or the user becomes stored XSS.**

- **HTML content:** sanitize at render time, e.g. `DOMPurify.sanitize(html)` (use `isomorphic-dompurify` on the server). Better still, store Markdown or rich text and render it to elements.
- **JSON-LD:** `JSON.stringify` doesn't escape `<`, so a value containing `</script>` breaks out of the tag. Use `JSON.stringify(data).replace(/</g, '\\u003c')`, as the Next.js JSON-LD guide shows.
- **DOM:** set `textContent` instead of `innerHTML` for text.
- **URLs:** allow only `http:`/`https:` (or a fixed set of schemes) before putting a value in `href`, which blocks `javascript:` URLs.
- If the HTML is static and authored in the repo, say so in a comment next to the sink.

Sources: https://nextjs.org/docs/app/guides/json-ld, https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
