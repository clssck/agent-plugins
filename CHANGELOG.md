# Changelog

Published changes to the first-party packs in `packs/`, newest first. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); each pack keeps its own semantic version in `packs/<pack>/package.json`. Generated `upstream/` packs are not listed. Earlier history: `git log`.

## [Unreleased]

## clssck 2.1.23 - 2026-10-30

- New `remove-animations` skill, ported from emilkowalski/skills at `a81dbca`. It gates every existing animation (keyboard-triggered, 100+ times a day, functional data, no named purpose), deletes or reduces what fails, checks removal hazards before deleting, then removes the code left orphaned. Its routing preview carries "feels slow" and "too much animation". OMP additions: a browser check that removed motion left nothing hidden, reduced-motion branches follow the animation they gate, and dependency removal is proposed, never run. Upstream's repo-root `ui-cheatsheet.md` is not vendored; the skill never reads it.
- `find-animation-opportunities` and `improve-animations` descriptions route "remove the animations", "too much animation", and "feels slow" to `remove-animations`; their first 99 characters are unchanged.

## clssck 2.1.22 - 2026-10-28

- `animation-performance`, `animation-vocabulary`, `animate` and `animate-expo` now put the phrasing users actually type inside the ~99-character routing preview OMP shows before a description is compressed: "stutter, jank, or drop frames", "what's it called when…", "decide it shouldn't animate: easing", and "gestures, sheets, and haptics in React Native and Expo". Blind routing trials with the preview text alone now select the intended skill for "my animation stutters", "what do you call the bounce-in effect", "should it even ripple", "what easing for a tooltip" and "haptics in our native app".
- `animation-performance` replaces a dangling "No." that answered a question no longer in the file, and states why a composited `filter: blur()` still costs.

## sanofi 1.2.3 - 2026-10-28

- `dbt` names dbt CI selectors and `state:modified` runs in its routing preview, so "our dbt CI selector runs every model" no longer reads as a GitHub Actions problem (`cicd-engineering`).

## sanofi 1.2.2 - 2026-10-25

- Every Sanofi skill that reads, searches, or publishes Confluence/Jira hands off to the `atl` skill through one routing line with the install command, one fallback (paste the content, record references as Links, never publish), and one publish sequence (`atl page create|update --file <path> --plan`, then its `next`).
- `dbt` and `sanofi-airflow` source-of-truth pages name the `atl page get <id>` read command.
- `adr-writing` treats `site_not_accessible` as a blocked item and passes `--site <host>` from the user's URLs for bare Jira keys and page ids.

## sanofi 1.2.1 - 2026-10-25

- `adr-writing` reads Confluence pages, comment threads, Jira issues, and links through named `atl` commands instead of generic Atlassian session tools.

## sanofi 1.2.0 - 2026-10-24

- Removed `search-company-knowledge` and `confluence-html-editor`; Confluence and Jira reading, search, and publishing move to the `atl` skill.
